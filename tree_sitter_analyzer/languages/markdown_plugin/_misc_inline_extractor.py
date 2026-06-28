"""Inline miscellaneous Markdown extraction helpers."""

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from ...utils import log_debug
from ._markdown_text_nodes import _iter_node_text
from ._misc_block_extractor import _tag_name
from .elements import MarkdownElement


@dataclass(frozen=True)
class TextFormatMatchContext:
    """Inputs needed to append an inline text formatting match."""

    node: Any
    raw_text: str
    match: re.Match[str]
    formatting_elements: list[Any]
    label: str
    element_type: str
    content_group: int


def _extract_inline_html_process_items(
    root_node: Any,
    html_elements: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    html_pattern = r"<(?!(?:https?://|mailto:|[^@\s]+@[^@\s]+\.[^@\s]+)[^>]*>)[^>]+>"
    text_nodes = _iter_node_text(
        root_node,
        "inline",
        get_node_text,
        traverse_nodes,
        "Failed to extract inline HTML",
    )
    for node, raw_text in text_nodes:
        for match in re.finditer(html_pattern, raw_text):
            _append_inline_html_match(node, raw_text, match, html_elements)


def _append_inline_html_match(
    node: Any,
    raw_text: str,
    match: re.Match[str],
    html_elements: list[Any],
) -> None:
    try:
        tag_text = match.group(0)
        tag_name = _tag_name(tag_text)
        start_line = _match_start_line(node, raw_text, match)
        html_element = MarkdownElement(
            name=f"HTML Tag: {tag_name}",
            start_line=start_line,
            end_line=start_line,
            raw_text=tag_text,
            element_type="html_inline",
        )
        html_element.type = "html_inline"
        html_element.name = tag_name
        html_elements.append(html_element)
    except Exception as e:
        log_debug(f"Failed to extract inline HTML: {e}")


def _extract_inline_code_spans_process_items(
    root_node: Any,
    formatting_elements: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    code_pattern = r"`([^`]+)`"
    text_nodes = _iter_node_text(
        root_node,
        "inline",
        get_node_text,
        traverse_nodes,
        "Failed to extract inline code",
    )
    for node, raw_text in text_nodes:
        for match in re.finditer(code_pattern, raw_text):
            context = TextFormatMatchContext(
                node=node,
                raw_text=raw_text,
                match=match,
                formatting_elements=formatting_elements,
                label="Inline Code",
                element_type="inline_code",
                content_group=1,
            )
            _append_text_format_match(context)


def _extract_strikethrough_elements_process_items(
    root_node: Any,
    formatting_elements: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    strike_pattern = r"~~([^~]+)~~"
    text_nodes = _iter_node_text(
        root_node,
        "inline",
        get_node_text,
        traverse_nodes,
        "Failed to extract strikethrough",
    )
    for node, raw_text in text_nodes:
        for match in re.finditer(strike_pattern, raw_text):
            context = TextFormatMatchContext(
                node=node,
                raw_text=raw_text,
                match=match,
                formatting_elements=formatting_elements,
                label="Strikethrough",
                element_type="strikethrough",
                content_group=1,
            )
            _append_text_format_match(context)


def _append_text_format_match(context: TextFormatMatchContext) -> None:
    try:
        content = context.match.group(context.content_group) or ""
        start_line = _match_start_line(context.node, context.raw_text, context.match)
        element = MarkdownElement(
            name=f"{context.label}: {content}",
            start_line=start_line,
            end_line=start_line,
            raw_text=context.match.group(0),
            element_type=context.element_type,
        )
        element.type = context.element_type
        element.text = content
        context.formatting_elements.append(element)
    except Exception as e:
        log_debug(f"Failed to extract {context.element_type}: {e}")


def _match_start_line(node: Any, raw_text: str, match: re.Match[str]) -> int:
    newlines_before = raw_text[: match.start()].count("\n")
    return node.start_point[0] + 1 + newlines_before
