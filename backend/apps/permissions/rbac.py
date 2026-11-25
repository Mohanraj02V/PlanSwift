"""Centralized three-role RBAC (Admin, Estimator, User) & multi-tenant object authorization."""

from __future__ import annotations

from rest_framework import permissions

from apps.organizations.models import Organization, OrganizationMember

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")

# Prefixes readable inside the Estimator Workspace by all active organization roles
WORKSPACE_READ_PREFIXES = (
    "/api/v1/projects/",
    "/api/v1/project-sources/",
    "/api/v1/source-inventory/",
    "/api/v1/extraction/",
    "/api/v1/cad-bim/",
    "/api/v1/objects/",
    "/api/v1/hierarchy/",
    "/api/v1/measurements/",
    "/api/v1/geometry/",
    "/api/v1/formulas/",
    "/api/v1/assemblies/",
    "/api/v1/classifications/",
    "/api/v1/components/",
    "/api/v1/annotations/",
    "/api/v1/validation/",
    "/api/v1/reconciliation/",
    "/api/v1/integrations/",
)

# Public / self-service auth prefixes that bypass role restrictions once authenticated (or AllowAny)
AUTH_SELF_SERVICE_PREFIXES = (
    "/api/v1/health/",
    "/api/v1/auth/login/",
    "/api/v1/auth/refresh/",
    "/api/v1/auth/logout/",
    "/api/v1/auth/csrf/",
    "/api/v1/auth/me/",
    "/api/v1/auth/change-password/",
    "/api/v1/auth/register/",
)


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


def _active_memberships_qs(user, organization=None):
    if not user or not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return OrganizationMember.objects.none()
    qs = OrganizationMember.objects.filter(user=user, is_active=True, organization__is_active=True)
    if organization is not None:
        org_id = getattr(organization, "id", organization)
        qs = qs.filter(organization_id=org_id)
    return qs


def get_user_org_ids(user) -> list:
    if not user or not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return []
    if getattr(user, "is_superuser", False):
        return list(Organization.objects.filter(is_active=True).values_list("id", flat=True))
    return list(_active_memberships_qs(user).values_list("organization_id", flat=True))


def get_user_admin_org_ids(user) -> list:
    """Return organization IDs where user holds an active OrganizationMember(role='admin')."""
    if not user or not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return []
    if getattr(user, "is_superuser", False):
        return list(Organization.objects.filter(is_active=True).values_list("id", flat=True))
    return list(
        _active_memberships_qs(user)
        .filter(role=OrganizationMember.Role.ADMIN)
        .values_list("organization_id", flat=True)
    )


def get_user_roles(user, organization=None) -> list[str]:
    if not user or not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return []
    if getattr(user, "is_superuser", False):
        return [OrganizationMember.Role.ADMIN]
    return list(_active_memberships_qs(user, organization).values_list("role", flat=True))


def get_primary_role(user, organization=None) -> str | None:
    """Resolve user's highest-privilege active organization role ('admin' | 'estimator' | 'user' | None)."""
    if not user or not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return None
    if getattr(user, "is_superuser", False):
        return OrganizationMember.Role.ADMIN
    roles = set(get_user_roles(user, organization))
    for r in (OrganizationMember.Role.ADMIN, OrganizationMember.Role.ESTIMATOR, OrganizationMember.Role.USER):
        if r in roles:
            return r
    return None


def is_admin(user, organization=None) -> bool:
    """True strictly for break-glass superuser or active OrganizationMember(role='admin')."""
    if not user or not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return _active_memberships_qs(user, organization).filter(role=OrganizationMember.Role.ADMIN).exists()


def is_estimator(user, organization=None) -> bool:
    if not user or not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return False
    return _active_memberships_qs(user, organization).filter(role=OrganizationMember.Role.ESTIMATOR).exists()


def is_user(user, organization=None) -> bool:
    if not user or not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return False
    return _active_memberships_qs(user, organization).filter(role=OrganizationMember.Role.USER).exists()


def is_org_admin_user(user) -> bool:
    return is_admin(user)


def can_view_estimator_workspace(user, organization=None) -> bool:
    return get_primary_role(user, organization) in (
        OrganizationMember.Role.ADMIN,
        OrganizationMember.Role.ESTIMATOR,
        OrganizationMember.Role.USER,
    )


def can_upload_source(user, organization=None) -> bool:
    if is_admin(user, organization):
        return True
    return is_estimator(user, organization)


def can_start_extraction(user, organization=None) -> bool:
    if is_admin(user, organization):
        return True
    return is_estimator(user, organization)


def can_view_extraction_results(user, organization=None) -> bool:
    return can_view_estimator_workspace(user, organization)


def can_manage_projects(user, organization=None) -> bool:
    return is_admin(user, organization)


def can_edit_project(user, organization=None) -> bool:
    return is_admin(user, organization)


def can_delete_project(user, organization=None) -> bool:
    return is_admin(user, organization)


def can_export(user, organization=None) -> bool:
    return is_admin(user, organization)


def can_manage_users(user, organization=None) -> bool:
    return is_admin(user, organization)


def can_view_audit(user, organization=None) -> bool:
    return is_admin(user, organization)


def get_user_capabilities(user, organization=None) -> dict[str, bool]:
    role = get_primary_role(user, organization)
    admin_flag = role == OrganizationMember.Role.ADMIN
    est_or_admin = role in (OrganizationMember.Role.ADMIN, OrganizationMember.Role.ESTIMATOR)
    member_flag = role in (
        OrganizationMember.Role.ADMIN,
        OrganizationMember.Role.ESTIMATOR,
        OrganizationMember.Role.USER,
    )
    return {
        "can_view_estimator_workspace": member_flag,
        "can_upload_source": est_or_admin,
        "can_start_extraction": est_or_admin,
        "can_view_extraction_results": member_flag,
        "can_manage_projects": admin_flag,
        "can_edit_project": admin_flag,
        "can_delete_project": admin_flag,
        "can_export": admin_flag,
        "can_manage_users": admin_flag,
        "can_view_audit": admin_flag,
        "can_access_admin_modules": admin_flag,
    }


def _record_permission_denial(request, role: str | None) -> None:
    try:
        from apps.audit_logs.services import log_audit_event

        org = None
        if getattr(request, "user", None) and request.user.is_authenticated:
            mem = (
                OrganizationMember.objects.filter(user=request.user, is_active=True)
                .select_related("organization")
                .first()
            )
            org = mem.organization if mem else None
        log_audit_event(
            action="auth.permission_denied",
            actor=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
            organization=org,
            request=request,
            resource_type="APIEndpoint",
            resource_id=(getattr(request, "path", "") or "")[:120],
            metadata={
                "method": getattr(request, "method", ""),
                "path": getattr(request, "path", ""),
                "primary_role": role or "none",
            },
        )
    except Exception:
        pass


def _request_allowed_for_role(request, role: str | None) -> bool:
    path = getattr(request, "path", "") or ""
    method = (getattr(request, "method", "GET") or "GET").upper()

    if any(path.startswith(prefix) for prefix in AUTH_SELF_SERVICE_PREFIXES):
        return True

    if role == OrganizationMember.Role.ADMIN:
        return True

    if role not in (OrganizationMember.Role.ESTIMATOR, OrganizationMember.Role.USER):
        return False

    # Organization list/detail (SAFE ONLY, never /members/ admin endpoints)
    if path.startswith("/api/v1/organizations/"):
        if "/members" in path:
            return False
        return method in SAFE_METHODS

    # Estimator-specific write endpoints: upload source and trigger extraction on existing org project
    if role == OrganizationMember.Role.ESTIMATOR and method == "POST":
        if path == "/api/v1/project-sources/upload/":
            return True
        if path == "/api/v1/extraction/":
            return True
        return False

    # Read-only Estimator Workspace inspection across extracted data prefixes
    if method in SAFE_METHODS and any(path.startswith(prefix) for prefix in WORKSPACE_READ_PREFIXES):
        return True

    # Deny everything else: project writes, source edits/deletes, cancel/delete runs, estimation, exports, AI, retrieval, audit, users
    return False


class RolePolicyPermission(permissions.BasePermission):
    """Global DRF permission enforcing Vortexen's 3-role RBAC policy across all routes."""

    message = "Your organization role does not permit this action."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or not getattr(user, "is_active", False):
            return False
        role = get_primary_role(user)
        allowed = _request_allowed_for_role(request, role)
        if not allowed:
            _record_permission_denial(request, role)
        return allowed


class IsOrgMember(permissions.BasePermission):
    """Requires active organization membership (any of Admin, Estimator, User)."""

    def has_permission(self, request, view) -> bool:
        role = get_primary_role(request.user)
        if role is None:
            _record_permission_denial(request, role)
            return False
        return True

    def has_object_permission(self, request, view, obj) -> bool:
        if getattr(request.user, "is_superuser", False):
            return True
        org = get_object_organization(obj)
        if org is None:
            _record_permission_denial(request, get_primary_role(request.user))
            return False
        ok = _active_memberships_qs(request.user, org).exists()
        if not ok:
            _record_permission_denial(request, get_primary_role(request.user))
        return ok


class IsEstimatorOrAdmin(permissions.BasePermission):
    """Allows active Admin or Estimator members within the target organization."""

    ALLOWED_ROLES = (OrganizationMember.Role.ADMIN, OrganizationMember.Role.ESTIMATOR)

    def has_permission(self, request, view) -> bool:
        role = get_primary_role(request.user)
        if role not in self.ALLOWED_ROLES:
            _record_permission_denial(request, role)
            return False
        return True

    def has_object_permission(self, request, view, obj) -> bool:
        if getattr(request.user, "is_superuser", False):
            return True
        org = get_object_organization(obj)
        if org is None:
            _record_permission_denial(request, get_primary_role(request.user))
            return False
        ok = _active_memberships_qs(request.user, org).filter(role__in=self.ALLOWED_ROLES).exists()
        if not ok:
            _record_permission_denial(request, get_primary_role(request.user))
        return ok


class IsAdminOnly(permissions.BasePermission):
    """Requires active Organization Admin (or break-glass superuser) at both view & object levels."""

    def has_permission(self, request, view) -> bool:
        ok = is_admin(request.user)
        if not ok:
            _record_permission_denial(request, get_primary_role(request.user))
        return ok

    def has_object_permission(self, request, view, obj) -> bool:
        if getattr(request.user, "is_superuser", False):
            return True
        org = get_object_organization(obj)
        ok = is_admin(request.user) if org is None else is_admin(request.user, org)
        if not ok:
            _record_permission_denial(request, get_primary_role(request.user))
        return ok
