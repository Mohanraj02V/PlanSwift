from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.object_model.views import ProjectObjectViewSet

router = DefaultRouter()
router.register("", ProjectObjectViewSet, basename="project-object")

urlpatterns = [path("", include(router.urls))]
