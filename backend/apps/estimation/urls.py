from __future__ import annotations

from datetime import datetime, timezone

from django.db import transaction
from django.http import HttpResponse
from django.urls import include, path
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from apps.audit_logs.services import log_audit_event
from apps.estimation.models import EstimationResult, EstimationSession
from apps.estimation.quotation_excel import generate_estimation_excel_workbook
from apps.estimation.quotation_pdf import default_quotation_metadata, generate_vortexen_quotation_pdf
from apps.estimation.services import approve_estimation_session, generate_estimation_session
from apps.permissions.rbac import IsAdminOnly, get_user_admin_org_ids, is_admin
from apps.projects.models import Project


class EstimationResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = EstimationResult
        fields = [
            "id",
            "object_guid",
            "object_name",
            "native_class",
            "category",
            "quantity",
            "unit",
            "unit_cost",
            "total_cost",
            "source_status",
            "formula_raw",
            "section_count",
            "notes",
        ]


class EstimationSessionSerializer(serializers.ModelSerializer):
    results = serializers.SerializerMethodField()
    quotation_defaults = serializers.SerializerMethodField()

    def get_results(self, obj: EstimationSession) -> list[dict]:
        filtered = [r for r in obj.results.all() if (r.native_class or "").strip().lower() != "folder"]
        return EstimationResultSerializer(filtered, many=True).data

    def get_quotation_defaults(self, obj: EstimationSession) -> dict:
        return default_quotation_metadata(obj)

    class Meta:
        model = EstimationSession
        fields = [
            "id",
            "project",
            "project_version",
            "name",
            "status",
            "summary_json",
            "quotation_defaults",
            "approved_at",
            "created_at",
            "results",
        ]
        read_only_fields = [
            "id",
            "project_version",
            "status",
            "summary_json",
            "quotation_defaults",
            "approved_at",
            "created_at",
            "results",
        ]


class EstimationSessionViewSet(viewsets.ModelViewSet):
    serializer_class = EstimationSessionSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOnly]
    filterset_fields = ["project", "status"]

    def get_queryset(self):
        org_ids = get_user_admin_org_ids(self.request.user)
        return (
            EstimationSession.objects.filter(project__organization_id__in=org_ids)
            .select_related("project", "project__organization")
            .prefetch_related("results")
        )

    def get_permissions(self):
        return [permissions.IsAuthenticated(), IsAdminOnly()]

    def create(self, request, *args, **kwargs):
        project_id = request.data.get("project")
        project = Project.objects.filter(id=project_id).select_related("organization").first()
        if not project:
            return Response({"detail": "Project not found."}, status=status.HTTP_404_NOT_FOUND)
        if not is_admin(request.user, project.organization):
            return Response({"detail": "Organization Admin privileges required."}, status=status.HTTP_403_FORBIDDEN)
        try:
            session = generate_estimation_session(project, request.user, session_name=request.data.get("name", ""))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        log_audit_event(
            action="estimation.generated",
            actor=request.user,
            organization=project.organization,
            request=request,
            resource_type="EstimationSession",
            resource_id=str(session.id),
        )
        return Response(EstimationSessionSerializer(session).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        session = self.get_object()
        approve_estimation_session(session, request.user)
        log_audit_event(
            action="estimation.approved",
            actor=request.user,
            organization=session.project.organization,
            request=request,
            resource_type="EstimationSession",
            resource_id=str(session.id),
        )
        return Response(EstimationSessionSerializer(session).data)

    @action(detail=True, methods=["patch", "post"], url_path="update-quotation")
    @transaction.atomic
    def update_quotation(self, request, pk=None):
        """Persist editable unit rates, opening sizes, and quotation header/terms metadata."""
        session = self.get_object()
        items_payload = request.data.get("items") or []
        by_id = {str(r.id): r for r in session.results.all()}
        updated_items = []
        for item in items_payload:
            row = by_id.get(str(item.get("id")))
            if row is None:
                continue
            if "object_name" in item and item["object_name"] is not None:
                row.object_name = str(item["object_name"])
            if "notes" in item and item["notes"] is not None:
                row.notes = str(item["notes"])
            if "quantity" in item and item["quantity"] is not None:
                row.quantity = float(item["quantity"])
            if "unit" in item and item["unit"] is not None:
                row.unit = str(item["unit"])
            if "unit_cost" in item:
                row.unit_cost = float(item["unit_cost"]) if item["unit_cost"] not in (None, "") else None
            if row.unit_cost is not None:
                row.total_cost = round(float(row.quantity or 0.0) * float(row.unit_cost), 2)
            elif "total_cost" in item:
                row.total_cost = float(item["total_cost"]) if item["total_cost"] not in (None, "") else None
            updated_items.append(row)

        if updated_items:
            EstimationResult.objects.bulk_update(
                updated_items, ["object_name", "notes", "quantity", "unit", "unit_cost", "total_cost"]
            )

        summary = dict(session.summary_json or {})
        if isinstance(request.data.get("quotation"), dict):
            q_meta = dict(summary.get("quotation") or {})
            q_meta.update(request.data["quotation"])
            summary["quotation"] = q_meta

        # Recompute commercial totals cleanly in summary_json (excluding Folder containers)
        subtotal = sum(
            float(r.total_cost if r.total_cost is not None else float(r.quantity or 0.0) * float(r.unit_cost or 0.0))
            for r in session.results.all()
            if (r.native_class or "").strip().lower() != "folder"
        )
        vat_pct = float((summary.get("quotation") or {}).get("vat_percent", 5.0))
        summary["subtotal"] = round(subtotal, 2)
        summary["vat_amount"] = round(subtotal * (vat_pct / 100.0), 3)
        summary["total_with_vat"] = round(subtotal + summary["vat_amount"], 2)
        session.summary_json = summary
        session.save(update_fields=["summary_json"])

        log_audit_event(
            action="estimation.updated",
            actor=request.user,
            organization=session.project.organization,
            request=request,
            resource_type="EstimationSession",
            resource_id=str(session.id),
            metadata={"updated_rows": len(updated_items), "total_with_vat": summary["total_with_vat"]},
        )
        session.refresh_from_db()
        return Response(EstimationSessionSerializer(session).data)

    @action(detail=True, methods=["get", "post"], url_path="export-excel")
    def export_excel(self, request, pk=None):
        """Download multi-sheet Excel BOQ + Takeoff workbook for this estimation session."""
        session = self.get_object()
        meta_override = request.data.get("quotation") if request.method == "POST" and isinstance(request.data, dict) else None
        xlsx_bytes = generate_estimation_excel_workbook(session, meta_override=meta_override)
        now_utc = datetime.now(timezone.utc)
        log_audit_event(
            action="estimation.excel_exported",
            actor=request.user,
            organization=session.project.organization,
            request=request,
            resource_type="EstimationSession",
            resource_id=str(session.id),
            metadata={
                "project_name": session.project.name,
                "exported_date": now_utc.strftime("%Y-%m-%d"),
                "exported_time": now_utc.strftime("%H:%M:%S UTC"),
            },
        )
        safe_proj = (session.project.name or "estimation").replace('"', "").replace(" ", "_")
        resp = HttpResponse(
            xlsx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = f'attachment; filename="{safe_proj}_Quotation_BOQ.xlsx"'
        return resp

    @action(detail=True, methods=["get", "post"], url_path="export-pdf")
    def export_pdf(self, request, pk=None):
        """Download formatted Vortexen Dynamics Commercial Quotation PDF with company logo."""
        session = self.get_object()
        meta_override = request.data.get("quotation") if request.method == "POST" and isinstance(request.data, dict) else None
        pdf_bytes = generate_vortexen_quotation_pdf(session, meta_override=meta_override)
        now_utc = datetime.now(timezone.utc)
        log_audit_event(
            action="estimation.pdf_quotation_exported",
            actor=request.user,
            organization=session.project.organization,
            request=request,
            resource_type="EstimationSession",
            resource_id=str(session.id),
            metadata={
                "project_name": session.project.name,
                "exported_date": now_utc.strftime("%Y-%m-%d"),
                "exported_time": now_utc.strftime("%H:%M:%S UTC"),
            },
        )
        safe_proj = (session.project.name or "quotation").replace('"', "").replace(" ", "_")
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{safe_proj}_Vortexen_Quotation.pdf"'
        return resp


router = DefaultRouter()
router.register("sessions", EstimationSessionViewSet, basename="estimation-session")

urlpatterns = [path("", include(router.urls))]
