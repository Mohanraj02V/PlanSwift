"""Django REST API, multipart upload, tenant isolation, persistence & export E2E tests for DXF & IFC."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import ezdxf
import ifcopenshell
import ifcopenshell.api
import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.cad_bim.models import BIMElement, CADDocument, CADEntity, CADLayer
from apps.organizations.models import Organization, OrganizationMember

User = get_user_model()


@pytest.mark.django_db
def test_dxf_and_ifc_upload_persistence_cad_bim_apis_exports_and_rbac(tmp_path: Path) -> None:
    org = Organization.objects.create(name="CAD Org", slug="cad-org")
    other_org = Organization.objects.create(name="Other CAD Org", slug="other-cad-org")
    user = User.objects.create_user(email="cad@vortexen.local", password="StrongPassword123!")
    outsider = User.objects.create_user(email="outsider_cad@vortexen.local", password="StrongPassword123!")
    OrganizationMember.objects.create(organization=org, user=user, role="estimator")
    OrganizationMember.objects.create(organization=other_org, user=outsider, role="estimator")

    client = APIClient()
    client.force_authenticate(user=user)

    # 1. Create DXF & IFC test files
    dxf_path = tmp_path / "floor.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("A-WALL", color=1)
    msp = doc.modelspace()
    msp.add_line((0, 0), (12, 0), dxfattribs={"layer": "A-WALL"})
    msp.add_lwpolyline([(0, 0), (4, 0), (4, 5), (0, 5)], close=True, dxfattribs={"layer": "A-WALL"})
    doc.saveas(dxf_path)

    ifc_path = tmp_path / "building.ifc"
    model = ifcopenshell.file(schema="IFC4")
    proj = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="BIM API Test")
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "METERS"})
    ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body = ifcopenshell.api.run("context.add_context", model, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="L1")
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=proj, products=[storey])
    wall = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWall", name="Wall-API")
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[wall])
    rep = ifcopenshell.api.run("geometry.add_wall_representation", model, context=body, length=4.0, height=3.0, thickness=0.25)
    ifcopenshell.api.run("geometry.assign_representation", model, product=wall, representation=rep)
    qto = ifcopenshell.api.run("pset.add_qto", model, product=wall, name="Qto_WallBaseQuantities")
    ifcopenshell.api.run("pset.edit_qto", model, qto=qto, properties={"NetVolume": 2.95})
    model.write(str(ifc_path))

    # 2. Reject invalid file disguised as .dxf
    p_dxf = client.post("/api/v1/projects/", {"organization": str(org.id), "name": "DXF Proj"}, format="json").json()["id"]
    bad_upload = SimpleUploadedFile("bad.dxf", b"not a real dxf", content_type="application/octet-stream")
    r_bad = client.post("/api/v1/project-sources/upload/", {"project": p_dxf, "file": bad_upload}, format="multipart")
    assert r_bad.status_code == 400

    # 3. Upload real DXF & verify CADDocument / CADLayer / CADEntity + Export
    dxf_upload = SimpleUploadedFile("floor.dxf", dxf_path.read_bytes(), content_type="application/dxf")
    r_up_dxf = client.post(
        "/api/v1/project-sources/upload/",
        {"project": p_dxf, "file": dxf_upload, "auto_extract": "true"},
        format="multipart",
    )
    assert r_up_dxf.status_code == 201
    assert r_up_dxf.json()["source"]["source_format"] == "dxf_ascii"
    assert r_up_dxf.json()["extraction_run"]["status"] == "COMPLETED"
    assert CADDocument.objects.filter(project_version__project_id=p_dxf).count() == 1
    assert CADLayer.objects.filter(cad_document__project_version__project_id=p_dxf, name="A-WALL").exists()
    assert CADEntity.objects.filter(cad_document__project_version__project_id=p_dxf).count() == 2

    r_docs = client.get(f"/api/v1/cad-bim/documents/?project_version__project={p_dxf}")
    assert r_docs.status_code == 200 and r_docs.json()["count"] == 1
    r_ents = client.get(f"/api/v1/cad-bim/entities/?cad_document__project_version__project={p_dxf}")
    assert r_ents.status_code == 200 and r_ents.json()["count"] == 2

    r_exp = client.get(f"/api/v1/exports/{p_dxf}/?export_format=json")
    assert r_exp.status_code == 200
    exp_json = json.loads(r_exp.content.decode("utf-8"))
    assert exp_json["cad_document"]["source_format"] == "dxf_ascii"
    assert len(exp_json["cad_document"]["cad_entities"]) == 2

    # 4. Upload IFC with extract_geometry=true & verify BIMElement native Qto vs calculated 3D volume
    p_ifc = client.post("/api/v1/projects/", {"organization": str(org.id), "name": "IFC Proj"}, format="json").json()["id"]
    ifc_upload = SimpleUploadedFile("building.ifc", ifc_path.read_bytes(), content_type="application/octet-stream")
    r_up_ifc = client.post(
        "/api/v1/project-sources/upload/",
        {"project": p_ifc, "file": ifc_upload, "auto_extract": "true", "extract_geometry": "true"},
        format="multipart",
    )
    assert r_up_ifc.status_code == 201
    assert r_up_ifc.json()["source"]["source_format"] == "ifc_step"
    assert BIMElement.objects.filter(cad_document__project_version__project_id=p_ifc, ifc_class="IfcWall").count() == 1

    r_bims = client.get(f"/api/v1/cad-bim/elements/?cad_document__project_version__project={p_ifc}&ifc_class=IfcWall")
    assert r_bims.status_code == 200
    w_el = r_bims.json()["results"][0]
    assert w_el["geometry_summary_json"]["status"] == "calculated"
    assert abs(w_el["geometry_summary_json"]["volume"] - 3.0) < 1e-4
    assert abs(w_el["quantity_sets_json"][0]["quantities"][0]["raw_value"] - 2.95) < 1e-6

    # 5. Tenant isolation: outsider in other_org cannot read CAD/BIM documents or entities
    out_client = APIClient()
    out_client.force_authenticate(user=outsider)
    assert out_client.get(f"/api/v1/cad-bim/documents/?project_version__project={p_ifc}").json()["count"] == 0
    assert out_client.get(f"/api/v1/cad-bim/elements/?cad_document__project_version__project={p_ifc}").json()["count"] == 0


@pytest.mark.django_db
def test_cad_bim_zip_bundle_upload_extracts_all_dxf_and_ifc_files_and_rejects_zip_slip(tmp_path: Path) -> None:
    org = Organization.objects.create(name="Bundle Org", slug="bundle-org")
    user = User.objects.create_user(email="bundle@vortexen.local", password="StrongPassword123!")
    OrganizationMember.objects.create(organization=org, user=user, role="estimator")

    client = APIClient()
    client.force_authenticate(user=user)

    # Create two DXF files (ASCII + Binary) and one IFC file inside a starter-pack style ZIP
    dxf_ascii = tmp_path / "01_basic.dxf"
    d1 = ezdxf.new("R2018")
    d1.modelspace().add_line((0, 0), (10, 0))
    d1.saveas(dxf_ascii)

    dxf_bin = tmp_path / "02_binary.dxf"
    d2 = ezdxf.new("R2018")
    d2.modelspace().add_circle((2, 3), 1.5)
    d2.saveas(dxf_bin, fmt="bin")

    ifc_file = tmp_path / "03_model.ifc"
    m = ifcopenshell.file(schema="IFC4")
    proj_ent = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcProject", name="BundleBIM")
    wall = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcWall", name="BundleWall")
    ifcopenshell.api.run("aggregate.assign_object", m, relating_object=proj_ent, products=[wall])
    m.write(str(ifc_file))

    bundle_zip = tmp_path / "CAD_Test_Files_Starter_Pack.zip"
    with zipfile.ZipFile(bundle_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(dxf_ascii, "CAD_Test_Files/01_basic.dxf")
        zf.write(dxf_bin, "CAD_Test_Files/02_binary.dxf")
        zf.write(ifc_file, "CAD_Test_Files/03_model.ifc")
        zf.writestr("CAD_Test_Files/README.txt", "Sample CAD/BIM test pack")
        zf.writestr("CAD_Test_Files/manifest.json", '{"count": 3}')
        zf.writestr("__MACOSX/CAD_Test_Files/._01_basic.dxf", b"\x00\x05\x16\x07junk")

    proj_id = client.post("/api/v1/projects/", {"organization": str(org.id), "name": "CAD Bundle Proj"}, format="json").json()["id"]

    up_bundle = SimpleUploadedFile("CAD_Test_Files_Starter_Pack.zip", bundle_zip.read_bytes(), content_type="application/zip")
    r_ok = client.post(
        "/api/v1/project-sources/upload/",
        {"project": proj_id, "file": up_bundle, "auto_extract": "true"},
        format="multipart",
    )
    assert r_ok.status_code == 201
    body = r_ok.json()
    assert body["bundle"] is True
    assert body["processed_count"] == 3
    assert len(body["sources"]) == 3
    assert len(body["extraction_runs"]) == 3
    assert all(run["status"] == "COMPLETED" for run in body["extraction_runs"])

    r_docs = client.get(f"/api/v1/cad-bim/documents/?project_version__project={proj_id}")
    assert r_docs.status_code == 200
    assert r_docs.json()["count"] == 3
    doc_names = {d["source_name"] for d in r_docs.json()["results"]}
    assert doc_names == {"01_basic.dxf", "02_binary.dxf", "03_model.ifc"}

    # Verify Zip Slip traversal inside a CAD bundle is strictly rejected with 400
    evil_zip = tmp_path / "evil_bundle.zip"
    with zipfile.ZipFile(evil_zip, "w") as zf:
        zf.writestr("../escape.dxf", "0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nEOF\n")
    up_evil = SimpleUploadedFile("evil_bundle.zip", evil_zip.read_bytes(), content_type="application/zip")
    r_evil = client.post(
        "/api/v1/project-sources/upload/",
        {"project": proj_id, "file": up_evil, "auto_extract": "true"},
        format="multipart",
    )
    assert r_evil.status_code == 400
