# CAD, BIM & PlanSwift Performance Benchmark Report

All timings and memory metrics in this report were measured directly on the repository using the reproducible benchmark suite [`extraction_engine/benchmarks/run_benchmarks.py`](extraction_engine/benchmarks/run_benchmarks.py).

---

## 1. Benchmark Environment & Reproducible Command

- **Platform**: Windows (12 logical CPUs)
- **Python**: `3.12.0` (`.\backend\.venv\Scripts\python.exe`)
- **Libraries**:
  - `ezdxf`: `1.4.5` (`use_c_ext=True`, Cython C-extensions enabled)
  - `ifcopenshell`: `0.9.0.post1`
  - `psutil`: `7.2.2`
- **Command to reproduce**:

```powershell
.\backend\.venv\Scripts\python.exe extraction_engine\benchmarks\run_benchmarks.py
```

### Measurement Methodology
- Wall-clock (`time.perf_counter()`), CPU (`time.process_time()`), and peak process RSS (`psutil.Process.memory_info().rss`) are measured across `3` trials for synthetic DXF/IFC fixtures **without `tracemalloc` active**, preventing Python allocation tracing overhead from inflating wall-clock timings.
- Peak Python heap (`tracemalloc.get_traced_memory()`) is measured in a separate pass immediately afterward.
- `median_ser_s` measures `build_structured_project_export()` + UTF-8 JSON encoding size (`output_json_bytes`).

---

## 2. Measured CAD & BIM Benchmark Results

| Benchmark Case | File Size | Objects / Elements | Geom. | Rels. | Median Wall (s) | Min / Max Wall (s) | Cold / Warm Wall (s) | Median CPU (s) | JSON Ser (s) | Peak RSS (MiB) | Peak Heap (MiB) | Output JSON (Bytes) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `dxf_small_100` | 32,441 B | 100 | 67 | 200 | **0.0921** | 0.0879 / 0.1330 | 0.1330 / 0.0921 | 0.0781 | 0.0219 | 98.41 | 4.05 | 779,400 |
| `dxf_medium_2500` | 385,138 B | 2,500 | 1,667 | 5,000 | **1.8999** | 1.6284 / 2.0133 | 1.6284 / 2.0133 | 1.8906 | 1.0202 | 254.89 | 66.55 | 19,483,592 |
| `dxf_large_15000` | 2,259,441 B | 15,000 | 10,000 | 30,000 | **8.3760** | 6.6004 / 11.1132 | 6.6004 / 8.3760 | 8.0625 | 5.2866 | 1,107.13 | 397.11 | 117,349,791 |
| `dxf_complex_blocks_splines` | 188,739 B | 1,002 | 501 | 2,254 | **0.9459** | 0.6907 / 1.0567 | 1.0567 / 0.6907 | 0.9531 | 0.2983 | 190.30 | 25.11 | 6,681,219 |
| `ifc_small_20_prop_only` | 3,258 B | 22 | 0 | 41 | **0.0480** | 0.0450 / 0.0892 | 0.0892 / 0.0480 | 0.0469 | 0.0056 | 139.79 | 4.02 | 177,139 |
| `ifc_medium_250_prop_only` | 20,968 B | 252 | 0 | 501 | **0.2011** | 0.1363 / 0.2748 | 0.2748 / 0.2011 | 0.1562 | 0.0590 | 144.65 | 6.11 | 2,104,245 |
| `ifc_large_1500_prop_only` | 120,556 B | 1,502 | 0 | 3,001 | **1.0376** | 0.8711 / 1.0625 | 1.0376 / 0.8711 | 0.9531 | 0.3602 | 204.81 | 36.95 | 12,591,681 |
| `ifc_geo_200_property_only` | 17,071 B | 202 | 0 | 401 | **0.1535** | 0.1237 / 0.2279 | 0.1535 / 0.2279 | 0.1406 | 0.0547 | 159.51 | 4.90 | 1,685,207 |
| `ifc_geo_200_iterator_1thread` | 17,071 B | 202 | 200 | 401 | **0.7507** | 0.7327 / 0.7672 | 0.7507 / 0.7672 | 0.7500 | 0.0526 | 166.77 | 5.64 | 2,246,767 |
| `ifc_geo_200_iterator_2threads` | 17,071 B | 202 | 200 | 401 | **0.4802** | 0.4672 / 0.5295 | 0.4672 / 0.5295 | 1.1562 | 0.0748 | 164.63 | 5.64 | 2,246,769 |

---

## 3. Stage-Level Timings (Last Trial Breakdown)

| Case | `validate_and_inspect_s` | `open_and_parse_s` | Extraction / Core Work | `digest_s` | `validation_s` |
|---|---:|---:|---|---:|---:|
| `dxf_medium_2500` | 0.0135s | 0.3444s | `layers_and_blocks_s=0.0026s`, `entities_and_geometry_s=1.5703s` | 0.0611s | 0.0148s |
| `dxf_large_15000` | 0.0146s | 1.1819s | `layers_and_blocks_s=0.0085s`, `entities_and_geometry_s=6.8421s` | 0.2442s | 0.0730s |
| `ifc_large_1500_prop_only` | 0.0090s | 0.0112s | `elements_rels_and_geom_s=0.8301s` | 0.0085s | 0.0096s |
| `ifc_geo_200_iterator_2threads` | 0.0198s | 0.0132s | `elements_rels_and_geom_s=0.4786s` | 0.0031s | 0.0102s |

---

## 4. Before / After Optimization Comparisons & Output Equivalence

### Optimization A — IFC `ifcopenshell.geom.iterator` vs. Naive Single-Object `create_shape()` (200 Walls)

| Mode | Wall (s) | CPU (s) | Peak RSS (MiB) | Calculated Walls | Total Surface Area (m²) | Total Volume (m³) | Speedup vs Naive |
|---|---:|---:|---:|---:|---:|---:|---:|
| Naive `create_shape()` loop | 0.6857 | 0.7031 | 168.75 | 200 | 5360.0 | 480.0 | 1.00× (baseline) |
| Full pipeline + `geom.iterator` (1 thread) | 0.7507 | 0.7500 | 166.77 | 200 | 5360.0 | 480.0 | 0.91× (includes full Pset/Qto/hierarchy/validation) |
| Full pipeline + `geom.iterator` (2 bounded threads) | **0.4802** | 1.1562 | 164.63 | 200 | 5360.0 | 480.0 | **1.43×** faster wall-clock (**1.56×** vs 1 thread) |
| Property/Qto-only mode (`ifc_extract_geometry=False`) | **0.1535** | 0.1406 | 159.51 | 0 (skipped) | — | — | **4.47×** faster than naive (`3.13×` vs 2-thread geo) |

- **Output Equivalence**: `ifc_geo_200_equivalence_verified = true` (`200` calculated elements, `5360.0 m²` total surface area, `480.0 m³` total volume match identically within `1e-4` tolerance across naive `create_shape()`, 1-thread `geom.iterator`, and 2-thread `geom.iterator`).

### Optimization B — Canonical JSON Exporter $O(N^2) \rightarrow O(N)$ Lookup (`json_exporter.py`)
- Before fix: `build_structured_project_export()` ran an inner `sum(1 for c in project.objects if c.parent_guid == o.native_guid ...)` per object with `depth >= 2` and `o.sections == []`, triggering **225,000,000 iterations per trial** on `dxf_large_15000` (>180s benchmark stall).
- After fix (`section_count_by_parent` dictionary pre-index): `15,000`-entity serialization completes cleanly in **`5.2866s`** for **`117.35 MB`** canonical JSON output, with identical PlanSwift output structure.

### Optimization C — Single-Open Indexed DXF Reading vs. Naive Re-Parse + `iterdxf` Trade-off
- Naive 3× re-open + unindexed `O(L)` layer scan on `dxf_medium_2500` spent **`1.0657s`** before computing geometry, OCS/WCS, dimensions, or validation; our single-open indexed `DXFAdapter` spent only **`0.3444s`** (`open_and_parse_s`) + **`0.0026s`** (`layers_and_blocks_s`) — **3.07× faster** on document open & table indexing.
- **`iterdxf` benchmark on `dxf_large_15000`**: `iterdxf.opendxf().modelspace()` took **`2.2475s`** for 15,000 modelspace items (vs **`1.1819s`** for Cython-accelerated `ezdxf.readfile()` + full table loading) and **omits** `HEADER`, `LAYERS`, `BLOCKS` definitions, and Paperspace, making it unsuitable for complete canonical extraction.

---

## 5. PlanSwift Non-Regression Baseline (Current Run)

| Real PlanSwift Fixture | File Size | Objects | Geom. | Rels. | Wall (s) | CPU (s) | JSON Ser (s) | Peak RSS (MiB) | Peak Heap (MiB) | SHA-256 Digest |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `extracted_tmp/Sample Project.SwiftJob` | 70,481,441 B | 224 | 41 | 425 | 0.7926 | 0.7656 | 0.2330 | 181.84 | 39.46 | `4d95c0e5c850566a7f46d8bdbd6bb13f56783f213f6a2fa5d1a1899b7564f738` |
| `project 4.SwiftJob.zip` | 582,831,166 B | 1,461 | 1,052 | 3,163 | 4.8177 | 4.8125 | 1.1637 | 353.89 | 177.23 | `43178b01eb2d9427ec66f81b36b93826ca1709e520f5828056570dae162376a8` |

PlanSwift object counts, property counts, geometry point totals, peak Python heap (`177.23 MiB` vs historical `177.22 MiB`), and deterministic SHA-256 digests remain intact with zero regression.
