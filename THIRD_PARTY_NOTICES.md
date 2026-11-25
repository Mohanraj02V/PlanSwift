# Third-Party Open-Source Notices

Vortexen Estimator integrates mature, unmodified upstream open-source libraries via their supported public Python APIs. No third-party library source code is forked or modified, and no native C++ parser was reimplemented.

---

## CAD / BIM Extraction, Document Export & Performance Dependencies

| Package | Installed / Declared Version | License | Role & Scope | Project URL |
|---|---|---|---|---|
| `ezdxf` | `1.4.5` | MIT License | **Runtime** — ASCII & Binary DXF reader (`ezdxf.readfile`, `ezdxf.recover.readfile`), block/INSERT transform math (`Matrix44`, `OCS`), curve path flattening (`make_path`) | https://github.com/mozman/ezdxf |
| `ifcopenshell` | `0.9.0.post1` | LGPL-3.0-or-later | **Runtime** — IFC2X3 / IFC4 / IFC4X3 STEP parser, `ifcopenshell.util.*` (element, unit, placement, shape), bounded `ifcopenshell.geom.iterator` | http://ifcopenshell.org |
| `reportlab` | `5.1.0` | BSD License | **Runtime** — Dynamic multi-page A4 commercial quotation PDF generation embedding official Vortexen branding | https://www.reportlab.com |
| `psutil` | `7.2.2` | BSD-3-Clause | **Runtime / Benchmarking** — OS-level process RSS memory measurement (`psutil.Process.memory_info().rss`) | https://github.com/giampaolo/psutil |

### Transitive Dependencies Pulled by `ezdxf` & `ifcopenshell`

| Package | Exact Installed Version | License | Project URL |
|---|---|---|---|
| `numpy` | `2.5.5` | BSD-3-Clause (with 0BSD / MIT / Zlib / CC0-1.0 components) | https://numpy.org |
| `shapely` | `2.2.0` | BSD-3-Clause | https://shapely.readthedocs.io/ |
| `fonttools` | `4.68.0` | MIT License | http://github.com/fonttools/fonttools |
| `pyparsing` | `3.3.3` | MIT License | https://pyparsing-docs.readthedocs.io/ |
| `isodate` | `0.7.2` | BSD-3-Clause | https://github.com/gweis/isodate/ |
| `lark` | `1.3.1` | MIT License | https://github.com/lark-parser/lark |

---

## Core Platform Dependencies

- Backend (`backend/requirements.txt`): `Django`, `djangorestframework`, `djangorestframework-simplejwt`, `django-cors-headers`, `django-filter`, `drf-spectacular`, `pydantic`, `lxml`, `celery`, `redis`, `psycopg[binary]`, `openpyxl`, `reportlab`, `httpx`, `whitenoise`, `gunicorn`.
- Dev/Test Only (`backend/requirements-dev.txt`): `pytest`, `pytest-django` (excluded from runtime production containers).
- Frontend (`frontend/package.json`): `next`, `react`, `react-dom`, `lucide-react`, `zod`.

---

## LGPL-3.0-or-Later Compliance Notes (`ifcopenshell`)

1. `ifcopenshell` (`0.9.0.post1`) is distributed and invoked strictly as an unmodified upstream Python wheel / C++ shared extension via its public API (`import ifcopenshell`).
2. Vortexen Estimator does not statically link modified `ifcopenshell` C++ sources into proprietary binaries; downstream deployments preserve standard LGPL-3.0-or-later user freedom to upgrade or swap the `ifcopenshell` wheel in the Python environment.
3. Retain this `THIRD_PARTY_NOTICES.md` alongside redistributions or container images, and inspect upstream license texts shipped in Python `site-packages/*.dist-info/licenses/` when packaging production artifacts.
