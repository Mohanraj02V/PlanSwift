"""Multi-tenant RBAC and project/object-level authorization enforcement."""

from __future__ import annotations

from rest_framework import permissions

from apps.organizations.models import Organization, OrganizationMember


def get_object_organization(obj) -> Organization | None:
    if isinstance(obj, Organization):
        return obj
    if hasattr(obj, "organization") and obj.organization is not None:
        return obj.organization
    if hasattr(obj, "project") and getattr(obj.project, "organization", None) is not None:
        return obj.project.organization
    if hasattr(obj, "project_version") and getattr(obj.project_version, "project", None) is not None:
        return obj.project_version.project.organization
    if hasattr(obj, "cad_document") and getattr(obj.cad_document, "project_version", None) is not None:
        return obj.cad_document.project_version.project.organization
    if hasattr(obj, "project_object") and getattr(obj.project_object, "project_version", None) is not None:
        return obj.project_object.project_version.project.organization
    if hasattr(obj, "session") and getattr(obj.session, "project", None) is not None:
        return obj.session.project.organization
    if hasattr(obj, "conversation") and getattr(obj.conversation, "project", None) is not None:
        return obj.conversation.project.organization
    return None


def is_estimation_only_user(user) -> bool:
    """Return True if an authenticated user is scoped strictly to the estimation_only role."""
    if not user or not user.is_authenticated or getattr(user, "is_superuser", False):
        return False
    roles = list(
        OrganizationMember.objects.filter(user=user, is_active=True).values_list("role", flat=True)
    )
    return bool(roles) and all(r == OrganizationMember.Role.ESTIMATION_ONLY for r in roles)


def is_org_admin_user(user) -> bool:
    """Return True if user is superuser, staff, or holds an active Owner/Admin membership."""
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    return OrganizationMember.objects.filter(
        user=user,
        is_active=True,
        role__in=(OrganizationMember.Role.OWNER, OrganizationMember.Role.ADMIN),
    ).exists()


def _estimation_only_request_allowed(request) -> bool:
    path = getattr(request, "path", "") or ""
    if path.startswith("/api/v1/estimation/") or path.startswith("/api/v1/auth/") or path.startswith("/api/v1/health/"):
        return True
    if request.method in permissions.SAFE_METHODS and (
        path.startswith("/api/v1/projects/") or path.startswith("/api/v1/organizations/")
    ):
        return True
    return False


def get_user_org_ids(user) -> list:
    if not user or not user.is_authenticated:
        return []
    return list(
        OrganizationMember.objects.filter(user=user, is_active=True).values_list("organization_id", flat=True)
    )


class IsOrgAdminOnly(permissions.BasePermission):
    """Requires Owner, Admin, Staff, or Superuser privileges at the view level."""

    def has_permission(self, request, view) -> bool:
        return is_org_admin_user(request.user)


class IsEstimationRoleScoped(permissions.BasePermission):
    """Global default guard ensuring estimation_only users cannot access non-estimation APIs."""

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if is_estimation_only_user(request.user):
            return _estimation_only_request_allowed(request)
        return True


class IsOrgMember(permissions.BasePermission):
    """Allows access only if authenticated user is an active member of the object's organization."""

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if is_estimation_only_user(request.user):
            return _estimation_only_request_allowed(request)
        return True

    def has_object_permission(self, request, view, obj) -> bool:
        if is_estimation_only_user(request.user) and not _estimation_only_request_allowed(request):
            return False
        org = get_object_organization(obj)
        if org is None:
            return False
        return OrganizationMember.objects.filter(
            organization=org,
            user=request.user,
            is_active=True,
        ).exists()


class IsEstimationAllowed(permissions.BasePermission):
    """Allows Owner, Admin, Estimator, Reviewer, and Estimation-Only users on /api/v1/estimation/."""

    ALLOWED_ROLES = (
        OrganizationMember.Role.OWNER,
        OrganizationMember.Role.ADMIN,
        OrganizationMember.Role.ESTIMATOR,
        OrganizationMember.Role.REVIEWER,
        OrganizationMember.Role.ESTIMATION_ONLY,
    )

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj) -> bool:
        org = get_object_organization(obj)
        if org is None:
            return False
        return OrganizationMember.objects.filter(
            organization=org,
            user=request.user,
            is_active=True,
            role__in=self.ALLOWED_ROLES,
        ).exists()


class IsOrgAdminOrOwner(permissions.BasePermission):
    """Requires Owner or Admin role inside the target organization."""

    ALLOWED_ROLES = (OrganizationMember.Role.OWNER, OrganizationMember.Role.ADMIN)

    def has_object_permission(self, request, view, obj) -> bool:
        org = get_object_organization(obj)
        if org is None:
            return False
        return OrganizationMember.objects.filter(
            organization=org,
            user=request.user,
            is_active=True,
            role__in=self.ALLOWED_ROLES,
        ).exists()


class IsOrgEditor(permissions.BasePermission):
    """Requires Owner, Admin, or Estimator role for mutating project/extraction/estimation actions."""

    ALLOWED_ROLES = (
        OrganizationMember.Role.OWNER,
        OrganizationMember.Role.ADMIN,
        OrganizationMember.Role.ESTIMATOR,
    )

    def has_object_permission(self, request, view, obj) -> bool:
        org = get_object_organization(obj)
        if org is None:
            return False
        return OrganizationMember.objects.filter(
            organization=org,
            user=request.user,
            is_active=True,
            role__in=self.ALLOWED_ROLES,
        ).exists()


class IsOrgReviewerOrEditor(permissions.BasePermission):
    """Allows read + review/approval comments for Owner, Admin, Estimator, or Reviewer."""

    ALLOWED_ROLES = (
        OrganizationMember.Role.OWNER,
        OrganizationMember.Role.ADMIN,
        OrganizationMember.Role.ESTIMATOR,
        OrganizationMember.Role.REVIEWER,
    )

    def has_object_permission(self, request, view, obj) -> bool:
        org = get_object_organization(obj)
        if org is None:
            return False
        return OrganizationMember.objects.filter(
            organization=org,
            user=request.user,
            is_active=True,
            role__in=self.ALLOWED_ROLES,
        ).exists()
