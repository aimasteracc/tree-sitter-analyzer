"""Markdown image reference definition extraction helpers."""

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from ...utils import log_debug
from ._markdown_text_nodes import _iter_node_text
from .elements import MarkdownElement


@dataclass(frozen=True)
class ImageReferenceDefinitionContext:
    """Inputs needed to extract image reference definitions."""

    root_node: Any
    images: list[Any]
    get_node_text: Callable[..., str]
    traverse_nodes: Callable[..., Iterator[Any]]
    image_refs_used: set[str]
    image_extensions: set[str]


def _collect_image_reference_labels(
    root_node: Any,
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> set[str]:
    image_refs_used: set[str] = set()
    ref_image_pattern = r"!\[([^\]]*)\]\[([^\]]*)\]"
    text_nodes = _iter_node_text(
        root_node,
        "inline",
        get_node_text,
        traverse_nodes,
        "Failed to scan for image references",
    )
    for _, raw_text in text_nodes:
        for match in re.finditer(ref_image_pattern, raw_text):
            ref = match.group(2) or ""
            if ref:
                image_refs_used.add(ref.lower())
    return image_refs_used


def _append_image_reference_definition(
    node: Any,
    raw_text: str,
    ref_pattern: str,
    context: ImageReferenceDefinitionContext,
) -> None:
    try:
        ref_match: re.Match[str] | None = re.match(ref_pattern, raw_text.strip())
        if not ref_match:
            return

        label = ref_match.group(1) or ""
        url = ref_match.group(2) or ""
        title = ref_match.group(3) or ""
        is_used_by_image = label.lower() in context.image_refs_used
        is_image_url = any(
            url.lower().endswith(ext) for ext in context.image_extensions
        )
        if not (is_used_by_image or is_image_url):
            return

        image_ref = MarkdownElement(
            name=f"Image Reference Definition: {label}",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=raw_text,
            element_type="image_reference_definition",
            url=url,
            alt_text=label,
            title=title,
        )
        image_ref.alt = label
        image_ref.type = "image_reference_definition"
        context.images.append(image_ref)
    except Exception as e:
        log_debug(f"Failed to extract image reference definition: {e}")


def _extract_image_reference_definitions_process_items(
    context: ImageReferenceDefinitionContext,
) -> None:
    ref_pattern = r'^\[([^\]]+)\]:\s*([^\s]+)(?:\s+"([^"]*)")?'
    text_nodes = _iter_node_text(
        context.root_node,
        "link_reference_definition",
        context.get_node_text,
        context.traverse_nodes,
        "Failed to extract image reference definition",
    )
    for node, raw_text in text_nodes:
        _append_image_reference_definition(node, raw_text, ref_pattern, context)
