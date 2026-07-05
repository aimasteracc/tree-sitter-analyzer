"""Loop helpers for miscellaneous Markdown element extraction."""

import re
from collections.abc import Callable, Iterator
from typing import Any

from ...utils import log_debug
from .elements import MarkdownElement


def _extract_emphasis_elements_process_items(
    root_node: Any,
    formatting_elements: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    bold_pattern = r"\*\*([^*]+)\*\*|__([^_]+)__"
    italic_pattern = r"(?<!\*)\*([^*]+)\*(?!\*)|(?<!_)_([^_]+)_(?!_)"
    for node in traverse_nodes(root_node):
        if node.type != "inline":
            continue
        try:
            raw_text = get_node_text(node)
            if not raw_text:
                continue

            for match in re.finditer(bold_pattern, raw_text):
                content = match.group(1) or match.group(2) or ""
                bold_element = MarkdownElement(
                    name=f"Bold: {content}",
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    raw_text=match.group(0),
                    element_type="strong_emphasis",
                )
                bold_element.type = "strong_emphasis"
                bold_element.text = content
                formatting_elements.append(bold_element)

            for match in re.finditer(italic_pattern, raw_text):
                content = match.group(1) or match.group(2) or ""
                italic_element = MarkdownElement(
                    name=f"Italic: {content}",
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    raw_text=match.group(0),
                    element_type="emphasis",
                )
                italic_element.type = "emphasis"
                italic_element.text = content
                formatting_elements.append(italic_element)

        except Exception as e:
            log_debug(f"Failed to extract emphasis elements: {e}")


def _extract_footnote_elements_process_items(
    root_node: Any,
    footnotes: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    footnote_ref_pattern = r"\[\^([^\]]+)\]"
    footnote_def_pattern = r"^\[\^([^\]]+)\]:\s*(.+)$"
    for node in traverse_nodes(root_node):
        if node.type == "inline":
            _append_footnote_references(
                node, footnotes, get_node_text, footnote_ref_pattern
            )
        elif node.type == "paragraph":
            _append_footnote_definition(
                node, footnotes, get_node_text, footnote_def_pattern
            )


def _append_footnote_references(
    node: Any,
    footnotes: list[Any],
    get_node_text: Callable[..., str],
    footnote_ref_pattern: str,
) -> None:
    try:
        raw_text = get_node_text(node)
        if not raw_text:
            return

        for match in re.finditer(footnote_ref_pattern, raw_text):
            ref_id = match.group(1) or ""
            footnote_element = MarkdownElement(
                name=f"Footnote Reference: {ref_id}",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=match.group(0),
                element_type="footnote_reference",
            )
            footnote_element.type = "footnote_reference"
            footnote_element.text = ref_id
            footnotes.append(footnote_element)

    except Exception as e:
        log_debug(f"Failed to extract footnote reference: {e}")


def _append_footnote_definition(
    node: Any,
    footnotes: list[Any],
    get_node_text: Callable[..., str],
    footnote_def_pattern: str,
) -> None:
    try:
        raw_text = get_node_text(node)
        if not raw_text:
            return

        footnote_match: re.Match[str] | None = re.match(
            footnote_def_pattern, raw_text.strip(), re.MULTILINE
        )
        if not footnote_match:
            return

        ref_id = footnote_match.group(1) or ""
        content = footnote_match.group(2) or ""
        footnote_element = MarkdownElement(
            name=f"Footnote Definition: {ref_id}",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=raw_text,
            element_type="footnote_definition",
        )
        footnote_element.type = "footnote_definition"
        footnote_element.text = content
        footnotes.append(footnote_element)

    except Exception as e:
        log_debug(f"Failed to extract footnote definition: {e}")
