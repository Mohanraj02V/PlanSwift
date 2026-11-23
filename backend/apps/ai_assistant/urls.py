from __future__ import annotations

from django.urls import path
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_agents.services import EstimationQAAgent
from apps.ai_assistant.models import AIConversation, AIMessage
from apps.audit_logs.services import log_audit_event
from apps.permissions.rbac import get_user_org_ids
from apps.projects.models import Project


class AIQuerySerializer(serializers.Serializer):
    project_id = serializers.UUIDField()
    question = serializers.CharField(min_length=2, max_length=2000)
    conversation_id = serializers.UUIDField(required=False, allow_null=True)
    provider = serializers.CharField(required=False, allow_blank=True)
    model = serializers.CharField(required=False, allow_blank=True)


class AIMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIMessage
        fields = ["id", "role", "content", "source_objects", "data_status", "inference_used", "metadata", "created_at"]


class AIConversationSerializer(serializers.ModelSerializer):
    messages = AIMessageSerializer(many=True, read_only=True)

    class Meta:
        model = AIConversation
        fields = ["id", "project", "title", "created_at", "messages"]


class AIQueryView(APIView):
    def post(self, request):
        ser = AIQuerySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        org_ids = get_user_org_ids(request.user)
        project = Project.objects.filter(id=ser.validated_data["project_id"], organization_id__in=org_ids).select_related("organization").first()
        if not project:
            return Response({"detail": "Project not found."}, status=status.HTTP_404_NOT_FOUND)

        conv_id = ser.validated_data.get("conversation_id")
        conv = AIConversation.objects.filter(id=conv_id, project=project, user=request.user).first() if conv_id else None
        if conv is None:
            conv = AIConversation.objects.create(project=project, user=request.user, title=ser.validated_data["question"][:80])

        AIMessage.objects.create(conversation=conv, role="user", content=ser.validated_data["question"], data_status="original")
        agent = EstimationQAAgent()
        result = agent.answer_question(
            project=project,
            question=ser.validated_data["question"],
            provider_name=ser.validated_data.get("provider") or None,
            model_name=ser.validated_data.get("model") or None,
        )

        AIMessage.objects.create(
            conversation=conv,
            role="assistant",
            content=result["answer"],
            source_objects=result["source_objects"],
            data_status=result["data_status"],
            inference_used=result["inference_used"],
            metadata={"provider_used": result["provider_used"], "retrieval_stats": result["retrieval_stats"]},
        )
        log_audit_event(
            action="ai.query",
            actor=request.user,
            organization=project.organization,
            request=request,
            resource_type="AIConversation",
            resource_id=str(conv.id),
            metadata={"data_status": result["data_status"], "inference_used": result["inference_used"]},
        )
        return Response({"conversation_id": str(conv.id), **result}, status=status.HTTP_200_OK)


class AIConversationListView(generics.ListAPIView):
    serializer_class = AIConversationSerializer
    filterset_fields = ["project"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return AIConversation.objects.filter(project__organization_id__in=org_ids, user=self.request.user).prefetch_related("messages")


urlpatterns = [
    path("query/", AIQueryView.as_view(), name="ai-query"),
    path("conversations/", AIConversationListView.as_view(), name="ai-conversations"),
]
