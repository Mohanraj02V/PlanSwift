"""Serializers for authentication, JWT claims, user profile, admin user management, and password reset."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.organizations.models import OrganizationMember
from apps.permissions.rbac import is_estimation_only_user, is_org_admin_user

User = get_user_model()


def _user_memberships_payload(user) -> list[dict]:
    return [
        {
            "organization_id": str(m.organization_id),
            "organization_name": m.organization.name,
            "role": m.role,
        }
        for m in OrganizationMember.objects.filter(user=user, is_active=True)
        .select_related("organization")
        .order_by("created_at")
    ]


def _resolve_primary_role(user, memberships: list[dict]) -> str:
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return "admin"
    roles = [m["role"] for m in memberships]
    if not roles:
        return "viewer"
    for priority in ("owner", "admin", "estimator", "reviewer", "estimation_only", "viewer", "connector_agent"):
        if priority in roles:
            return priority
    return roles[0]


class UserProfileSerializer(serializers.ModelSerializer):
    is_admin = serializers.SerializerMethodField()
    primary_role = serializers.SerializerMethodField()
    allowed_pages = serializers.SerializerMethodField()
    memberships = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "job_title",
            "is_staff",
            "is_superuser",
            "is_admin",
            "primary_role",
            "allowed_pages",
            "memberships",
            "mfa_enabled",
            "is_active",
            "last_login",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "email",
            "is_staff",
            "is_superuser",
            "is_admin",
            "primary_role",
            "allowed_pages",
            "memberships",
            "mfa_enabled",
            "is_active",
            "last_login",
            "created_at",
        ]

    def get_is_admin(self, obj) -> bool:
        return is_org_admin_user(obj)

    def get_primary_role(self, obj) -> str:
        return _resolve_primary_role(obj, _user_memberships_payload(obj))

    def get_allowed_pages(self, obj) -> list[str]:
        if is_estimation_only_user(obj):
            return ["/estimation"]
        return ["*"]

    def get_memberships(self, obj) -> list[dict]:
        return _user_memberships_payload(obj)


class VortexenTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Enhanced JWT serializer adding role/admin/identity claims and returning user profile."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        memberships = _user_memberships_payload(user)
        primary_role = _resolve_primary_role(user, memberships)
        token["email"] = user.email
        token["full_name"] = user.full_name or ""
        token["is_admin"] = is_org_admin_user(user)
        token["primary_role"] = primary_role
        token["roles"] = [m["role"] for m in memberships]
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserProfileSerializer(self.user).data
        return data


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=10)

    class Meta:
        model = User
        fields = ["email", "password", "full_name", "job_title"]

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=10)

    def validate_new_password(self, value: str) -> str:
        validate_password(value)
        return value


class AdminUserCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=10)
    full_name = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    job_title = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    organization = serializers.UUIDField(required=False)
    role = serializers.ChoiceField(choices=OrganizationMember.Role.choices, default=OrganizationMember.Role.ESTIMATOR)
    is_active = serializers.BooleanField(default=True)

    def validate_email(self, value: str) -> str:
        normalized = User.objects.normalize_email(value).strip()
        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return normalized

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value


class AdminUserUpdateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    job_title = serializers.CharField(max_length=120, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=OrganizationMember.Role.choices, required=False)
    organization = serializers.UUIDField(required=False)
    is_active = serializers.BooleanField(required=False)
    password = serializers.CharField(write_only=True, min_length=10, required=False, allow_blank=True)

    def validate_password(self, value: str) -> str:
        if value:
            validate_password(value)
        return value
