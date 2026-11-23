from django.urls import path
from rest_framework import generics, serializers

from apps.permissions.rbac import get_user_org_ids
from apps.validation.models import ValidationResult


class ValidationResultSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source="project_version.project.name", read_only=True)

    class Meta:
        model = ValidationResult
        fields = [
            "id",
            "project_version",
            "project_name",
            "extraction_run",
            "overall_status",
            "objects_discovered",
            "objects_extracted",
            "unknown_class_objects",
            "skipped_objects",
            "properties_extracted",
            "empty_name_properties",
            "pages_discovered",
            "pages_matched_to_tiff",
            "sections_extracted",
            "sections_with_resolved_page",
            "geometry_features_extracted",
            "points_extracted",
            "formulas_extracted",
            "unresolved_formulas",
            "circular_formulas",
            "unresolved_references",
            "unparsed_files",
            "unsupported_classes",
            "overall_verified_accuracy_pct",
            "checks_json",
            "created_at",
        ]


class ValidationListView(generics.ListAPIView):
    serializer_class = ValidationResultSerializer
    filterset_fields = ["project_version", "project_version__project", "overall_status"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return ValidationResult.objects.filter(project_version__project__organization_id__in=org_ids).select_related("project_version__project")


urlpatterns = [path("", ValidationListView.as_view(), name="validation-list")]
