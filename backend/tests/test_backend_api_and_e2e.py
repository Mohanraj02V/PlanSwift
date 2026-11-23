"""Comprehensive Django backend API, RBAC, tenant-isolation, idempotent extraction, AI, and E2E tests."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.audit_logs.models import AuditLog, ImmutableAuditError
from apps.geometry.models import GeometryFeature, MeasurementPoint
from apps.measurements.models import MeasurementSection
from apps.object_model.models import ObjectProperty, ProjectObject
from apps.organizations.models import Organization, OrganizationMember
from apps.projects.models import ProjectPage

User = get_user_model()
PROJECT_4_PATH = Path(__file__).resolve().parents[2] / "project 4.SwiftJob.zip"


def _auth_client(email: str, password: str = "StrongPass123!") -> tuple[APIClient, User]:
    user = User.objects.create_user(email=email, password=password, full_name=email)
    client = APIClient()
    resp = client.post("/api/v1/auth/login/", {"email": email, "password": password}, format="json")
    assert resp.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")
    return client, user


@pytest.mark.django_db
def test_auth_lifecycle_rbac_tenant_isolation_and_audit_immutability() -> None:
    client = APIClient()
    health = client.get("/api/v1/health/")
    assert health.status_code == 200
    assert health.data["status"] == "ok"

    schema = client.get("/api/schema/")
    assert schema.status_code == 200

    # Register & login Org A owner
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

    # Refresh rotation & logout blacklist
    ref = client_a.post("/api/v1/auth/refresh/", {"refresh": login.data["refresh"]}, format="json")
    assert ref.status_code == 200
    assert "access" in ref.data

    # Create Org A & Project A
    org_a_resp = client_a.post("/api/v1/organizations/", {"name": "Org Alpha", "slug": "org-alpha"}, format="json")
    assert org_a_resp.status_code == 201
    org_a_id = org_a_resp.data["id"]

    proj_a_resp = client_a.post("/api/v1/projects/", {"organization": org_a_id, "name": "Alpha Job"}, format="json")
    assert proj_a_resp.status_code == 201
    proj_a_id = proj_a_resp.data["id"]

    # Create Org B user & verify strict cross-tenant isolation
    client_b, user_b = _auth_client("owner_b@vortexen.test")
    assert client_b.get("/api/v1/projects/").data["count"] == 0
    assert client_b.get(f"/api/v1/projects/{proj_a_id}/").status_code == 404
    assert client_b.post("/api/v1/projects/", {"organization": org_a_id, "name": "Hijack"}, format="json").status_code == 403

    # Add user_b as VIEWER in Org A -> can read, CANNOT mutate or trigger extraction
    org_a = Organization.objects.get(id=org_a_id)
    OrganizationMember.objects.create(organization=org_a, user=user_b, role=OrganizationMember.Role.VIEWER)
    assert client_b.get(f"/api/v1/projects/{proj_a_id}/").status_code == 200
    assert client_b.post("/api/v1/projects/", {"organization": org_a_id, "name": "Viewer Write"}, format="json").status_code == 403

    # Verify AuditLog immutability
    log_entry = AuditLog.objects.first()
    assert log_entry is not None
    log_entry.action = "tampered"
    with pytest.raises(ImmutableAuditError):
        log_entry.save()
    with pytest.raises(ImmutableAuditError):
        log_entry.delete()

    # Logout blacklists token
    logout_resp = client_a.post("/api/v1/auth/logout/", {"refresh": ref.data["refresh"]}, format="json")
    assert logout_resp.status_code == 200
    assert client_a.post("/api/v1/auth/refresh/", {"refresh": ref.data["refresh"]}, format="json").status_code == 401


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


def test_extraction_engine_has_zero_image_ocr_or_llm_imports() -> None:
    """Enforce rule: extraction_engine never uses OCR, raster image libs, vision models, or LLMs."""
    forbidden_prefixes = (
        "PIL",
        "cv2",
        "pytesseract",
        "easyocr",
        "ultralytics",
        "torch",
        "tensorflow",
        "openai",
        "anthropic",
        "google.genai",
        "apps.ai_",
    )
    engine_dir = Path(__file__).resolve().parents[2] / "extraction_engine"
    for py_file in engine_dir.rglob("*.py"):
        mods = _collect_imported_modules(py_file)
        for mod in mods:
            assert not any(mod == fp or mod.startswith(f"{fp}.") or mod.startswith(fp) for fp in forbidden_prefixes), (
                f"Forbidden raster/OCR/LLM import '{mod}' in {py_file}"
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

    # Reject outside ALLOWED_SOURCE_ROOTS
    bad_src = client.post("/api/v1/project-sources/", {"project": project_id, "source_path": "C:\\Windows\\win.ini"}, format="json")
    assert bad_src.status_code == 400

    # Register real 556 MB project 4.SwiftJob.zip
    src_resp = client.post(
        "/api/v1/project-sources/",
        {"project": project_id, "source_path": str(PROJECT_4_PATH)},
        format="json",
    )
    assert src_resp.status_code == 201
    assert src_resp.data["container_format"] == "pkzip_swiftjob"
    assert src_resp.data["manifest_summary"]["total_entries"] == 325
    assert src_resp.data["manifest_summary"]["raster_entry_count"] == 324

    # Trigger extraction run #1
    run1 = client.post("/api/v1/extraction/", {"project": project_id, "project_source": src_resp.data["id"]}, format="json")
    assert run1.status_code == 201
    assert run1.data["status"] == "COMPLETED"
    assert run1.data["summary"]["objects_extracted"] == 1461

    # Assert exact canonical DB counts
    assert ProjectObject.objects.count() == 1461
    assert ObjectProperty.objects.count() == 28355
    assert ObjectProperty.objects.filter(name="").count() == 16
    assert ProjectPage.objects.count() == 324
    assert MeasurementSection.objects.count() == 1052
    assert MeasurementPoint.objects.count() == 4868

    # Trigger extraction run #2 (Idempotency check — ZERO duplicates created!)
    run2 = client.post("/api/v1/extraction/", {"project": project_id, "project_source": src_resp.data["id"]}, format="json")
    assert run2.status_code == 201
    assert run2.data["status"] == "COMPLETED"
    assert ProjectObject.objects.count() == 1461
    assert ObjectProperty.objects.count() == 28355
    assert ProjectPage.objects.count() == 324
    assert MeasurementSection.objects.count() == 1052
    assert MeasurementPoint.objects.count() == 4868

    # Hierarchy, Geometry, Measurements, Formulas, Validation API checks
    tree = client.get(f"/api/v1/hierarchy/tree/{project_id}/?max_depth=2")
    assert tree.status_code == 200
    assert len(tree.data["nodes"]) > 5

    duct_obj = ProjectObject.objects.get(name="Duct 350x200mm")
    obj_detail = client.get(f"/api/v1/objects/{duct_obj.id}/")
    assert obj_detail.status_code == 200
    assert obj_detail.data["native_class"] == "Count"
    assert len(obj_detail.data["properties"]) > 30

    geom_list = client.get(f"/api/v1/geometry/?parent_object_guid={duct_obj.native_guid}")
    assert geom_list.status_code == 200
    assert geom_list.data["count"] == 49
    first_geom_id = geom_list.data["results"][0]["id"]
    geom_detail = client.get(f"/api/v1/geometry/{first_geom_id}/")
    assert geom_detail.status_code == 200
    assert len(geom_detail.data["points"]) >= 1

    val_resp = client.get("/api/v1/validation/")
    assert val_resp.status_code == 200
    assert val_resp.data["results"][0]["overall_verified_accuracy_pct"] == 100.0

    # Estimation generation + approval
    est_resp = client.post("/api/v1/estimation/sessions/", {"project": project_id, "name": "MEP Check"}, format="json")
    assert est_resp.status_code == 201
    assert est_resp.data["summary_json"]["total_items"] == 79
    duct_row = next(r for r in est_resp.data["results"] if r["object_name"] == "Duct 350x200mm")
    assert duct_row["quantity"] == 286.0
    assert duct_row["source_status"] == "derived"
    assert duct_row["formula_raw"] == "[Takeoff]"

    app_resp = client.post(f"/api/v1/estimation/sessions/{est_resp.data['id']}/approve/")
    assert app_resp.status_code == 200
    assert app_resp.data["status"] == "approved"

    # Exports (JSON, CSV, GeoJSON, XLSX)
    for fmt in ("json", "jsonl", "csv", "xlsx", "geojson"):
        exp = client.get(f"/api/v1/exports/{project_id}/?export_format={fmt}")
        assert exp.status_code == 200
        assert len(exp.content) > 100

    # Add Knowledge Base doc + AI Estimation query with strict provenance check
    kb = client.post(
        "/api/v1/retrieval/knowledge/",
        {
            "organization": org_id,
            "title": "MEP Duct Takeoff Standard",
            "category": "HVAC",
            "content": "Rectangular duct items (Duct 350x200mm) measured via Count sections reflect diffuser or fitting counts unless Linear sections are used.",
        },
        format="json",
    )
    assert kb.status_code == 201

    ai_resp = client.post(
        "/api/v1/ai/query/",
        {"project_id": project_id, "question": "What is the quantity of Duct 350x200mm?"},
        format="json",
    )
    assert ai_resp.status_code == 200
    assert ai_resp.data["inference_used"] is False
    assert ai_resp.data["data_status"] == "derived"
    assert any(s["object_guid"] == duct_obj.native_guid for s in ai_resp.data["source_objects"])
    assert "286" in ai_resp.data["answer"]

    # COM Connector ingest + auto-reconciliation check (including PageWidth & Qty)
    first_page = ProjectPage.objects.first()
    assert first_page is not None
    com_ingest = client.post(
        "/api/v1/planswift/ingest/",
        {
            "project_id": project_id,
            "agent_name": "TestWin64Agent",
            "payload": {
                "source_system": "PlanSwiftCOM",
                "planswift_version": "11.0",
                "prog_id": "PlanSwift9.PlanSwift",
                "objects": [
                    {
                        "native_guid": duct_obj.native_guid,
                        "native_class": "Count",
                        "name": "Duct 350x200mm",
                        "properties": {
                            "Qty": {"formula": "[Takeoff]", "result": "286"},
                        },
                    },
                    {
                        "native_guid": first_page.native_guid,
                        "native_class": "Page",
                        "name": first_page.name,
                        "properties": {
                            "PageWidth": {"formula": "[!PageWidth]", "result": "11906"},
                            "PageHeight": {"formula": "[!PageHeight]", "result": "8419"},
                        },
                    },
                ],
            },
        },
        format="json",
    )
    assert com_ingest.status_code == 201
    assert com_ingest.data["reconciliation"]["matched_objects"] == 2
    assert com_ingest.data["reconciliation"]["formulas_updated"] >= 3
    assert com_ingest.data["reconciliation"]["measurements_updated"] == 1

    # Immediate check BEFORE re-running extraction: PageWidth & Qty already reconciled!
    pw_formula = duct_obj.project_version.formulas.get(project_object__native_guid=first_page.native_guid, property_name="PageWidth")
    assert pw_formula.raw_expression == "[!PageWidth]"
    assert pw_formula.planswift_evaluated_value == "11906"
    assert pw_formula.evaluation_status == "computed_by_planswift"

    duct_qty_now = duct_obj.measurements.get(property_name="Qty")
    assert duct_qty_now.planswift_computed_quantity == 286.0
    assert duct_qty_now.status == "computed_by_planswift"

    # Re-run extraction to ensure COM reconciled values remain idempotent without duplicating rows
    run3 = client.post("/api/v1/extraction/", {"project": project_id, "project_source": src_resp.data["id"]}, format="json")
    assert run3.status_code == 201
    assert run3.data["status"] == "COMPLETED"
    assert ProjectObject.objects.count() == 1461

    rec_resp = client.get("/api/v1/reconciliation/")
    assert rec_resp.status_code == 200
    latest_rec = rec_resp.data["results"][0]
    assert latest_rec["com_available"] is True
    assert latest_rec["matched_objects"] == 2

    duct_qty = duct_obj.measurements.get(property_name="Qty")
    assert duct_qty.planswift_computed_quantity == 286.0
    assert duct_qty.status == "computed_by_planswift"
    assert duct_qty.raw_formula == "[Takeoff]"
