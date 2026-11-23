from __future__ import annotations

from django.urls import path
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.knowledge_base.models import KnowledgeChunk, KnowledgeDocument
from apps.organizations.models import OrganizationMember
from apps.permissions.rbac import IsOrgEditor, get_user_org_ids
from apps.projects.models import Project
from apps.retrieval.models import RetrievalRecord
from apps.retrieval.services import HybridRetrievalService, compute_term_weights


class KnowledgeDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeDocument
        fields = ["id", "organization", "title", "category", "content", "source_reference", "created_at"]


class KnowledgeDocumentListCreateView(generics.ListCreateAPIView):
    serializer_class = KnowledgeDocumentSerializer

    def get_queryset(self):
        return KnowledgeDocument.objects.filter(organization_id__in=get_user_org_ids(self.request.user))

    def perform_create(self, serializer):
        org = serializer.validated_data["organization"]
        if not OrganizationMember.objects.filter(
            organization=org, user=self.request.user, is_active=True, role__in=IsOrgEditor.ALLOWED_ROLES
        ).exists():
            raise PermissionError("Forbidden")
        doc = serializer.save()
        chunks = [p.strip() for p in doc.content.split("\n\n") if p.strip()] or [doc.content]
        KnowledgeChunk.objects.bulk_create(
            [
                KnowledgeChunk(document=doc, chunk_index=idx, text=chunk, term_weights_json=compute_term_weights(chunk))
                for idx, chunk in enumerate(chunks)
            ]
        )


class RetrievalPreviewView(APIView):
    def post(self, request):
        project_id = request.data.get("project_id")
        query = request.data.get("query", "")
        org_ids = get_user_org_ids(request.user)
        project = Project.objects.filter(id=project_id, organization_id__in=org_ids).first()
        if not project:
            return Response({"detail": "Project not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(HybridRetrievalService().retrieve(project, query))


class RetrievalLogListView(generics.ListAPIView):
    class _Ser(serializers.ModelSerializer):
        class Meta:
            model = RetrievalRecord
            fields = "__all__"

    serializer_class = _Ser

    def get_queryset(self):
        return RetrievalRecord.objects.filter(project__organization_id__in=get_user_org_ids(self.request.user))


urlpatterns = [
    path("preview/", RetrievalPreviewView.as_view(), name="retrieval-preview"),
    path("logs/", RetrievalLogListView.as_view(), name="retrieval-logs"),
    path("knowledge/", KnowledgeDocumentListCreateView.as_view(), name="knowledge-list-create"),
]
