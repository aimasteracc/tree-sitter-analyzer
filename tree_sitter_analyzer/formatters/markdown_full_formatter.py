"""Markdown full-format section rendering — extracted from markdown_formatter.py."""

from collections.abc import Callable
from typing import Any


def format_full(
    analysis_result: dict[str, Any],
    collect_images: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
) -> str:
    """Format full table output for Markdown files."""
    file_path = analysis_result.get("file_path", "")
    elements = analysis_result.get("elements", [])

    filename = file_path.split("/")[-1].split("\\")[-1]
    if filename.endswith((".md", ".markdown")):
        filename = filename.rsplit(".", 1)[0]

    output = [f"# {filename}\n"]

    # Document Overview
    output.append("## Document Overview\n")
    output.append("| Property | Value |")
    output.append("|----------|-------|")
    output.append(f"| File | {file_path} |")
    output.append("| Language | markdown |")
    output.append(f"| Total Lines | {analysis_result.get('line_count', 0)} |")
    output.append(f"| Total Elements | {len(elements)} |")
    output.append("")

    # Headers Section
    headers = [e for e in elements if e.get("type") == "heading"]
    if headers:
        output.append("## Document Structure\n")
        output.append("| Level | Header | Line |")
        output.append("|-------|--------|------|")
        for header in headers:
            level = "#" * header.get("level", 1)
            text = header.get("text", "").strip()
            line = header.get("line_range", {}).get("start", "")
            output.append(f"| {level} | {text} | {line} |")
        output.append("")

    # Links Section
    links = [
        e for e in elements if e.get("type") in ["link", "autolink", "reference_link"]
    ]
    if links:
        output.append("## Links\n")
        output.append("| Text | URL | Type | Line |")
        output.append("|------|-----|------|------|")
        for link in links:
            text = link.get("text", "")
            url = link.get("url", "") or ""
            link_type = (
                "External"
                if url and url.startswith(("http://", "https://"))
                else "Internal"
            )
            line = link.get("line_range", {}).get("start", "")
            output.append(f"| {text} | {url} | {link_type} | {line} |")
        output.append("")

    # Images Section
    images = collect_images(elements)
    if images:
        output.append("## Images\n")
        output.append("| Alt Text | URL | Line |")
        output.append("|----------|-----|------|")
        for image in images:
            alt = image.get("alt", "")
            url = image.get("url", "")
            line = image.get("line_range", {}).get("start", "")
            output.append(f"| {alt} | {url} | {line} |")
        output.append("")

    # Code Blocks Section
    code_blocks = [e for e in elements if e.get("type") == "code_block"]
    if code_blocks:
        output.append("## Code Blocks\n")
        output.append("| Language | Lines | Line Range |")
        output.append("|----------|-------|------------|")
        for cb in code_blocks:
            language = cb.get("language", "text")
            lines = cb.get("line_count", 0)
            line_range = cb.get("line_range", {})
            start = line_range.get("start", "")
            end = line_range.get("end", "")
            range_str = f"{start}-{end}" if start and end else str(start)
            output.append(f"| {language} | {lines} | {range_str} |")
        output.append("")

    # Lists Section
    lists = [e for e in elements if e.get("type") in ["list", "task_list"]]
    if lists:
        output.append("## Lists\n")
        output.append("| Type | Items | Line |")
        output.append("|------|-------|------|")
        for lst in lists:
            list_type = lst.get("list_type", "unordered")
            items = lst.get("item_count", 0)
            line = lst.get("line_range", {}).get("start", "")
            output.append(f"| {list_type} | {items} | {line} |")
        output.append("")

    # Tables Section
    tables = [e for e in elements if e.get("type") == "table"]
    if tables:
        output.append("## Tables\n")
        output.append("| Columns | Rows | Line |")
        output.append("|---------|------|------|")
        for table in tables:
            columns = table.get("column_count", 0)
            rows = table.get("row_count", 0)
            line = table.get("line_range", {}).get("start", "")
            output.append(f"| {columns} | {rows} | {line} |")
        output.append("")

    # Blockquotes Section
    blockquotes = [e for e in elements if e.get("type") == "blockquote"]
    if blockquotes:
        output.append("## Blockquotes\n")
        output.append("| Content | Line |")
        output.append("|---------|------|")
        for bq in blockquotes:
            content = (
                bq.get("text", "")[:50] + "..."
                if len(bq.get("text", "")) > 50
                else bq.get("text", "")
            )
            line = bq.get("line_range", {}).get("start", "")
            output.append(f"| {content} | {line} |")
        output.append("")

    # Horizontal Rules Section
    horizontal_rules = [e for e in elements if e.get("type") == "horizontal_rule"]
    if horizontal_rules:
        output.append("## Horizontal Rules\n")
        output.append("| Type | Line |")
        output.append("|------|------|")
        for hr in horizontal_rules:
            line = hr.get("line_range", {}).get("start", "")
            output.append(f"| Horizontal Rule | {line} |")
        output.append("")

    # HTML Elements Section
    html_elements = [
        e for e in elements if e.get("type") in ["html_block", "html_inline"]
    ]
    if html_elements:
        output.append("## HTML Elements\n")
        output.append("| Type | Content | Line |")
        output.append("|------|---------|------|")
        for html in html_elements:
            element_type = html.get("type", "")
            content = (
                html.get("name", "")[:30] + "..."
                if len(html.get("name", "")) > 30
                else html.get("name", "")
            )
            line = html.get("line_range", {}).get("start", "")
            output.append(f"| {element_type} | {content} | {line} |")
        output.append("")

    # Text Formatting Section
    formatting_elements = [
        e
        for e in elements
        if e.get("type")
        in ["strong_emphasis", "emphasis", "inline_code", "strikethrough"]
    ]
    if formatting_elements:
        output.append("## Text Formatting\n")
        output.append("| Type | Content | Line |")
        output.append("|------|---------|------|")
        for fmt in formatting_elements:
            format_type = fmt.get("type", "")
            content = (
                fmt.get("text", "")[:30] + "..."
                if len(fmt.get("text", "")) > 30
                else fmt.get("text", "")
            )
            line = fmt.get("line_range", {}).get("start", "")
            output.append(f"| {format_type} | {content} | {line} |")
        output.append("")

    # Footnotes Section
    footnotes = [
        e
        for e in elements
        if e.get("type") in ["footnote_reference", "footnote_definition"]
    ]
    if footnotes:
        output.append("## Footnotes\n")
        output.append("| Type | Content | Line |")
        output.append("|------|---------|------|")
        for fn in footnotes:
            footnote_type = fn.get("type", "")
            content = (
                fn.get("text", "")[:30] + "..."
                if len(fn.get("text", "")) > 30
                else fn.get("text", "")
            )
            line = fn.get("line_range", {}).get("start", "")
            output.append(f"| {footnote_type} | {content} | {line} |")
        output.append("")

    # Reference Definitions Section
    references = [e for e in elements if e.get("type") == "reference_definition"]
    if references:
        output.append("## Reference Definitions\n")
        output.append("| Content | Line |")
        output.append("|---------|------|")
        for ref in references:
            content = (
                ref.get("name", "")[:50] + "..."
                if len(ref.get("name", "")) > 50
                else ref.get("name", "")
            )
            line = ref.get("line_range", {}).get("start", "")
            output.append(f"| {content} | {line} |")
        output.append("")

    return "\n".join(output)
