"""Serializers for authentication, JWT claims, user profile, admin user management, and password reset."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.organizations.models import OrganizationMember
from apps.permissions.rbac import get_primary_role, get_user_capabilities, is_admin

User = get_user_model()


def _user_memberships_payload(user) -> list[dict]:
    return [
        {
            "organization_id": str(m.organization_id),
            "organization_name": m.organization.name,
            "role": m.role,
        }
        for m in OrganizationMember.objects.filter(user=user, is_active=True, organization__is_active=True)
        .select_related("organization")
        .order_by("created_at")
    ]


class UserProfileSerializer(serializers.ModelSerializer):
    is_admin = serializers.SerializerMethodField()
    primary_role = serializers.SerializerMethodField()
    allowed_pages = serializers.SerializerMethodField()
    capabilities = serializers.SerializerMethodField()
    memberships = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "job_title",
            "is_superuser",
            "is_admin",
            "primary_role",
            "allowed_pages",
            "capabilities",
            "must_change_password",
            "memberships",
            "mfa_enabled",
            "is_active",
            "last_login",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "email",
            "is_superuser",
            "is_admin",
            "primary_role",
            "allowed_pages",
            "capabilities",
            "must_change_password",
            "memberships",
            "mfa_enabled",
            "is_active",
            "last_login",
            "created_at",
        ]

    def get_is_admin(self, obj) -> bool:
        return is_admin(obj)

    def get_primary_role(self, obj) -> str | None:
        return get_primary_role(obj)

    def get_capabilities(self, obj) -> dict[str, bool]:
        return get_user_capabilities(obj)

    def get_allowed_pages(self, obj) -> list[str]:
        role = get_primary_role(obj)
        if role == OrganizationMember.Role.ADMIN:
            return ["*"]
        if role in (OrganizationMember.Role.ESTIMATOR, OrganizationMember.Role.USER):
            return ["/estimator"]
        return []

    def get_memberships(self, obj) -> list[dict]:
        return _user_memberships_payload(obj)


class VortexenTokenObtainPairSerializer(TokenObtainPairSerializer):
    """JWT serializer embedding role, token_version revocation counter, and sanitized auth failures."""

    default_error_messages = {
        "no_active_account": "Invalid email or password.",
    }

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        memberships = _user_memberships_payload(user)
        token["email"] = user.email
        token["full_name"] = user.full_name or ""
        token["is_admin"] = is_admin(user)
        token["primary_role"] = get_primary_role(user) or ""
        token["roles"] = [m["role"] for m in memberships]
        token["token_version"] = int(getattr(user, "token_version", 1))
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        if not getattr(self.user, "is_superuser", False) and get_primary_role(self.user) is None:
            raise AuthenticationFailed("Invalid email or password.", code="no_active_membership")
        data["user"] = UserProfileSerializer(self.user).data
        return data


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
    role = serializers.ChoiceField(choices=OrganizationMember.Role.choices, default=OrganizationMember.Role.USER)
    is_active = serializers.BooleanField(default=True)
    must_change_password = serializers.BooleanField(default=False)

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
    must_change_password = serializers.BooleanField(required=False)

    def validate_password(self, value: str) -> str:
        if value:
            validate_password(value)
        return value
