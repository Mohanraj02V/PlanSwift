from django.urls import path

from apps.object_hierarchy.views import ObjectRelationshipListView, ProjectHierarchyTreeView

urlpatterns = [
    path("relationships/", ObjectRelationshipListView.as_view(), name="hierarchy-relationships"),
    path("tree/<uuid:project_id>/", ProjectHierarchyTreeView.as_view(), name="hierarchy-tree"),
]
