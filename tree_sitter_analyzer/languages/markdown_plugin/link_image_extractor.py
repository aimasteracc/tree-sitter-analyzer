"""Markdown link and image extraction — extracted from extractor.py."""

import re
from collections.abc import Callable, Iterator
from typing import Any

from ...utils import log_debug
from ._image_reference_extractor_helpers import (
    ImageReferenceDefinitionContext,
    _collect_image_reference_labels,
    _extract_image_reference_definitions_process_items,
)
from ._link_image_extractor_helpers import (
    _extract_autolinks_process_items,
    _extract_inline_links_process_items,
    _extract_reference_links_process_items,
)


def parse_link_components(raw_text: str) -> tuple[str, str, str]:
    """Parse ``[text](url "title")`` components from raw Markdown text."""
    pattern = r'\[([^\]]*)\]\(([^)]*?)(?:\s+"([^"]*)")?\)'
    match = re.search(pattern, raw_text)
    if not match:
        return "", "", ""
    return match.group(1) or "", match.group(2) or "", match.group(3) or ""


def parse_image_components(raw_text: str) -> tuple[str, str, str]:
    """Parse ``![alt](url "title")`` components from raw Markdown text."""
    pattern = r'!\[([^\]]*)\]\(([^)]*?)(?:\s+"([^"]*)")?\)'
    match = re.search(pattern, raw_text)
    if not match:
        return "", "", ""
    return match.group(1) or "", match.group(2) or "", match.group(3) or ""


# Extract elements from AST: extract_md_links
def extract_md_links(
    root_node: Any,
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
    extracted_links: set[str] | None = None,
) -> list[Any]:
    """Extract all link types (inline, reference, autolinks) from markdown."""

    links: list[Any] = []

    _extract_inline_links(
        root_node, links, get_node_text, traverse_nodes, extracted_links
    )
    _extract_reference_links(root_node, links, get_node_text, traverse_nodes)
    _extract_autolinks(root_node, links, get_node_text, traverse_nodes, extracted_links)

    return links


# Extract elements from AST: extract_md_images
def extract_md_images(
    root_node: Any,
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> list[Any]:
    """Extract all image types (inline, reference, ref definitions) from markdown."""

    images: list[Any] = []

    _extract_inline_images(root_node, images, get_node_text, traverse_nodes)
    _extract_reference_images(root_node, images, get_node_text, traverse_nodes)
    _extract_image_reference_definitions(
        root_node, images, get_node_text, traverse_nodes
    )

    return images


# Extract elements from AST: extract_md_link_reference_definitions
def extract_md_link_reference_definitions(
    root_node: Any,
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> list[Any]:
    """Extract link reference definitions from markdown."""
    from .elements import MarkdownElement

    references: list[Any] = []

    for node in traverse_nodes(root_node):
        if node.type == "link_reference_definition":
            try:
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                raw_text = get_node_text(node)

                reference = MarkdownElement(
                    name=raw_text or "Reference Definition",
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    element_type="reference_definition",
                )
                references.append(reference)
            except Exception as e:
                log_debug(f"Failed to extract reference definition: {e}")

    return references


# Extract elements from AST: _extract_inline_links
def _extract_inline_links(
    root_node: Any,
    links: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
    extracted_links: set[str] | None = None,
) -> None:
    """Extract inline links."""
    _extract_inline_links_process_items(
        root_node, links, get_node_text, traverse_nodes, extracted_links
    )


# Extract elements from AST: _extract_reference_links
def _extract_reference_links(
    root_node: Any,
    links: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    """Extract reference links."""
    processed_ref_links: set[tuple[str, str, int]] = set()
    _extract_reference_links_process_items(
        root_node, links, get_node_text, traverse_nodes, processed_ref_links
    )


# Extract elements from AST: _extract_autolinks
def _extract_autolinks(
    root_node: Any,
    links: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
    extracted_links: set[str] | None = None,
) -> None:
    """Extract autolinks."""
    _extract_autolinks_process_items(
        root_node, links, get_node_text, traverse_nodes, extracted_links
    )


# Extract elements from AST: _extract_inline_images
def _extract_inline_images(
    root_node: Any,
    images: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    """Extract inline images."""
    for node in traverse_nodes(root_node):
        if node.type == "inline":
            try:
                raw_text = get_node_text(node)
                if not raw_text:
                    continue

                image_pattern = r'!\[([^\]]*)\]\(([^)]*?)(?:\s+"([^"]*)")?\)'
                matches = re.finditer(image_pattern, raw_text)

                for match in matches:
                    alt_text = match.group(1) or ""
                    url = match.group(2) or ""
                    title = match.group(3) or ""

                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1

                    from .elements import MarkdownElement

                    image = MarkdownElement(
                        name=alt_text or "Image",
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=match.group(0),
                        element_type="image",
                        url=url,
                        alt_text=alt_text,
                        title=title,
                    )
                    image.alt = alt_text or ""
                    image.type = "image"
                    images.append(image)

            except Exception as e:
                log_debug(f"Failed to extract inline image: {e}")


# Extract elements from AST: _extract_reference_images
def _extract_reference_images(
    root_node: Any,
    images: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    """Extract reference images."""
    for node in traverse_nodes(root_node):
        if node.type == "inline":
            try:
                raw_text = get_node_text(node)
                if not raw_text:
                    continue

                ref_image_pattern = r"!\[([^\]]*)\]\[([^\]]*)\]"
                matches = re.finditer(ref_image_pattern, raw_text)

                # Iterate over match
                for match in matches:
                    alt_text = match.group(1) or ""

                    text_before_match = raw_text[: match.start()]
                    newlines_before = text_before_match.count("\n")
                    start_line = node.start_point[0] + 1 + newlines_before
                    end_line = start_line

                    from .elements import MarkdownElement

                    image = MarkdownElement(
                        name=alt_text or "Reference Image",
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=match.group(0),
                        element_type="reference_image",
                    )
                    image.alt = alt_text or ""
                    image.type = "reference_image"
                    images.append(image)

            except Exception as e:
                log_debug(f"Failed to extract reference image: {e}")


# Extract elements from AST: _extract_image_reference_definitions
def _extract_image_reference_definitions(
    root_node: Any,
    images: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    """Extract image reference definitions."""
    image_refs_used = _collect_image_reference_labels(
        root_node, get_node_text, traverse_nodes
    )
    image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp"}
    _extract_image_reference_definitions_process_items(
        ImageReferenceDefinitionContext(
            root_node=root_node,
            images=images,
            get_node_text=get_node_text,
            traverse_nodes=traverse_nodes,
            image_refs_used=image_refs_used,
            image_extensions=image_extensions,
        )
    )
