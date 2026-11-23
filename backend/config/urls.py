"""Root URL configuration for Vortexen Estimator."""

from __future__ import annotations

from django.contrib import admin
from django.db import connection
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return Response({"status": "ok", "service": "vortexen-estimator-api", "database": "connected"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", HealthCheckView.as_view(), name="api-health"),
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-docs"),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/organizations/", include("apps.organizations.urls")),
    path("api/v1/projects/", include("apps.projects.urls")),
    path("api/v1/project-sources/", include("apps.project_sources.urls")),
    path("api/v1/source-inventory/", include("apps.source_inventory.urls")),
    path("api/v1/planswift/", include("apps.planswift_connector.urls")),
    path("api/v1/extraction/", include("apps.extraction.urls")),
    path("api/v1/objects/", include("apps.object_model.urls")),
    path("api/v1/hierarchy/", include("apps.object_hierarchy.urls")),
    path("api/v1/measurements/", include("apps.measurements.urls")),
    path("api/v1/geometry/", include("apps.geometry.urls")),
    path("api/v1/formulas/", include("apps.formulas.urls")),
    path("api/v1/classifications/", include("apps.classifications.urls")),
    path("api/v1/assemblies/", include("apps.assemblies.urls")),
    path("api/v1/components/", include("apps.components.urls")),
    path("api/v1/annotations/", include("apps.annotations.urls")),
    path("api/v1/validation/", include("apps.validation.urls")),
    path("api/v1/reconciliation/", include("apps.reconciliation.urls")),
    path("api/v1/estimation/", include("apps.estimation.urls")),
    path("api/v1/exports/", include("apps.exports.urls")),
    path("api/v1/integrations/", include("apps.integrations.urls")),
    path("api/v1/ai/", include("apps.ai_assistant.urls")),
    path("api/v1/retrieval/", include("apps.retrieval.urls")),
    path("api/v1/audit/", include("apps.audit_logs.urls")),
    path("api/v1/notifications/", include("apps.notifications.urls")),
]
