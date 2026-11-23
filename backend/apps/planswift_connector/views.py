from __future__ import annotations

import hashlib
import json

from django.conf import settings
from django.db import transaction
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs.services import log_audit_event
from apps.formulas.models import Formula, FormulaDependency
from apps.measurements.models import Measurement
from apps.object_model.models import ProjectObject
from apps.organizations.models import OrganizationMember
from apps.permissions.rbac import IsOrgEditor, get_user_org_ids
from apps.planswift_connector.models import ConnectorAgent, ConnectorSyncBatch
from apps.projects.models import Project
from apps.reconciliation.models import ReconciliationReport
from extraction_engine.adapters.planswift_version_adapters.version_detector import detect_planswift_environment
from extraction_engine.normalizers.identity_normalizer import canonical_guid_key
from extraction_engine.parsers.formula_parser import _OUTER_TOKEN_RE, _classify_token


_COM_NON_FORMULA_PROPS = frozenset(
    {"Form Layout", "Circle", "Diamond", "Plus", "Square", "Triangle", "Symbol Shape", "Symbol Icon"}
)


def _is_real_com_formula(prop_name: str, raw_formula: str) -> bool:
    """Return True when a COM property carries a genuine PlanSwift formula rather than XML/shape metadata."""
    if not prop_name or prop_name in _COM_NON_FORMULA_PROPS:
        return False
    stripped = (raw_formula or "").strip()
    if not stripped:
        return False
    if stripped.startswith("<") or "TokenGuid=" in stripped:
        return False
    return ("[" in stripped) or (":=" in stripped and "\n" in stripped)


class ConnectorIngestSerializer(serializers.Serializer):
    project_id = serializers.UUIDField()
    agent_name = serializers.CharField(max_length=128, default="VortexenPlanSwiftConnector")
    machine_name = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    auto_reconcile = serializers.BooleanField(default=True)
    payload = serializers.DictField()


class PlanSwiftEnvironmentView(APIView):
    def get(self, request):
        env = detect_planswift_environment()
        return Response(env.__dict__)


class PlanSwiftIngestView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if getattr(settings, "CONNECTOR_REQUIRE_TLS", False) and not request.is_secure():
            return Response({"detail": "TLS (HTTPS) is required for connector ingest."}, status=status.HTTP_403_FORBIDDEN)

        expected_tok = getattr(settings, "CONNECTOR_SHARED_TOKEN", "")
        if expected_tok:
            provided = request.META.get("HTTP_X_CONNECTOR_TOKEN", "")
            if provided and provided != expected_tok:
                return Response({"detail": "Invalid X-Connector-Token."}, status=status.HTTP_403_FORBIDDEN)

        ser = ConnectorIngestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        project = Project.objects.filter(id=ser.validated_data["project_id"]).select_related("organization").first()
        if not project:
            return Response({"detail": "Project not found."}, status=status.HTTP_404_NOT_FOUND)

        if not OrganizationMember.objects.filter(
            organization=project.organization,
            user=request.user,
            is_active=True,
            role__in=[*IsOrgEditor.ALLOWED_ROLES, OrganizationMember.Role.CONNECTOR_AGENT],
        ).exists():
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        raw_payload = ser.validated_data["payload"]
        if raw_payload.get("source_system") != "PlanSwiftCOM":
            return Response({"detail": "Payload source_system must be 'PlanSwiftCOM'."}, status=status.HTTP_400_BAD_REQUEST)

        canonical_str = json.dumps(raw_payload, sort_keys=True)
        sha = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

        agent, _ = ConnectorAgent.objects.get_or_create(
            organization=project.organization,
            name=ser.validated_data["agent_name"],
            defaults={
                "machine_name": ser.validated_data["machine_name"],
                "prog_id": raw_payload.get("prog_id", ""),
                "planswift_version": raw_payload.get("planswift_version", ""),
            },
        )

        batch = ConnectorSyncBatch.objects.create(
            project=project,
            agent=agent,
            prog_id=raw_payload.get("prog_id", "unknown"),
            planswift_version=raw_payload.get("planswift_version", "unknown"),
            payload_sha256=sha,
            object_count=len(raw_payload.get("objects", [])),
            raw_payload=raw_payload,
            warnings=raw_payload.get("warnings", []),
        )

        reconciliation_stats = None
        if ser.validated_data["auto_reconcile"]:
            reconciliation_stats = _reconcile_batch_into_current_version(project, raw_payload)

        log_audit_event(
            action="planswift_connector.ingested",
            actor=request.user,
            organization=project.organization,
            request=request,
            resource_type="ConnectorSyncBatch",
            resource_id=str(batch.id),
            metadata={"object_count": batch.object_count, "prog_id": batch.prog_id, "reconciliation": reconciliation_stats},
        )
        return Response(
            {
                "batch_id": str(batch.id),
                "payload_sha256": sha,
                "object_count": batch.object_count,
                "prog_id": batch.prog_id,
                "reconciliation": reconciliation_stats,
            },
            status=status.HTTP_201_CREATED,
        )


@transaction.atomic
def _reconcile_batch_into_current_version(project: Project, raw_payload: dict) -> dict | None:
    version = project.versions.filter(is_current=True).first()
    if version is None or version.project_objects.count() == 0:
        return None

    com_objects = raw_payload.get("objects", [])
    com_by_guid = {
        canonical_guid_key(o.get("native_guid", "")): o
        for o in com_objects
        if o.get("native_guid")
    }
    if not com_by_guid:
        return {"matched_objects": 0, "formulas_updated": 0, "measurements_updated": 0}

    db_objs = list(ProjectObject.objects.filter(project_version=version))
    db_by_guid = {canonical_guid_key(o.native_guid): o for o in db_objs}

    matched = 0
    formulas_updated = 0
    measurements_updated = 0

    matched_obj_ids = []
    matched_pairs: list[tuple[ProjectObject, dict]] = []
    for gkey, db_obj in db_by_guid.items():
        if gkey in com_by_guid:
            matched += 1
            matched_obj_ids.append(db_obj.id)
            matched_pairs.append((db_obj, com_by_guid[gkey]))

    existing_keys = set(
        Formula.objects.filter(project_version=version).values_list("formula_key", flat=True)
    )
    existing_pairs: set[tuple] = set()
    formulas_to_update = []
    for f in Formula.objects.filter(project_version=version, project_object_id__in=matched_obj_ids).select_related("project_object"):
        existing_pairs.add((f.project_object_id, f.property_name))
        com_obj = com_by_guid.get(canonical_guid_key(f.project_object.native_guid))
        if not com_obj:
            continue
        com_prop = (com_obj.get("properties") or {}).get(f.property_name)
        if com_prop and com_prop.get("result") not in (None, ""):
            f.planswift_evaluated_value = str(com_prop["result"])
            f.evaluation_status = "computed_by_planswift"
            formulas_to_update.append(f)
            formulas_updated += 1

    if formulas_to_update:
        Formula.objects.bulk_update(formulas_to_update, ["planswift_evaluated_value", "evaluation_status"], batch_size=500)

    new_formulas: list[Formula] = []
    new_deps: list[FormulaDependency] = []
    for db_obj, com_obj in matched_pairs:
        for prop_name, com_prop in (com_obj.get("properties") or {}).items():
            if (db_obj.id, prop_name) in existing_pairs:
                continue
            raw_formula = (com_prop or {}).get("formula") or ""
            if not _is_real_com_formula(prop_name, raw_formula):
                continue
            fkey = f"{db_obj.native_guid}:COM:{prop_name}"[:255]
            if fkey in existing_keys:
                continue

            result_val = (com_prop or {}).get("result")
            has_eval = result_val not in (None, "")
            is_pascal = ":=" in raw_formula and "\n" in raw_formula

            tokens: list[str] = []
            parsed_deps = []
            for match in _OUTER_TOKEN_RE.finditer(raw_formula):
                inner = match.group(1)
                tok = f"[{inner}]"
                tokens.append(tok)
                parsed_deps.append(_classify_token(tok, inner))

            formula_obj = Formula(
                project_version=version,
                project_object=db_obj,
                formula_key=fkey,
                property_guid=((com_prop or {}).get("property_guid") or "COM")[:64],
                property_name=prop_name[:255],
                raw_expression=raw_formula,
                is_pascal_script=is_pascal,
                unresolved_references=[] if has_eval else tokens,
                evaluation_status="computed_by_planswift" if has_eval else "unresolved",
                planswift_evaluated_value=str(result_val) if has_eval else "",
            )
            new_formulas.append(formula_obj)
            for dep in parsed_deps:
                new_deps.append(
                    FormulaDependency(
                        formula=formula_obj,
                        raw_token=(dep.raw_token or "")[:255],
                        reference_kind=(dep.reference_kind or "property_reference")[:64],
                        target_property=(dep.target_property or "")[:255],
                        target_object_guid=(dep.target_object_guid or "")[:64],
                        resolved=dep.resolved,
                    )
                )
            existing_pairs.add((db_obj.id, prop_name))
            existing_keys.add(fkey)

    if new_formulas:
        Formula.objects.bulk_create(new_formulas, batch_size=1000)
    if new_deps:
        FormulaDependency.objects.bulk_create(new_deps, batch_size=2000)
    evaluated_created = sum(1 for nf in new_formulas if nf.evaluation_status == "computed_by_planswift")

    meas_to_update = []
    for m in Measurement.objects.filter(project_version=version, project_object_id__in=matched_obj_ids, property_name="Qty").select_related("project_object"):
        com_obj = com_by_guid.get(canonical_guid_key(m.project_object.native_guid))
        if not com_obj:
            continue
        qty_prop = (com_obj.get("properties") or {}).get("Qty")
        if qty_prop and qty_prop.get("result") not in (None, ""):
            try:
                m.planswift_computed_quantity = float(qty_prop["result"])
                m.status = "computed_by_planswift"
                meas_to_update.append(m)
                measurements_updated += 1
            except (TypeError, ValueError):
                pass

    if meas_to_update:
        Measurement.objects.bulk_update(meas_to_update, ["planswift_computed_quantity", "status"], batch_size=500)

    total_applied = formulas_updated + measurements_updated + evaluated_created
    is_partial_pages = raw_payload.get("extraction_scope") == "pages_only"
    pkg_only = max(0, len(db_by_guid) - matched)
    com_only = max(0, len(com_by_guid) - matched)
    stats = {
        "mode": "package_and_com_reconciled",
        "com_available": True,
        "matched_objects": matched,
        "package_only_objects": pkg_only,
        "com_only_objects": com_only,
        "formulas_updated": formulas_updated,
        "formulas_created_from_com": len(new_formulas),
        "measurements_updated": measurements_updated,
        "computed_values_applied": total_applied,
    }
    if is_partial_pages:
        existing_report = (
            ReconciliationReport.objects.filter(project_version=version, mode="package_and_com_reconciled")
            .order_by("-created_at")
            .first()
        )
        if existing_report is not None:
            existing_report.computed_values_applied += total_applied
            summary = dict(existing_report.summary_json or {})
            summary["page_dimensions_updated"] = formulas_updated
            summary["computed_values_applied"] = existing_report.computed_values_applied
            existing_report.summary_json = summary
            existing_report.save(update_fields=["computed_values_applied", "summary_json"])
            return {**stats, "extraction_scope": "pages_only", "merged_into_report": str(existing_report.id)}

    ReconciliationReport.objects.create(
        project_version=version,
        mode="package_and_com_reconciled",
        com_available=True,
        matched_objects=matched,
        package_only_objects=pkg_only,
        com_only_objects=com_only,
        computed_values_applied=total_applied,
        duplicate_guid_count=0,
        summary_json=stats,
    )
    return stats


class ConnectorSyncListView(APIView):
    def get(self, request):
        org_ids = get_user_org_ids(request.user)
        batches = ConnectorSyncBatch.objects.filter(project__organization_id__in=org_ids).values(
            "id", "project_id", "prog_id", "planswift_version", "object_count", "payload_sha256", "received_at"
        )[:50]
        return Response(list(batches))
