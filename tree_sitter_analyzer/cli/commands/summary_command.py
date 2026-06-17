#!/usr/bin/env python3
"""
Summary Command

Handles summary functionality with specified element types.
"""

from typing import TYPE_CHECKING, Any

from ..._api_result_helpers import normalize_parameters
from ...constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)
from ...output_manager import output_data, output_json, output_section
from .base_command import BaseCommand

# TOON formatter for CLI output
try:
    from ...formatters.toon_formatter import ToonFormatter

    _toon_available = True
except ImportError:
    _toon_available = False

if TYPE_CHECKING:
    from ...models import AnalysisResult


def _format_element_summary_line(element: dict[str, Any]) -> str:
    """Format a single ``element`` dict as the text-summary bullet line.

    Joins ``name | L<start>-<end> | <visibility> | <modifiers>`` with
    ``|`` separators, skipping fields that are missing or sentinel
    values (``unknown``, ``None``, empty string). Used by
    ``_output_text_format`` to render each element row.

    r37dy (dogfood): lifted to flatten nesting 6 → 3.
    """
    name = str(element.get("name", "unknown"))
    parts: list[str] = [name]
    start = element.get("start_line")
    end = element.get("end_line")
    if start and end:
        parts.append(f"L{start}-{end}")
    vis = element.get("visibility")
    if vis and str(vis) not in ("unknown", "None", ""):
        parts.append(str(vis))
    modifiers = element.get("modifiers", [])
    if modifiers:
        parts.append(" ".join(str(m) for m in modifiers))
    return " | ".join(parts)


class SummaryCommand(BaseCommand):
    """Command for summary analysis with specified element types."""

    async def execute_async(self, language: str) -> int:
        analysis_result = await self.analyze_file(language)
        if not analysis_result:
            return 1

        self._output_summary_analysis(analysis_result)
        return 0

    def _output_summary_analysis(self, analysis_result: "AnalysisResult") -> None:
        """Output summary analysis results.

        r37d5 (dogfood): 138 lines → ~20 lines of phase dispatch. Phase
        helpers (``_requested_summary_types``, ``_partition_elements``,
        ``_build_summary_payload``, ``_attach_summary_envelope``,
        ``_emit_summary``) own the per-section work. ``--summary`` now
        composes from those pieces so the canonical envelope (added in
        r37z) and the toon/json/text fan-out (added in r36 and r37) all
        stay testable in isolation.
        """
        if self.args.output_format not in ("json", "toon"):
            output_section("Summary Results")

        requested_types = self._requested_summary_types()
        classes, methods, fields, imports = self._partition_elements(analysis_result)
        summary_data = self._build_summary_payload(
            analysis_result,
            requested_types=requested_types,
            classes=classes,
            methods=methods,
            fields=fields,
            imports=imports,
        )
        self._attach_summary_envelope(summary_data, analysis_result, requested_types)
        self._emit_summary(summary_data, requested_types)

    def _requested_summary_types(self) -> list[str]:
        """Return the list of summary element types from ``--summary``."""
        summary_types = getattr(self.args, "summary", "classes,methods")
        if summary_types:
            return [t.strip() for t in summary_types.split(",")]
        return ["classes", "methods"]

    @staticmethod
    def _partition_elements(
        analysis_result: "AnalysisResult",
    ) -> tuple[list[Any], list[Any], list[Any], list[Any]]:
        """Bucket analysis elements into (classes, methods, fields, imports)."""
        classes = [
            e
            for e in analysis_result.elements
            if is_element_of_type(e, ELEMENT_TYPE_CLASS)
        ]
        methods = [
            e
            for e in analysis_result.elements
            if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)
        ]
        fields = [
            e
            for e in analysis_result.elements
            if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)
        ]
        imports = [
            e
            for e in analysis_result.elements
            if is_element_of_type(e, ELEMENT_TYPE_IMPORT)
        ]
        return classes, methods, fields, imports

    @staticmethod
    def _build_summary_payload(
        analysis_result: "AnalysisResult",
        *,
        requested_types: list[str],
        classes: list[Any],
        methods: list[Any],
        fields: list[Any],
        imports: list[Any],
    ) -> dict[str, Any]:
        """Build the ``summary_data`` dict honouring ``requested_types``.

        Each section is included only when its key appears in
        ``requested_types`` — empty sections are NOT added (preserves the
        prior behaviour exactly).
        """
        summary_data: dict[str, Any] = {
            "success": True,
            "file_path": analysis_result.file_path,
            "language": analysis_result.language,
            "summary": {},
        }
        if "classes" in requested_types:
            summary_data["summary"]["classes"] = [
                {
                    "name": getattr(c, "name", "unknown"),
                    "start_line": getattr(c, "start_line", None),
                    "end_line": getattr(c, "end_line", None),
                    "visibility": getattr(c, "visibility", None),
                    "modifiers": getattr(c, "modifiers", []),
                }
                for c in classes
            ]
        if "methods" in requested_types:
            summary_data["summary"]["methods"] = [
                {
                    "name": getattr(m, "name", "unknown"),
                    "start_line": getattr(m, "start_line", None),
                    "end_line": getattr(m, "end_line", None),
                    "visibility": getattr(m, "visibility", None),
                    "modifiers": getattr(m, "modifiers", []),
                    "parameters": normalize_parameters(getattr(m, "parameters", [])),
                    "return_type": getattr(m, "return_type", None),
                }
                for m in methods
            ]
        if "fields" in requested_types:
            summary_data["summary"]["fields"] = [
                {
                    "name": getattr(f, "name", "unknown"),
                    "start_line": getattr(f, "start_line", None),
                    "end_line": getattr(f, "end_line", None),
                    "visibility": getattr(f, "visibility", None),
                    "modifiers": getattr(f, "modifiers", []),
                }
                for f in fields
            ]
        if "imports" in requested_types:
            summary_data["summary"]["imports"] = [
                {
                    "name": getattr(i, "name", "unknown"),
                    "start_line": getattr(i, "start_line", None),
                }
                for i in imports
            ]
        return summary_data

    @staticmethod
    def _attach_summary_envelope(
        summary_data: dict[str, Any],
        analysis_result: "AnalysisResult",
        requested_types: list[str],
    ) -> None:
        """Attach the canonical ``summary_line`` + ``agent_summary`` envelope.

        r37z (dogfood): ``--summary`` was the second CLI path (after
        ``--advanced`` in r37y) that emitted ``summary_line=None`` /
        ``verdict=None`` / ``agent_summary=None`` — agents reading the
        response shape couldn't tell the call succeeded vs. silently
        failed. The headline reports the requested element types so the
        caller sees what they got at a glance.
        """

        def _count(key: str) -> int:
            if key not in requested_types:
                return 0
            return len(summary_data["summary"].get(key, []))

        n_classes = _count("classes")
        n_methods = _count("methods")
        n_fields = _count("fields")
        n_imports = _count("imports")
        summary_line = (
            f"{analysis_result.file_path} ({analysis_result.language}) summary: "
            f"classes={n_classes} methods={n_methods} fields={n_fields} imports={n_imports} "
            f"types={','.join(requested_types)}"
        )
        summary_data["summary_line"] = summary_line
        summary_data["verdict"] = "INFO"
        summary_data["agent_summary"] = {
            "summary_line": summary_line,
            "next_step": (
                "Use --structure / --advanced for full details or "
                "extract_code_section (MCP) to read specific symbols."
            ),
            "verdict": "INFO",
        }

    def _emit_summary(
        self, summary_data: dict[str, Any], requested_types: list[str]
    ) -> None:
        """Dispatch to json / toon / text emitter based on ``output_format``."""
        if self.args.output_format == "json":
            output_json(summary_data)
            return
        if self.args.output_format == "toon" and _toon_available:
            use_tabs = getattr(self.args, "toon_use_tabs", False)
            formatter = ToonFormatter(use_tabs=use_tabs)
            print(formatter.format(summary_data))
            return
        self._output_text_format(summary_data, requested_types)

    def _output_text_format(self, summary_data: dict, requested_types: list) -> None:
        """Output summary in human-readable text format."""
        output_data(f"File: {summary_data['file_path']}")
        output_data(f"Language: {summary_data['language']}")

        # r37dy (dogfood): flatten nesting 6 → 3 via early-continue +
        # _format_element_summary_line helper.
        type_name_map = {
            "classes": "Classes",
            "methods": "Methods",
            "fields": "Fields",
            "imports": "Imports",
        }
        for element_type in requested_types:
            if element_type not in summary_data["summary"]:
                continue
            elements = summary_data["summary"][element_type]
            type_name = type_name_map.get(element_type, element_type)
            output_data(f"\n{type_name} ({len(elements)} items):")
            for element in elements:
                output_data(f"  - {_format_element_summary_line(element)}")
