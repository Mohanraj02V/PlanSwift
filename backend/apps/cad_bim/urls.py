from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.cad_bim.views import (
    BIMElementViewSet,
    CADBlockViewSet,
    CADDocumentViewSet,
    CADEntityViewSet,
    CADLayerViewSet,
)

router = DefaultRouter()
router.register("documents", CADDocumentViewSet, basename="cad-document")
router.register("layers", CADLayerViewSet, basename="cad-layer")
router.register("blocks", CADBlockViewSet, basename="cad-block")
router.register("entities", CADEntityViewSet, basename="cad-entity")
router.register("elements", BIMElementViewSet, basename="bim-element")

urlpatterns = [path("", include(router.urls))]
