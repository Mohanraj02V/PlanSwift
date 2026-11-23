"""Structured SQL + Object Graph + Spatial Geometry first; Vector RAG strictly for remarks/docs."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from django.db.models import Q

from apps.formulas.models import Formula
from apps.geometry.models import GeometryFeature
from apps.knowledge_base.models import KnowledgeChunk
from apps.measurements.models import Measurement
from apps.object_hierarchy.models import ObjectRelationship
from apps.object_model.models import ProjectObject
from apps.projects.models import Project
from apps.remarks.models import Remark
from apps.retrieval.models import RetrievalRecord

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_GUID_RE = re.compile(r"\{?[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}?")
_STOP_WORDS = {
    "the", "and", "for", "with", "what", "how", "many", "are", "from", "this", "that",
    "show", "tell", "project", "in", "on", "of", "all", "is", "quantity", "quantities",
    "count", "total", "value", "values", "object", "objects", "measurement", "measurements",
    "item", "items", "list", "give", "find", "about", "explain", "summary",
}


def compute_term_weights(text: str) -> dict[str, float]:
    tokens = [t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1 and t not in _STOP_WORDS]
    counts = Counter(tokens)
    total = sum(counts.values()) or 1
    return {k: round(v / total, 6) for k, v in counts.items()}


def cosine_sim(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return (dot / (na * nb)) if (na > 0 and nb > 0) else 0.0


class HybridRetrievalService:
    """Strictly retrieves SQL/relational + graph + geometry records BEFORE semantic text retrieval."""

    def retrieve(self, project: Project, query: str, limit: int = 15) -> dict[str, Any]:
        version = project.versions.filter(is_current=True).first()
        if version is None:
            return {
                "project": {"native_guid": project.native_guid, "name": project.name, "total_objects": 0, "total_pages": 0},
                "objects": [],
                "relationships": [],
                "unresolved_formulas": [],
                "knowledge_snippets": [],
            }

        # 1. Exact SQL lookup (by GUID, class, or keyword)
        guid_matches = _GUID_RE.findall(query)
        keywords = [t for t in _TOKEN_RE.findall(query.lower()) if len(t) >= 2 and t not in _STOP_WORDS]

        base_qs = ProjectObject.objects.filter(project_version=version).prefetch_related("measurements", "child_sections", "formulas")
        if guid_matches:
            q_filter = Q()
            for g in guid_matches:
                braced = g.upper() if g.startswith("{") else f"{{{g.upper()}}}"
                q_filter |= Q(native_guid__iexact=braced) | Q(native_guid__iexact=g)
            matched_qs = base_qs.filter(q_filter)
        elif keywords:
            q_filter = Q()
            for kw in keywords[:8]:
                q_filter |= Q(name__icontains=kw) | Q(native_class__icontains=kw) | Q(division__icontains=kw)
            candidates = list(
                base_qs.filter(q_filter).exclude(depth__lte=1).order_by("is_measurement_section", "is_page", "depth", "name")[:250]
            )
            q_low = query.lower()

            def _score_obj(obj: ProjectObject) -> tuple[int, int, int, str]:
                n_low = (obj.name or "").lower()
                c_low = (obj.native_class or "").lower()
                exact_hit = 1 if (n_low and n_low in q_low) else 0
                kw_hits = sum(1 for kw in keywords if kw in n_low or kw in c_low)
                primary_takeoff = 1 if (not obj.is_page and not obj.is_measurement_section) else 0
                return (-exact_hit, -kw_hits, -primary_takeoff, obj.name or "")

            candidates.sort(key=_score_obj)
            matched_objs = candidates[:limit]
        else:
            matched_objs = list(base_qs.filter(is_page=False, is_measurement_section=False, depth__gte=2).order_by("name")[:limit])

        if not guid_matches and not keywords:
            pass
        elif guid_matches:
            matched_objs = list(matched_qs[:limit])
        obj_guids = [o.native_guid for o in matched_objs]

        # 2. Object Graph & Geometry counts
        rels = list(
            ObjectRelationship.objects.filter(project_version=version)
            .filter(Q(source_guid__in=obj_guids) | Q(target_guid__in=obj_guids))
            .values("relationship_type", "source_guid", "target_guid", "order_index")[:50]
        )
        geoms_by_parent = {}
        for g in GeometryFeature.objects.filter(project_version=version, parent_object_guid__in=obj_guids):
            geoms_by_parent.setdefault(g.parent_object_guid.upper(), []).append(
                {
                    "section_guid": g.section_guid,
                    "page_guid": g.page_guid,
                    "geometry_type": g.geometry_type,
                    "point_count": g.point_count,
                    "bbox": [g.bbox_min_x, g.bbox_min_y, g.bbox_max_x, g.bbox_max_y],
                }
            )

        # 3. Unresolved formulas summary
        unresolved_forms = list(
            Formula.objects.filter(project_version=version, evaluation_status="unresolved")
            .values("property_name", "raw_expression", "is_pascal_script")[:10]
        )

        # 4. Semantic similarity retrieval ONLY for Knowledge Base docs & Remarks (never replacing SQL quantities)
        q_weights = compute_term_weights(query)
        kb_scored = []
        for chunk in KnowledgeChunk.objects.filter(document__organization=project.organization).select_related("document"):
            sim = cosine_sim(q_weights, chunk.term_weights_json or compute_term_weights(chunk.text))
            if sim > 0:
                kb_scored.append((sim, {"title": chunk.document.title, "text": chunk.text[:400], "score": round(sim, 4)}))
        for rem in Remark.objects.filter(project_version=version, project_object__in=matched_objs):
            kb_scored.append((1.0, {"title": f"Remark ({rem.field_name})", "text": rem.text[:400], "score": 1.0}))
        kb_scored.sort(key=lambda x: x[0], reverse=True)
        kb_snippets = [item for _, item in kb_scored[:5]]

        serialized_objects = []
        for obj in matched_objs:
            meas_list = [
                {
                    "property_name": m.property_name,
                    "raw_formula": m.raw_formula,
                    "native_stored_value": m.native_stored_value,
                    "derived_quantity": m.derived_quantity,
                    "planswift_computed_quantity": m.planswift_computed_quantity,
                    "unit": m.unit,
                    "status": m.status,
                    "is_default_template_value": m.is_default_template_value,
                }
                for m in obj.measurements.all()
            ]
            qty_m = next((m for m in meas_list if m["property_name"] == "Qty"), None)
            if qty_m:
                if qty_m["planswift_computed_quantity"] is not None:
                    qty_prov = "computed_by_planswift"
                elif qty_m["derived_quantity"] is not None:
                    qty_prov = "derived"
                else:
                    qty_prov = qty_m["status"]
            else:
                qty_prov = obj.provenance
            serialized_objects.append(
                {
                    "native_guid": obj.native_guid,
                    "native_class": obj.native_class,
                    "name": obj.name,
                    "parent_guid": obj.parent_guid,
                    "section_count": obj.child_sections.count(),
                    "provenance": obj.provenance,
                    "quantity_provenance": qty_prov,
                    "measurements": meas_list,
                    "geometries": geoms_by_parent.get(obj.native_guid.upper(), []),
                }
            )

        RetrievalRecord.objects.create(
            project=project,
            query_text=query,
            sql_object_count=len(serialized_objects),
            graph_edge_count=len(rels),
            geometry_count=sum(len(v) for v in geoms_by_parent.values()),
            vector_snippet_count=len(kb_snippets),
            retrieved_guids=obj_guids,
        )

        return {
            "project": {
                "native_guid": project.native_guid,
                "name": project.name,
                "measurement_system": project.measurement_system,
                "total_objects": version.project_objects.count(),
                "total_pages": version.pages.count(),
            },
            "objects": serialized_objects,
            "relationships": rels,
            "unresolved_formulas": unresolved_forms,
            "knowledge_snippets": kb_snippets,
        }
