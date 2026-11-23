"""Safe streaming PlanSwift archive/package inspector with Zip Slip, zip bomb, and symlink protection."""

from __future__ import annotations

import hashlib
import io
import os
import posixpath
import re
import stat
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from lxml import etree

from extraction_engine.core.extraction_context import ExtractionConfig, SecurityValidationError
from extraction_engine.core.source_manifest import SourceFileEntry, SourceManifest, compute_file_sha256

_GUID_FILENAME_RE = re.compile(r"(\{[0-9A-Fa-f-]{36}\})\.(?:tiff|tif|png|jpg|jpeg)$", re.IGNORECASE)
_NESTED_ARCHIVE_EXTS = (".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz")
_RASTER_EXTS = (".tiff", ".tif", ".png", ".jpg", ".jpeg", ".bmp", ".gif")


def validate_source_path_allowed(source_path: Path, config: ExtractionConfig) -> Path:
    """Resolve and validate that source_path exists and sits inside allowed_source_roots if configured."""
    resolved = source_path.resolve(strict=True)
    if config.allowed_source_roots:
        allowed = False
        for root in config.allowed_source_roots:
            resolved_root = root.resolve()
            try:
                resolved.relative_to(resolved_root)
                allowed = True
                break
            except ValueError:
                continue
        if not allowed:
            raise SecurityValidationError(
                f"Source path '{resolved}' is outside configured ALLOWED_SOURCE_ROOTS."
            )
    return resolved


def validate_archive_member_path(member_name: str) -> str:
    """Reject Zip Slip, absolute paths, drive letters, and NUL bytes."""
    if "\x00" in member_name:
        raise SecurityValidationError(f"Archive entry contains NUL byte: {member_name!r}")
    normalized = member_name.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise SecurityValidationError(f"Archive entry uses an absolute path: {member_name}")
    parts = [part for part in normalized.split("/") if part]
    if any(part == ".." for part in parts):
        raise SecurityValidationError(f"Archive entry attempts path traversal (Zip Slip): {member_name}")
    clean = posixpath.normpath(normalized)
    if clean.startswith("..") or clean.startswith("/"):
        raise SecurityValidationError(f"Normalized archive entry escapes root: {member_name}")
    return normalized


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    unix_mode = (info.external_attr >> 16) & 0o170000
    return stat.S_ISLNK(unix_mode)


def inspect_archive_manifest(source_path: Path, config: ExtractionConfig | None = None) -> SourceManifest:
    """Inspect a PlanSwift SwiftJob/ZIP archive, directory, or XML file strictly read-only."""
    cfg = config or ExtractionConfig()
    resolved = validate_source_path_allowed(source_path, cfg)

    if resolved.is_dir():
        return _inspect_directory_source(resolved, cfg)

    with resolved.open("rb") as fh:
        magic = fh.read(16)
    magic_hex = " ".join(f"{b:02X}" for b in magic)
    file_size = resolved.stat().st_size
    source_sha256 = compute_file_sha256(resolved, chunk_size=cfg.hash_chunk_size)

    # Check if PKZIP (PK\x03\x04 or empty PK\x05\x06)
    if magic.startswith(b"PK\x03\x04") or zipfile.is_zipfile(resolved):
        return _inspect_zip_manifest(resolved, file_size, source_sha256, magic_hex, cfg)

    # Direct XMLData.XML fallback
    if magic.lstrip().startswith(b"<?xml") or magic.lstrip().startswith(b"<Item"):
        entry = SourceFileEntry(
            relative_path=resolved.name,
            file_name=resolved.name,
            extension=resolved.suffix.lower(),
            compressed_size=file_size,
            uncompressed_size=file_size,
            compression_ratio=1.0,
            is_xml_data=True,
            content_sha256=source_sha256,
            security_status="safe",
        )
        return SourceManifest(
            source_path=str(resolved),
            source_name=resolved.name,
            actual_extension=resolved.suffix.lower(),
            magic_bytes_hex=magic_hex,
            container_format="xml_only",
            file_size_bytes=file_size,
            source_sha256=source_sha256,
            total_entries=1,
            total_compressed_bytes=file_size,
            total_uncompressed_bytes=file_size,
            xml_entry_path=resolved.name,
            xml_entry_size=file_size,
            entries=[entry],
        )

    raise SecurityValidationError(
        f"Unsupported or unrecognized container signature ({magic_hex}) for '{resolved.name}'."
    )


def _inspect_directory_source(resolved: Path, cfg: ExtractionConfig) -> SourceManifest:
    entries: list[SourceFileEntry] = []
    xml_entry_path: str | None = None
    xml_entry_size = 0
    raster_count = 0
    raster_bytes = 0
    total_bytes = 0

    for root, _, files in os.walk(resolved):
        for fname in sorted(files):
            fpath = Path(root) / fname
            if fpath.is_symlink():
                raise SecurityValidationError(f"Symlink detected inside source directory: {fpath}")
            rel = fpath.relative_to(resolved).as_posix()
            ext = fpath.suffix.lower()
            if ext in cfg.disallowed_extensions:
                raise SecurityValidationError(f"Unexpected executable file inside source: {rel}")
            size = fpath.stat().st_size
            total_bytes += size
            is_xml = rel.lower() == "xmldata.xml" or fname.lower() == "xmldata.xml"
            is_raster = ext in _RASTER_EXTS
            guid_match = _GUID_FILENAME_RE.search(fname)
            asset_guid = guid_match.group(1).upper() if guid_match else None
            if is_xml:
                xml_entry_path = rel
                xml_entry_size = size
            if is_raster:
                raster_count += 1
                raster_bytes += size
            entries.append(
                SourceFileEntry(
                    relative_path=rel,
                    file_name=fname,
                    extension=ext,
                    compressed_size=size,
                    uncompressed_size=size,
                    is_xml_data=is_xml,
                    is_raster_asset=is_raster,
                    asset_guid=asset_guid,
                    security_status="skipped_raster" if is_raster else "safe",
                )
            )
            if len(entries) > cfg.max_archive_entries:
                raise SecurityValidationError("Directory entry limit exceeded.")

    container_format = "directory_project"
    dir_sha256 = ""
    if xml_entry_path is not None:
        dir_sha256 = compute_file_sha256(resolved / xml_entry_path, cfg.hash_chunk_size)
    elif (resolved / "Data.xml").is_file():
        container_format = "planswift_job_directory"
        xml_entry_path = "Data.xml"
        xml_entry_size = (resolved / "Data.xml").stat().st_size
        hasher = hashlib.sha256()
        for entry in entries:
            if entry.file_name.lower() == "data.xml":
                entry.is_xml_data = True
                hasher.update(entry.relative_path.encode("utf-8"))
                hasher.update((resolved / entry.relative_path).read_bytes())
        dir_sha256 = hasher.hexdigest()

    return SourceManifest(
        source_path=str(resolved),
        source_name=resolved.name,
        actual_extension=".dir",
        magic_bytes_hex="DIRECTORY",
        container_format=container_format,
        file_size_bytes=total_bytes,
        source_sha256=dir_sha256,
        total_entries=len(entries),
        total_compressed_bytes=total_bytes,
        total_uncompressed_bytes=total_bytes,
        xml_entry_path=xml_entry_path,
        xml_entry_size=xml_entry_size,
        raster_entry_count=raster_count,
        raster_total_bytes=raster_bytes,
        entries=entries,
    )


def _inspect_zip_manifest(
    resolved: Path,
    file_size: int,
    source_sha256: str,
    magic_hex: str,
    cfg: ExtractionConfig,
) -> SourceManifest:
    entries: list[SourceFileEntry] = []
    crc_groups: dict[str, list[str]] = {}
    suspicious: list[str] = []
    xml_entry_path: str | None = None
    xml_entry_size = 0
    raster_count = 0
    raster_bytes = 0
    total_comp = 0
    total_uncomp = 0

    with zipfile.ZipFile(resolved, mode="r") as zf:
        infos = zf.infolist()
        if len(infos) > cfg.max_archive_entries:
            raise SecurityValidationError(
                f"Archive entry count {len(infos)} exceeds max_archive_entries={cfg.max_archive_entries}."
            )

        for info in infos:
            rel_path = validate_archive_member_path(info.filename)
            if _is_zip_symlink(info):
                raise SecurityValidationError(f"Archive contains forbidden symlink: {rel_path}")
            if info.is_dir():
                continue

            uncomp = int(info.file_size)
            comp = int(info.compress_size)
            total_uncomp += uncomp
            total_comp += comp

            if total_uncomp > cfg.max_uncompressed_bytes:
                raise SecurityValidationError(
                    f"Archive uncompressed total ({total_uncomp} bytes) exceeds limit ({cfg.max_uncompressed_bytes})."
                )

            ratio = (uncomp / comp) if comp > 0 else (float(uncomp) if uncomp > 0 else 1.0)
            if ratio > cfg.max_compression_ratio and uncomp > 10 * 1024 * 1024:
                raise SecurityValidationError(
                    f"Potential ZIP bomb detected on '{rel_path}': ratio={ratio:.1f}x, size={uncomp}."
                )

            ext = posixpath.splitext(rel_path)[1].lower()
            fname = posixpath.basename(rel_path)

            if ext in cfg.disallowed_extensions:
                raise SecurityValidationError(f"Disallowed executable entry in archive: {rel_path}")
            if ext in _NESTED_ARCHIVE_EXTS and cfg.max_nested_archive_depth == 0:
                suspicious.append(rel_path)
                raise SecurityValidationError(f"Disallowed nested archive entry: {rel_path}")

            is_xml = fname.lower() == "xmldata.xml"
            if is_xml:
                if uncomp > cfg.max_xml_bytes:
                    raise SecurityValidationError(
                        f"XMLData.XML size ({uncomp}) exceeds max_xml_bytes={cfg.max_xml_bytes}."
                    )
                xml_entry_path = rel_path
                xml_entry_size = uncomp

            is_raster = ext in _RASTER_EXTS
            guid_match = _GUID_FILENAME_RE.search(fname)
            asset_guid = guid_match.group(1).upper() if guid_match else None
            if is_raster:
                raster_count += 1
                raster_bytes += uncomp

            crc_hex = f"{info.CRC:08X}"
            crc_groups.setdefault(f"{crc_hex}:{uncomp}", []).append(rel_path)

            mod_dt: str | None = None
            if info.date_time:
                try:
                    mod_dt = datetime(*info.date_time).isoformat()
                except ValueError:
                    mod_dt = None
            entries.append(
                SourceFileEntry(
                    relative_path=rel_path,
                    file_name=fname,
                    extension=ext,
                    compressed_size=comp,
                    uncompressed_size=uncomp,
                    compression_ratio=round(ratio, 3),
                    crc32=info.CRC,
                    modified_at=mod_dt,
                    is_xml_data=is_xml,
                    is_raster_asset=is_raster,
                    asset_guid=asset_guid,
                    security_status="skipped_raster" if is_raster else "safe",
                )
            )

    duplicates = {k: paths for k, paths in crc_groups.items() if len(paths) > 1}
    return SourceManifest(
        source_path=str(resolved),
        source_name=resolved.name,
        actual_extension=resolved.suffix.lower(),
        magic_bytes_hex=magic_hex,
        container_format="pkzip_swiftjob",
        file_size_bytes=file_size,
        source_sha256=source_sha256,
        total_entries=len(entries),
        total_compressed_bytes=total_comp,
        total_uncompressed_bytes=total_uncomp,
        xml_entry_path=xml_entry_path,
        xml_entry_size=xml_entry_size,
        raster_entry_count=raster_count,
        raster_total_bytes=raster_bytes,
        duplicate_crc_groups=duplicates,
        suspicious_entries=suspicious,
        entries=entries,
    )


def _read_order_index(item_elem: etree._Element) -> int:
    for prop in item_elem.findall("./Properties/Property"):
        if prop.attrib.get("Name") == "OrderIndex" and prop.text:
            try:
                return int(float(prop.text.strip()))
            except ValueError:
                pass
    return 10**9


def merge_planswift_job_directory_xml(root_dir: Path) -> bytes:
    """Merge an unzipped PlanSwift job directory (nested Data.xml files) into a single XMLData.xml byte payload."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)

    def _load_item(folder: Path) -> etree._Element:
        data_xml = folder / "Data.xml"
        try:
            tree = etree.parse(str(data_xml), parser)
        except etree.XMLSyntaxError as exc:
            raise SecurityValidationError(f"Unsafe or malformed XML in '{data_xml}': {exc}") from exc
        elem = tree.getroot()

        child_items: list[tuple[int, str, etree._Element]] = []
        for child_dir in folder.iterdir():
            if child_dir.is_dir() and not child_dir.is_symlink() and (child_dir / "Data.xml").is_file():
                child_elem = _load_item(child_dir)
                child_items.append((_read_order_index(child_elem), child_dir.name.lower(), child_elem))

        child_items.sort(key=lambda entry: (entry[0], entry[1]))
        for _, _, child_elem in child_items:
            elem.append(child_elem)
        return elem

    root_elem = _load_item(root_dir)
    return etree.tostring(root_elem, encoding="utf-8", xml_declaration=True)


@contextmanager
def open_xml_stream(source_path: Path, manifest: SourceManifest) -> Iterator[object]:
    """Open XMLData.XML as a read-only binary stream without extracting TIFF rasters."""
    resolved = source_path.resolve(strict=True)
    if manifest.container_format == "pkzip_swiftjob":
        if not manifest.xml_entry_path:
            raise SecurityValidationError("Archive does not contain XMLData.XML.")
        with zipfile.ZipFile(resolved, mode="r") as zf:
            info = zf.getinfo(manifest.xml_entry_path)
            validate_archive_member_path(info.filename)
            with zf.open(info, mode="r") as stream:
                yield stream
    elif manifest.container_format == "planswift_job_directory":
        yield io.BytesIO(merge_planswift_job_directory_xml(resolved))
    elif manifest.container_format == "directory_project":
        if not manifest.xml_entry_path:
            raise SecurityValidationError("Directory project does not contain XMLData.XML.")
        with (resolved / manifest.xml_entry_path).open("rb") as stream:
            yield stream
    elif manifest.container_format == "xml_only":
        with resolved.open("rb") as stream:
            yield stream
    else:
        raise SecurityValidationError(f"Cannot stream XML from container format {manifest.container_format}.")
