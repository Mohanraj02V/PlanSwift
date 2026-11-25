"""Tests for the production-safe bootstrap_admin management command."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command

from apps.organizations.models import Organization, OrganizationMember


@pytest.mark.django_db
def test_bootstrap_admin_is_idempotent_and_validates_passwords():
    User = get_user_model()

    with pytest.raises(CommandError):
        call_command(
            "bootstrap_admin",
            email="admin@vortexen.com",
            password="short",
        )

    call_command(
        "bootstrap_admin",
        email="Admin@Vortexen.com",
        full_name="Vortexen Admin",
        org_name="Vortexen Engineering",
        org_slug="vortexen-eng",
        password="VortexenStrongPass!2026",
    )

    user = User.objects.get(email="admin@vortexen.com")
    assert user.is_staff is True
    assert user.is_superuser is True
    assert user.is_active is True
    assert user.must_change_password is False
    assert user.check_password("VortexenStrongPass!2026") is True

    org = Organization.objects.get(slug="vortexen-eng")
    member = OrganizationMember.objects.get(organization=org, user=user)
    assert member.role == OrganizationMember.Role.ADMIN
    assert member.is_active is True

    # Re-running without --reset-password must keep existing password and stay idempotent
    call_command(
        "bootstrap_admin",
        email="admin@vortexen.com",
        org_name="Vortexen Engineering",
        org_slug="vortexen-eng",
    )
    user.refresh_from_db()
    assert user.check_password("VortexenStrongPass!2026") is True
    assert OrganizationMember.objects.filter(organization=org, user=user).count() == 1

    # Explicit --reset-password rotates the password
    call_command(
        "bootstrap_admin",
        email="admin@vortexen.com",
        org_slug="vortexen-eng",
        password="VortexenRotatedPass!2026",
        reset_password=True,
    )
    user.refresh_from_db()
    assert user.check_password("VortexenRotatedPass!2026") is True
