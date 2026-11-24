"""Tests for enhanced JWT claims, Admin user creation, upload/activity audit logs, estimation_only RBAC, and Excel/PDF quotations."""

from __future__ import annotations

import base64
import io
import json

import ezdxf
import openpyxl
import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.audit_logs.models import AuditLog
from apps.estimation.models import EstimationResult, EstimationSession
from apps.object_model.models import ProjectObject
from apps.organizations.models import Organization, OrganizationMember
from apps.projects.models import Project, ProjectVersion

User = get_user_model()


def _decode_jwt_payload(jwt_token: str) -> dict:
    payload_b64 = jwt_token.split(".")[1]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))


@pytest.mark.django_db
def test_jwt_claims_admin_user_creation_upload_logs_estimation_only_role_and_exports(tmp_path) -> None:
    org = Organization.objects.create(name="Vortexen Dynamics", slug="vortexen-dynamics")
    admin_user = User.objects.create_user(email="admin@vortexen.local", password="AdminPassword123!", full_name="Site Admin")
    OrganizationMember.objects.create(organization=org, user=admin_user, role=OrganizationMember.Role.ADMIN)

    # 1. Failed login is recorded cleanly in audit logs
    anon = APIClient()
    bad_login = anon.post("/api/v1/auth/login/", {"email": "admin@vortexen.local", "password": "WrongPassword!"}, format="json")
    assert bad_login.status_code == 401
    assert AuditLog.objects.filter(action="auth.login_failed").exists()

    # 2. Successful admin login returns custom JWT claims + user profile
    ok_login = anon.post("/api/v1/auth/login/", {"email": "admin@vortexen.local", "password": "AdminPassword123!"}, format="json")
    assert ok_login.status_code == 200
    claims = _decode_jwt_payload(ok_login.data["access"])
    assert claims["email"] == "admin@vortexen.local"
    assert claims["is_admin"] is True
    assert claims["primary_role"] == "admin"
    assert ok_login.data["user"]["allowed_pages"] == ["*"]
    assert AuditLog.objects.filter(action="auth.login", actor=admin_user).exists()

    admin_client = APIClient()
    admin_client.credentials(HTTP_AUTHORIZATION=f"Bearer {ok_login.data['access']}")

    # 3. Admin creates an estimation_only user
    create_u = admin_client.post(
        "/api/v1/auth/users/",
        {
            "email": "estimator.only@vortexen.local",
            "password": "EstOnlyPassword123!",
            "full_name": "Commercial Estimator",
            "job_title": "Sales Estimator",
            "organization": str(org.id),
            "role": "estimation_only",
        },
        format="json",
    )
    assert create_u.status_code == 201
    assert create_u.data["primary_role"] == "estimation_only"
    assert create_u.data["allowed_pages"] == ["/estimation"]
    assert AuditLog.objects.filter(action="admin.user_created", actor=admin_user).exists()

    # 4. Admin creates a project and uploads a DXF file -> file.uploaded audit log records user, filename, date & time
    proj_resp = admin_client.post("/api/v1/projects/", {"organization": str(org.id), "name": "KIZAD DXB 61"}, format="json")
    assert proj_resp.status_code == 201
    proj_id = proj_resp.data["id"]

    dxf_path = tmp_path / "cable_tray.dxf"
    d = ezdxf.new("R2018")
    d.modelspace().add_line((0, 0), (5, 0))
    d.saveas(dxf_path)

    up_resp = admin_client.post(
        "/api/v1/project-sources/upload/",
        {"project": proj_id, "file": SimpleUploadedFile("cable_tray.dxf", dxf_path.read_bytes(), content_type="application/dxf"), "auto_extract": "true"},
        format="multipart",
    )
    assert up_resp.status_code == 201

    upload_logs = admin_client.get("/api/v1/audit/?category=uploads")
    assert upload_logs.status_code == 200
    assert upload_logs.data["count"] >= 1
    up_entry = upload_logs.data["results"][0]
    assert up_entry["actor_email"] == "admin@vortexen.local"
    assert up_entry["metadata"]["file_name"] == "cable_tray.dxf"
    assert up_entry["date"]
    assert up_entry["time"]

    # Seed takeoff item on current version so estimation session has items to price & quote
    proj = Project.objects.get(id=proj_id)
    ver = proj.versions.filter(is_current=True).first()
    sess = EstimationSession.objects.create(project=proj, project_version=ver, name="KIZAD BOQ", created_by=admin_user)
    EstimationResult.objects.create(
        session=sess,
        object_guid="{ITEM-1}",
        object_name="Cable tray 300x50",
        native_class="Count",
        category="Electrical Services",
        quantity=5,
        unit="EA",
        notes="450x100",
    )
    EstimationResult.objects.create(
        session=sess,
        object_guid="{FOLDER-1}",
        object_name="OneDrive_1_07-10-2026",
        native_class="Folder",
        category="Folder",
        quantity=0,
        unit="",
    )

    # 5. estimation_only user logs in -> restricted strictly to Estimation endpoints, blocked everywhere else
    est_login = anon.post(
        "/api/v1/auth/login/",
        {"email": "estimator.only@vortexen.local", "password": "EstOnlyPassword123!"},
        format="json",
    )
    assert est_login.status_code == 200
    assert est_login.data["user"]["primary_role"] == "estimation_only"
    assert est_login.data["user"]["allowed_pages"] == ["/estimation"]

    est_client = APIClient()
    est_client.credentials(HTTP_AUTHORIZATION=f"Bearer {est_login.data['access']}")

    # Blocked from admin user creation, audit logs, extraction, cad-bim, objects, and project mutations
    assert est_client.get("/api/v1/auth/users/").status_code == 403
    assert est_client.get("/api/v1/audit/").status_code == 403
    assert est_client.get(f"/api/v1/extraction/?project={proj_id}").status_code == 403
    assert est_client.get(f"/api/v1/cad-bim/documents/?project_version__project={proj_id}").status_code == 403
    assert est_client.get(f"/api/v1/objects/?project_version__project={proj_id}").status_code == 403
    assert est_client.post("/api/v1/projects/", {"organization": str(org.id), "name": "Nope"}, format="json").status_code == 403

    # Allowed on estimation: read, update rates/quotation metadata, export Excel & Vortexen PDF
    row = sess.results.first()
    upd = est_client.patch(
        f"/api/v1/estimation/sessions/{sess.id}/update-quotation/",
        {
            "quotation": {
                "reference": "VDIS/FM/2024/23316",
                "to_client": "M/s. Jones Engineering",
                "contact_person": "Mohamed Shefeer",
                "vat_percent": 5,
            },
            "items": [{"id": str(row.id), "unit_cost": 135.85, "notes": "450x100"}],
        },
        format="json",
    )
    assert upd.status_code == 200
    assert all(r["native_class"].lower() != "folder" for r in upd.data["results"])
    assert len(upd.data["results"]) == 1
    assert abs(upd.data["summary_json"]["subtotal"] - 679.25) < 1e-6

    xlsx_resp = est_client.get(f"/api/v1/estimation/sessions/{sess.id}/export-excel/")
    assert xlsx_resp.status_code == 200
    assert "spreadsheetml" in xlsx_resp["Content-Type"]
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_resp.content))
    assert "Quotation BOQ" in wb.sheetnames
    assert "Takeoff Details" in wb.sheetnames
    assert wb["Quotation BOQ"]["F8"].value == "=C8*E8"
    assert wb["Quotation BOQ"]["B9"].value is None  # Folder row excluded from Excel BOQ

    pdf_resp = est_client.get(f"/api/v1/estimation/sessions/{sess.id}/export-pdf/")
    assert pdf_resp.status_code == 200
    assert pdf_resp["Content-Type"] == "application/pdf"
    assert pdf_resp.content.startswith(b"%PDF-")

    # Multi-page dynamic pagination check with 45 items (no Opening Size, no overlap)
    for k in range(2, 46):
        EstimationResult.objects.create(
            session=sess,
            object_guid=f"{{ITEM-{k}}}",
            object_name=f"Dynamic Item {k} — Duct 300x100",
            native_class="Count",
            category="Electrical Services",
            quantity=k,
            unit="EA",
            unit_cost=100.0,
            total_cost=100.0 * k,
        )
    multi_pdf = est_client.get(f"/api/v1/estimation/sessions/{sess.id}/export-pdf/")
    assert multi_pdf.status_code == 200
    assert multi_pdf.content.startswith(b"%PDF-")
    assert len(multi_pdf.content) > len(pdf_resp.content)

    assert AuditLog.objects.filter(action="estimation.excel_exported", actor__email="estimator.only@vortexen.local").exists()
    assert AuditLog.objects.filter(action="estimation.pdf_quotation_exported", actor__email="estimator.only@vortexen.local").exists()

    # 6. Viewer user can read projects, but is blocked (403) from audit logs and file uploads
    viewer_create = admin_client.post(
        "/api/v1/auth/users/",
        {
            "email": "viewer.user@vortexen.local",
            "password": "ViewerPassword123!",
            "full_name": "Read Only Viewer",
            "organization": str(org.id),
            "role": "viewer",
        },
        format="json",
    )
    assert viewer_create.status_code == 201
    v_login = anon.post("/api/v1/auth/login/", {"email": "viewer.user@vortexen.local", "password": "ViewerPassword123!"}, format="json")
    assert v_login.status_code == 200
    v_client = APIClient()
    v_client.credentials(HTTP_AUTHORIZATION=f"Bearer {v_login.data['access']}")
    assert v_client.get("/api/v1/projects/").status_code == 200
    assert v_client.get("/api/v1/audit/").status_code == 403
    assert v_client.post(
        "/api/v1/project-sources/upload/",
        {"project": proj_id, "file": SimpleUploadedFile("x.dxf", dxf_path.read_bytes())},
        format="multipart",
    ).status_code == 403

    # 7. Logout blacklists refresh token and records auth.logout
    out_resp = est_client.post("/api/v1/auth/logout/", {"refresh": est_login.data["refresh"]}, format="json")
    assert out_resp.status_code == 200
    assert AuditLog.objects.filter(action="auth.logout", actor__email="estimator.only@vortexen.local").exists()
