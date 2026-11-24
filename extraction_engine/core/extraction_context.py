"""Extraction configuration, state machine enums, checkpoints, and cancellation context."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable


class ExtractionStage(str, Enum):
    """Supported standalone pipeline execution and lifecycle states."""

    QUEUED = "QUEUED"
    PENDING = "PENDING"
    VALIDATING_ARCHIVE = "VALIDATING_ARCHIVE"
    INSPECTING_ARCHIVE = "INSPECTING_ARCHIVE"
    INSPECTING_SOURCE = "INSPECTING_SOURCE"
    BUILDING_MANIFEST = "BUILDING_MANIFEST"
    DETECTING_PROJECT = "DETECTING_PROJECT"
    PARSING_XML = "PARSING_XML"
    PARSING_PACKAGE = "PARSING_PACKAGE"
    INTERPRETING_OBJECTS = "INTERPRETING_OBJECTS"
    EXTRACTING_OBJECTS = "EXTRACTING_OBJECTS"
    RECONSTRUCTING_RELATIONSHIPS = "RECONSTRUCTING_RELATIONSHIPS"
    BUILDING_RELATIONSHIPS = "BUILDING_RELATIONSHIPS"
    PROCESSING_GEOMETRY = "PROCESSING_GEOMETRY"
    EVALUATING_FORMULAS = "EVALUATING_FORMULAS"
    CALCULATING_QUANTITIES = "CALCULATING_QUANTITIES"
    NORMALIZING = "NORMALIZING"
    NORMALIZING_DATA = "NORMALIZING_DATA"
    RECONCILING_SOURCES = "RECONCILING_SOURCES"
    VALIDATING = "VALIDATING"
    PERSISTING = "PERSISTING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"
    REQUIRES_USER_ACTION = "REQUIRES_USER_ACTION"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"


class ExtractionCancelledError(RuntimeError):
    """Raised cleanly when cancellation is requested between stages or items."""


class SecurityValidationError(ValueError):
    """Raised when an archive or XML payload violates security bounds."""


@dataclass(slots=True)
class ExtractionConfig:
    """Bounds and runtime policy for safe, standalone PlanSwift ZIP extraction."""

    allowed_source_roots: tuple[Path, ...] = field(default_factory=tuple)
    work_dir: Path = field(default_factory=lambda: Path("./extracted_tmp"))
    checkpoint_dir: Path | None = None
    max_upload_bytes: int = 1024 * 1024 * 1024  # 1 GiB
    max_archive_entries: int = 10_000
    max_uncompressed_bytes: int = 5 * 1024 * 1024 * 1024  # 5 GiB
    max_xml_bytes: int = 256 * 1024 * 1024  # 256 MiB for XMLData.XML
    max_compression_ratio: float = 100.0
    max_nested_archive_depth: int = 0
    max_xml_depth: int = 64
    max_xml_nodes: int = 2_000_000
    max_parse_seconds: float = 300.0
    extract_raster_tiffs: bool = False  # Strictly disabled: never render or inspect TIFF pixels
    disallowed_extensions: tuple[str, ...] = (
        ".exe",
        ".dll",
        ".bat",
        ".cmd",
        ".ps1",
        ".vbs",
        ".msi",
        ".scr",
        ".com",
        ".pif",
        ".sh",
    )
    parser_version: str = "2.0.0"
    hash_chunk_size: int = 4 * 1024 * 1024  # 4 MiB streaming chunks


ProgressCallback = Callable[[ExtractionStage, int, str], None]


@dataclass
class ExtractionContext:
    """Mutable runtime execution state shared safely across pipeline stages."""

    source_path: Path | None = None
    config: ExtractionConfig = field(default_factory=ExtractionConfig)
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    current_stage: ExtractionStage = ExtractionStage.PENDING
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cancel_event: threading.Event = field(default_factory=threading.Event)
    progress_callback: ProgressCallback | None = None
    completed_stages: list[str] = field(default_factory=list)
    events: list[dict[str, object]] = field(default_factory=list)
    errors: list[dict[str, object]] = field(default_factory=list)

    def check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            self.current_stage = ExtractionStage.CANCELLED
            raise ExtractionCancelledError(f"Extraction run {self.run_id} was cancelled.")

    def transition(self, stage: ExtractionStage, progress_pct: int, message: str) -> None:
        self.check_cancelled()
        self.current_stage = stage
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": stage.value,
            "progress_pct": progress_pct,
            "message": message,
        }
        self.events.append(event)
        if stage.value not in self.completed_stages and stage not in (
            ExtractionStage.PENDING,
            ExtractionStage.QUEUED,
            ExtractionStage.FAILED,
            ExtractionStage.CANCELLED,
        ):
            self.completed_stages.append(stage.value)
        if self.progress_callback is not None:
            self.progress_callback(stage, progress_pct, message)

    def record_error(self, stage: ExtractionStage, code: str, message: str, recoverable: bool = False) -> None:
        self.errors.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stage": stage.value,
                "code": code,
                "message": message,
                "recoverable": recoverable,
            }
        )
