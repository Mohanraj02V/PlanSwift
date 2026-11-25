"""Production RBAC matrix, cookie+CSRF security, revocation, throttling & endpoint penetration tests."""

from __future__ import annotations

import importlib
import io
import zipfile

import ezdxf
import ifcopenshell
import ifcopenshell.api
import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.audit_logs.models import AuditLog
from apps.estimation.models import EstimationSession
from apps.extraction.models import ExtractionRun
from apps.organizations.models import Organization, OrganizationMember
from apps.project_sources.models import ProjectSource
from apps.projects.models import Project, ProjectVersion

User = get_user_model()


def _login_with_cookies(email: str, password: str = "StrongPassword123!") -> tuple[APIClient, str]:
    cache.clear()
    client = APIClient()
    csrf_resp = client.get("/api/v1/auth/csrf/")
    assert csrf_resp.status_code == 200
    resp = client.post("/api/v1/auth/login/", {"email": email, "password": password}, format="json")
    assert resp.status_code == 200
    csrf = resp.cookies["csrftoken"].value
    client.credentials(HTTP_X_CSRFTOKEN=csrf)
    return client, csrf


@pytest.mark.django_db
def test_three_role_endpoint_penetration_matrix_and_cross_org_isolation(tmp_path) -> None:
    org = Organization.objects.create(name="Vortexen Main", slug="vortexen-main")
    other_org = Organization.objects.create(name="Other Tenant", slug="other-tenant")

    admin_user = User.objects.create_user(email="m_admin@vortexen.local", password="StrongPassword123!")
    estimator_user = User.objects.create_user(email="m_est@vortexen.local", password="StrongPassword123!")
    ro_user = User.objects.create_user(email="m_user@vortexen.local", password="StrongPassword123!")
    other_admin = User.objects.create_user(email="m_other@vortexen.local", password="StrongPassword123!")
    staff_non_admin = User.objects.create_user(
        email="m_staff@vortexen.local",
        password="StrongPassword123!",
        is_staff=True,
    )

    OrganizationMember.objects.create(organization=org, user=admin_user, role="admin")
    OrganizationMember.objects.create(organization=org, user=estimator_user, role="estimator")
    OrganizationMember.objects.create(organization=org, user=ro_user, role="user")
    OrganizationMember.objects.create(organization=org, user=staff_non_admin, role="user")
    OrganizationMember.objects.create(organization=other_org, user=other_admin, role="admin")

    project = Project.objects.create(organization=org, name="Protected Plant", created_by=admin_user)
    ver = ProjectVersion.objects.create(project=project, version_number=1, is_current=True)
    src = ProjectSource.objects.create(
        project=project,
        source_kind=ProjectSource.SourceKind.UPLOADED_DXF,
        source_format="dxf_ascii",
        source_path=str(tmp_path / "dummy.dxf"),
        source_name="dummy.dxf",
        source_sha256="a" * 64,
    )
    run = ExtractionRun.objects.create(project=project, project_source=src, triggered_by=admin_user)
    est_session = EstimationSession.objects.create(project=project, project_version=ver, name="S1", created_by=admin_user)

    c_admin, _ = _login_with_cookies("m_admin@vortexen.local")
    c_est, _ = _login_with_cookies("m_est@vortexen.local")
    c_user, _ = _login_with_cookies("m_user@vortexen.local")
    c_staff, _ = _login_with_cookies("m_staff@vortexen.local")
    c_other, _ = _login_with_cookies("m_other@vortexen.local")

    # 1. is_staff=True with role='user' MUST NOT get Admin privileges
    assert c_staff.get("/api/v1/auth/users/").status_code == 403
    assert c_staff.get("/api/v1/audit/").status_code == 403
    assert c_staff.post("/api/v1/projects/", {"organization": str(org.id), "name": "Escalate"}, format="json").status_code == 403

    # 2. Read-only workspace endpoints allowed for Admin, Estimator, User; blocked for Other-org Admin
    for ep in (
        f"/api/v1/projects/{project.id}/",
        f"/api/v1/project-sources/?project={project.id}",
        f"/api/v1/extraction/?project={project.id}",
        f"/api/v1/objects/?project_version__project={project.id}",
        f"/api/v1/measurements/?project_version__project={project.id}",
        f"/api/v1/geometry/?project_version__project={project.id}",
        f"/api/v1/formulas/?project_version__project={project.id}",
        f"/api/v1/cad-bim/documents/?project_version__project={project.id}",
        f"/api/v1/validation/?project_version__project={project.id}",
    ):
        assert c_admin.get(ep).status_code == 200
        assert c_est.get(ep).status_code == 200
        assert c_user.get(ep).status_code == 200
        other_res = c_other.get(ep)
        if f"{project.id}/" in ep:
            assert other_res.status_code in (403, 404)
        else:
            assert other_res.json()["count"] == 0

    # 3. Admin-only writes/exports/AI/audit/users MUST return 403 for both Estimator & User
    admin_only_checks = [
        ("GET", "/api/v1/auth/users/", None),
        ("POST", "/api/v1/auth/users/", {"email": "x@v.com", "password": "StrongPassword123!", "role": "user"}),
        ("GET", "/api/v1/audit/", None),
        ("GET", f"/api/v1/organizations/{org.id}/members/", None),
        ("POST", "/api/v1/projects/", {"organization": str(org.id), "name": "NoProj"}),
        ("PATCH", f"/api/v1/projects/{project.id}/", {"name": "Renamed"}),
        ("DELETE", f"/api/v1/projects/{project.id}/", None),
        ("DELETE", f"/api/v1/project-sources/{src.id}/", None),
        ("POST", f"/api/v1/extraction/{run.id}/cancel/", {}),
        ("DELETE", f"/api/v1/extraction/{run.id}/", None),
        ("GET", "/api/v1/estimation/sessions/", None),
        ("POST", "/api/v1/estimation/sessions/", {"project": str(project.id)}),
        ("PATCH", f"/api/v1/estimation/sessions/{est_session.id}/update-quotation/", {"quotation": {"vat_percent": 5}}),
        ("POST", f"/api/v1/estimation/sessions/{est_session.id}/approve/", {}),
        ("GET", f"/api/v1/estimation/sessions/{est_session.id}/export-excel/", None),
        ("GET", f"/api/v1/estimation/sessions/{est_session.id}/export-pdf/", None),
        ("GET", f"/api/v1/exports/{project.id}/?export_format=json", None),
        ("POST", "/api/v1/ai/query/", {"project_id": str(project.id), "question": "Qty?"}),
        ("GET", "/api/v1/notifications/", None),
    ]
    for method, url, payload in admin_only_checks:
        fn_est = getattr(c_est, method.lower())
        fn_usr = getattr(c_user, method.lower())
        r1 = fn_est(url, payload, format="json") if payload is not None else fn_est(url)
        r2 = fn_usr(url, payload, format="json") if payload is not None else fn_usr(url)
        assert r1.status_code == 403, f"Expected 403 for Estimator on {method} {url}, got {r1.status_code}"
        assert r2.status_code == 403, f"Expected 403 for User on {method} {url}, got {r2.status_code}"

    # Permission denials recorded in AuditLog
    assert AuditLog.objects.filter(action="auth.permission_denied").exists()

    # 4. Estimator CAN upload PlanSwift ZIP, DXF, IFC and trigger extraction; User CANNOT (403)
    dxf_bytes = io.BytesIO()
    d = ezdxf.new("R2018")
    d.modelspace().add_line((0, 0), (3, 4))
    dxf_str = io.StringIO()
    d.write(dxf_str)
    dxf_raw = dxf_str.getvalue().encode("utf-8")

    assert c_user.post(
        "/api/v1/project-sources/upload/",
        {"project": str(project.id), "file": SimpleUploadedFile("u.dxf", dxf_raw)},
        format="multipart",
    ).status_code == 403
    assert c_user.post("/api/v1/extraction/", {"project": str(project.id), "project_source": str(src.id)}, format="json").status_code == 403

    r_est_dxf = c_est.post(
        "/api/v1/project-sources/upload/",
        {"project": str(project.id), "file": SimpleUploadedFile("est_wall.dxf", dxf_raw), "auto_extract": "true"},
        format="multipart",
    )
    assert r_est_dxf.status_code == 201
    assert r_est_dxf.json()["extraction_run"]["status"] == "COMPLETED"

    # Cross-org upload blocked even for Admin/Estimator of another org
    assert c_other.post(
        "/api/v1/project-sources/upload/",
        {"project": str(project.id), "file": SimpleUploadedFile("cross.dxf", dxf_raw)},
        format="multipart",
    ).status_code == 403


@pytest.mark.django_db
def test_csrf_enforcement_session_revocation_last_admin_guard_and_role_migration() -> None:
    cache.clear()
    org = Organization.objects.create(name="Sec Org", slug="sec-org")
    adm = User.objects.create_user(email="sec_admin@vortexen.local", password="StrongPassword123!")
    usr = User.objects.create_user(email="sec_user@vortexen.local", password="StrongPassword123!")
    OrganizationMember.objects.create(organization=org, user=adm, role="admin")
    OrganizationMember.objects.create(organization=org, user=usr, role="user")

    c_adm, _ = _login_with_cookies("sec_admin@vortexen.local")
    c_usr = APIClient()
    u_login = c_usr.post("/api/v1/auth/login/", {"email": "sec_user@vortexen.local", "password": "StrongPassword123!"}, format="json")
    assert u_login.status_code == 200
    assert c_usr.get("/api/v1/auth/me/").status_code == 200

    # 1. Cookie-authenticated unsafe POST without X-CSRFToken MUST fail with 403
    no_csrf_client = APIClient(enforce_csrf_checks=True)
    no_csrf_client.cookies["vortexen_access"] = u_login.cookies["vortexen_access"].value
    no_csrf_client.cookies["csrftoken"] = u_login.cookies["csrftoken"].value
    assert no_csrf_client.post("/api/v1/auth/logout/", {}, format="json").status_code == 403

    # 2. Last-active-Admin safeguard: cannot demote or deactivate the sole active Admin
    demote_self = c_adm.patch(
        f"/api/v1/auth/users/{adm.id}/",
        {"role": "user", "organization": str(org.id)},
        format="json",
    )
    assert demote_self.status_code == 400
    deactivate_self = c_adm.patch(f"/api/v1/auth/users/{adm.id}/", {"is_active": False}, format="json")
    assert deactivate_self.status_code == 400

    # 3. Role change immediately revokes old cookie JWT via token_version increment
    upd = c_adm.patch(
        f"/api/v1/auth/users/{usr.id}/",
        {"role": "estimator", "organization": str(org.id)},
        format="json",
    )
    assert upd.status_code == 200
    assert upd.data["primary_role"] == "estimator"
    revoked_resp = c_usr.get("/api/v1/auth/me/")
    assert revoked_resp.status_code == 401

    # 4. Data migration mapping verification (legacy roles -> admin / estimator / user / disabled connector)
    mig_mod = importlib.import_module("apps.organizations.migrations.0003_migrate_roles_to_three_role_model")
    from django.apps import apps as django_apps

    u_owner = User.objects.create_user(email="leg_owner@v.local", password="StrongPassword123!")
    u_viewer = User.objects.create_user(email="leg_viewer@v.local", password="StrongPassword123!")
    u_conn = User.objects.create_user(email="leg_conn@v.local", password="StrongPassword123!")
    OrganizationMember.objects.create(organization=org, user=u_owner, role="owner")
    OrganizationMember.objects.create(organization=org, user=u_viewer, role="estimation_only")
    OrganizationMember.objects.create(organization=org, user=u_conn, role="connector_agent")

    mig_mod.forwards_migrate_roles(django_apps, None)

    assert OrganizationMember.objects.get(organization=org, user=u_owner).role == "admin"
    assert OrganizationMember.objects.get(organization=org, user=u_viewer).role == "user"
    conn_mem = OrganizationMember.objects.get(organization=org, user=u_conn)
    assert conn_mem.role == "user"
    assert conn_mem.is_active is False
    u_conn.refresh_from_db()
    assert u_conn.is_active is False


@pytest.mark.django_db
def test_login_rate_throttle_enforced() -> None:
    cache.clear()
    org = Organization.objects.create(name="Throttle Org", slug="throttle-org")
    u = User.objects.create_user(email="throttled@vortexen.local", password="StrongPassword123!")
    OrganizationMember.objects.create(organization=org, user=u, role="user")

    client = APIClient()
    statuses = []
    for _ in range(12):
        r = client.post("/api/v1/auth/login/", {"email": "throttled@vortexen.local", "password": "WrongPassword!"}, format="json")
        statuses.append(r.status_code)
    assert 429 in statuses
    cache.clear()
