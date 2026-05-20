#!/usr/bin/env python3
"""JSON payload builders for Markdown formatter modes."""

from __future__ import annotations

from typing import Any

from ._markdown_formatter_elements import collect_markdown_groups
from ._markdown_formatter_rendering import calculate_document_complexity


def build_summary_result(
    file_path: str,
    elements: list[dict[str, Any]],
    images: list[dict[str, Any]],
    robust_counts: dict[str, int],
) -> dict[str, Any]:
    """Build the JSON summary payload for Markdown analysis."""
    groups = collect_markdown_groups(elements)
    links = links_with_robust_placeholders(groups["links"], robust_counts)
    images = images_with_robust_placeholders(images, robust_counts)

    return {
        "file_path": file_path,
        "language": "markdown",
        "summary": {
            "headers": summary_headers(groups["headers"]),
            "links": summary_links(links),
            "images": summary_images(images),
            "code_blocks": summary_code_blocks(groups["code_blocks"]),
            "lists": summary_lists(groups["lists"]),
        },
    }


def links_with_robust_placeholders(
    links: list[dict[str, Any]], robust_counts: dict[str, int]
) -> list[dict[str, Any]]:
    """Pad links when raw Markdown scanning found parser-undetected links."""
    missing = robust_counts.get("link_count", 0) - len(links)
    if missing <= 0:
        return links
    return links + [{"text": "autolink", "url": "autolink"} for _ in range(missing)]


def images_with_robust_placeholders(
    images: list[dict[str, Any]], robust_counts: dict[str, int]
) -> list[dict[str, Any]]:
    """Pad images when raw Markdown scanning found parser-undetected images."""
    expected_images = robust_counts.get("image_count", 0)
    if not expected_images or len(images) >= expected_images:
        return images
    return images + ([{"alt": "", "url": ""}] * (expected_images - len(images)))


def summary_headers(headers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build summary header entries."""
    return [
        {"name": header.get("text", "").strip(), "level": header.get("level", 1)}
        for header in headers
    ]


def summary_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build summary link entries."""
    return [
        {"text": link.get("text", ""), "url": link.get("url", "")} for link in links
    ]


def summary_images(images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build summary image entries."""
    return [
        {"alt": image.get("alt", ""), "url": image.get("url", "")} for image in images
    ]


def summary_code_blocks(code_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build summary code block entries."""
    return [
        {"language": block.get("language", ""), "lines": block.get("line_count", 0)}
        for block in code_blocks
    ]


def summary_lists(lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build summary list entries."""
    return [
        {"type": item.get("list_type", ""), "items": item.get("item_count", 0)}
        for item in lists
    ]


def build_structure_result(
    analysis_result: dict[str, Any],
    images: list[dict[str, Any]],
    robust_counts: dict[str, int],
) -> dict[str, Any]:
    """Build the JSON structure payload for Markdown analysis."""
    groups = collect_markdown_groups(analysis_result.get("elements", []))
    return {
        "file_path": analysis_result.get("file_path", ""),
        "language": "markdown",
        "headers": structure_headers(groups["headers"]),
        "links": structure_links(groups["links"]),
        "images": structure_images(images),
        "code_blocks": structure_code_blocks(groups["code_blocks"]),
        "lists": structure_lists(groups["lists"]),
        "tables": structure_tables(groups["tables"]),
        "statistics": build_structure_statistics(
            analysis_result, groups, images, robust_counts
        ),
        "analysis_metadata": analysis_result.get("analysis_metadata", {}),
    }


def structure_headers(headers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build structure header entries."""
    return [
        {
            "text": header.get("text", "").strip(),
            "level": header.get("level", 1),
            "line_range": header.get("line_range", {}),
        }
        for header in headers
    ]


def structure_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build structure link entries."""
    return [
        {
            "text": link.get("text", ""),
            "url": link.get("url", ""),
            "line_range": link.get("line_range", {}),
        }
        for link in links
    ]


def structure_images(images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build structure image entries."""
    return [
        {
            "alt": image.get("alt", ""),
            "url": image.get("url", ""),
            "line_range": image.get("line_range", {}),
        }
        for image in images
    ]


def structure_code_blocks(code_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build structure code block entries."""
    return [
        {
            "language": block.get("language", ""),
            "line_count": block.get("line_count", 0),
            "line_range": block.get("line_range", {}),
        }
        for block in code_blocks
    ]


def structure_lists(lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build structure list entries."""
    return [
        {
            "type": item.get("list_type", ""),
            "item_count": item.get("item_count", 0),
            "line_range": item.get("line_range", {}),
        }
        for item in lists
    ]


def structure_tables(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build structure table entries."""
    return [
        {
            "columns": table.get("column_count", 0),
            "rows": table.get("row_count", 0),
            "line_range": table.get("line_range", {}),
        }
        for table in tables
    ]


def build_structure_statistics(
    analysis_result: dict[str, Any],
    groups: dict[str, list[Any]],
    images: list[dict[str, Any]],
    robust_counts: dict[str, int],
) -> dict[str, Any]:
    """Build structure statistics with parser-count fallbacks."""
    return {
        "header_count": len(groups["headers"]),
        "link_count": robust_counts.get("link_count", 0) or len(groups["links"]),
        "image_count": robust_counts.get("image_count", 0) or len(images),
        "code_block_count": len(groups["code_blocks"]),
        "list_count": len(groups["lists"]),
        "table_count": len(groups["tables"]),
        "total_lines": analysis_result.get("line_count", 0),
    }


def build_advanced_result(
    analysis_result: dict[str, Any],
    images: list[dict[str, Any]],
    robust_counts: dict[str, int],
) -> dict[str, Any]:
    """Build the JSON advanced-analysis payload for Markdown analysis."""
    elements = analysis_result.get("elements", [])
    groups = collect_markdown_groups(elements)
    external_links, internal_links = partition_external_links(groups["links"])

    return {
        "file_path": analysis_result.get("file_path", ""),
        "language": "markdown",
        "line_count": analysis_result.get("line_count", 0),
        "element_count": len(elements),
        "success": True,
        "elements": elements,
        "document_metrics": build_document_metrics(
            groups, images, external_links, internal_links, robust_counts
        ),
        "content_analysis": build_content_analysis(groups, images, external_links),
    }


def partition_external_links(
    links: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split links into external HTTP(S) links and the remaining internal links."""
    external_links = [
        link
        for link in links
        if link.get("url") and link.get("url", "").startswith(("http://", "https://"))
    ]
    internal_links = [
        link
        for link in links
        if not (
            link.get("url") and link.get("url", "").startswith(("http://", "https://"))
        )
    ]
    return external_links, internal_links


def build_document_metrics(
    groups: dict[str, list[Any]],
    images: list[dict[str, Any]],
    external_links: list[dict[str, Any]],
    internal_links: list[dict[str, Any]],
    robust_counts: dict[str, int],
) -> dict[str, Any]:
    """Build aggregate Markdown document metrics."""
    header_levels = [header.get("level", 1) for header in groups["headers"]]
    avg_header_level = sum(header_levels) / len(header_levels) if header_levels else 0

    return {
        "header_count": len(groups["headers"]),
        "max_header_level": max(header_levels) if header_levels else 0,
        "avg_header_level": round(avg_header_level, 2),
        "link_count": robust_counts.get("link_count", 0) or len(groups["links"]),
        "external_link_count": len(external_links),
        "internal_link_count": len(internal_links),
        "image_count": robust_counts.get("image_count", 0) or len(images),
        "code_block_count": len(groups["code_blocks"]),
        "total_code_lines": sum(
            block.get("line_count", 0) for block in groups["code_blocks"]
        ),
        "list_count": len(groups["lists"]),
        "total_list_items": sum(item.get("item_count", 0) for item in groups["lists"]),
        "table_count": len(groups["tables"]),
    }


def build_content_analysis(
    groups: dict[str, list[Any]],
    images: list[dict[str, Any]],
    external_links: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build qualitative Markdown content-analysis flags."""
    return {
        "has_toc": any(
            "table of contents" in header.get("text", "").lower()
            for header in groups["headers"]
        ),
        "has_code_examples": len(groups["code_blocks"]) > 0,
        "has_images": len(images) > 0,
        "has_external_links": len(external_links) > 0,
        "document_complexity": calculate_document_complexity(
            groups["headers"],
            groups["links"],
            groups["code_blocks"],
            groups["tables"],
        ),
    }
