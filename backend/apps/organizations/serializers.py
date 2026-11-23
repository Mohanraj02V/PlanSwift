from __future__ import annotations

from rest_framework import serializers

from apps.organizations.models import Organization, OrganizationMember


class OrganizationSerializer(serializers.ModelSerializer):
    my_role = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = ["id", "name", "slug", "is_active", "my_role", "created_at"]
        read_only_fields = ["id", "is_active", "my_role", "created_at"]

    def get_my_role(self, obj: Organization) -> str | None:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        member = obj.members.filter(user=request.user, is_active=True).first()
        return member.role if member else None


class OrganizationMemberSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = OrganizationMember
        fields = ["id", "organization", "user", "user_email", "role", "is_active", "created_at"]
        read_only_fields = ["id", "organization", "user_email", "created_at"]
