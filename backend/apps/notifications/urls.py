from django.urls import path
from rest_framework import generics, serializers

from apps.notifications.models import Notification
from apps.permissions.rbac import get_user_org_ids


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "organization", "level", "title", "message", "is_read", "metadata", "created_at"]


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return Notification.objects.filter(organization_id__in=org_ids)


urlpatterns = [path("", NotificationListView.as_view(), name="notification-list")]
