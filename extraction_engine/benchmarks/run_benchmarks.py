"""Reproducible multi-trial benchmark harness for PlanSwift, DXF (ezdxf), and IFC (IfcOpenShell)."""

from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf.addons import iterdxf
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.geom
import ifcopenshell.guid
import psutil

from extraction_engine.adapters.ifc.ifc_geometry_extractor import _compute_mesh_metrics
from extraction_engine.core.extraction_context import ExtractionConfig
from extraction_engine.exporters.json_exporter import build_structured_project_export
from extraction_engine.pipeline import ExtractionPipeline

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


def _build_dxf_fixture(path: Path, entity_count: int, with_blocks_and_splines: bool = False) -> None:
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    if with_blocks_and_splines:
        doc.layers.add("A-WALL", color=1)
        doc.layers.add("M-HVAC", color=3)
        blk = doc.blocks.new(name="COMPLEX_UNIT")
        blk.add_line((0, 0), (1.5, 0))
        blk.add_circle((0.75, 0.75), 0.5)
        n_spl = max(10, entity_count // 4)
        for i in range(n_spl):
            msp.add_spline([(i, 0, 0), (i + 0.5, 2, 0), (i + 1, 0, 0)], dxfattribs={"layer": "M-HVAC"})
            msp.add_blockref("COMPLEX_UNIT", insert=(i * 2.0, 5.0), dxfattribs={"layer": "A-WALL", "rotation": i % 90})
            msp.add_lwpolyline([(0, i), (3, i), (3, i + 1), (0, i + 1)], close=True)
            msp.add_line((0, i), (10, i + 1))
    else:
        for i in range(entity_count):
            if i % 3 == 0:
                msp.add_line((float(i), 0.0), (float(i) + 2.5, 1.0))
            elif i % 3 == 1:
                msp.add_lwpolyline([(0.0, float(i)), (2.0, float(i)), (2.0, float(i) + 1.0), (0.0, float(i) + 1.0)], close=True)
            else:
                msp.add_circle((float(i), float(i)), 1.0)
    doc.saveas(path)


def _build_ifc_fixture(path: Path, element_count: int, with_reps: bool = True) -> None:
    model = ifcopenshell.file(schema="IFC4")
    proj = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name=path.stem)
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "METERS"})
    ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body = ifcopenshell.api.run("context.add_context", model, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Level 1")
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=proj, products=[storey])

    wall_rep = None
    if with_reps:
        wall_rep = ifcopenshell.api.run("geometry.add_wall_representation", model, context=body, length=4.0, height=3.0, thickness=0.2)

    prod_def = (
        model.create_entity("IfcProductDefinitionShape", Representations=[wall_rep])
        if wall_rep is not None
        else None
    )

    q_len = model.create_entity("IfcQuantityLength", Name="Length", LengthValue=4.0)
    q_h = model.create_entity("IfcQuantityLength", Name="Height", LengthValue=3.0)
    q_vol = model.create_entity("IfcQuantityVolume", Name="NetVolume", VolumeValue=2.4)
    qto = model.create_entity(
        "IfcElementQuantity",
        GlobalId=ifcopenshell.guid.new(),
        Name="Qto_WallBaseQuantities",
        Quantities=[q_len, q_h, q_vol],
    )

    walls = []
    for i in range(element_count):
        w = model.create_entity(
            "IfcWall",
            GlobalId=ifcopenshell.guid.new(),
            Name=f"Wall-{i}",
            Representation=prod_def,
        )
        walls.append(w)

    model.create_entity(
        "IfcRelDefinesByProperties",
        GlobalId=ifcopenshell.guid.new(),
        RelatedObjects=walls,
        RelatingPropertyDefinition=qto,
    )
    model.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=walls,
    )
    model.write(str(path))


def _naive_dxf_unindexed_baseline(dxf_path: Path) -> dict[str, Any]:
    """Reference unoptimized DXF baseline: re-parse DXF for header/layers/entities + unindexed layer lookup."""
    proc = psutil.Process(os.getpid())
    t0 = time.perf_counter()
    c0 = time.process_time()
    rss_start = proc.memory_info().rss

    doc_units = ezdxf.readfile(str(dxf_path))
    _ = int(doc_units.header.get("$INSUNITS", 0))
    doc_layers = ezdxf.readfile(str(dxf_path))
    layers = [ly.dxf.name for ly in doc_layers.layers]
    doc_ents = ezdxf.readfile(str(dxf_path))
    count = 0
    for ent in doc_ents.modelspace():
        # Simulate naive O(L) scan per entity
        _ = any(ly == ent.dxf.layer for ly in layers)
        count += 1

    dt = time.perf_counter() - t0
    cpu_dt = time.process_time() - c0
    rss_mb = round(max(rss_start, proc.memory_info().rss) / (1024 * 1024), 2)
    return {"wall_s": round(dt, 4), "cpu_s": round(cpu_dt, 4), "peak_rss_mb": rss_mb, "entities": count}


def _naive_ifc_single_shape_baseline(ifc_path: Path) -> dict[str, Any]:
    """Reference unoptimized baseline: single-object create_shape() loop + same mesh metrics."""
    proc = psutil.Process(os.getpid())
    t0 = time.perf_counter()
    cpu0 = time.process_time()
    rss_start = proc.memory_info().rss

    model = ifcopenshell.open(str(ifc_path))
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    objs = model.by_type("IfcObject")
    calculated = 0
    total_surface_area = 0.0
    total_volume = 0.0
    for ent in objs:
        if getattr(ent, "Representation", None) is not None:
            shape = ifcopenshell.geom.create_shape(settings, ent)
            m = _compute_mesh_metrics(shape.geometry.verts, shape.geometry.faces)
            total_surface_area += float(m["surface_area"] or 0.0)
            total_volume += float(m["volume"] or 0.0)
            calculated += 1
    dt = time.perf_counter() - t0
    cpu_dt = time.process_time() - cpu0
    rss_mb = round(max(rss_start, proc.memory_info().rss) / (1024 * 1024), 2)
    return {
        "wall_s": round(dt, 4),
        "cpu_s": round(cpu_dt, 4),
        "peak_rss_mb": rss_mb,
        "calculated": calculated,
        "total_surface_area": round(total_surface_area, 6),
        "total_volume": round(total_volume, 6),
    }


def _measure_pipeline(path: Path, config: ExtractionConfig, trials: int = 3) -> dict[str, Any]:
    proc = psutil.Process(os.getpid())
    walls: list[float] = []
    cpus: list[float] = []
    rss_peaks: list[float] = []
    ser_times: list[float] = []
    last_proj = None
    last_rep = None
    payload_bytes = 0

    for _ in range(trials):
        pipe = ExtractionPipeline(config=config)
        t0 = time.perf_counter()
        c0 = time.process_time()
        proj, rep = pipe.run(path, track_memory=False)
        c1 = time.process_time()
        t1 = time.perf_counter()

        ts0 = time.perf_counter()
        exported = build_structured_project_export(proj, rep)
        payload_bytes = len(json.dumps(exported, ensure_ascii=False).encode("utf-8"))
        ts1 = time.perf_counter()

        walls.append(round(t1 - t0, 4))
        cpus.append(round(c1 - c0, 4))
        rss_peaks.append(round(proc.memory_info().rss / (1024 * 1024), 2))
        ser_times.append(round(ts1 - ts0, 4))
        last_proj, last_rep = proj, rep

    # Separate single heap measurement pass so tracemalloc never slows wall-clock trials
    tracemalloc.start()
    ExtractionPipeline(config=config).run(path, track_memory=False)
    _, heap_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert last_proj is not None and last_rep is not None
    cad = last_proj.cad_document
    total_geo_area = 0.0
    total_geo_vol = 0.0
    calc_count = 0
    if cad and cad.ifc_elements:
        for el in cad.ifc_elements:
            if el.geometry_summary.status == "calculated":
                calc_count += 1
                total_geo_area += float(el.geometry_summary.surface_area or 0.0)
                total_geo_vol += float(el.geometry_summary.volume or 0.0)

    return {
        "file_size_bytes": path.stat().st_size,
        "source_format": cad.source_format if cad else last_proj.source_system,
        "version": cad.file_version if cad else last_proj.native_project_version,
        "entities_or_elements": len(cad.cad_entities) if cad and cad.cad_entities else (len(cad.ifc_elements) if cad and cad.ifc_elements else len(last_proj.objects)),
        "geometries": sum(len(o.geometries) for o in last_proj.objects) or calc_count,
        "relationships": len(last_proj.relationships),
        "trials": trials,
        "median_wall_s": round(statistics.median(walls), 4),
        "min_wall_s": min(walls),
        "max_wall_s": max(walls),
        "cold_wall_s": walls[0],
        "warm_wall_s": walls[-1],
        "median_cpu_s": round(statistics.median(cpus), 4),
        "median_ser_s": round(statistics.median(ser_times), 4),
        "peak_rss_mb": max(rss_peaks),
        "peak_heap_mb": round(heap_peak / (1024 * 1024), 2),
        "output_json_bytes": payload_bytes,
        "stage_timings": last_rep.stage_timings,
        "validation_status": last_rep.validation.overall_status if last_rep.validation else "",
        "digest": last_proj.deterministic_digest_sha256,
        "ifc_calc_totals": {"calculated": calc_count, "surface_area": round(total_geo_area, 6), "volume": round(total_geo_vol, 6)} if calc_count else None,
    }


def run_all_benchmarks() -> dict[str, Any]:
    results: dict[str, Any] = {
        "libraries": {
            "ezdxf": ezdxf.__version__,
            "ezdxf_c_ext": bool(getattr(ezdxf.options, "use_c_ext", False)),
            "ifcopenshell": str(ifcopenshell.version),
            "psutil": psutil.__version__,
            "cpu_count": os.cpu_count(),
        },
        "benchmarks": {},
    }

    with tempfile.TemporaryDirectory() as tmp:
        tdir = Path(tmp)
        print("[bench] Building DXF fixtures...", file=sys.stderr, flush=True)
        dxf_small = tdir / "small.dxf"
        dxf_med = tdir / "medium.dxf"
        dxf_large = tdir / "large.dxf"
        dxf_complex = tdir / "complex.dxf"
        _build_dxf_fixture(dxf_small, 100)
        _build_dxf_fixture(dxf_med, 2500)
        _build_dxf_fixture(dxf_large, 15000)
        _build_dxf_fixture(dxf_complex, 1000, with_blocks_and_splines=True)

        print("[bench] Running DXF benchmarks...", file=sys.stderr, flush=True)
        results["benchmarks"]["dxf_small_100"] = _measure_pipeline(dxf_small, ExtractionConfig())
        results["benchmarks"]["dxf_medium_2500_naive_reparse"] = _naive_dxf_unindexed_baseline(dxf_med)
        results["benchmarks"]["dxf_medium_2500"] = _measure_pipeline(dxf_med, ExtractionConfig())
        results["benchmarks"]["dxf_large_15000"] = _measure_pipeline(dxf_large, ExtractionConfig())
        results["benchmarks"]["dxf_complex_blocks_splines"] = _measure_pipeline(dxf_complex, ExtractionConfig())

        # Evaluate iterdxf on Large DXF (modelspace-only coverage vs complete extraction)
        t_it0 = time.perf_counter()
        it_count = sum(1 for _ in iterdxf.opendxf(str(dxf_large)).modelspace())
        results["benchmarks"]["dxf_large_iterdxf_modelspace_only"] = {
            "wall_s": round(time.perf_counter() - t_it0, 4),
            "entities": it_count,
            "note": "Modelspace-only stream; omits HEADER/TABLES/LAYERS/BLOCKS/Paperspace so NOT used as default replacement.",
        }

        print("[bench] Building IFC fixtures...", file=sys.stderr, flush=True)
        ifc_small = tdir / "small.ifc"
        ifc_med = tdir / "medium.ifc"
        ifc_large = tdir / "large.ifc"
        ifc_geo = tdir / "geo_heavy.ifc"
        _build_ifc_fixture(ifc_small, 20, with_reps=True)
        _build_ifc_fixture(ifc_med, 250, with_reps=True)
        _build_ifc_fixture(ifc_large, 1500, with_reps=True)
        _build_ifc_fixture(ifc_geo, 200, with_reps=True)

        print("[bench] Running IFC property-only benchmarks...", file=sys.stderr, flush=True)
        results["benchmarks"]["ifc_small_20_prop_only"] = _measure_pipeline(ifc_small, ExtractionConfig(ifc_extract_geometry=False))
        results["benchmarks"]["ifc_medium_250_prop_only"] = _measure_pipeline(ifc_med, ExtractionConfig(ifc_extract_geometry=False))
        results["benchmarks"]["ifc_large_1500_prop_only"] = _measure_pipeline(ifc_large, ExtractionConfig(ifc_extract_geometry=False))

        print("[bench] Running IFC geometry naive vs iterator benchmarks...", file=sys.stderr, flush=True)
        baseline_geo = _naive_ifc_single_shape_baseline(ifc_geo)
        opt_geo_1t = _measure_pipeline(ifc_geo, ExtractionConfig(ifc_extract_geometry=True, ifc_geometry_threads=1))
        opt_geo_2t = _measure_pipeline(ifc_geo, ExtractionConfig(ifc_extract_geometry=True, ifc_geometry_threads=2))
        opt_geo_prop_skip = _measure_pipeline(ifc_geo, ExtractionConfig(ifc_extract_geometry=False))

        it_totals = opt_geo_2t.get("ifc_calc_totals") or {}
        eq_ok = (
            baseline_geo["calculated"] == it_totals.get("calculated")
            and abs(baseline_geo["total_surface_area"] - float(it_totals.get("surface_area", -1.0))) < 1e-4
            and abs(baseline_geo["total_volume"] - float(it_totals.get("volume", -1.0))) < 1e-4
        )
        results["benchmarks"]["ifc_geo_200_naive_create_shape"] = baseline_geo
        results["benchmarks"]["ifc_geo_200_iterator_1thread"] = opt_geo_1t
        results["benchmarks"]["ifc_geo_200_iterator_2threads"] = opt_geo_2t
        results["benchmarks"]["ifc_geo_200_property_only"] = opt_geo_prop_skip
        results["benchmarks"]["ifc_geo_200_equivalence_verified"] = eq_ok

    print("[bench] Running PlanSwift regression benchmarks...", file=sys.stderr, flush=True)
    sample_ps = WORKSPACE_ROOT / "extracted_tmp" / "Sample Project.SwiftJob"
    if sample_ps.exists():
        results["benchmarks"]["planswift_sample_project"] = _measure_pipeline(sample_ps, ExtractionConfig(), trials=1)
    proj4 = WORKSPACE_ROOT / "project 4.SwiftJob.zip"
    if proj4.exists():
        results["benchmarks"]["planswift_project_4"] = _measure_pipeline(proj4, ExtractionConfig(), trials=1)

    return results


if __name__ == "__main__":
    print(json.dumps(run_all_benchmarks(), indent=2))
