from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.project_sources.views import ProjectSourceViewSet

router = DefaultRouter()
router.register("", ProjectSourceViewSet, basename="project-source")

urlpatterns = [path("", include(router.urls))]
