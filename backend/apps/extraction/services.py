"""Extraction orchestration & idempotent standalone canonical ORM persistence service."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.assemblies.models import Assembly
from apps.audit_logs.services import log_audit_event
from apps.cad_bim.models import BIMElement, CADBlock, CADDocument, CADEntity, CADLayer
from apps.classifications.models import ObjectClassification
from apps.components.models import AssemblyComponent
from apps.denotations.models import Denotation
from apps.extraction.models import ExtractionError, ExtractionEvent, ExtractionRun
from apps.formulas.models import CalculatedValue, Formula, FormulaDependency
from apps.geometry.models import GeometryFeature, MeasurementPoint
from apps.measurements.models import Measurement, MeasurementSection
from apps.notifications.models import Notification
from apps.object_hierarchy.models import ObjectGroup, ObjectRelationship
from apps.object_model.models import (
    ObjectProperty,
    ObjectType,
    ProjectObject,
    PropertyDefinition,
    ProvenanceRecord,
)
from apps.project_sources.models import ProjectSource
from apps.projects.models import ProjectPage, ProjectVersion
from apps.reconciliation.models import ReconciliationReport
from apps.remarks.models import Remark
from apps.source_inventory.models import SourceFile
from apps.validation.models import ValidationResult
from extraction_engine.core.extraction_context import ExtractionConfig, ExtractionContext, ExtractionStage
from extraction_engine.core.extraction_result import CanonicalProject, ExtractionReport
from extraction_engine.pipeline import ExtractionPipeline


class ExtractionOrchestrationService:
    """Runs standalone ExtractionPipeline on a registered/uploaded ProjectSource and persists canonical records."""

    @staticmethod
    def _build_engine_config(extraction_options: dict[str, Any] | None = None) -> ExtractionConfig:
        opts = extraction_options or {}
        allowed_roots = tuple(Path(r) for r in settings.ALLOWED_SOURCE_ROOTS) + (
            Path(settings.EXTRACTION_WORK_DIR).resolve(),
        )
        checkpoint_dir = Path(settings.EXTRACTION_WORK_DIR) / "checkpoints"
        default_threads = int(getattr(settings, "IFC_GEOMETRY_THREADS", 2))
        req_threads = int(opts.get("ifc_geometry_threads", default_threads))
        return ExtractionConfig(
            allowed_source_roots=allowed_roots,
            work_dir=Path(settings.EXTRACTION_WORK_DIR),
            checkpoint_dir=checkpoint_dir,
            max_upload_bytes=int(getattr(settings, "MAX_UPLOAD_ZIP_BYTES", 1024 * 1024 * 1024)),
            max_archive_entries=int(getattr(settings, "EXTRACTION_MAX_ARCHIVE_ENTRIES", 10_000)),
            max_uncompressed_bytes=int(getattr(settings, "EXTRACTION_MAX_UNCOMPRESSED_BYTES", 5 * 1024 * 1024 * 1024)),
            max_compression_ratio=float(getattr(settings, "EXTRACTION_MAX_COMPRESSION_RATIO", 100.0)),
            max_xml_depth=int(getattr(settings, "EXTRACTION_MAX_XML_DEPTH", 64)),
            max_xml_nodes=int(getattr(settings, "EXTRACTION_MAX_XML_NODES", 2_000_000)),
            max_parse_seconds=float(getattr(settings, "EXTRACTION_MAX_PARSE_SECONDS", 300.0)),
            dxf_max_file_bytes=int(getattr(settings, "MAX_UPLOAD_DXF_BYTES", 512 * 1024 * 1024)),
            dxf_max_entities=int(getattr(settings, "DXF_MAX_ENTITIES", 500_000)),
            dxf_max_block_depth=int(getattr(settings, "DXF_MAX_BLOCK_DEPTH", 32)),
            ifc_max_file_bytes=int(getattr(settings, "MAX_UPLOAD_IFC_BYTES", 1024 * 1024 * 1024)),
            ifc_extract_geometry=bool(opts.get("ifc_extract_geometry", getattr(settings, "IFC_EXTRACT_GEOMETRY_DEFAULT", False))),
            ifc_geometry_threads=max(1, min(req_threads, 4)),
            ifc_geometry_timeout_seconds=float(getattr(settings, "IFC_GEOMETRY_TIMEOUT_SECONDS", 120.0)),
        )

    @staticmethod
    def execute_run(run_id: str) -> ExtractionRun:
        run = (
            ExtractionRun.objects.select_related("project", "project__organization", "project_source", "triggered_by")
            .get(id=run_id)
        )
        project = run.project
        source = run.project_source
        if source is None:
            run.status = ExtractionRun.Status.FAILED
            run.summary = {"error": "No ProjectSource attached to ExtractionRun."}
            run.save(update_fields=["status", "summary"])
            return run

        run.started_at = timezone.now()
        run.status = ExtractionRun.Status.VALIDATING_ARCHIVE
        run.progress_pct = 5
        run.save(update_fields=["started_at", "status", "progress_pct"])

        cancel_evt = threading.Event()
        cfg = ExtractionOrchestrationService._build_engine_config(run.extraction_options)

        def on_progress(stage: ExtractionStage, pct: int, message: str) -> None:
            run.refresh_from_db(fields=["cancel_requested"])
            if run.cancel_requested:
                cancel_evt.set()
            ExtractionRun.objects.filter(id=run.id).update(status=stage.value, progress_pct=pct)
            ExtractionEvent.objects.create(
                extraction_run=run,
                stage=stage.value,
                progress_pct=pct,
                message=message,
            )

        ctx = ExtractionContext(
            source_path=Path(source.source_path),
            config=cfg,
            run_id=str(run.id),
            cancel_event=cancel_evt,
            progress_callback=on_progress,
        )

        pipeline = ExtractionPipeline(config=cfg)
        try:
            canonical_project, report = pipeline.run(Path(source.source_path), ctx=ctx)
        except Exception as exc:
            is_cancel = cancel_evt.is_set()
            run.status = ExtractionRun.Status.CANCELLED if is_cancel else ExtractionRun.Status.FAILED
            run.finished_at = timezone.now()
            run.summary = {"error": str(exc)}
            run.save(update_fields=["status", "finished_at", "summary"])
            ExtractionError.objects.create(
                extraction_run=run,
                stage=ctx.current_stage.value,
                code=type(exc).__name__,
                message=str(exc),
                recoverable=is_cancel,
            )
            return run

        ExtractionRun.objects.filter(id=run.id).update(status=ExtractionStage.PERSISTING.value, progress_pct=98)
        ExtractionEvent.objects.create(
            extraction_run=run,
            stage=ExtractionStage.PERSISTING.value,
            progress_pct=98,
            message=f"Persisting {len(canonical_project.objects)} canonical objects to database.",
        )

        version = ExtractionOrchestrationService._persist_canonical_project(
            run=run,
            source=source,
            canonical_project=canonical_project,
            report=report,
        )

        run.project_version = version
        run.status = ExtractionRun.Status.COMPLETED
        run.progress_pct = 100
        run.adapter_used = report.adapter_used
        run.parser_version = report.parser_version
        run.source_sha256 = source.source_sha256
        run.deterministic_digest_sha256 = canonical_project.deterministic_digest_sha256 or ""
        run.duration_seconds = report.duration_seconds
        run.peak_memory_mb = report.peak_memory_mb
        run.peak_rss_mb = getattr(report, "peak_rss_mb", 0.0)
        run.finished_at = timezone.now()
        cad_doc = getattr(canonical_project, "cad_document", None)
        run.summary = {
            "source_system": canonical_project.source_system,
            "objects_extracted": len(canonical_project.objects),
            "pages_extracted": len(canonical_project.pages),
            "relationships_extracted": len(canonical_project.relationships),
            "discovered_classes": canonical_project.discovered_classes,
            "unsupported_objects_count": len(canonical_project.unsupported_objects),
            "formulas_calculated": report.validation.formulas_calculated if report.validation else 0,
            "validation_accuracy_pct": report.validation.overall_verified_accuracy_pct if report.validation else None,
            **(
                {
                    "cad_source_format": cad_doc.source_format,
                    "entities_extracted": len(cad_doc.cad_entities),
                    "layers_extracted": len(cad_doc.layers),
                    "blocks_extracted": len(cad_doc.blocks),
                    "ifc_elements_extracted": len(cad_doc.ifc_elements),
                    "stage_timings": report.stage_timings,
                }
                if cad_doc is not None
                else {}
            ),
        }
        run.save()

        Notification.objects.create(
            organization=project.organization,
            recipient=run.triggered_by,
            level="success",
            title=f"Extraction completed: {project.name}",
            message=f"Extracted {len(canonical_project.objects)} objects across {len(canonical_project.pages)} pages.",
            metadata={"run_id": str(run.id), "project_id": str(project.id)},
        )
        log_audit_event(
            action="extraction.completed",
            actor=run.triggered_by,
            organization=project.organization,
            resource_type="ExtractionRun",
            resource_id=str(run.id),
            metadata=run.summary,
        )
        return run

    @staticmethod
    @transaction.atomic
    def _persist_canonical_project(
        run: ExtractionRun,
        source: ProjectSource,
        canonical_project: CanonicalProject,
        report: ExtractionReport,
    ) -> ProjectVersion:
        project = run.project
        digest = canonical_project.deterministic_digest_sha256 or ""

        # Update project-level PlanSwift metadata
        project.native_guid = canonical_project.native_guid
        if not project.name or project.name.lower().startswith("untitled"):
            project.name = canonical_project.name
        project.description = canonical_project.description
        project.notes = canonical_project.notes
        project.project_type = canonical_project.project_type
        project.source_format = canonical_project.source_system.lower()
        project.native_project_version = canonical_project.native_project_version or ""
        project.measurement_system = canonical_project.measurement_system
        project.excel_workbook_connected = canonical_project.excel_workbook_connected
        project.xml_encoding = canonical_project.xml_encoding
        project.native_timestamp_raw = canonical_project.timestamp_raw
        project.save()

        cad_doc = getattr(canonical_project, "cad_document", None)
        ext_opts_key = cad_doc.extraction_options if cad_doc is not None else {}

        # Idempotency check: reuse existing version with same source+digest+engine_version+options
        existing_version = (
            ProjectVersion.objects.filter(
                project=project,
                source_sha256=source.source_sha256,
                deterministic_digest_sha256=digest,
            )
            .order_by("-version_number")
            .first()
        )
        if (
            existing_version is not None
            and existing_version.project_objects.count() == len(canonical_project.objects)
            and existing_version.metadata.get("engine_version") == canonical_project.engine_version
            and existing_version.metadata.get("extraction_options", {}) == ext_opts_key
        ):
            ProjectVersion.objects.filter(project=project).exclude(id=existing_version.id).update(is_current=False)
            if not existing_version.is_current:
                existing_version.is_current = True
                existing_version.save(update_fields=["is_current"])
            ExtractionOrchestrationService._persist_validation_and_reconciliation(
                version=existing_version, run=run, report=report
            )
            return existing_version

        last_ver = ProjectVersion.objects.filter(project=project).order_by("-version_number").first()
        if (
            last_ver
            and last_ver.project_objects.count() == 0
            and (not last_ver.source_sha256 or last_ver.source_sha256 == source.source_sha256)
        ):
            version = last_ver
            version.source_sha256 = source.source_sha256
            version.deterministic_digest_sha256 = digest
            version.is_current = True
            version.metadata = {
                "discovered_classes": canonical_project.discovered_classes,
                "unsupported_classes": canonical_project.unsupported_classes,
                "engine_version": canonical_project.engine_version,
                "extraction_options": ext_opts_key,
            }
            version.save(update_fields=["source_sha256", "deterministic_digest_sha256", "is_current", "metadata"])
        else:
            ProjectVersion.objects.filter(project=project).update(is_current=False)
            next_num = (last_ver.version_number + 1) if last_ver else 1
            version = ProjectVersion.objects.create(
                project=project,
                version_number=next_num,
                source_sha256=source.source_sha256,
                deterministic_digest_sha256=digest,
                is_current=True,
                metadata={
                    "discovered_classes": canonical_project.discovered_classes,
                    "unsupported_classes": canonical_project.unsupported_classes,
                    "engine_version": canonical_project.engine_version,
                    "extraction_options": ext_opts_key,
                },
            )

        if canonical_project.source_manifest is not None:
            for entry in canonical_project.source_manifest.entries:
                if entry.linked_page_guid:
                    SourceFile.objects.filter(project_source=source, relative_path=entry.relative_path).update(
                        linked_page_guid=entry.linked_page_guid
                    )

        # 1. Pages
        page_models = [
            ProjectPage(
                project_version=version,
                native_guid=pg.native_guid,
                name=pg.name,
                native_class=pg.native_class,
                page_type=pg.page_type,
                order_index=pg.order_index,
                image_property_guid=pg.image_property_guid or "",
                tiff_archive_path=pg.tiff_archive_path or "",
                tiff_size_bytes=pg.tiff_size_bytes,
                scale_units=pg.scale_units or "",
                scale_x=pg.scale_x,
                scale_y=pg.scale_y,
                page_width_raw=pg.page_width_raw or "",
                page_height_raw=pg.page_height_raw or "",
                numeric_scale_factor=pg.numeric_scale_factor,
                rotation_degrees=pg.rotation_degrees,
                section_count=pg.section_count,
                created_by_raw=pg.created_by or "",
                timestamp_raw=pg.timestamp_raw or "",
                provenance=pg.provenance.value,
            )
            for pg in canonical_project.pages
        ]
        ProjectPage.objects.bulk_create(page_models, batch_size=500)
        page_by_guid = {p.native_guid.upper(): p for p in ProjectPage.objects.filter(project_version=version)}

        # 2. ObjectTypes & PropertyDefinitions
        ObjectType.objects.bulk_create(
            [
                ObjectType(
                    project_version=version,
                    native_class=cls_name,
                    object_count=cnt,
                    is_known_class=cls_name not in canonical_project.unsupported_classes,
                )
                for cls_name, cnt in canonical_project.discovered_classes.items()
            ],
            batch_size=500,
        )

        prop_def_counts: dict[tuple[str, str, str], int] = {}
        for obj in canonical_project.objects:
            for p in obj.properties:
                key = (p.name, p.property_class, p.group or "")
                prop_def_counts[key] = prop_def_counts.get(key, 0) + 1
        PropertyDefinition.objects.bulk_create(
            [
                PropertyDefinition(
                    project_version=version,
                    name=k[0],
                    property_class=k[1],
                    group=k[2],
                    occurrence_count=cnt,
                )
                for k, cnt in prop_def_counts.items()
            ],
            batch_size=500,
            ignore_conflicts=True,
        )

        # 3. ProjectObjects
        obj_models = [
            ProjectObject(
                project_version=version,
                native_guid=o.native_guid,
                native_class=o.native_class,
                native_type=o.native_type,
                name=o.name,
                parent_guid=o.parent_guid,
                root_path=o.root_path,
                depth=o.depth,
                order_index=o.order_index,
                is_known_class=o.is_known_class,
                is_measurement_section=o.is_measurement_section,
                is_page=o.is_page,
                page_guid=o.page_guid,
                group_id=o.group_id,
                division=o.division or "",
                subdivision=o.subdivision or "",
                phase=o.phase or "",
                cost_code=o.cost_code or "",
                location=o.location or "",
                zone=o.zone or "",
                created_by_raw=o.created_by or "",
                timestamp_raw=o.timestamp_raw or "",
                provenance=o.provenance.value,
                raw_attributes=o.raw_attributes,
            )
            for o in canonical_project.objects
        ]
        ProjectObject.objects.bulk_create(obj_models, batch_size=500)
        obj_by_guid = {o.native_guid.upper(): o for o in ProjectObject.objects.filter(project_version=version)}

        # 4. ObjectProperties, Denotations, Remarks, Classifications, Groups
        prop_models: list[ObjectProperty] = []
        denotation_models: list[Denotation] = []
        remark_models: list[Remark] = []
        classification_models: list[ObjectClassification] = []
        group_counts: dict[str, int] = {}

        for co in canonical_project.objects:
            db_obj = obj_by_guid[co.native_guid.upper()]
            if co.group_id:
                group_counts[co.group_id] = group_counts.get(co.group_id, 0) + 1
            if co.division or co.subdivision or co.cost_code:
                classification_models.append(
                    ObjectClassification(
                        project_version=version,
                        project_object=db_obj,
                        family=co.native_class,
                        category=co.native_type,
                        division=co.division or "",
                        subdivision=co.subdivision or "",
                        cost_code=co.cost_code or "",
                        provenance="native",
                    )
                )
            for p in co.properties:
                prop_models.append(
                    ObjectProperty(
                        project_object=db_obj,
                        native_property_guid=p.native_property_guid,
                        name=p.name,
                        property_class=p.property_class,
                        raw_value=p.raw_value,
                        parsed_value_json=p.parsed_value,
                        normalized_value_json=p.normalized_value,
                        normalized_unit=p.normalized_unit or "",
                        units=p.units or "",
                        input_units=p.input_units or "",
                        group=p.group or "",
                        order_index=p.order_index,
                        decimal_places=p.decimal_places or "",
                        parse_formula=p.parse_formula or "",
                        expression_flag=p.expression_flag or "",
                        is_formula=p.is_formula,
                        is_expression_script=p.is_expression_script,
                        is_dynamic_page_order=p.is_dynamic_page_order,
                        dynamic_page_guid=p.dynamic_page_guid or "",
                        has_image_data=p.has_image_data,
                        image_data_length=p.image_data_length,
                        image_data_sha256=p.image_data_sha256 or "",
                        attributes_json=p.attributes,
                        source_location=p.source_location or "",
                        provenance=p.provenance.value,
                        normalization_provenance=p.normalization_provenance.value if p.normalization_provenance else "",
                    )
                )
            for d in co.denotations:
                denotation_models.append(
                    Denotation(
                        project_version=version,
                        project_object=db_obj,
                        denotation_key=d.denotation_key,
                        kind=d.kind,
                        label=d.label,
                        value=d.value,
                        metadata=d.metadata,
                        provenance=d.provenance.value,
                    )
                )
            for r in co.remarks:
                remark_models.append(
                    Remark(
                        project_version=version,
                        project_object=db_obj,
                        remark_key=r.remark_key,
                        field_name=r.field_name,
                        text=r.text,
                        provenance=r.provenance.value,
                    )
                )

        ObjectProperty.objects.bulk_create(prop_models, batch_size=1000)
        Denotation.objects.bulk_create(denotation_models, batch_size=500, ignore_conflicts=True)
        Remark.objects.bulk_create(remark_models, batch_size=500, ignore_conflicts=True)
        ObjectClassification.objects.bulk_create(classification_models, batch_size=500)
        ObjectGroup.objects.bulk_create(
            [
                ObjectGroup(project_version=version, group_id=gid, name=gid, member_count=cnt)
                for gid, cnt in group_counts.items()
            ],
            batch_size=500,
        )

        # 5. MeasurementSections
        sec_models = []
        for co in canonical_project.objects:
            db_obj = obj_by_guid[co.native_guid.upper()]
            for s in co.sections:
                sec_models.append(
                    MeasurementSection(
                        project_version=version,
                        project_object=db_obj,
                        parent_object=obj_by_guid.get(s.parent_object_guid.upper()),
                        native_guid=s.native_guid,
                        native_class=s.native_class,
                        name=s.name,
                        order_index=s.order_index,
                        z_order=s.z_order,
                        page_guid=s.page_guid,
                        page=page_by_guid.get(s.page_guid.upper()) if s.page_guid else None,
                        page_name_formula=s.page_name_formula or "",
                        visible=s.visible,
                        box_mode=s.box_mode or "",
                        point_count=s.point_count,
                        derived_quantity=s.derived_quantity,
                        derived_unit=s.derived_unit or "",
                        provenance=s.provenance.value,
                    )
                )
        MeasurementSection.objects.bulk_create(sec_models, batch_size=500)
        sec_by_guid = {s.native_guid.upper(): s for s in MeasurementSection.objects.filter(project_version=version)}

        # 6. Measurements
        meas_models = []
        for co in canonical_project.objects:
            db_obj = obj_by_guid[co.native_guid.upper()]
            for m in co.measurements:
                meas_models.append(
                    Measurement(
                        project_version=version,
                        project_object=db_obj,
                        section=sec_by_guid.get(m.section_guid.upper()) if m.section_guid else None,
                        measurement_key=m.measurement_key,
                        page_guid=m.page_guid,
                        measurement_type=m.measurement_type,
                        property_name=m.property_name,
                        raw_formula=m.raw_formula or "",
                        native_stored_value=m.native_stored_value or "",
                        planswift_computed_quantity=m.calculated_quantity,
                        calculated_quantity=m.calculated_quantity,
                        reconstructed_quantity=m.reconstructed_quantity,
                        derived_quantity=m.derived_quantity,
                        unit=m.unit or "",
                        normalized_quantity=m.normalized_quantity,
                        normalized_unit=m.normalized_unit or "",
                        precision=m.precision or "",
                        is_default_template_value=m.is_default_template_value,
                        calculation_inputs_json=m.calculation_inputs,
                        status=m.status.value,
                        notes=m.notes or "",
                    )
                )
        Measurement.objects.bulk_create(meas_models, batch_size=500)

        # 7. GeometryFeatures & MeasurementPoints
        geom_models = []
        pts_by_sec_guid: dict[str, list[Any]] = {}
        for co in canonical_project.objects:
            db_obj = obj_by_guid[co.native_guid.upper()]
            for g in co.geometries:
                geom_models.append(
                    GeometryFeature(
                        project_version=version,
                        project_object=db_obj,
                        section=sec_by_guid.get(g.section_guid.upper()),
                        section_guid=g.section_guid,
                        parent_object_guid=g.parent_object_guid,
                        page_guid=g.page_guid,
                        geometry_type=g.geometry_type,
                        coordinate_system=g.coordinate_system,
                        point_count=g.point_count,
                        bbox_min_x=g.bbox_min_x,
                        bbox_min_y=g.bbox_min_y,
                        bbox_max_x=g.bbox_max_x,
                        bbox_max_y=g.bbox_max_y,
                        derived_polyline_length=g.derived_polyline_length,
                        derived_polygon_area=g.derived_polygon_area,
                        scale_x=g.scale_x,
                        scale_y=g.scale_y,
                        scale_unit=g.scale_unit,
                        is_calibrated=g.is_calibrated,
                        calibrated_length=g.calibrated_length,
                        calibrated_area=g.calibrated_area,
                        calibrated_unit=g.calibrated_unit,
                        normalized_length_m=g.normalized_length_m,
                        normalized_area_m2=g.normalized_area_m2,
                        raw_digitizer_xml=g.raw_digitizer_xml,
                        provenance=g.provenance.value,
                        derived_metrics_provenance=g.derived_metrics_provenance.value,
                    )
                )
                pts_by_sec_guid[g.section_guid.upper()] = g.points
        GeometryFeature.objects.bulk_create(geom_models, batch_size=500)
        geom_by_sec = {gf.section_guid.upper(): gf for gf in GeometryFeature.objects.filter(project_version=version)}

        point_models = []
        for sec_guid_key, pt_list in pts_by_sec_guid.items():
            gf = geom_by_sec[sec_guid_key]
            for pt in pt_list:
                point_models.append(
                    MeasurementPoint(
                        geometry_feature=gf,
                        point_order=pt.point_order,
                        x=pt.x,
                        y=pt.y,
                        point_type=pt.point_type,
                        raw_x=pt.raw_x,
                        raw_y=pt.raw_y,
                        normalized_x=pt.normalized_x,
                        normalized_y=pt.normalized_y,
                        provenance=pt.provenance.value,
                    )
                )
        MeasurementPoint.objects.bulk_create(point_models, batch_size=1000)

        # 8. Formulas, Dependencies, & CalculatedValues
        form_models = []
        deps_by_fkey: dict[str, list[Any]] = {}
        calc_by_fkey: dict[str, Any] = {}
        for co in canonical_project.objects:
            db_obj = obj_by_guid[co.native_guid.upper()]
            for f in co.formulas:
                form_models.append(
                    Formula(
                        project_version=version,
                        project_object=db_obj,
                        formula_key=f.formula_key,
                        property_guid=f.property_guid,
                        property_name=f.property_name,
                        raw_expression=f.raw_expression,
                        is_pascal_script=f.is_pascal_script,
                        parse_formula_attr=f.parse_formula_attr or "",
                        expression_attr=f.expression_attr or "",
                        has_circular_dependency=f.has_circular_dependency,
                        circular_path=f.circular_path,
                        unresolved_references=f.unresolved_references,
                        evaluation_status=f.evaluation_status.value,
                        planswift_evaluated_value=f.calculated_value or "",
                        calculated_value=f.calculated_value or "",
                        calculated_numeric=f.calculated_numeric,
                        calculation_unit=f.calculation_unit or "",
                        calculation_reason=f.calculation_reason or "",
                        calculation_inputs_json=f.calculation_inputs,
                    )
                )
                deps_by_fkey[f.formula_key] = f.dependencies
                if f.calculated_value is not None:
                    calc_by_fkey[f.formula_key] = f
        Formula.objects.bulk_create(form_models, batch_size=1000)
        form_by_key = {f.formula_key: f for f in Formula.objects.filter(project_version=version)}

        dep_models = []
        for fkey, deps in deps_by_fkey.items():
            db_f = form_by_key[fkey]
            for dep in deps:
                dep_models.append(
                    FormulaDependency(
                        formula=db_f,
                        raw_token=dep.raw_token,
                        reference_kind=dep.reference_kind,
                        target_property=dep.target_property or "",
                        target_object_guid=dep.target_object_guid or "",
                        resolved=dep.resolved,
                    )
                )
        FormulaDependency.objects.bulk_create(dep_models, batch_size=1000)

        calc_models = [
            CalculatedValue(
                formula=form_by_key[fkey],
                value_text=f.calculated_value or "",
                numeric_value=f.calculated_numeric,
                source_status=f.evaluation_status.value,
            )
            for fkey, f in calc_by_fkey.items()
        ]
        CalculatedValue.objects.bulk_create(calc_models, batch_size=1000)

        # 9. Relationships, Assemblies, and ProvenanceRecords
        ObjectRelationship.objects.bulk_create(
            [
                ObjectRelationship(
                    project_version=version,
                    relationship_key=r.relationship_key,
                    relationship_type=r.relationship_type,
                    source_guid=r.source_guid,
                    target_guid=r.target_guid,
                    order_index=r.order_index,
                    metadata=r.metadata,
                    provenance=r.provenance.value,
                )
                for r in canonical_project.relationships
            ],
            batch_size=1000,
        )

        for asm in canonical_project.assemblies:
            db_asm = Assembly.objects.create(
                project_version=version,
                project_object=obj_by_guid[asm.native_guid.upper()],
                native_guid=asm.native_guid,
                name=asm.name,
                native_class=asm.native_class,
                assembly_type=asm.assembly_type or "",
                provenance=asm.provenance.value,
            )
            AssemblyComponent.objects.bulk_create(
                [
                    AssemblyComponent(
                        project_version=version,
                        assembly=db_asm,
                        project_object=obj_by_guid.get(c.native_guid.upper()),
                        native_guid=c.native_guid,
                        name=c.name,
                        native_class=c.native_class,
                        quantity_raw=c.quantity_raw or "",
                        unit=c.unit or "",
                        cost_each_raw=c.cost_each_raw or "",
                        provenance=c.provenance.value,
                    )
                    for c in asm.components
                ]
            )

        ProvenanceRecord.objects.bulk_create(
            [
                ProvenanceRecord(
                    project_version=version,
                    extraction_run=run,
                    source_system=pr.source_system,
                    source_adapter=pr.source_adapter,
                    source_file=pr.source_file,
                    source_location=pr.source_location or "",
                    source_object_guid=pr.source_object_guid or "",
                    source_class=pr.source_class or "",
                    property_name=pr.property_name or "",
                    status=pr.status.value,
                    parser_version=pr.parser_version,
                )
                for pr in canonical_project.provenance_records
            ],
            batch_size=1000,
        )

        if cad_doc is not None:
            header_meta = dict(cad_doc.header_variables or {})
            header_meta["_source_name"] = source.source_name
            db_cad_doc = CADDocument.objects.create(
                project_version=version,
                source_format=cad_doc.source_format,
                library_name=cad_doc.library_name,
                library_version=cad_doc.library_version,
                file_version=cad_doc.file_version,
                schema_name=cad_doc.schema_name,
                source_units=cad_doc.source_units,
                unit_to_meter_factor=cad_doc.unit_to_meter_factor,
                entity_count=len(cad_doc.cad_entities),
                layer_count=len(cad_doc.layers),
                block_count=len(cad_doc.blocks),
                ifc_element_count=len(cad_doc.ifc_elements),
                unsupported_count=len(canonical_project.unsupported_objects),
                header_metadata_json=header_meta,
                external_references_json=cad_doc.external_references,
                extraction_options_json=cad_doc.extraction_options,
                stage_timings_json=cad_doc.stage_timings,
                peak_rss_mb=cad_doc.peak_rss_mb,
            )
            if cad_doc.layers:
                CADLayer.objects.bulk_create(
                    [
                        CADLayer(
                            cad_document=db_cad_doc,
                            layer_id=lyr.layer_id,
                            name=lyr.name,
                            color=lyr.color,
                            true_color=lyr.true_color,
                            linetype=lyr.linetype,
                            lineweight=lyr.lineweight,
                            is_on=lyr.is_on,
                            is_frozen=lyr.is_frozen,
                            is_locked=lyr.is_locked,
                            is_plottable=lyr.is_plottable,
                            entity_count=lyr.entity_count,
                            raw_attributes_json=lyr.raw_attributes,
                            provenance=lyr.provenance.value,
                        )
                        for lyr in cad_doc.layers
                    ],
                    batch_size=500,
                )
            if cad_doc.blocks:
                CADBlock.objects.bulk_create(
                    [
                        CADBlock(
                            cad_document=db_cad_doc,
                            block_id=blk.block_id,
                            name=blk.name,
                            base_point_json=blk.base_point,
                            is_layout=blk.is_layout,
                            is_anonymous=blk.is_anonymous,
                            is_xref=blk.is_xref,
                            xref_path=blk.xref_path,
                            entity_count=blk.entity_count,
                            nested_blocks_json=blk.nested_block_names,
                            raw_attributes_json=blk.raw_attributes,
                            provenance=blk.provenance.value,
                        )
                        for blk in cad_doc.blocks
                    ],
                    batch_size=500,
                )
            if cad_doc.cad_entities:
                CADEntity.objects.bulk_create(
                    [
                        CADEntity(
                            cad_document=db_cad_doc,
                            entity_key=ent.entity_key,
                            handle=ent.handle,
                            entity_type=ent.entity_type,
                            owner_handle=ent.owner_handle,
                            layer_name=ent.layer,
                            layout_name=ent.layout_name,
                            block_name=ent.block_name,
                            linetype=ent.linetype,
                            color=ent.color,
                            true_color=ent.true_color,
                            lineweight=ent.lineweight,
                            invisible=ent.invisible,
                            ocs_applied=ent.ocs_applied,
                            is_supported=ent.is_supported,
                            native_coordinates_json=ent.native_coordinates,
                            world_coordinates_json=ent.world_coordinates,
                            geometry_metrics_json=ent.geometry_metrics,
                            dimension_data_json=ent.dimension_data,
                            classification_json=ent.classification.model_dump(mode="json"),
                            attributes_json=ent.attributes,
                            warnings_json=ent.warnings,
                            raw_metadata_json=ent.raw_metadata,
                            provenance=ent.provenance.value,
                        )
                        for ent in cad_doc.cad_entities
                    ],
                    batch_size=500,
                )
            if cad_doc.ifc_elements:
                BIMElement.objects.bulk_create(
                    [
                        BIMElement(
                            cad_document=db_cad_doc,
                            global_id=el.global_id,
                            step_id=el.step_id,
                            ifc_class=el.ifc_class,
                            name=el.name,
                            description=el.description,
                            object_type=el.object_type,
                            predefined_type=el.predefined_type,
                            tag=el.tag,
                            spatial_parent_guid=el.spatial_parent_guid,
                            storey_name=el.storey_name,
                            placement_json={
                                "matrix": el.placement_matrix,
                                "world_origin": el.world_origin,
                            },
                            property_sets_json=[ps.model_dump(mode="json") for ps in el.property_sets],
                            quantity_sets_json=[qs.model_dump(mode="json") for qs in el.quantity_sets],
                            materials_json=el.materials,
                            classifications_json=el.classifications,
                            representations_json=el.representations,
                            geometry_summary_json=el.geometry_summary.model_dump(mode="json"),
                            warnings_json=el.warnings,
                            provenance=el.provenance.value,
                        )
                        for el in cad_doc.ifc_elements
                    ],
                    batch_size=500,
                )

        ExtractionOrchestrationService._persist_validation_and_reconciliation(version=version, run=run, report=report)
        return version

    @staticmethod
    def _persist_validation_and_reconciliation(version: ProjectVersion, run: ExtractionRun, report: ExtractionReport) -> None:
        if report.validation is not None:
            v = report.validation
            ValidationResult.objects.create(
                project_version=version,
                extraction_run=run,
                overall_status=v.overall_status,
                objects_discovered=v.objects_discovered,
                objects_extracted=v.objects_extracted,
                unknown_class_objects=v.unknown_class_objects,
                skipped_objects=v.skipped_objects,
                properties_extracted=v.properties_extracted,
                empty_name_properties=v.empty_name_properties,
                pages_discovered=v.pages_discovered,
                pages_matched_to_tiff=v.pages_matched_to_tiff,
                sections_extracted=v.sections_extracted,
                sections_with_resolved_page=v.sections_with_resolved_page,
                geometry_features_extracted=v.geometry_features_extracted,
                points_extracted=v.points_extracted,
                formulas_extracted=v.formulas_extracted,
                unresolved_formulas=v.unresolved_formulas,
                circular_formulas=v.circular_formulas,
                unresolved_references=v.unresolved_references,
                unparsed_files=v.unparsed_files,
                unsupported_classes=v.unsupported_classes,
                overall_verified_accuracy_pct=v.overall_verified_accuracy_pct,
                checks_json=[c.model_dump(mode="json") for c in v.checks],
            )
        if report.reconciliation_summary is not None:
            rec = report.reconciliation_summary
            ReconciliationReport.objects.create(
                project_version=version,
                extraction_run=run,
                mode=rec.get("mode", "standalone_zip_verified"),
                com_available=False,
                matched_objects=int(rec.get("matched_objects", 0)),
                package_only_objects=int(rec.get("package_only_objects", 0)),
                com_only_objects=0,
                computed_values_applied=int(rec.get("computed_values_applied", 0)),
                duplicate_guid_count=int(rec.get("duplicate_detection", {}).get("duplicate_guid_count", 0)),
                summary_json=rec,
            )
