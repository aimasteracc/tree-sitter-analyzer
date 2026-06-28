"""Block-level miscellaneous Markdown extraction helpers."""

import re
from collections.abc import Callable, Iterator
from typing import Any

from ...utils import log_debug
from ._markdown_text_nodes import _iter_node_text
from .elements import MarkdownElement


def _extract_block_quotes_process_items(
    root_node: Any,
    blockquotes: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    text_nodes = _iter_node_text(
        root_node,
        "block_quote",
        get_node_text,
        traverse_nodes,
        "Failed to extract blockquote",
    )
    for node, raw_text in text_nodes:
        try:
            content = _clean_blockquote_content(raw_text)
            blockquote = MarkdownElement(
                name=_blockquote_name(content),
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=raw_text,
                element_type="blockquote",
            )
            blockquote.type = "blockquote"
            blockquote.text = content
            blockquotes.append(blockquote)
        except Exception as e:
            log_debug(f"Failed to extract blockquote: {e}")


def _clean_blockquote_content(raw_text: str) -> str:
    lines = raw_text.strip().split("\n")
    content_lines = [re.sub(r"^>\s?", "", line) for line in lines]
    return "\n".join(content_lines).strip()


def _blockquote_name(content: str) -> str:
    if len(content) > 50:
        return f"Blockquote: {content[:50]}..."
    return f"Blockquote: {content}"


def _extract_thematic_breaks_process_items(
    root_node: Any,
    horizontal_rules: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    text_nodes = _iter_node_text(
        root_node,
        "thematic_break",
        get_node_text,
        traverse_nodes,
        "Failed to extract horizontal rule",
    )
    for node, raw_text in text_nodes:
        try:
            hr = MarkdownElement(
                name="Horizontal Rule",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=raw_text,
                element_type="horizontal_rule",
            )
            hr.type = "horizontal_rule"
            horizontal_rules.append(hr)
        except Exception as e:
            log_debug(f"Failed to extract horizontal rule: {e}")


def _extract_html_blocks_process_items(
    root_node: Any,
    html_elements: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    text_nodes = _iter_node_text(
        root_node,
        "html_block",
        get_node_text,
        traverse_nodes,
        "Failed to extract HTML block",
    )
    for node, raw_text in text_nodes:
        try:
            tag_name = _tag_name(raw_text)
            html_element = MarkdownElement(
                name=f"HTML Block: {tag_name}",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=raw_text,
                element_type="html_block",
            )
            html_element.type = "html_block"
            html_elements.append(html_element)
        except Exception as e:
            log_debug(f"Failed to extract HTML block: {e}")


def _tag_name(raw_text: str) -> str:
    tag_match = re.search(r"<(\w+)", raw_text)
    return tag_match.group(1) if tag_match else "HTML"
