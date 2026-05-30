#!/usr/bin/env python3
"""
Analysis result model.

Contains: AnalysisResult
Helpers live in _result_helpers.py (kept private to models package).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..constants import (
    ELEMENT_TYPE_ANNOTATION,
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)
from ._result_helpers import (
    _group_elements_by_type,
    _mcp_annotation_entries,
    _mcp_class_entries,
    _mcp_field_entries,
    _mcp_import_entries,
    _mcp_metadata_block,
    _mcp_method_entries,
    _mcp_package_info,
    _to_dict_annotation_row,
    _to_dict_class_row,
    _to_dict_field_row,
    _to_dict_import_row,
    _to_dict_method_row,
)
from .base import CodeElement
from .java_models import JavaPackage

if TYPE_CHECKING:
    pass


@dataclass(frozen=False)
class AnalysisResult:
    """Comprehensive analysis result container"""

    file_path: str
    language: str = "unknown"  # Add language field for new architecture compatibility
    line_count: int = 0  # Add line_count for compatibility
    elements: Sequence[CodeElement] = field(
        default_factory=list
    )  # Generic elements for new architecture
    node_count: int = 0  # Node count for new architecture
    query_results: dict[str, Any] = field(
        default_factory=dict
    )  # Query results for new architecture
    source_code: str = ""  # Source code for new architecture
    package: JavaPackage | None = None
    # Legacy fields removed - use elements list instead
    # imports: list[JavaImport] = field(default_factory=list)
    # classes: list[JavaClass] = field(default_factory=list)
    # methods: list[JavaMethod] = field(default_factory=list)
    # fields: list[JavaField] = field(default_factory=list)
    # annotations: list[JavaAnnotation] = field(default_factory=list)
    analysis_time: float = 0.0
    success: bool = True
    error_message: str | None = None

    # Additional language-specific data
    throws: list[str] | None = None
    complexity_score: int | None = None

    # Language-specific attributes
    is_suspend: bool | None = None  # Kotlin
    receiver: str | None = None  # Go
    receiver_type: str | None = None  # Go
    is_constructor: bool | None = None  # Java
    modules: list[Any] | None = None
    impls: list[Any] | None = None
    goroutines: list[Any] | None = None
    channels: list[Any] | None = None
    defers: list[Any] | None = None

    def __post_init__(self) -> None:
        pass

    def to_dict(self) -> dict[str, Any]:
        """Convert analysis result to dictionary for serialization.

        r37e7 (dogfood): 78 lines -> ~20 lines of phase dispatch via
        ``_group_elements_by_type`` + per-type row builders.
        """
        grouped = _group_elements_by_type(self.elements or [])
        annotation_source = grouped["annotation"] or getattr(self, "annotations", [])
        packages = grouped["package"]
        return {
            "file_path": self.file_path,
            "line_count": self.line_count,
            "package": {"name": packages[0].name} if packages else None,
            "imports": [_to_dict_import_row(imp) for imp in grouped["import"]],
            "classes": [_to_dict_class_row(cls) for cls in grouped["class"]],
            "methods": [_to_dict_method_row(m) for m in grouped["function"]],
            "fields": [_to_dict_field_row(f) for f in grouped["variable"]],
            "annotations": [_to_dict_annotation_row(a) for a in annotation_source],
            "analysis_time": self.analysis_time,
            "success": self.success,
            "error_message": self.error_message,
        }

    def to_summary_dict(self, types: list[str] | None = None) -> dict[str, Any]:
        """
        Return analysis summary as a dictionary using unified elements.
        Only include specified element types (e.g., 'classes', 'methods', 'fields').
        """
        if types is None:
            types = ["classes", "methods"]  # default

        summary: dict[str, Any] = {"file_path": self.file_path, "summary_elements": []}
        elements = self.elements or []

        # Map type names to element_type constants
        type_mapping = {
            "imports": ELEMENT_TYPE_IMPORT,
            "classes": ELEMENT_TYPE_CLASS,
            "methods": ELEMENT_TYPE_FUNCTION,
            "fields": ELEMENT_TYPE_VARIABLE,
            "annotations": ELEMENT_TYPE_ANNOTATION,
        }

        # Select relevant types based on input
        target_types = set()
        if "all" in types:
            target_types = set(type_mapping.values())
        else:
            for t in types:
                if t in type_mapping:
                    target_types.add(type_mapping[t])

        # Single pass filtering
        from ..constants import get_element_type

        for element in elements:
            if get_element_type(element) in target_types:
                summary["summary_elements"].append(element.to_summary_item())

        return summary

    def get_summary(self) -> dict[str, Any]:
        """Get analysis summary statistics using unified elements"""
        elements = self.elements or []

        # Count elements by type from unified list using constants
        classes = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_CLASS)]
        methods = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)]
        fields = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)]
        imports = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_IMPORT)]
        annotations = [
            e for e in elements if is_element_of_type(e, ELEMENT_TYPE_ANNOTATION)
        ]

        return {
            "file_path": self.file_path,
            "line_count": self.line_count,
            "class_count": len(classes),
            "method_count": len(methods),
            "field_count": len(fields),
            "import_count": len(imports),
            "annotation_count": len(annotations),
            "success": self.success,
            "analysis_time": self.analysis_time,
        }

    def to_mcp_format(self) -> dict[str, Any]:
        """Produce output in MCP-compatible format.

        r37bo (dogfood): tool flagged this at 150 lines. The body was a
        single dict literal with 6 list-comprehensions + a metadata block.
        Refactor extracts each element-type entry-list to a helper plus
        the metadata count block, dropping the method to ~20 lines.
        """
        elements = self.elements or []
        return {
            "file_path": self.file_path,
            "structure": {
                "package": _mcp_package_info(self.package),
                "imports": _mcp_import_entries(elements),
                "classes": _mcp_class_entries(elements),
                "methods": _mcp_method_entries(elements),
                "fields": _mcp_field_entries(elements),
                "annotations": _mcp_annotation_entries(elements),
            },
            "metadata": _mcp_metadata_block(
                elements,
                line_count=self.line_count,
                analysis_time=self.analysis_time,
                success=self.success,
                error_message=self.error_message,
            ),
        }

    def get_statistics(self) -> dict[str, Any]:
        """Get detailed statistics (alias for get_summary)"""
        return self.get_summary()

    def to_json(self) -> dict[str, Any]:
        """Convert to JSON-serializable format (alias for to_dict)"""
        return self.to_dict()


__all__ = ["AnalysisResult"]
