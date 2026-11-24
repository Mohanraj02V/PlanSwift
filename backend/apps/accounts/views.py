"""Authentication views (JWT obtain/refresh/logout+blacklist, register, profile, admin user management)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts.serializers import (
    AdminUserCreateSerializer,
    AdminUserUpdateSerializer,
    ChangePasswordSerializer,
    RegisterSerializer,
    UserProfileSerializer,
    VortexenTokenObtainPairSerializer,
)
from apps.audit_logs.services import log_audit_event
from apps.organizations.models import Organization, OrganizationMember
from apps.permissions.rbac import get_user_org_ids, is_org_admin_user

User = get_user_model()


def _primary_org(user):
    if not user or not getattr(user, "is_authenticated", False):
        return None
    mem = (
        OrganizationMember.objects.filter(user=user, is_active=True)
        .select_related("organization")
        .order_by("created_at")
        .first()
    )
    return mem.organization if mem else None


class AuditedTokenObtainPairView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]
    serializer_class = VortexenTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        email = (request.data.get("email") or "").strip()
        try:
            resp = super().post(request, *args, **kwargs)
        except Exception as exc:
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
            raise exc
        if resp.status_code == 200:
            user = User.objects.filter(email__iexact=email).first()
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

    def post(self, request, *args, **kwargs):
        resp = super().post(request, *args, **kwargs)
        if resp.status_code == 200:
            log_audit_event(action="auth.token_refresh", actor=None, request=request)
        return resp


class RegisterView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        log_audit_event(
            action="auth.register",
            actor=user,
            request=self.request,
            resource_type="User",
            resource_id=str(user.id),
            metadata={"email": user.email},
        )


class LogoutView(APIView):
    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "Refresh token is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            return Response({"detail": "Invalid or expired refresh token."}, status=status.HTTP_400_BAD_REQUEST)
        log_audit_event(
            action="auth.logout",
            actor=request.user,
            organization=_primary_org(request.user),
            request=request,
            resource_type="User",
            resource_id=str(request.user.id),
            metadata={"email": request.user.email},
        )
        return Response({"status": "logged_out"}, status=status.HTTP_200_OK)


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
        user.save(update_fields=["password"])
        log_audit_event(
            action="auth.password_changed",
            actor=user,
            organization=_primary_org(user),
            request=request,
            resource_type="User",
            resource_id=str(user.id),
        )
        return Response({"status": "password_updated"}, status=status.HTTP_200_OK)


def _admin_manageable_orgs(user):
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return Organization.objects.filter(is_active=True)
    return Organization.objects.filter(
        members__user=user,
        members__is_active=True,
        members__role__in=(OrganizationMember.Role.OWNER, OrganizationMember.Role.ADMIN),
    ).distinct()


class AdminUserListCreateView(APIView):
    """Allow Admin/Owner to list organization users and create new users with explicit roles."""

    def get(self, request):
        if not is_org_admin_user(request.user):
            return Response({"detail": "Admin or Owner privileges required."}, status=status.HTTP_403_FORBIDDEN)
        if getattr(request.user, "is_superuser", False):
            qs = User.objects.all().order_by("email")
        else:
            org_ids = get_user_org_ids(request.user)
            qs = User.objects.filter(organization_memberships__organization_id__in=org_ids).distinct().order_by("email")
        return Response({"results": UserProfileSerializer(qs, many=True).data})

    @transaction.atomic
    def post(self, request):
        if not is_org_admin_user(request.user):
            return Response({"detail": "Admin or Owner privileges required."}, status=status.HTTP_403_FORBIDDEN)

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
            org = manageable_orgs.first() or _primary_org(request.user)
            if org is None:
                return Response({"detail": "Create an organization first before adding users."}, status=status.HTTP_400_BAD_REQUEST)

        new_user = User.objects.create_user(
            email=data["email"],
            password=data["password"],
            full_name=data.get("full_name", ""),
            job_title=data.get("job_title", ""),
            is_active=data.get("is_active", True),
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
    """Allow Admin/Owner to update role, active status, profile, or reset password for an org user."""

    @transaction.atomic
    def patch(self, request, user_id):
        if not is_org_admin_user(request.user):
            return Response({"detail": "Admin or Owner privileges required."}, status=status.HTTP_403_FORBIDDEN)

        manageable_orgs = _admin_manageable_orgs(request.user)
        target = User.objects.filter(id=user_id).first()
        if target is None:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        if not getattr(request.user, "is_superuser", False):
            if not OrganizationMember.objects.filter(user=target, organization__in=manageable_orgs).exists():
                return Response({"detail": "Forbidden for user outside your admin organizations."}, status=status.HTTP_403_FORBIDDEN)

        ser = AdminUserUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        if "full_name" in data:
            target.full_name = data["full_name"]
        if "job_title" in data:
            target.job_title = data["job_title"]
        if "is_active" in data:
            target.is_active = data["is_active"]
        if data.get("password"):
            target.set_password(data["password"])
        target.save()

        org_for_log = manageable_orgs.first() or _primary_org(target)
        if "role" in data:
            org_id = data.get("organization")
            target_org = manageable_orgs.filter(id=org_id).first() if org_id else org_for_log
            if target_org is None:
                return Response({"detail": "Target organization not found or forbidden."}, status=status.HTTP_403_FORBIDDEN)
            OrganizationMember.objects.update_or_create(
                organization=target_org,
                user=target,
                defaults={"role": data["role"], "is_active": True},
            )
            org_for_log = target_org

        log_audit_event(
            action="admin.user_updated",
            actor=request.user,
            organization=org_for_log,
            request=request,
            resource_type="User",
            resource_id=str(target.id),
            metadata={
                "target_user_email": target.email,
                "updated_fields": sorted(k for k in data.keys() if k != "password") + (["password"] if data.get("password") else []),
                "role": data.get("role"),
                "is_active": target.is_active,
            },
        )
        return Response(UserProfileSerializer(target).data)

    @transaction.atomic
    def delete(self, request, user_id):
        if not is_org_admin_user(request.user):
            return Response({"detail": "Admin or Owner privileges required."}, status=status.HTTP_403_FORBIDDEN)

        manageable_orgs = _admin_manageable_orgs(request.user)
        target = User.objects.filter(id=user_id).first()
        if target is None:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        if target.id == request.user.id:
            return Response({"detail": "You cannot deactivate your own active admin account."}, status=status.HTTP_400_BAD_REQUEST)
        if not getattr(request.user, "is_superuser", False):
            if not OrganizationMember.objects.filter(user=target, organization__in=manageable_orgs).exists():
                return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        target.is_active = False
        target.save(update_fields=["is_active"])
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
