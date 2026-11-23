from __future__ import annotations

import csv
import io
import json

from django.http import HttpResponse
from django.urls import path
from openpyxl import Workbook
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs.services import log_audit_event
from apps.exports.models import ExportJob
from apps.geometry.models import GeometryFeature
from apps.object_model.models import ProjectObject
from apps.permissions.rbac import get_user_org_ids
from apps.projects.models import Project


class ProjectExportView(APIView):
    """Stream JSON, JSONL, CSV, XLSX, GeoJSON, or Manifest directly from persisted canonical records."""

    def get(self, request, project_id):
        fmt = request.query_params.get("export_format", "json").lower()
        org_ids = get_user_org_ids(request.user)
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
        ExportJob.objects.create(project=project, project_version=version, export_format=fmt, requested_by=request.user, record_count=len(objs))
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
            payload = {
                "source_system": "PlanSwift",
                "project": {"id": str(project.id), "native_guid": project.native_guid, "name": project.name, "measurement_system": project.measurement_system},
                "objects": [
                    {
                        "native_guid": o.native_guid,
                        "native_class": o.native_class,
                        "name": o.name,
                        "parent_guid": o.parent_guid,
                        "depth": o.depth,
                        "provenance": o.provenance,
                        "properties": [{"guid": p.native_property_guid, "name": p.name, "class": p.property_class, "raw_value": p.raw_value} for p in o.properties.all()],
                        "measurements": [{"property": m.property_name, "raw_formula": m.raw_formula, "derived_quantity": m.derived_quantity, "unit": m.unit, "status": m.status} for m in o.measurements.all()],
                    }
                    for o in objs
                ],
            }
            resp = HttpResponse(json.dumps(payload, indent=2), content_type="application/json")
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
            writer.writerow(["project_guid", "native_guid", "native_class", "name", "raw_qty_formula", "derived_quantity", "unit", "provenance"])
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
                        qty_m.derived_quantity if qty_m else "",
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
            ws.append(["Project GUID", "Object GUID", "Class", "Name", "Raw Qty Formula", "Derived Qty", "Unit", "Provenance"])
            for o in objs:
                if o.is_page or o.is_measurement_section or o.depth < 2:
                    continue
                qty_m = next((m for m in o.measurements.all() if m.property_name == "Qty"), None)
                ws.append([project.native_guid, o.native_guid, o.native_class, o.name, qty_m.raw_formula if qty_m else "", qty_m.derived_quantity if qty_m else "", qty_m.unit if qty_m else "", qty_m.status if qty_m else o.provenance])
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
                        "properties": {"section_guid": gf.section_guid, "parent_object_guid": gf.parent_object_guid, "page_guid": gf.page_guid, "geometry_type": gf.geometry_type, "provenance": gf.provenance},
                    }
                )
            resp = HttpResponse(json.dumps({"type": "FeatureCollection", "features": features}, indent=2), content_type="application/geo+json")
            resp["Content-Disposition"] = f'attachment; filename="{project.name}_geometry.geojson"'
            return resp

        return Response({"detail": f"Unsupported export format '{fmt}'."}, status=status.HTTP_400_BAD_REQUEST)


urlpatterns = [path("<uuid:project_id>/", ProjectExportView.as_view(), name="project-export")]
