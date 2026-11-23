from __future__ import annotations

from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.object_hierarchy.models import ObjectRelationship
from apps.object_model.models import ProjectObject
from apps.permissions.rbac import get_user_org_ids
from apps.projects.models import Project


class ObjectRelationshipSerializer(serializers.ModelSerializer):
    class Meta:
        model = ObjectRelationship
        fields = ["id", "relationship_key", "relationship_type", "source_guid", "target_guid", "order_index", "metadata", "provenance"]


class ObjectRelationshipListView(generics.ListAPIView):
    serializer_class = ObjectRelationshipSerializer
    filterset_fields = ["project_version", "relationship_type", "source_guid", "target_guid"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return ObjectRelationship.objects.filter(project_version__project__organization_id__in=org_ids)


class ProjectHierarchyTreeView(APIView):
    """Returns structured tree nodes preserving native PlanSwift order."""

    def get(self, request, project_id):
        org_ids = get_user_org_ids(request.user)
        project = Project.objects.filter(id=project_id, organization_id__in=org_ids).first()
        if not project:
            return Response({"detail": "Project not found."}, status=404)
        ver = project.versions.filter(is_current=True).first()
        if not ver:
            return Response({"nodes": []})

        max_depth = int(request.query_params.get("max_depth", 3))
        parent_guid = request.query_params.get("parent_guid")
        qs = ProjectObject.objects.filter(project_version=ver)
        if parent_guid:
            qs = qs.filter(parent_guid__iexact=parent_guid)
        else:
            qs = qs.filter(depth__lte=max_depth)

        nodes = list(
            qs.order_by("depth", "order_index", "name").values(
                "id",
                "native_guid",
                "native_class",
                "native_type",
                "name",
                "parent_guid",
                "depth",
                "order_index",
                "is_page",
                "is_measurement_section",
                "is_known_class",
                "page_guid",
                "provenance",
            )
        )
        return Response({"project_id": str(project.id), "project_guid": project.native_guid, "nodes": nodes})
