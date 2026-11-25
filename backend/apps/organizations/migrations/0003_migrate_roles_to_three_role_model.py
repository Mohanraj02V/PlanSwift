"""Safe data migration consolidating legacy roles into Admin, Estimator, and User."""

from __future__ import annotations

from django.db import migrations


def forwards_migrate_roles(apps, schema_editor):
    OrganizationMember = apps.get_model("organizations", "OrganizationMember")
    User = apps.get_model("accounts", "User")

    # 1. owner / admin -> admin
    OrganizationMember.objects.filter(role__in=["owner", "admin"]).update(role="admin")

    # 2. estimator stays estimator
    OrganizationMember.objects.filter(role="estimator").update(role="estimator")

    # 3. reviewer / viewer / estimation_only -> user
    OrganizationMember.objects.filter(role__in=["reviewer", "viewer", "estimation_only"]).update(role="user")

    # 4. connector_agent -> deactivate membership & convert to user (never elevate)
    connector_user_ids = list(
        OrganizationMember.objects.filter(role="connector_agent").values_list("user_id", flat=True)
    )
    OrganizationMember.objects.filter(role="connector_agent").update(role="user", is_active=False)

    for uid in connector_user_ids:
        has_other_active = OrganizationMember.objects.filter(user_id=uid, is_active=True).exists()
        if not has_other_active:
            User.objects.filter(id=uid).update(is_active=False)

    # 5. Any unknown stray value -> safest read-only role 'user'
    OrganizationMember.objects.exclude(role__in=["admin", "estimator", "user"]).update(role="user")


def backwards_noop(apps, schema_editor):
    # Deliberate no-op: consolidated roles preserve tenant boundaries safely.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0002_alter_organizationmember_role"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards_migrate_roles, backwards_noop),
    ]
