"""Production-safe management command to idempotently bootstrap an Organization Admin."""

from __future__ import annotations

import getpass
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.organizations.models import Organization, OrganizationMember


class Command(BaseCommand):
    help = "Idempotently create or promote the initial Organization and Admin user."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="Admin user email address.")
        parser.add_argument("--full-name", default="Vortexen Administrator", help="Admin full name.")
        parser.add_argument("--job-title", default="System Administrator", help="Admin job title.")
        parser.add_argument("--org-name", default="Vortexen Engineering", help="Organization display name.")
        parser.add_argument("--org-slug", default="vortexen", help="Organization unique slug.")
        parser.add_argument(
            "--password",
            default="",
            help="Admin password (falls back to VORTEXEN_ADMIN_PASSWORD env var or interactive prompt).",
        )
        parser.add_argument(
            "--reset-password",
            action="store_true",
            help="Update password if the user already exists.",
        )

    def _resolve_password(self, raw_password: str, user) -> str:
        password = (raw_password or os.environ.get("VORTEXEN_ADMIN_PASSWORD", "")).strip()
        if not password:
            password = getpass.getpass("Admin password (min 10 chars): ").strip()
            confirm = getpass.getpass("Confirm admin password: ").strip()
            if password != confirm:
                raise CommandError("Passwords do not match.")
        if not password:
            raise CommandError("Password cannot be empty.")
        try:
            validate_password(password, user=user)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc
        return password

    @transaction.atomic
    def handle(self, *args, **options):
        email = (options["email"] or "").strip().lower()
        if not email or "@" not in email:
            raise CommandError("A valid --email address is required.")

        User = get_user_model()
        existing_user = User.objects.filter(email__iexact=email).first()
        reset_password = bool(options.get("reset_password"))

        if existing_user is None:
            candidate = User(
                email=email,
                full_name=options["full_name"].strip(),
                job_title=options["job_title"].strip(),
                is_staff=True,
                is_superuser=True,
                is_active=True,
                must_change_password=False,
            )
            password = self._resolve_password(options.get("password", ""), candidate)
            candidate.set_password(password)
            candidate.save()
            user = candidate
            user_status = "created"
        else:
            user = existing_user
            changed_fields = []
            if not user.is_staff:
                user.is_staff = True
                changed_fields.append("is_staff")
            if not user.is_superuser:
                user.is_superuser = True
                changed_fields.append("is_superuser")
            if not user.is_active:
                user.is_active = True
                changed_fields.append("is_active")
            if user.must_change_password:
                user.must_change_password = False
                changed_fields.append("must_change_password")
            if reset_password:
                password = self._resolve_password(options.get("password", ""), user)
                user.set_password(password)
                changed_fields.append("password")
            if changed_fields:
                user.save()
            user_status = "updated" if reset_password or changed_fields else "unchanged"

        org_slug = options["org_slug"].strip()
        org_name = options["org_name"].strip()
        org, org_created = Organization.objects.get_or_create(
            slug=org_slug,
            defaults={
                "name": org_name,
                "is_active": True,
                "created_by": user,
            },
        )
        if not org_created and not org.is_active:
            org.is_active = True
            org.save(update_fields=["is_active", "updated_at"])

        membership, mem_created = OrganizationMember.objects.get_or_create(
            organization=org,
            user=user,
            defaults={
                "role": OrganizationMember.Role.ADMIN,
                "is_active": True,
            },
        )
        if not mem_created and (membership.role != OrganizationMember.Role.ADMIN or not membership.is_active):
            membership.role = OrganizationMember.Role.ADMIN
            membership.is_active = True
            membership.save(update_fields=["role", "is_active"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Admin user {user.email} ({user_status}) linked as ADMIN to organization '{org.name}' [{org.slug}]."
            )
        )
