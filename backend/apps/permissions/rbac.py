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
    if hasattr(obj, "project_object") and getattr(obj.project_object, "project_version", None) is not None:
        return obj.project_object.project_version.project.organization
    if hasattr(obj, "session") and getattr(obj.session, "project", None) is not None:
        return obj.session.project.organization
    if hasattr(obj, "conversation") and getattr(obj.conversation, "project", None) is not None:
        return obj.conversation.project.organization
    return None


def get_user_org_ids(user) -> list:
    if not user or not user.is_authenticated:
        return []
    return list(
        OrganizationMember.objects.filter(user=user, is_active=True).values_list("organization_id", flat=True)
    )


class IsOrgMember(permissions.BasePermission):
    """Allows access only if authenticated user is an active member of the object's organization."""

    def has_object_permission(self, request, view, obj) -> bool:
        org = get_object_organization(obj)
        if org is None:
            return False
        return OrganizationMember.objects.filter(
            organization=org,
            user=request.user,
            is_active=True,
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
