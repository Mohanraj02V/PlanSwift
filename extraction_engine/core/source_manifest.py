"""Source inventory manifest and streaming SHA-256 checksum helpers."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


def compute_file_sha256(file_path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    """Stream a large archive in fixed chunks to compute SHA-256 without loading into memory."""
    digest = hashlib.sha256()
    with file_path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


class SourceFileEntry(BaseModel):
    """Inventory record for a single file inside the PlanSwift package or directory."""

    relative_path: str
    file_name: str
    extension: str
    compressed_size: int = 0
    uncompressed_size: int = 0
    compression_ratio: float = 1.0
    crc32: int | None = None
    modified_at: str | None = None
    is_directory: bool = False
    is_xml_data: bool = False
    is_raster_asset: bool = False
    asset_guid: str | None = None
    linked_page_guid: str | None = None
    content_sha256: str | None = None
    security_status: Literal["safe", "rejected", "skipped_raster"] = "safe"
    notes: str | None = None


class SourceManifest(BaseModel):
    """Complete read-only source package manifest built before object parsing."""

    manifest_version: str = "2.0.0"
    source_path: str
    source_name: str
    actual_extension: str
    magic_bytes_hex: str
    container_format: Literal[
        "pkzip_swiftjob",
        "planswift_job_directory",
        "directory_project",
        "xml_only",
        "dxf_ascii",
        "dxf_binary",
        "ifc_step",
        "unknown",
    ]
    file_size_bytes: int
    source_sha256: str
    total_entries: int
    total_compressed_bytes: int
    total_uncompressed_bytes: int
    xml_entry_path: str | None = None
    xml_entry_size: int = 0
    detected_xml_encoding: str = ""
    detected_project_version: str = ""
    raster_entry_count: int = 0
    raster_total_bytes: int = 0
    duplicate_crc_groups: dict[str, list[str]] = Field(default_factory=dict)
    duplicate_paths: list[str] = Field(default_factory=list)
    missing_referenced_files: list[str] = Field(default_factory=list)
    corrupted_entries: list[str] = Field(default_factory=list)
    suspicious_entries: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    entries: list[SourceFileEntry] = Field(default_factory=list)
    inspected_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
