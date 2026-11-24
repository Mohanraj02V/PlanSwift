"""DXF block table extraction preserving definitions, XREF metadata (never opened), and nesting."""

from __future__ import annotations

from typing import Any

from ezdxf.document import Drawing

from extraction_engine.core.cad_models import CanonicalCADBlock
from extraction_engine.core.extraction_result import ProvenanceStatus


def extract_dxf_blocks(
    doc: Drawing,
    doc_hash_prefix: str,
) -> tuple[list[CanonicalCADBlock], dict[str, CanonicalCADBlock], list[dict[str, Any]]]:
    """Extract block definitions separately from INSERTs; record XREF paths strictly as untrusted metadata."""
    blocks: list[CanonicalCADBlock] = []
    by_name: dict[str, CanonicalCADBlock] = {}
    external_refs: list[dict[str, Any]] = []

    raw_blocks = sorted(doc.blocks, key=lambda blk: (blk.name or "").lower())
    for blk in raw_blocks:
        name = blk.name or ""
        blk_record = blk.block
        dxf = blk_record.dxf
        base_pt = getattr(dxf, "base_point", (0.0, 0.0, 0.0))
        base_coords = [float(base_pt[0]), float(base_pt[1]), float(base_pt[2]) if len(base_pt) > 2 else 0.0]

        xref_path = getattr(dxf, "xref_path", "") or ""
        is_xref = bool(getattr(blk, "is_xref", False) or xref_path)
        is_layout = bool(getattr(blk, "is_any_layout", False))

        nested_names_set: set[str] = set()
        ent_count = 0
        for ent in blk:
            ent_count += 1
            if ent.dxftype() == "INSERT":
                child_blk = getattr(ent.dxf, "name", "")
                if child_blk:
                    nested_names_set.add(child_blk)

        handle = getattr(dxf, "handle", "") or ""
        block_id = f"dxf:{doc_hash_prefix}:block:{handle or name}"
        model = CanonicalCADBlock(
            block_id=block_id,
            name=name,
            base_point=base_coords,
            is_layout=is_layout,
            is_anonymous=bool(name.startswith("*")),
            is_xref=is_xref,
            xref_path=xref_path,
            entity_count=ent_count,
            nested_block_names=sorted(nested_names_set),
            raw_attributes={
                "handle": handle,
                "flags": getattr(dxf, "flags", 0),
                "description": getattr(dxf, "description", "") or "",
            },
            provenance=ProvenanceStatus.NATIVE,
        )
        blocks.append(model)
        by_name[name] = model
        by_name.setdefault(name.lower(), model)

        if is_xref:
            external_refs.append(
                {
                    "kind": "dxf_xref_block",
                    "block_name": name,
                    "handle": handle,
                    "path": xref_path,
                    "loaded": False,
                    "security_note": "XREF metadata preserved; external filesystem/network loading disabled.",
                }
            )

    return blocks, by_name, external_refs
