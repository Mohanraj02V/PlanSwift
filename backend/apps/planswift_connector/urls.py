from django.urls import path

from apps.planswift_connector.views import ConnectorSyncListView, PlanSwiftEnvironmentView, PlanSwiftIngestView

urlpatterns = [
    path("environment/", PlanSwiftEnvironmentView.as_view(), name="planswift-environment"),
    path("ingest/", PlanSwiftIngestView.as_view(), name="planswift-ingest"),
    path("batches/", ConnectorSyncListView.as_view(), name="planswift-batches"),
]
