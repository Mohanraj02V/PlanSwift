from __future__ import annotations

from django.db.models import Case, IntegerField, Value, When
from django.urls import path
from rest_framework import generics, serializers

from apps.formulas.models import Formula, FormulaDependency
from apps.permissions.rbac import get_user_org_ids


class FormulaDependencySerializer(serializers.ModelSerializer):
    class Meta:
        model = FormulaDependency
        fields = ["raw_token", "reference_kind", "target_property", "target_object_guid", "resolved"]


class FormulaSerializer(serializers.ModelSerializer):
    object_name = serializers.CharField(source="project_object.name", read_only=True)
    object_guid = serializers.CharField(source="project_object.native_guid", read_only=True)
    dependencies = FormulaDependencySerializer(many=True, read_only=True)

    class Meta:
        model = Formula
        fields = [
            "id",
            "project_version",
            "object_guid",
            "object_name",
            "formula_key",
            "property_guid",
            "property_name",
            "raw_expression",
            "is_pascal_script",
            "has_circular_dependency",
            "circular_path",
            "unresolved_references",
            "evaluation_status",
            "calculated_value",
            "calculated_numeric",
            "calculation_unit",
            "calculation_reason",
            "calculation_inputs_json",
            "dependencies",
        ]


class CalculationResultSerializer(serializers.ModelSerializer):
    object_name = serializers.CharField(source="project_object.name", read_only=True)
    object_guid = serializers.CharField(source="project_object.native_guid", read_only=True)
    native_class = serializers.CharField(source="project_object.native_class", read_only=True)

    class Meta:
        model = Formula
        fields = [
            "id",
            "project_version",
            "object_guid",
            "object_name",
            "native_class",
            "property_guid",
            "property_name",
            "raw_expression",
            "evaluation_status",
            "calculated_value",
            "calculated_numeric",
            "calculation_unit",
            "calculation_reason",
            "calculation_inputs_json",
        ]


class FormulaListView(generics.ListAPIView):
    serializer_class = FormulaSerializer
    filterset_fields = [
        "project_version",
        "project_version__project",
        "is_pascal_script",
        "has_circular_dependency",
        "evaluation_status",
        "calculation_reason",
        "property_name",
    ]
    search_fields = ["property_name", "raw_expression", "project_object__name", "project_object__native_guid"]
    ordering_fields = ["evaluation_status", "property_name", "is_pascal_script"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        qs = Formula.objects.filter(project_version__project__organization_id__in=org_ids)
        category = self.request.query_params.get("category", "").strip().lower()
        if category == "cost":
            qs = qs.filter(property_name__in=["Cost Total", "Price Total", "Price Each", "Markup Each", "Markup Total"])
        elif category == "calc":
            qs = qs.filter(
                property_name__in=[
                    "Qty",
                    "Qty Formula",
                    "Takeoff",
                    "Takeoff %",
                    "Point Count",
                    "Linear Total",
                    "Area",
                    "Volume",
                    "Wall Area",
                    "Pitch Factor",
                    "Section Count",
                    "Segment Count",
                    "Line Width",
                    "Default",
                ]
            )
        elif category == "page_ref":
            qs = qs.filter(
                property_name__in=[
                    "Page",
                    "Scale Units",
                    "Takeoff Item Units",
                    "Takeoff Name",
                    "Folder",
                    "Folder Path",
                ]
            )
        elif category == "page_dims":
            qs = qs.filter(property_name__in=["PageWidth", "PageHeight"])

        return (
            qs.annotate(
                priority=Case(
                    When(
                        property_name__in=[
                            "Qty",
                            "Qty Formula",
                            "Wall Area",
                            "Area",
                            "Linear Total",
                            "Cost Total",
                            "Price Total",
                            "Volume",
                        ],
                        then=Value(1),
                    ),
                    When(
                        property_name__in=[
                            "Takeoff",
                            "Takeoff %",
                            "Point Count",
                            "Pitch Factor",
                            "Section Count",
                            "Segment Count",
                            "Line Width",
                        ],
                        then=Value(2),
                    ),
                    When(property_name__in=["PageWidth", "PageHeight"], then=Value(3)),
                    When(
                        property_name__in=["Page", "Scale Units", "Takeoff Name", "Takeoff Item Units", "Folder"],
                        then=Value(4),
                    ),
                    When(is_pascal_script=True, then=Value(5)),
                    default=Value(6),
                    output_field=IntegerField(),
                )
            )
            .select_related("project_object")
            .prefetch_related("dependencies")
            .order_by("priority", "project_object__name", "property_name", "id")
        )


class FormulaCalculationListView(generics.ListAPIView):
    serializer_class = CalculationResultSerializer
    filterset_fields = [
        "project_version",
        "project_version__project",
        "evaluation_status",
        "calculation_reason",
        "property_name",
    ]
    search_fields = ["property_name", "raw_expression", "calculated_value", "project_object__name"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return (
            Formula.objects.filter(project_version__project__organization_id__in=org_ids)
            .select_related("project_object")
            .order_by("evaluation_status", "project_object__name", "property_name")
        )


urlpatterns = [
    path("", FormulaListView.as_view(), name="formula-list"),
    path("calculations/", FormulaCalculationListView.as_view(), name="formula-calculations"),
]
