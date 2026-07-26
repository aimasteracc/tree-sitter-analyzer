"""Generic element formatters registered by :mod:`formatter_registry`."""

import csv
import io
import json
from typing import Any

from ..models import CodeElement
from ._csv_safety import csv_safe_row
from ._formatter_interface import IFormatter


class JsonFormatter(IFormatter):
    """JSON formatter for CodeElement lists."""

    @staticmethod
    def get_format_name() -> str:
        """Return the registry key."""
        return "json"

    @staticmethod
    def _element_to_dict(element: Any) -> dict[str, Any]:
        """Convert one element to a JSON-serialisable dict."""
        elem_type = getattr(element, "element_type", "unknown")
        data: dict[str, Any] = {
            "name": element.name,
            "type": elem_type,
            "start_line": element.start_line,
            "end_line": element.end_line,
            "language": element.language,
        }
        for attribute in (
            "parameters",
            "return_type",
            "visibility",
            "modifiers",
            "tag_name",
            "selector",
            "element_class",
        ):
            if hasattr(element, attribute):
                data[attribute] = getattr(element, attribute)
        return data

    def format(self, elements: list[CodeElement]) -> str:
        """Format elements as JSON."""
        result = [self._element_to_dict(element) for element in elements]
        return json.dumps(result, indent=2, ensure_ascii=False)


class CsvFormatter(IFormatter):
    """CSV formatter for CodeElement lists."""

    @staticmethod
    def get_format_name() -> str:
        """Return the registry key."""
        return "csv"

    def format(self, elements: list[CodeElement]) -> str:
        """Format elements as CSV."""
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(
            [
                "Type",
                "Name",
                "Start Line",
                "End Line",
                "Language",
                "Visibility",
                "Parameters",
                "Return Type",
                "Modifiers",
            ]
        )
        for element in elements:
            writer.writerow(_csv_element_row(element))
        csv_content = output.getvalue()
        output.close()
        return csv_content.rstrip("\n")


def _csv_element_row(element: CodeElement) -> list[Any]:
    """Return one control-character-safe generic CSV row."""
    return csv_safe_row(
        [
            getattr(element, "element_type", "unknown"),
            element.name,
            element.start_line,
            element.end_line,
            element.language,
            getattr(element, "visibility", ""),
            str(getattr(element, "parameters", [])),
            getattr(element, "return_type", ""),
            str(getattr(element, "modifiers", [])),
        ]
    )


def _append_full_element_lines(lines: list[str], element: CodeElement) -> None:
    """Append one detailed element block."""
    lines.append(f"  {element.name}")
    lines.append(f"    Lines: {element.start_line}-{element.end_line}")
    lines.append(f"    Language: {element.language}")
    if hasattr(element, "visibility"):
        lines.append(f"    Visibility: {element.visibility}")
    if hasattr(element, "parameters") and (params := element.parameters):
        lines.append(f"    Parameters: {', '.join(map(str, params))}")
    if ret_type := getattr(element, "return_type", None):
        lines.append(f"    Return Type: {ret_type}")
    lines.append("")


class FullFormatter(IFormatter):
    """Full table formatter for CodeElement lists."""

    @staticmethod
    def get_format_name() -> str:
        """Return the registry key."""
        return "full"

    def format(self, elements: list[CodeElement]) -> str:
        """Format elements as a full text table."""
        if not elements:
            return "No elements found."

        lines = ["=" * 80, "CODE STRUCTURE ANALYSIS", "=" * 80, ""]
        element_groups: dict[str, list[CodeElement]] = {}
        for element in elements:
            element_type = getattr(element, "element_type", "unknown")
            element_groups.setdefault(element_type, []).append(element)

        for element_type, group_elements in element_groups.items():
            lines.extend([f"{element_type.upper()}S ({len(group_elements)})", "-" * 40])
            for element in group_elements:
                _append_full_element_lines(lines, element)
            lines.append("")
        return "\n".join(lines)


class CompactFormatter(IFormatter):
    """Compact formatter for CodeElement lists."""

    @staticmethod
    def get_format_name() -> str:
        """Return the registry key."""
        return "compact"

    def format(self, elements: list[CodeElement]) -> str:
        """Format elements in compact form."""
        if not elements:
            return "No elements found."

        lines = ["CODE ELEMENTS", "-" * 20]
        for element in elements:
            visibility = getattr(element, "visibility", "")
            lines.append(
                f"{self._get_visibility_symbol(visibility)} {element.name} "
                f"({getattr(element, 'element_type', 'unknown')}) "
                f"[{element.start_line}-{element.end_line}]"
            )
        return "\n".join(lines)

    @staticmethod
    def _get_visibility_symbol(visibility: str) -> str:
        """Return the compact visibility marker."""
        mapping = {"public": "+", "private": "-", "protected": "#", "package": "~"}
        return mapping.get(visibility, "?")
