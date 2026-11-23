"""Registry of known PlanSwift native classes and pluggable extraction adapters."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ClassBehavior:
    """Declares how a discovered PlanSwift native Item Class behaves structurally."""

    native_class: str
    role: str  # root_job | container | page | takeoff_item | measurement_section | assembly | component | annotation | dimension | custom
    supports_digitizer_geometry: bool = False
    geometry_kind: str = "None"  # PointCollection | Polyline | Polygon | Segment | None
    known: bool = True


KNOWN_CLASS_BEHAVIORS: dict[str, ClassBehavior] = {
    "Item": ClassBehavior("Item", "container", False, "None", True),
    "Folder": ClassBehavior("Folder", "container", False, "None", True),
    "Page": ClassBehavior("Page", "page", False, "None", True),
    "Count": ClassBehavior("Count", "takeoff_item", False, "None", True),
    "Count Section": ClassBehavior("Count Section", "measurement_section", True, "PointCollection", True),
    "Linear": ClassBehavior("Linear", "takeoff_item", False, "None", True),
    "Linear Section": ClassBehavior("Linear Section", "measurement_section", True, "Polyline", True),
    "Segment": ClassBehavior("Segment", "takeoff_item", False, "None", True),
    "Segment Section": ClassBehavior("Segment Section", "measurement_section", True, "Segment", True),
    "Area": ClassBehavior("Area", "takeoff_item", False, "None", True),
    "Area Section": ClassBehavior("Area Section", "measurement_section", True, "Polygon", True),
    "Perimeter": ClassBehavior("Perimeter", "takeoff_item", False, "None", True),
    "Perimeter Section": ClassBehavior("Perimeter Section", "measurement_section", True, "Polygon", True),
    "Volume": ClassBehavior("Volume", "takeoff_item", False, "None", True),
    "Volume Section": ClassBehavior("Volume Section", "measurement_section", True, "Polygon", True),
    "Assembly": ClassBehavior("Assembly", "assembly", False, "None", True),
    "Part": ClassBehavior("Part", "component", False, "None", True),
    "Component": ClassBehavior("Component", "component", False, "None", True),
    "Annotation": ClassBehavior("Annotation", "annotation", True, "PointCollection", True),
    "Markup": ClassBehavior("Markup", "annotation", True, "Polyline", True),
    "Note": ClassBehavior("Note", "annotation", True, "PointCollection", True),
    "Bookmark": ClassBehavior("Bookmark", "annotation", False, "None", True),
    "PageLegend": ClassBehavior("PageLegend", "annotation", True, "PointCollection", True),
    "Dimension": ClassBehavior("Dimension", "dimension", True, "Segment", True),
}


@dataclass
class ExtractionRegistry:
    """Maintains adapter list and generic fallback classification for unknown PlanSwift classes."""

    class_behaviors: dict[str, ClassBehavior] = field(default_factory=lambda: dict(KNOWN_CLASS_BEHAVIORS))

    def describe_class(self, native_class: str, native_type: str = "") -> ClassBehavior:
        if native_class in self.class_behaviors:
            return self.class_behaviors[native_class]
        if native_type and native_type in self.class_behaviors:
            return self.class_behaviors[native_type]
        return ClassBehavior(
            native_class=native_class,
            role="custom",
            supports_digitizer_geometry=False,
            geometry_kind="Unknown",
            known=False,
        )
