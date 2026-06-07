#!/usr/bin/env python3
"""Text, compact table, and CSV rendering helpers for Markdown formatter."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from ._markdown_formatter_elements import (
    LINK_TYPES,
    LIST_TYPES,
    collect_markdown_groups,
)


def format_advanced_text(data: dict[str, Any]) -> str:
    """Format advanced analysis in text format."""
    output = ["--- Advanced Analysis Results ---"]
    output.extend(format_advanced_basic_lines(data))
    output.extend(format_advanced_metric_lines(data["document_metrics"]))
    output.extend(format_advanced_content_lines(data["content_analysis"]))
    return "\n".join(output)


def format_advanced_basic_lines(data: dict[str, Any]) -> list[str]:
    """Build basic advanced-analysis text lines."""
    return [
        f'"File: {data["file_path"]}"',
        f'"Language: {data["language"]}"',
        f'"Lines: {data["line_count"]}"',
        f'"Elements: {data["element_count"]}"',
    ]


def format_advanced_metric_lines(metrics: dict[str, Any]) -> list[str]:
    """Build document metric text lines."""
    return [
        f'"Headers: {metrics["header_count"]}"',
        f'"Max Header Level: {metrics["max_header_level"]}"',
        f'"Links: {metrics["link_count"]}"',
        f'"External Links: {metrics["external_link_count"]}"',
        f'"Images: {metrics["image_count"]}"',
        f'"Code Blocks: {metrics["code_block_count"]}"',
        f'"Code Lines: {metrics["total_code_lines"]}"',
        f'"Lists: {metrics["list_count"]}"',
        f'"Tables: {metrics["table_count"]}"',
    ]


def format_advanced_content_lines(content: dict[str, Any]) -> list[str]:
    """Build content-analysis text lines."""
    return [
        f'"Has TOC: {content["has_toc"]}"',
        f'"Has Code: {content["has_code_examples"]}"',
        f'"Has Images: {content["has_images"]}"',
        f'"Has External Links: {content["has_external_links"]}"',
        f'"Document Complexity: {content["document_complexity"]}"',
    ]


def calculate_document_complexity(
    headers: list[dict[str, Any]],
    links: list[dict[str, Any]],
    code_blocks: list[dict[str, Any]],
    tables: list[dict[str, Any]],
) -> str:
    """Calculate document complexity based on structure and content."""
    score = document_complexity_score(headers, links, code_blocks, tables)
    if score < 20:
        return "Simple"
    if score < 50:
        return "Moderate"
    if score < 100:
        return "Complex"
    return "Very Complex"


def document_complexity_score(
    headers: list[dict[str, Any]],
    links: list[dict[str, Any]],
    code_blocks: list[dict[str, Any]],
    tables: list[dict[str, Any]],
) -> int:
    """Return the numeric complexity score before label classification."""
    score = 0
    if headers:
        header_levels = [header.get("level", 1) for header in headers]
        score += len(headers) * 2
        score += max(header_levels) * 3

    score += len(links)
    score += len(code_blocks) * 5
    score += len(tables) * 3
    return score


def format_json_output(title: str, data: dict[str, Any]) -> str:
    """Format JSON output with title."""
    output = [f"--- {title} ---"]
    output.append(json.dumps(data, indent=2, ensure_ascii=False))
    return "\n".join(output)


def format_compact_output(
    analysis_result: dict[str, Any], images: list[dict[str, Any]]
) -> str:
    """Format compact table output for Markdown files."""
    elements = analysis_result.get("elements", [])
    groups = collect_markdown_groups(elements)
    output = compact_summary_lines(
        analysis_result.get("file_path", ""), groups, images, len(elements)
    )
    append_compact_headers(output, groups["headers"])
    return "\n".join(output)


def compact_summary_lines(
    file_path: str,
    groups: dict[str, list[Any]],
    images: list[dict[str, Any]],
    total_elements: int,
) -> list[str]:
    """Build compact summary table lines."""
    return [
        f"# {markdown_display_filename(file_path)}\n",
        "## Summary\n",
        "| Element Type | Count |",
        "|--------------|-------|",
        f"| Headers | {len(groups['headers'])} |",
        f"| Links | {len(groups['links'])} |",
        f"| Images | {len(images)} |",
        f"| Code Blocks | {len(groups['code_blocks'])} |",
        f"| Lists | {len(groups['lists'])} |",
        f"| Tables | {len(groups['tables'])} |",
        f"| **Total** | **{total_elements}** |",
        "",
    ]


def markdown_display_filename(file_path: str) -> str:
    """Return display filename for compact output."""
    filename = file_path.split("/")[-1].split("\\")[-1]
    if filename.endswith((".md", ".markdown")):
        return filename.rsplit(".", 1)[0]
    return filename


def append_compact_headers(output: list[str], headers: list[dict[str, Any]]) -> None:
    """Append compact document structure rows."""
    if not headers:
        return

    output.append("## Document Structure\n")
    output.append("| Level | Header | Line |")
    output.append("|-------|--------|------|")
    output.extend(compact_header_rows(headers))
    output.append("")


def compact_header_rows(headers: list[dict[str, Any]]) -> list[str]:
    """Build compact header rows."""
    rows = [compact_header_row(header) for header in headers[:20]]
    if len(headers) > 20:
        rows.append(f"| ... | ({len(headers) - 20} more) | |")
    return rows


def compact_header_row(header: dict[str, Any]) -> str:
    """Build one compact header row."""
    level = "#" * header.get("level", 1)
    text = header.get("text", "").strip()[:50]
    line = header.get("line_range", {}).get("start", "")
    return f"| {level} | {text} | {line} |"


def format_csv_output(analysis_result: dict[str, Any]) -> str:
    """Format CSV output for Markdown files."""
    output = io.StringIO()
    # escapechar handles control chars (e.g. NULL bytes) that Python 3.10's
    # csv.writer cannot quote — without it, "\x00" raises _csv.Error there.
    writer = csv.writer(output, lineterminator="\n", escapechar="\\")
    writer.writerow(
        ["Type", "Text/URL/Language", "Level/Count", "Start Line", "End Line"]
    )
    for element in analysis_result.get("elements", []):
        writer.writerow(markdown_csv_row(element))

    csv_content = output.getvalue()
    output.close()
    return csv_content.rstrip("\n")


def markdown_csv_row(element: dict[str, Any]) -> list[Any]:
    """Return one Markdown element as a CSV row."""
    elem_type = element.get("type", "unknown")
    start_line = element.get("line_range", {}).get("start", 0)
    end_line = element.get("line_range", {}).get("end", 0)

    if elem_type == "heading":
        return [
            elem_type,
            element.get("text", "")[:50],
            element.get("level", 1),
            start_line,
            end_line,
        ]
    if elem_type in LINK_TYPES:
        return link_csv_row(element, elem_type, start_line, end_line)
    if elem_type == "image":
        return image_csv_row(element, elem_type, start_line, end_line)
    if elem_type == "code_block":
        return code_block_csv_row(element, elem_type, start_line, end_line)
    if elem_type in LIST_TYPES:
        return list_csv_row(element, elem_type, start_line, end_line)
    if elem_type == "table":
        return table_csv_row(element, elem_type, start_line, end_line)
    return [elem_type, element.get("name", "")[:50], "-", start_line, end_line]


def link_csv_row(
    element: dict[str, Any], elem_type: str, start_line: int, end_line: int
) -> list[Any]:
    """Build a CSV row for a Markdown link."""
    text = element.get("text", "")[:30]
    return [elem_type, f"{text} -> {element.get('url', '')}", "-", start_line, end_line]


def image_csv_row(
    element: dict[str, Any], elem_type: str, start_line: int, end_line: int
) -> list[Any]:
    """Build a CSV row for a Markdown image."""
    alt = element.get("alt", "")[:30]
    return [elem_type, f"{alt} -> {element.get('url', '')}", "-", start_line, end_line]


def code_block_csv_row(
    element: dict[str, Any], elem_type: str, start_line: int, end_line: int
) -> list[Any]:
    """Build a CSV row for a Markdown code block."""
    return [
        elem_type,
        element.get("language", ""),
        element.get("line_count", 0),
        start_line,
        end_line,
    ]


def list_csv_row(
    element: dict[str, Any], elem_type: str, start_line: int, end_line: int
) -> list[Any]:
    """Build a CSV row for a Markdown list."""
    return [
        elem_type,
        element.get("list_type", ""),
        element.get("item_count", 0),
        start_line,
        end_line,
    ]


def table_csv_row(
    element: dict[str, Any], elem_type: str, start_line: int, end_line: int
) -> list[Any]:
    """Build a CSV row for a Markdown table."""
    cols = element.get("column_count", 0)
    rows = element.get("row_count", 0)
    return [elem_type, f"{cols}x{rows}", "-", start_line, end_line]
