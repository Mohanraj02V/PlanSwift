"""Authentication views with HttpOnly JWT cookies, CSRF protection, throttling, immediate revocation, and Admin user management."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import generics, permissions, status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts.authentication import enforce_csrf
from apps.accounts.serializers import (
    AdminUserCreateSerializer,
    AdminUserUpdateSerializer,
    ChangePasswordSerializer,
    UserProfileSerializer,
    VortexenTokenObtainPairSerializer,
)
from apps.audit_logs.services import log_audit_event
from apps.organizations.models import Organization, OrganizationMember
from apps.permissions.rbac import IsAdminOnly, get_user_admin_org_ids, is_admin

User = get_user_model()


def _primary_org(user):
    if not user or not getattr(user, "is_authenticated", False):
        return None
    mem = (
        OrganizationMember.objects.filter(user=user, is_active=True, organization__is_active=True)
        .select_related("organization")
        .order_by("created_at")
        .first()
    )
    return mem.organization if mem else None


def _set_jwt_cookies(response: Response, access: str, refresh: str | None = None) -> None:
    access_cookie = getattr(settings, "JWT_ACCESS_COOKIE_NAME", "vortexen_access")
    refresh_cookie = getattr(settings, "JWT_REFRESH_COOKIE_NAME", "vortexen_refresh")
    secure = bool(getattr(settings, "JWT_COOKIE_SECURE", not settings.DEBUG))
    samesite = getattr(settings, "JWT_COOKIE_SAMESITE", "Lax")

    access_max_age = int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds())
    refresh_max_age = int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())

    response.set_cookie(
        key=access_cookie,
        value=access,
        max_age=access_max_age,
        httponly=True,
        secure=secure,
        samesite=samesite,
        path="/api/",
    )
    if refresh:
        response.set_cookie(
            key=refresh_cookie,
            value=refresh,
            max_age=refresh_max_age,
            httponly=True,
            secure=secure,
            samesite=samesite,
            path="/api/v1/auth/",
        )


def _clear_jwt_cookies(response: Response) -> None:
    access_cookie = getattr(settings, "JWT_ACCESS_COOKIE_NAME", "vortexen_access")
    refresh_cookie = getattr(settings, "JWT_REFRESH_COOKIE_NAME", "vortexen_refresh")
    response.delete_cookie(access_cookie, path="/api/")
    response.delete_cookie(refresh_cookie, path="/api/v1/auth/")


class CsrfTokenView(APIView):
    """Issue CSRF cookie for browser SPA clients using HttpOnly JWT cookies."""

    permission_classes = [permissions.AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response({"csrfToken": get_token(request)}, status=status.HTTP_200_OK)


class AuditedTokenObtainPairView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]
    serializer_class = VortexenTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_login"

    def post(self, request, *args, **kwargs):
        email = (request.data.get("email") or "").strip()
        try:
            resp = super().post(request, *args, **kwargs)
        except AuthenticationFailed:
            target = User.objects.filter(email__iexact=email).first() if email else None
            log_audit_event(
                action="auth.login_failed",
                actor=None,
                organization=_primary_org(target) if target else None,
                request=request,
                resource_type="User",
                resource_id=str(target.id) if target else "",
                metadata={"email": email, "reason": "invalid_credentials"},
            )
            return Response({"detail": "Invalid email or password."}, status=status.HTTP_401_UNAUTHORIZED)

        if resp.status_code == 200:
            access_tok = resp.data.pop("access", None)
            refresh_tok = resp.data.pop("refresh", None)
            user = User.objects.filter(email__iexact=email).first()
            if access_tok:
                _set_jwt_cookies(resp, access=access_tok, refresh=refresh_tok)
            get_token(request)
            resp.data["authenticated"] = True
            log_audit_event(
                action="auth.login",
                actor=user,
                organization=_primary_org(user),
                request=request,
                resource_type="User",
                resource_id=str(user.id) if user else "",
                metadata={"email": email, "full_name": user.full_name if user else ""},
            )
        return resp


class AuditedTokenRefreshView(TokenRefreshView):
    permission_classes = [permissions.AllowAny]
    serializer_class = TokenRefreshSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_refresh"

    def post(self, request, *args, **kwargs):
        refresh_cookie_name = getattr(settings, "JWT_REFRESH_COOKIE_NAME", "vortexen_refresh")
        cookie_refresh = request.COOKIES.get(refresh_cookie_name)
        body_refresh = request.data.get("refresh") if isinstance(request.data, dict) else None
        used_cookie = cookie_refresh is not None and not body_refresh

        if used_cookie:
            enforce_csrf(request)

        raw_refresh = body_refresh or cookie_refresh
        if not raw_refresh:
            return Response({"detail": "Refresh credentials are required."}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            incoming = RefreshToken(raw_refresh)
            uid = incoming.get("user_id")
            user = User.objects.filter(id=uid, is_active=True).first()
            if user is None or int(incoming.get("token_version", 1)) != int(getattr(user, "token_version", 1)):
                raise InvalidToken("Session expired or revoked.")
            serializer = self.get_serializer(data={"refresh": raw_refresh})
            serializer.is_valid(raise_exception=True)
        except (TokenError, InvalidToken) as exc:
            resp = Response({"detail": "Invalid or expired session token."}, status=status.HTTP_401_UNAUTHORIZED)
            if used_cookie:
                _clear_jwt_cookies(resp)
            return resp

        validated = serializer.validated_data
        access_tok = validated.get("access")
        new_refresh_tok = validated.get("refresh") or raw_refresh
        resp = Response({"authenticated": True, "user": UserProfileSerializer(user).data}, status=status.HTTP_200_OK)
        if access_tok:
            _set_jwt_cookies(resp, access=access_tok, refresh=new_refresh_tok)
        log_audit_event(action="auth.token_refresh", actor=user, organization=_primary_org(user), request=request)
        return resp


class DisabledRegisterView(APIView):
    """Public self-registration is strictly disabled; accounts are organization-provisioned by Admins."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        log_audit_event(
            action="auth.register_blocked",
            actor=None,
            request=request,
            resource_type="User",
            metadata={"email": (request.data.get("email") or "").strip()},
        )
        return Response(
            {"detail": "Public registration is disabled. Contact your organization administrator."},
            status=status.HTTP_403_FORBIDDEN,
        )


class LogoutView(APIView):
    def post(self, request):
        refresh_cookie_name = getattr(settings, "JWT_REFRESH_COOKIE_NAME", "vortexen_refresh")
        refresh_token = (request.data.get("refresh") if isinstance(request.data, dict) else None) or request.COOKIES.get(
            refresh_cookie_name
        )
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass
        log_audit_event(
            action="auth.logout",
            actor=request.user,
            organization=_primary_org(request.user),
            request=request,
            resource_type="User",
            resource_id=str(request.user.id),
            metadata={"email": request.user.email},
        )
        resp = Response({"status": "logged_out"}, status=status.HTTP_200_OK)
        _clear_jwt_cookies(resp)
        return resp


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["current_password"]):
            return Response({"detail": "Current password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(serializer.validated_data["new_password"])
        user.must_change_password = False
        user.token_version = int(getattr(user, "token_version", 1)) + 1
        user.save(update_fields=["password", "must_change_password", "token_version"])

        # Reissue fresh HttpOnly cookies for the active user session after revoking all older sessions
        refresh = VortexenTokenObtainPairSerializer.get_token(user)
        resp = Response({"status": "password_updated"}, status=status.HTTP_200_OK)
        _set_jwt_cookies(resp, access=str(refresh.access_token), refresh=str(refresh))
        log_audit_event(
            action="auth.password_changed",
            actor=user,
            organization=_primary_org(user),
            request=request,
            resource_type="User",
            resource_id=str(user.id),
        )
        return resp


def _admin_manageable_orgs(user):
    if getattr(user, "is_superuser", False):
        return Organization.objects.filter(is_active=True)
    admin_org_ids = get_user_admin_org_ids(user)
    return Organization.objects.filter(id__in=admin_org_ids, is_active=True)


def _would_remove_last_admin(org: Organization, target_user) -> bool:
    other_admins = (
        OrganizationMember.objects.filter(
            organization=org,
            role=OrganizationMember.Role.ADMIN,
            is_active=True,
            user__is_active=True,
        )
        .exclude(user=target_user)
        .exists()
    )
    return not other_admins


class AdminUserListCreateView(APIView):
    """Allow active Organization Admin to list organization users and create users with Admin/Estimator/User roles."""

    permission_classes = [permissions.IsAuthenticated, IsAdminOnly]

    def get(self, request):
        if getattr(request.user, "is_superuser", False):
            qs = User.objects.all().order_by("email")
        else:
            admin_org_ids = get_user_admin_org_ids(request.user)
            qs = (
                User.objects.filter(organization_memberships__organization_id__in=admin_org_ids)
                .distinct()
                .order_by("email")
            )
        return Response({"results": UserProfileSerializer(qs, many=True).data})

    @transaction.atomic
    def post(self, request):
        if not is_admin(request.user):
            return Response({"detail": "Organization Admin privileges required."}, status=status.HTTP_403_FORBIDDEN)

        ser = AdminUserCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        manageable_orgs = _admin_manageable_orgs(request.user)
        org_id = data.get("organization")
        if org_id:
            org = manageable_orgs.filter(id=org_id).first()
            if org is None:
                return Response({"detail": "You do not have Admin rights for that organization."}, status=status.HTTP_403_FORBIDDEN)
        else:
            org = manageable_orgs.first()
            if org is None:
                return Response({"detail": "Create an organization first before adding users."}, status=status.HTTP_400_BAD_REQUEST)

        new_user = User.objects.create_user(
            email=data["email"],
            password=data["password"],
            full_name=data.get("full_name", ""),
            job_title=data.get("job_title", ""),
            is_active=data.get("is_active", True),
            must_change_password=data.get("must_change_password", False),
        )
        OrganizationMember.objects.create(
            organization=org,
            user=new_user,
            role=data["role"],
            is_active=True,
        )
        log_audit_event(
            action="admin.user_created",
            actor=request.user,
            organization=org,
            request=request,
            resource_type="User",
            resource_id=str(new_user.id),
            metadata={
                "created_user_email": new_user.email,
                "created_user_name": new_user.full_name,
                "role": data["role"],
                "organization_name": org.name,
            },
        )
        return Response(UserProfileSerializer(new_user).data, status=status.HTTP_201_CREATED)


class AdminUserDetailView(APIView):
    """Allow Organization Admin to update role, active status, profile, or reset password with immediate revocation."""

    permission_classes = [permissions.IsAuthenticated, IsAdminOnly]

    @transaction.atomic
    def patch(self, request, user_id):
        if not is_admin(request.user):
            return Response({"detail": "Organization Admin privileges required."}, status=status.HTTP_403_FORBIDDEN)

        manageable_orgs = _admin_manageable_orgs(request.user)
        target = User.objects.filter(id=user_id).first()
        if target is None:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        if getattr(target, "is_superuser", False) and not getattr(request.user, "is_superuser", False):
            return Response({"detail": "Forbidden to modify break-glass superuser."}, status=status.HTTP_403_FORBIDDEN)
        if not getattr(request.user, "is_superuser", False):
            if not OrganizationMember.objects.filter(user=target, organization__in=manageable_orgs).exists():
                return Response({"detail": "Forbidden for user outside your admin organizations."}, status=status.HTTP_403_FORBIDDEN)

        ser = AdminUserUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        target_org = None
        if "role" in data or "organization" in data:
            org_id = data.get("organization")
            if org_id:
                target_org = manageable_orgs.filter(id=org_id).first()
            else:
                mem = (
                    OrganizationMember.objects.filter(user=target, organization__in=manageable_orgs)
                    .select_related("organization")
                    .first()
                )
                target_org = mem.organization if mem else manageable_orgs.first()
            if target_org is None:
                return Response({"detail": "Target organization not found or forbidden."}, status=status.HTTP_403_FORBIDDEN)

        # Safeguard against removing or disabling the last active Admin in an org
        if data.get("is_active") is False:
            target_admin_orgs = Organization.objects.filter(
                members__user=target,
                members__role=OrganizationMember.Role.ADMIN,
                members__is_active=True,
                is_active=True,
            )
            for adm_org in target_admin_orgs:
                if _would_remove_last_admin(adm_org, target):
                    return Response(
                        {"detail": "Cannot deactivate the last active Admin in an organization."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        if "role" in data and target_org is not None and data["role"] != OrganizationMember.Role.ADMIN:
            is_currently_admin = OrganizationMember.objects.filter(
                organization=target_org,
                user=target,
                role=OrganizationMember.Role.ADMIN,
                is_active=True,
            ).exists()
            if is_currently_admin and _would_remove_last_admin(target_org, target):
                return Response(
                    {"detail": "Cannot demote the last active Admin in this organization."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        revoke_sessions = False
        if "full_name" in data:
            target.full_name = data["full_name"]
        if "job_title" in data:
            target.job_title = data["job_title"]
        if "is_active" in data and data["is_active"] != target.is_active:
            target.is_active = data["is_active"]
            revoke_sessions = True
        if "must_change_password" in data:
            target.must_change_password = data["must_change_password"]
        if data.get("password"):
            target.set_password(data["password"])
            target.must_change_password = bool(data.get("must_change_password", True))
            revoke_sessions = True

        if "role" in data and target_org is not None:
            existing_mem = OrganizationMember.objects.filter(organization=target_org, user=target).first()
            if existing_mem is None or existing_mem.role != data["role"] or not existing_mem.is_active:
                revoke_sessions = True
            OrganizationMember.objects.update_or_create(
                organization=target_org,
                user=target,
                defaults={"role": data["role"], "is_active": True},
            )

        if revoke_sessions:
            target.token_version = int(getattr(target, "token_version", 1)) + 1
        target.save()

        org_for_log = target_org or manageable_orgs.first() or _primary_org(target)
        log_audit_event(
            action="admin.user_updated",
            actor=request.user,
            organization=org_for_log,
            request=request,
            resource_type="User",
            resource_id=str(target.id),
            metadata={
                "target_user_email": target.email,
                "updated_fields": sorted(k for k in data.keys() if k != "password")
                + (["password"] if data.get("password") else []),
                "role": data.get("role"),
                "is_active": target.is_active,
                "sessions_revoked": revoke_sessions,
            },
        )
        return Response(UserProfileSerializer(target).data)

    @transaction.atomic
    def delete(self, request, user_id):
        if not is_admin(request.user):
            return Response({"detail": "Organization Admin privileges required."}, status=status.HTTP_403_FORBIDDEN)

        manageable_orgs = _admin_manageable_orgs(request.user)
        target = User.objects.filter(id=user_id).first()
        if target is None:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        if target.id == request.user.id:
            return Response({"detail": "You cannot deactivate your own active admin account."}, status=status.HTTP_400_BAD_REQUEST)
        if getattr(target, "is_superuser", False) and not getattr(request.user, "is_superuser", False):
            return Response({"detail": "Forbidden to deactivate break-glass superuser."}, status=status.HTTP_403_FORBIDDEN)
        if not getattr(request.user, "is_superuser", False):
            if not OrganizationMember.objects.filter(user=target, organization__in=manageable_orgs).exists():
                return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        target_admin_orgs = Organization.objects.filter(
            members__user=target,
            members__role=OrganizationMember.Role.ADMIN,
            members__is_active=True,
            is_active=True,
        )
        for adm_org in target_admin_orgs:
            if _would_remove_last_admin(adm_org, target):
                return Response(
                    {"detail": "Cannot deactivate the last active Admin in an organization."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        target.is_active = False
        target.token_version = int(getattr(target, "token_version", 1)) + 1
        target.save(update_fields=["is_active", "token_version"])
        OrganizationMember.objects.filter(user=target, organization__in=manageable_orgs).update(is_active=False)
        log_audit_event(
            action="admin.user_deactivated",
            actor=request.user,
            organization=manageable_orgs.first() or _primary_org(target),
            request=request,
            resource_type="User",
            resource_id=str(target.id),
            metadata={"target_user_email": target.email},
        )
        return Response({"status": "deactivated"})
