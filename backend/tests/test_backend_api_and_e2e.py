"""Comprehensive Django backend API, RBAC, tenant-isolation, multipart ZIP upload, calculations, exports & E2E tests."""

from __future__ import annotations

import ast
import io
import json
import zipfile
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.audit_logs.models import AuditLog, ImmutableAuditError
from apps.geometry.models import GeometryFeature, MeasurementPoint
from apps.measurements.models import MeasurementSection
from apps.object_model.models import ObjectProperty, ProjectObject
from apps.organizations.models import Organization, OrganizationMember
from apps.projects.models import ProjectPage

User = get_user_model()
PROJECT_4_PATH = Path(__file__).resolve().parents[2] / "project 4.SwiftJob.zip"

SYNTHETIC_UPLOAD_XML = """<?xml version="1.0" encoding="Windows-1252"?>
<Item Class="Item" Name="UploadedJob" GUID="{10000000-0000-0000-0000-000000000001}">
  <Properties>
    <Property Class="Type" GUID="{10000000-0000-0000-0000-000000000002}" Name="Type">Job</Property>
    <Property Class="Text" GUID="{10000000-0000-0000-0000-000000000003}" Name="Measurement Type">Imperial</Property>
  </Properties>
  <Items>
    <Item Class="Page" Name="Sheet A1" GUID="{20000000-0000-0000-0000-000000000001}">
      <Properties>
        <Property Class="Type" GUID="{20000000-0000-0000-0000-000000000002}" Name="Type">.TIFF Page</Property>
        <Property Class="Number" GUID="{20000000-0000-0000-0000-000000000003}" Name="ScaleX">20</Property>
        <Property Class="Number" GUID="{20000000-0000-0000-0000-000000000004}" Name="ScaleY">20</Property>
        <Property Class="Text" GUID="{20000000-0000-0000-0000-000000000005}" Name="Scale Units">FT</Property>
      </Properties>
      <Items/>
    </Item>
    <Item Class="Folder" Name="Takeoff" GUID="{30000000-0000-0000-0000-000000000001}">
      <Properties/>
      <Items>
        <Item Class="Area" Name="Office Slab" GUID="{40000000-0000-0000-0000-000000000001}">
          <Properties>
            <Property Class="Type" GUID="{40000000-0000-0000-0000-000000000002}" Name="Type">Area</Property>
            <Property Class="Number" GUID="{40000000-0000-0000-0000-000000000003}" Name="Qty" units="SQ FT">[Takeoff]</Property>
          </Properties>
          <Items>
            <Item Class="Area Section" Name="Section 1" GUID="{41000000-0000-0000-0000-000000000001}">
              <Properties>
                <Property Class="Text" GUID="{41000000-0000-0000-0000-000000000002}" Name="PageGUID">{20000000-0000-0000-0000-000000000001}</Property>
                <Property Class="Text" GUID="{41000000-0000-0000-0000-000000000003}" Name="DigitizerData"><![CDATA[<Points><Point X="0" Y="0"/><Point X="200" Y="0"/><Point X="200" Y="400"/><Point X="0" Y="400"/></Points>]]></Property>
              </Properties>
              <Items/>
            </Item>
          </Items>
        </Item>
        <Item Class="UnsupportedVendorType" Name="Custom Item" GUID="{50000000-0000-0000-0000-000000000001}">
          <Properties>
            <Property Class="Text" GUID="{50000000-0000-0000-0000-000000000002}" Name="RawAttr">keep_me</Property>
          </Properties>
          <Items/>
        </Item>
      </Items>
    </Item>
  </Items>
</Item>"""


def _auth_client(email: str, password: str = "StrongPass123!") -> tuple[APIClient, User]:
    user = User.objects.create_user(email=email, password=password, full_name=email)
    client = APIClient()
    resp = client.post("/api/v1/auth/login/", {"email": email, "password": password}, format="json")
    assert resp.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")
    return client, user


def _make_zip_bytes(entries: dict[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for k, v in entries.items():
            zf.writestr(k, v)
    return buf.getvalue()


@pytest.mark.django_db
def test_auth_lifecycle_rbac_tenant_isolation_and_audit_immutability() -> None:
    client = APIClient()
    health = client.get("/api/v1/health/")
    assert health.status_code == 200
    assert health.data["status"] == "ok"

    # Legacy COM endpoint removed
    assert client.get("/api/v1/planswift/environment/").status_code == 404

    schema = client.get("/api/schema/")
    assert schema.status_code == 200

    reg = client.post(
        "/api/v1/auth/register/",
        {"email": "owner_a@vortexen.test", "password": "VeryStrongPassword123!", "full_name": "Owner A"},
        format="json",
    )
    assert reg.status_code == 201
    login = client.post(
        "/api/v1/auth/login/",
        {"email": "owner_a@vortexen.test", "password": "VeryStrongPassword123!"},
        format="json",
    )
    assert login.status_code == 200
    client_a = APIClient()
    client_a.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    ref = client_a.post("/api/v1/auth/refresh/", {"refresh": login.data["refresh"]}, format="json")
    assert ref.status_code == 200
    assert "access" in ref.data

    org_a_resp = client_a.post("/api/v1/organizations/", {"name": "Org Alpha", "slug": "org-alpha"}, format="json")
    assert org_a_resp.status_code == 201
    org_a_id = org_a_resp.data["id"]

    proj_a_resp = client_a.post("/api/v1/projects/", {"organization": org_a_id, "name": "Alpha Job"}, format="json")
    assert proj_a_resp.status_code == 201
    proj_a_id = proj_a_resp.data["id"]

    client_b, user_b = _auth_client("owner_b@vortexen.test")
    assert client_b.get("/api/v1/projects/").data["count"] == 0
    assert client_b.get(f"/api/v1/projects/{proj_a_id}/").status_code == 404
    assert client_b.post("/api/v1/projects/", {"organization": org_a_id, "name": "Hijack"}, format="json").status_code == 403

    org_a = Organization.objects.get(id=org_a_id)
    OrganizationMember.objects.create(organization=org_a, user=user_b, role=OrganizationMember.Role.VIEWER)
    assert client_b.get(f"/api/v1/projects/{proj_a_id}/").status_code == 200
    assert client_b.post("/api/v1/projects/", {"organization": org_a_id, "name": "Viewer Write"}, format="json").status_code == 403

    log_entry = AuditLog.objects.first()
    assert log_entry is not None
    log_entry.action = "tampered"
    with pytest.raises(ImmutableAuditError):
        log_entry.save()
    with pytest.raises(ImmutableAuditError):
        log_entry.delete()

    logout_resp = client_a.post("/api/v1/auth/logout/", {"refresh": ref.data["refresh"]}, format="json")
    assert logout_resp.status_code == 200
    assert client_a.post("/api/v1/auth/refresh/", {"refresh": ref.data["refresh"]}, format="json").status_code == 401


@pytest.mark.django_db
def test_multipart_zip_upload_standalone_calculations_unsupported_and_export(tmp_path: Path, settings) -> None:
    settings.EXTRACTION_WORK_DIR = tmp_path / "work"
    client, _ = _auth_client("uploader@vortexen.test")
    org_id = client.post("/api/v1/organizations/", {"name": "Upload Co", "slug": "upload-co"}, format="json").data["id"]
    proj_id = client.post("/api/v1/projects/", {"organization": org_id, "name": "Uploaded Test"}, format="json").data["id"]

    # 1. Reject non-ZIP / Zip-Slip archive safely
    bad_ext = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
    r_bad_ext = client.post("/api/v1/project-sources/upload/", {"project": proj_id, "file": bad_ext}, format="multipart")
    assert r_bad_ext.status_code == 400

    slip_zip = SimpleUploadedFile("slip.SwiftJob.zip", _make_zip_bytes({"../../evil.xml": "<Item/>"}), content_type="application/zip")
    r_slip = client.post("/api/v1/project-sources/upload/", {"project": proj_id, "file": slip_zip}, format="multipart")
    assert r_slip.status_code == 400

    # 2. Valid multipart PlanSwift ZIP upload with auto_extract=true
    good_bytes = _make_zip_bytes({"XMLData.XML": SYNTHETIC_UPLOAD_XML})
    good_file = SimpleUploadedFile("sample_upload.SwiftJob.zip", good_bytes, content_type="application/zip")
    up_resp = client.post(
        "/api/v1/project-sources/upload/",
        {"project": proj_id, "file": good_file, "auto_extract": "true"},
        format="multipart",
    )
    assert up_resp.status_code == 201
    src_data = up_resp.data["source"]
    run_data = up_resp.data["extraction_run"]

    # Security: internal filesystem source_path MUST NOT be leaked
    assert "source_path" not in src_data
    assert "source_path" not in (src_data.get("manifest_summary") or {})
    assert src_data["source_name"] == "sample_upload.SwiftJob.zip"
    assert run_data["status"] == "COMPLETED"

    # Extraction logs endpoint
    logs_resp = client.get(f"/api/v1/extraction/{run_data['id']}/logs/")
    assert logs_resp.status_code == 200
    assert len(logs_resp.data["events"]) >= 5

    # Calibrated geometry + calculation results API
    # 200x400 px at ScaleX=ScaleY=20 => 10x20 FT = 200 SQ FT
    calcs_resp = client.get(f"/api/v1/formulas/calculations/?project_version__project={proj_id}")
    assert calcs_resp.status_code == 200
    qty_calc = next(r for r in calcs_resp.data["results"] if r["property_name"] == "Qty")
    assert qty_calc["evaluation_status"] == "calculated"
    assert qty_calc["calculated_numeric"] == 200.0

    # Unsupported objects endpoint preserves custom unknown class raw
    unsup_resp = client.get(f"/api/v1/objects/unsupported/?project_version__project={proj_id}")
    assert unsup_resp.status_code == 200
    assert unsup_resp.data["count"] == 1
    assert unsup_resp.data["results"][0]["native_class"] == "UnsupportedVendorType"

    # Versioned structured JSON export
    exp_resp = client.get(f"/api/v1/exports/{proj_id}/?export_format=json")
    assert exp_resp.status_code == 200
    exported = json.loads(exp_resp.content.decode("utf-8"))
    assert exported["schema_version"] == "1.0"
    assert exported["engine"]["name"] == "Standalone PlanSwift ZIP Extraction Engine"
    assert len(exported["extraction"]["unsupported_objects"]) == 1
    assert exported["extraction"]["source_filename"] == "sample_upload.SwiftJob.zip"
    assert len(exported["calculations"]) >= 1


def _collect_imported_modules(py_path: Path) -> set[str]:
    tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


@pytest.mark.django_db
def test_ai_layer_has_zero_extraction_engine_imports() -> None:
    """Enforce architectural boundary: AI apps never import extraction_engine directly."""
    ai_dirs = ["ai_providers", "ai_prompts", "knowledge_base", "retrieval", "ai_agents", "ai_assistant"]
    backend_apps_dir = Path(__file__).resolve().parents[1] / "apps"
    for app_name in ai_dirs:
        for py_file in (backend_apps_dir / app_name).rglob("*.py"):
            mods = _collect_imported_modules(py_file)
            assert not any(m == "extraction_engine" or m.startswith("extraction_engine.") for m in mods), (
                f"Forbidden import of extraction_engine in {py_file}: {mods}"
            )


@pytest.mark.django_db
@pytest.mark.skipif(not PROJECT_4_PATH.exists(), reason="Real project 4.SwiftJob.zip not present.")
def test_end_to_end_real_project4_extraction_idempotency_estimation_exports_and_ai() -> None:
    client, user = _auth_client("lead_est@vortexen.test")
    org_resp = client.post("/api/v1/organizations/", {"name": "Marina Engineering", "slug": "marina-eng"}, format="json")
    org_id = org_resp.data["id"]

    proj_resp = client.post("/api/v1/projects/", {"organization": org_id, "name": "project 4"}, format="json")
    assert proj_resp.status_code == 201
    project_id = proj_resp.data["id"]

    bad_src = client.post("/api/v1/project-sources/", {"project": project_id, "source_path": "C:\\Windows\\win.ini"}, format="json")
    assert bad_src.status_code == 400

    src_resp = client.post(
        "/api/v1/project-sources/",
        {"project": project_id, "source_path": str(PROJECT_4_PATH)},
        format="json",
    )
    assert src_resp.status_code == 201
    assert "source_path" not in src_resp.data
    assert src_resp.data["container_format"] == "pkzip_swiftjob"
    assert src_resp.data["manifest_summary"]["total_entries"] == 325
    assert src_resp.data["manifest_summary"]["raster_entry_count"] == 324

    run1 = client.post("/api/v1/extraction/", {"project": project_id, "project_source": src_resp.data["id"]}, format="json")
    assert run1.status_code == 201
    assert run1.data["status"] == "COMPLETED"
    assert run1.data["summary"]["objects_extracted"] == 1461

    assert ProjectObject.objects.count() == 1461
    assert ObjectProperty.objects.count() == 28355
    assert ObjectProperty.objects.filter(name="").count() == 16
    assert ProjectPage.objects.count() == 324
    assert MeasurementSection.objects.count() == 1052
    assert MeasurementPoint.objects.count() == 4868

    # Idempotency check
    run2 = client.post("/api/v1/extraction/", {"project": project_id, "project_source": src_resp.data["id"]}, format="json")
    assert run2.status_code == 201
    assert run2.data["status"] == "COMPLETED"
    assert ProjectObject.objects.count() == 1461
    assert ObjectProperty.objects.count() == 28355

    duct_obj = ProjectObject.objects.get(name="Duct 350x200mm")
    obj_detail = client.get(f"/api/v1/objects/{duct_obj.id}/")
    assert obj_detail.status_code == 200
    assert len(obj_detail.data["properties"]) > 30

    geom_list = client.get(f"/api/v1/geometry/?parent_object_guid={duct_obj.native_guid}")
    assert geom_list.status_code == 200
    assert geom_list.data["count"] == 49

    val_resp = client.get("/api/v1/validation/")
    assert val_resp.status_code == 200
    assert val_resp.data["results"][0]["overall_verified_accuracy_pct"] == 100.0

    # Standalone calculated estimation
    est_resp = client.post("/api/v1/estimation/sessions/", {"project": project_id, "name": "MEP Check"}, format="json")
    assert est_resp.status_code == 201
    assert est_resp.data["summary_json"]["total_items"] == 79
    duct_row = next(r for r in est_resp.data["results"] if r["object_name"] == "Duct 350x200mm")
    assert duct_row["quantity"] == 286.0
    assert duct_row["source_status"] == "calculated"
    assert duct_row["formula_raw"] == "[Takeoff]"

    for fmt in ("json", "jsonl", "csv", "xlsx", "geojson"):
        exp = client.get(f"/api/v1/exports/{project_id}/?export_format={fmt}")
        assert exp.status_code == 200
        assert len(exp.content) > 100

    # Standalone formula calculation & AI query verification (NO COM required!)
    ai_resp = client.post(
        "/api/v1/ai/query/",
        {"project_id": project_id, "question": "What is the quantity of Duct 350x200mm?"},
        format="json",
    )
    assert ai_resp.status_code == 200
    assert ai_resp.data["inference_used"] is False
    assert ai_resp.data["data_status"] == "calculated"
    assert "286" in ai_resp.data["answer"]

    rec_resp = client.get("/api/v1/reconciliation/")
    assert rec_resp.status_code == 200
    latest_rec = rec_resp.data["results"][0]
    assert latest_rec["mode"] == "standalone_zip_verified"
    assert latest_rec["com_available"] is False
