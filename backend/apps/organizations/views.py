from __future__ import annotations

from django.db import transaction
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit_logs.services import log_audit_event
from apps.organizations.models import Organization, OrganizationMember
from apps.organizations.serializers import OrganizationMemberSerializer, OrganizationSerializer
from apps.permissions.rbac import IsOrgAdminOrOwner, IsOrgMember


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSerializer

    def get_queryset(self):
        return Organization.objects.filter(members__user=self.request.user, members__is_active=True).distinct()

    def get_permissions(self):
        if self.action in ("list", "create"):
            return [permissions.IsAuthenticated()]
        if self.action in ("update", "partial_update", "destroy", "add_member"):
            return [permissions.IsAuthenticated(), IsOrgAdminOrOwner()]
        return [permissions.IsAuthenticated(), IsOrgMember()]

    @transaction.atomic
    def perform_create(self, serializer):
        org = serializer.save(created_by=self.request.user)
        OrganizationMember.objects.create(
            organization=org,
            user=self.request.user,
            role=OrganizationMember.Role.OWNER,
        )
        log_audit_event(
            action="organization.created",
            actor=self.request.user,
            organization=org,
            request=self.request,
            resource_type="Organization",
            resource_id=str(org.id),
        )

    @action(detail=True, methods=["get", "post"], url_path="members")
    def members(self, request, pk=None):
        org = self.get_object()
        if request.method == "GET":
            qs = OrganizationMember.objects.filter(organization=org).select_related("user")
            return Response(OrganizationMemberSerializer(qs, many=True).data)
        member_check = IsOrgAdminOrOwner()
        if not member_check.has_object_permission(request, self, org):
            return Response({"detail": "Admin or Owner role required."}, status=status.HTTP_403_FORBIDDEN)
        ser = OrganizationMemberSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        member = ser.save(organization=org)
        log_audit_event(
            action="organization.member_added",
            actor=request.user,
            organization=org,
            request=request,
            resource_type="OrganizationMember",
            resource_id=str(member.id),
        )
        return Response(OrganizationMemberSerializer(member).data, status=status.HTTP_201_CREATED)
