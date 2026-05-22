"""Markdown full-format section rendering — extracted from markdown_formatter.py.

r37cs (dogfood): tool flagged ``format_full`` at 218 lines critical.
Refactor splits each Markdown element category into a focused
``_render_*`` helper that takes the pre-filtered element list and a
target output buffer. ``format_full`` is now ~30 lines of category
dispatch. Behaviour preserved — table headers, columns, truncation
rules are all identical.
"""

from collections.abc import Callable
from typing import Any


def format_full(
    analysis_result: dict[str, Any],
    collect_images: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
) -> str:
    """Format full table output for Markdown files."""
    file_path = analysis_result.get("file_path", "")
    elements = analysis_result.get("elements", [])

    output: list[str] = [f"# {_strip_md_extension(file_path)}\n"]
    _render_overview(output, file_path, analysis_result, len(elements))
    _render_headers(output, _filter_by_type(elements, ("heading",)))
    _render_links(
        output, _filter_by_type(elements, ("link", "autolink", "reference_link"))
    )
    _render_images(output, collect_images(elements))
    _render_code_blocks(output, _filter_by_type(elements, ("code_block",)))
    _render_lists(output, _filter_by_type(elements, ("list", "task_list")))
    _render_tables(output, _filter_by_type(elements, ("table",)))
    _render_blockquotes(output, _filter_by_type(elements, ("blockquote",)))
    _render_horizontal_rules(output, _filter_by_type(elements, ("horizontal_rule",)))
    _render_html_elements(
        output, _filter_by_type(elements, ("html_block", "html_inline"))
    )
    _render_text_formatting(
        output,
        _filter_by_type(
            elements,
            ("strong_emphasis", "emphasis", "inline_code", "strikethrough"),
        ),
    )
    _render_footnotes(
        output,
        _filter_by_type(elements, ("footnote_reference", "footnote_definition")),
    )
    _render_references(output, _filter_by_type(elements, ("reference_definition",)))
    return "\n".join(output)


def _strip_md_extension(file_path: str) -> str:
    """Return the filename without its ``.md`` / ``.markdown`` extension."""
    filename = file_path.split("/")[-1].split("\\")[-1]
    if filename.endswith((".md", ".markdown")):
        filename = filename.rsplit(".", 1)[0]
    return filename


def _filter_by_type(
    elements: list[dict[str, Any]], types: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Return elements whose ``type`` field is one of ``types``."""
    return [e for e in elements if e.get("type") in types]


def _start_line(entry: dict[str, Any]) -> str:
    """Return the ``line_range.start`` field or empty string."""
    return str(entry.get("line_range", {}).get("start", ""))


def _truncate(text: str, limit: int) -> str:
    """Truncate ``text`` to ``limit`` chars with a ``...`` suffix when needed."""
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def _render_overview(
    output: list[str],
    file_path: str,
    analysis_result: dict[str, Any],
    element_count: int,
) -> None:
    """Document Overview table — file path, language, line count, element count."""
    output.append("## Document Overview\n")
    output.append("| Property | Value |")
    output.append("|----------|-------|")
    output.append(f"| File | {file_path} |")
    output.append("| Language | markdown |")
    output.append(f"| Total Lines | {analysis_result.get('line_count', 0)} |")
    output.append(f"| Total Elements | {element_count} |")
    output.append("")


def _render_headers(output: list[str], headers: list[dict[str, Any]]) -> None:
    """Document Structure table — Markdown headings."""
    if not headers:
        return
    output.append("## Document Structure\n")
    output.append("| Level | Header | Line |")
    output.append("|-------|--------|------|")
    for header in headers:
        level = "#" * header.get("level", 1)
        text = header.get("text", "").strip()
        output.append(f"| {level} | {text} | {_start_line(header)} |")
    output.append("")


def _render_links(output: list[str], links: list[dict[str, Any]]) -> None:
    """Links table — text + URL + External/Internal classification."""
    if not links:
        return
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
        output.append(f"| {text} | {url} | {link_type} | {_start_line(link)} |")
    output.append("")


def _render_images(output: list[str], images: list[dict[str, Any]]) -> None:
    """Images table — alt text + URL."""
    if not images:
        return
    output.append("## Images\n")
    output.append("| Alt Text | URL | Line |")
    output.append("|----------|-----|------|")
    for image in images:
        output.append(
            f"| {image.get('alt', '')} | {image.get('url', '')} | "
            f"{_start_line(image)} |"
        )
    output.append("")


def _render_code_blocks(output: list[str], code_blocks: list[dict[str, Any]]) -> None:
    """Code Blocks table — language + line count + line range."""
    if not code_blocks:
        return
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


def _render_lists(output: list[str], lists: list[dict[str, Any]]) -> None:
    """Lists table — list_type + item count."""
    if not lists:
        return
    output.append("## Lists\n")
    output.append("| Type | Items | Line |")
    output.append("|------|-------|------|")
    for lst in lists:
        list_type = lst.get("list_type", "unordered")
        items = lst.get("item_count", 0)
        output.append(f"| {list_type} | {items} | {_start_line(lst)} |")
    output.append("")


def _render_tables(output: list[str], tables: list[dict[str, Any]]) -> None:
    """Tables table — column + row counts."""
    if not tables:
        return
    output.append("## Tables\n")
    output.append("| Columns | Rows | Line |")
    output.append("|---------|------|------|")
    for table in tables:
        columns = table.get("column_count", 0)
        rows = table.get("row_count", 0)
        output.append(f"| {columns} | {rows} | {_start_line(table)} |")
    output.append("")


def _render_blockquotes(output: list[str], blockquotes: list[dict[str, Any]]) -> None:
    """Blockquotes table — truncated content + line."""
    if not blockquotes:
        return
    output.append("## Blockquotes\n")
    output.append("| Content | Line |")
    output.append("|---------|------|")
    for bq in blockquotes:
        output.append(f"| {_truncate(bq.get('text', ''), 50)} | {_start_line(bq)} |")
    output.append("")


def _render_horizontal_rules(
    output: list[str], horizontal_rules: list[dict[str, Any]]
) -> None:
    """Horizontal Rules table."""
    if not horizontal_rules:
        return
    output.append("## Horizontal Rules\n")
    output.append("| Type | Line |")
    output.append("|------|------|")
    for hr in horizontal_rules:
        output.append(f"| Horizontal Rule | {_start_line(hr)} |")
    output.append("")


def _render_html_elements(
    output: list[str], html_elements: list[dict[str, Any]]
) -> None:
    """HTML Elements table — element type + truncated name."""
    if not html_elements:
        return
    output.append("## HTML Elements\n")
    output.append("| Type | Content | Line |")
    output.append("|------|---------|------|")
    for html in html_elements:
        element_type = html.get("type", "")
        content = _truncate(html.get("name", ""), 30)
        output.append(f"| {element_type} | {content} | {_start_line(html)} |")
    output.append("")


def _render_text_formatting(
    output: list[str], formatting_elements: list[dict[str, Any]]
) -> None:
    """Text Formatting table — type + truncated text."""
    if not formatting_elements:
        return
    output.append("## Text Formatting\n")
    output.append("| Type | Content | Line |")
    output.append("|------|---------|------|")
    for fmt in formatting_elements:
        format_type = fmt.get("type", "")
        content = _truncate(fmt.get("text", ""), 30)
        output.append(f"| {format_type} | {content} | {_start_line(fmt)} |")
    output.append("")


def _render_footnotes(output: list[str], footnotes: list[dict[str, Any]]) -> None:
    """Footnotes table — reference + definition variants."""
    if not footnotes:
        return
    output.append("## Footnotes\n")
    output.append("| Type | Content | Line |")
    output.append("|------|---------|------|")
    for fn in footnotes:
        footnote_type = fn.get("type", "")
        content = _truncate(fn.get("text", ""), 30)
        output.append(f"| {footnote_type} | {content} | {_start_line(fn)} |")
    output.append("")


def _render_references(output: list[str], references: list[dict[str, Any]]) -> None:
    """Reference Definitions table — truncated name + line."""
    if not references:
        return
    output.append("## Reference Definitions\n")
    output.append("| Content | Line |")
    output.append("|---------|------|")
    for ref in references:
        content = _truncate(ref.get("name", ""), 50)
        output.append(f"| {content} | {_start_line(ref)} |")
    output.append("")
