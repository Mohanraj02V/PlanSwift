"""GUID identity normalization preserving exact original_guid formatting."""

from __future__ import annotations

import re

_BRACED_GUID_RE = re.compile(r"^\{?[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}?$")


def canonical_guid_key(raw_guid: str | None) -> str:
    """Return canonical uppercase braced GUID key for deduplication without altering stored raw GUID."""
    if not raw_guid:
        return ""
    trimmed = raw_guid.strip().upper()
    if _BRACED_GUID_RE.match(trimmed):
        if not trimmed.startswith("{"):
            return f"{{{trimmed}}}"
        return trimmed
    return trimmed
