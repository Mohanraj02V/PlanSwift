from __future__ import annotations

import csv
import io
import json

from django.http import HttpResponse
from django.urls import path
from openpyxl import Workbook
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs.services import log_audit_event
from apps.cad_bim.models import CADDocument
from apps.cad_bim.views import (
    BIMElementSerializer,
    CADBlockSerializer,
    CADDocumentSerializer,
    CADEntitySerializer,
    CADLayerSerializer,
)
from apps.exports.models import ExportJob
from apps.formulas.models import Formula
from apps.geometry.models import GeometryFeature
from apps.object_hierarchy.models import ObjectRelationship
from apps.object_model.models import ProjectObject
from apps.permissions.rbac import IsAdminOnly, get_user_admin_org_ids
from apps.projects.models import Project, ProjectPage
from apps.validation.models import ValidationResult


class ProjectExportView(APIView):
    """Stream versioned JSON, JSONL, CSV, XLSX, or GeoJSON directly from persisted canonical records (Admin only)."""

    permission_classes = [permissions.IsAuthenticated, IsAdminOnly]

    def get(self, request, project_id):
        fmt = request.query_params.get("export_format", "json").lower()
        org_ids = get_user_admin_org_ids(request.user)
        project = Project.objects.filter(id=project_id, organization_id__in=org_ids).select_related("organization").first()
        if not project:
            return Response({"detail": "Project not found."}, status=status.HTTP_404_NOT_FOUND)
        version = project.versions.filter(is_current=True).first()
        if not version:
            return Response({"detail": "Project has no extracted version."}, status=status.HTTP_400_BAD_REQUEST)

        objs = list(
            ProjectObject.objects.filter(project_version=version)
            .prefetch_related("properties", "measurements", "formulas", "denotations", "remarks")
            .order_by("depth", "order_index", "name")
        )
        ExportJob.objects.create(
            project=project,
            project_version=version,
            export_format=fmt,
            requested_by=request.user,
            record_count=len(objs),
        )
        log_audit_event(
            action="project.exported",
            actor=request.user,
            organization=project.organization,
            request=request,
            resource_type="Project",
            resource_id=str(project.id),
            metadata={"format": fmt, "records": len(objs)},
        )

        if fmt == "json":
            latest_run = project.extraction_runs.filter(project_version=version).order_by("-created_at").first()
            latest_source = latest_run.project_source if latest_run else project.sources.order_by("-created_at").first()
            pages = list(ProjectPage.objects.filter(project_version=version).order_by("order_index", "name"))
            geoms = list(GeometryFeature.objects.filter(project_version=version).prefetch_related("points"))
            rels = list(ObjectRelationship.objects.filter(project_version=version))
            formulas = list(Formula.objects.filter(project_version=version).select_related("project_object"))
            val = ValidationResult.objects.filter(project_version=version).order_by("-created_at").first()
            cad_doc = CADDocument.objects.filter(project_version=version).first()

            unsupported_objs = [
                {
                    "native_guid": o.native_guid,
                    "native_class": o.native_class,
                    "native_type": o.native_type,
                    "name": o.name,
                    "parent_guid": o.parent_guid,
                    "status": o.provenance,
                }
                for o in objs
                if not o.is_known_class
            ]

            payload = {
                "schema_version": "1.0",
                "engine": {
                    "name": "Standalone PlanSwift ZIP Extraction Engine",
                    "version": "2.0.0",
                },
                "project": {
                    "id": project.native_guid or str(project.id),
                    "api_id": str(project.id),
                    "name": project.name,
                    "native_version": project.native_project_version or None,
                    "measurement_system": project.measurement_system or None,
                    "xml_encoding": project.xml_encoding,
                    "deterministic_digest_sha256": version.deterministic_digest_sha256,
                },
                "extraction": {
                    "status": latest_run.status.lower() if latest_run else "completed",
                    "source_filename": latest_source.source_name if latest_source else "",
                    "source_hash": version.source_sha256,
                    "warnings": list(latest_source.manifest_summary.get("warnings", [])) if latest_source else [],
                    "unsupported_objects": unsupported_objs,
                },
                "pages": [
                    {
                        "native_guid": p.native_guid,
                        "name": p.name,
                        "page_type": p.page_type,
                        "scale_units": p.scale_units,
                        "scale_x": p.scale_x,
                        "scale_y": p.scale_y,
                        "section_count": p.section_count,
                        "provenance": p.provenance,
                    }
                    for p in pages
                ],
                "takeoffs": [
                    {
                        "native_guid": o.native_guid,
                        "native_class": o.native_class,
                        "native_type": o.native_type,
                        "name": o.name,
                        "parent_guid": o.parent_guid,
                        "provenance": o.provenance,
                        "measurements": [
                            {
                                "property": m.property_name,
                                "raw_formula": m.raw_formula,
                                "calculated_quantity": m.calculated_quantity,
                                "reconstructed_quantity": m.reconstructed_quantity,
                                "unit": m.unit,
                                "status": m.status,
                            }
                            for m in o.measurements.all()
                        ],
                    }
                    for o in objs
                    if not o.is_page and not o.is_measurement_section and o.depth >= 2
                ],
                "objects": [
                    {
                        "native_guid": o.native_guid,
                        "native_class": o.native_class,
                        "native_type": o.native_type,
                        "name": o.name,
                        "parent_guid": o.parent_guid,
                        "depth": o.depth,
                        "is_known_class": o.is_known_class,
                        "provenance": o.provenance,
                        "properties": [
                            {
                                "guid": p.native_property_guid,
                                "name": p.name,
                                "class": p.property_class,
                                "raw_value": p.raw_value,
                                "units": p.units,
                                "provenance": p.provenance,
                            }
                            for p in o.properties.all()
                        ],
                    }
                    for o in objs
                ],
                "measurements": [
                    {
                        "object_guid": o.native_guid,
                        "object_name": o.name,
                        "property": m.property_name,
                        "measurement_type": m.measurement_type,
                        "raw_formula": m.raw_formula,
                        "native_stored_value": m.native_stored_value,
                        "calculated_quantity": m.calculated_quantity,
                        "reconstructed_quantity": m.reconstructed_quantity,
                        "derived_quantity": m.derived_quantity,
                        "unit": m.unit,
                        "normalized_quantity": m.normalized_quantity,
                        "normalized_unit": m.normalized_unit,
                        "status": m.status,
                    }
                    for o in objs
                    for m in o.measurements.all()
                ],
                "geometry": [
                    {
                        "section_guid": gf.section_guid,
                        "parent_object_guid": gf.parent_object_guid,
                        "page_guid": gf.page_guid,
                        "geometry_type": gf.geometry_type,
                        "coordinate_system": gf.coordinate_system,
                        "point_count": gf.point_count,
                        "is_calibrated": gf.is_calibrated,
                        "scale_x": gf.scale_x,
                        "scale_y": gf.scale_y,
                        "scale_unit": gf.scale_unit,
                        "calibrated_length": gf.calibrated_length,
                        "calibrated_area": gf.calibrated_area,
                        "calibrated_unit": gf.calibrated_unit,
                        "derived_polyline_length": gf.derived_polyline_length,
                        "derived_polygon_area": gf.derived_polygon_area,
                        "points": [{"order": pt.point_order, "x": pt.x, "y": pt.y, "normalized_x": pt.normalized_x, "normalized_y": pt.normalized_y} for pt in gf.points.all()],
                        "provenance": gf.provenance,
                    }
                    for gf in geoms
                ],
                "formulas": [
                    {
                        "object_guid": f.project_object.native_guid,
                        "property_name": f.property_name,
                        "raw_expression": f.raw_expression,
                        "evaluation_status": f.evaluation_status,
                        "calculated_value": f.calculated_value,
                        "calculated_numeric": f.calculated_numeric,
                        "calculation_reason": f.calculation_reason,
                    }
                    for f in formulas
                ],
                "calculations": [
                    {
                        "object_guid": f.project_object.native_guid,
                        "object_name": f.project_object.name,
                        "property_name": f.property_name,
                        "status": f.evaluation_status,
                        "calculated_value": f.calculated_value,
                        "calculated_numeric": f.calculated_numeric,
                        "unit": f.calculation_unit,
                        "reason": f.calculation_reason,
                        "inputs": f.calculation_inputs_json,
                    }
                    for f in formulas
                ],
                "relationships": [
                    {
                        "relationship_type": r.relationship_type,
                        "source_guid": r.source_guid,
                        "target_guid": r.target_guid,
                        "order_index": r.order_index,
                    }
                    for r in rels
                ],
                "validation": val.checks_json if val else [],
                **(
                    {
                        "cad_document": {
                            **CADDocumentSerializer(cad_doc).data,
                            "layers": CADLayerSerializer(cad_doc.layers.all(), many=True).data,
                            "blocks": CADBlockSerializer(cad_doc.blocks.all(), many=True).data,
                            "cad_entities": CADEntitySerializer(cad_doc.entities.all(), many=True).data,
                            "ifc_elements": BIMElementSerializer(cad_doc.bim_elements.all(), many=True).data,
                        }
                    }
                    if cad_doc is not None
                    else {}
                ),
            }
            resp = HttpResponse(json.dumps(payload, indent=2, ensure_ascii=False, default=str), content_type="application/json; charset=utf-8")
            resp["Content-Disposition"] = f'attachment; filename="{project.name}_canonical.json"'
            return resp

        if fmt == "jsonl":
            lines = [
                json.dumps(
                    {
                        "project_guid": project.native_guid,
                        "native_guid": o.native_guid,
                        "native_class": o.native_class,
                        "name": o.name,
                        "parent_guid": o.parent_guid,
                        "provenance": o.provenance,
                    }
                )
                for o in objs
            ]
            resp = HttpResponse("\n".join(lines), content_type="application/x-ndjson")
            resp["Content-Disposition"] = f'attachment; filename="{project.name}_objects.jsonl"'
            return resp

        if fmt == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(["project_guid", "native_guid", "native_class", "name", "raw_qty_formula", "calculated_quantity", "reconstructed_quantity", "unit", "provenance"])
            for o in objs:
                if o.is_page or o.is_measurement_section or o.depth < 2:
                    continue
                qty_m = next((m for m in o.measurements.all() if m.property_name == "Qty"), None)
                writer.writerow(
                    [
                        project.native_guid,
                        o.native_guid,
                        o.native_class,
                        o.name,
                        qty_m.raw_formula if qty_m else "",
                        qty_m.calculated_quantity if qty_m else "",
                        qty_m.reconstructed_quantity if qty_m else "",
                        qty_m.unit if qty_m else "",
                        qty_m.status if qty_m else o.provenance,
                    ]
                )
            resp = HttpResponse(buf.getvalue(), content_type="text/csv")
            resp["Content-Disposition"] = f'attachment; filename="{project.name}_takeoff.csv"'
            return resp

        if fmt == "xlsx":
            wb = Workbook()
            ws = wb.active
            ws.title = "Takeoff"
            ws.append(["Project GUID", "Object GUID", "Class", "Name", "Raw Qty Formula", "Calculated Qty", "Reconstructed Qty", "Unit", "Provenance"])
            for o in objs:
                if o.is_page or o.is_measurement_section or o.depth < 2:
                    continue
                qty_m = next((m for m in o.measurements.all() if m.property_name == "Qty"), None)
                ws.append([
                    project.native_guid,
                    o.native_guid,
                    o.native_class,
                    o.name,
                    qty_m.raw_formula if qty_m else "",
                    qty_m.calculated_quantity if qty_m else "",
                    qty_m.reconstructed_quantity if qty_m else "",
                    qty_m.unit if qty_m else "",
                    qty_m.status if qty_m else o.provenance,
                ])
            bio = io.BytesIO()
            wb.save(bio)
            resp = HttpResponse(bio.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            resp["Content-Disposition"] = f'attachment; filename="{project.name}_report.xlsx"'
            return resp

        if fmt == "geojson":
            features = []
            for gf in GeometryFeature.objects.filter(project_version=version).prefetch_related("points"):
                pts = [[pt.x, pt.y] for pt in gf.points.all()]
                if not pts:
                    continue
                features.append(
                    {
                        "type": "Feature",
                        "id": gf.section_guid,
                        "geometry": {"type": "Point", "coordinates": pts[0]} if len(pts) == 1 else {"type": "MultiPoint", "coordinates": pts},
                        "properties": {
                            "section_guid": gf.section_guid,
                            "parent_object_guid": gf.parent_object_guid,
                            "page_guid": gf.page_guid,
                            "geometry_type": gf.geometry_type,
                            "is_calibrated": gf.is_calibrated,
                            "calibrated_length": gf.calibrated_length,
                            "calibrated_area": gf.calibrated_area,
                            "calibrated_unit": gf.calibrated_unit,
                            "provenance": gf.provenance,
                        },
                    }
                )
            resp = HttpResponse(json.dumps({"type": "FeatureCollection", "features": features}, indent=2), content_type="application/geo+json")
            resp["Content-Disposition"] = f'attachment; filename="{project.name}_geometry.geojson"'
            return resp

        return Response({"detail": f"Unsupported export format '{fmt}'."}, status=status.HTTP_400_BAD_REQUEST)


urlpatterns = [path("<uuid:project_id>/", ProjectExportView.as_view(), name="project-export")]
