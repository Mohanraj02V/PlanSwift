"""DXF layer table extraction preserving native layer flags, colors, linetypes, and counts."""

from __future__ import annotations

from ezdxf.document import Drawing

from extraction_engine.core.cad_models import CanonicalCADLayer
from extraction_engine.core.extraction_result import ProvenanceStatus


def extract_dxf_layers(doc: Drawing, doc_hash_prefix: str) -> tuple[list[CanonicalCADLayer], dict[str, CanonicalCADLayer]]:
    """Extract all DXF layer definitions deterministically sorted by layer name."""
    layers: list[CanonicalCADLayer] = []
    by_name: dict[str, CanonicalCADLayer] = {}

    raw_layers = sorted(doc.layers, key=lambda lyr: (lyr.dxf.name or "").lower())
    for lyr in raw_layers:
        dxf = lyr.dxf
        name = dxf.name or ""
        handle = getattr(dxf, "handle", "") or ""
        layer_id = f"dxf:{doc_hash_prefix}:layer:{handle or name}"
        model = CanonicalCADLayer(
            layer_id=layer_id,
            name=name,
            color=getattr(dxf, "color", None),
            true_color=getattr(dxf, "true_color", None),
            linetype=getattr(dxf, "linetype", "") or "",
            lineweight=getattr(dxf, "lineweight", None),
            is_on=bool(lyr.is_on()),
            is_frozen=bool(lyr.is_frozen()),
            is_locked=bool(lyr.is_locked()),
            is_plottable=bool(getattr(dxf, "plot", 1)),
            raw_attributes={
                "handle": handle,
                "flags": getattr(dxf, "flags", 0),
                "description": getattr(lyr, "description", "") or "",
            },
            provenance=ProvenanceStatus.NATIVE,
        )
        layers.append(model)
        by_name[name] = model
        by_name.setdefault(name.lower(), model)

    return layers, by_name
