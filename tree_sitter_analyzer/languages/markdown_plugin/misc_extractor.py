"""Markdown miscellaneous element extraction — extracted from extractor.py."""

from collections.abc import Callable, Iterator
from typing import Any

from ._misc_block_extractor_helpers import (
    _extract_block_quotes_process_items,
    _extract_html_blocks_process_items,
    _extract_thematic_breaks_process_items,
)
from ._misc_extractor_helpers import (
    _extract_emphasis_elements_process_items,
    _extract_footnote_elements_process_items,
)
from ._misc_inline_extractor_helpers import (
    _extract_inline_code_spans_process_items,
    _extract_inline_html_process_items,
    _extract_strikethrough_elements_process_items,
)


# Extract elements from AST: extract_block_quotes
def extract_block_quotes(
    root_node: Any,
    blockquotes: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    """Extract blockquotes."""
    _extract_block_quotes_process_items(
        root_node, blockquotes, get_node_text, traverse_nodes
    )


# Extract elements from AST: extract_thematic_breaks
def extract_thematic_breaks(
    root_node: Any,
    horizontal_rules: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    """Extract thematic breaks (horizontal rules)."""
    _extract_thematic_breaks_process_items(
        root_node, horizontal_rules, get_node_text, traverse_nodes
    )


# Extract elements from AST: extract_html_blocks
def extract_html_blocks(
    root_node: Any,
    html_elements: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    """Extract HTML block elements."""
    _extract_html_blocks_process_items(
        root_node, html_elements, get_node_text, traverse_nodes
    )


# Extract elements from AST: extract_inline_html
def extract_inline_html(
    root_node: Any,
    html_elements: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    """Extract inline HTML elements."""
    _extract_inline_html_process_items(
        root_node, html_elements, get_node_text, traverse_nodes
    )


# Extract elements from AST: extract_emphasis_elements
def extract_emphasis_elements(
    root_node: Any,
    formatting_elements: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    """Extract emphasis and strong emphasis elements."""
    _extract_emphasis_elements_process_items(
        root_node, formatting_elements, get_node_text, traverse_nodes
    )


# Extract elements from AST: extract_inline_code_spans
def extract_inline_code_spans(
    root_node: Any,
    formatting_elements: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    """Extract inline code spans."""
    _extract_inline_code_spans_process_items(
        root_node, formatting_elements, get_node_text, traverse_nodes
    )


# Extract elements from AST: extract_strikethrough_elements
def extract_strikethrough_elements(
    root_node: Any,
    formatting_elements: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    """Extract strikethrough elements."""
    _extract_strikethrough_elements_process_items(
        root_node, formatting_elements, get_node_text, traverse_nodes
    )


# Extract elements from AST: extract_footnote_elements
def extract_footnote_elements(
    root_node: Any,
    footnotes: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    """Extract footnote elements."""
    _extract_footnote_elements_process_items(
        root_node, footnotes, get_node_text, traverse_nodes
    )
