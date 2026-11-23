from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.extraction.views import ExtractionRunViewSet

router = DefaultRouter()
router.register("", ExtractionRunViewSet, basename="extraction-run")

urlpatterns = [path("", include(router.urls))]
