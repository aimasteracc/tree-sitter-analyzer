"""Markdown link and image extraction — extracted from extractor.py."""

import re
from collections.abc import Callable, Iterator
from typing import Any

from ...utils import log_debug


# Extract elements from AST: extract_md_links
# Section: imports and module configuration
# Section: main class definition
# Section: helper functions
# Section: data processing methods
# Section: output formatting methods
# Section: validation and error handling
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
    from .extractor import MarkdownElement

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
    for node in traverse_nodes(root_node):
        if node.type == "inline":
            try:
                raw_text = get_node_text(node)
                if not raw_text:
                    continue

                inline_pattern = r'(?<!\!)\[([^\]]*)\]\(([^)]*?)(?:\s+"([^"]*)")?\)'
                matches = re.finditer(inline_pattern, raw_text)

                for match in matches:
                    text = match.group(1) or ""
                    url = match.group(2) or ""
                    title = match.group(3) or ""

                    link_signature = f"{text}|{url}"
                    if extracted_links is not None:
                        if link_signature in extracted_links:
                            continue
                        extracted_links.add(link_signature)

                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1

                    from .extractor import MarkdownElement

                    link = MarkdownElement(
                        name=text or "Link",
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=match.group(0),
                        element_type="link",
                        url=url,
                        title=title,
                    )
                    link.text = text or "Link"
                    link.type = "link"
                    links.append(link)

            except Exception as e:
                log_debug(f"Failed to extract inline link: {e}")


# Extract elements from AST: _extract_reference_links
def _extract_reference_links(
    root_node: Any,
    links: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
) -> None:
    """Extract reference links."""
    processed_ref_links: set[tuple[str, str, int]] = set()

    for node in traverse_nodes(root_node):
        if node.type == "inline":
            try:
                raw_text = get_node_text(node)
                if not raw_text:
                    continue

                ref_pattern = r"\[([^\]]*)\]\[([^\]]*)\]"
                matches = re.finditer(ref_pattern, raw_text)

                for match in matches:
                    text = match.group(1) or ""
                    ref = match.group(2) or ""

                    if match.start() > 0 and raw_text[match.start() - 1] == "!":
                        continue

                    text_before_match = raw_text[: match.start()]
                    newlines_before = text_before_match.count("\n")
                    start_line = node.start_point[0] + 1 + newlines_before

                    ref_link_key = (text, ref, start_line)

                    if ref_link_key in processed_ref_links:
                        continue
                    processed_ref_links.add(ref_link_key)

                    end_line = start_line

                    from .extractor import MarkdownElement

                    link = MarkdownElement(
                        name=text or "Reference Link",
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=match.group(0),
                        element_type="reference_link",
                    )
                    link.text = text or "Reference Link"
                    link.type = "reference_link"
                    links.append(link)

            except Exception as e:
                log_debug(f"Failed to extract reference link: {e}")


# Extract elements from AST: _extract_autolinks
def _extract_autolinks(
    root_node: Any,
    links: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
    extracted_links: set[str] | None = None,
) -> None:
    """Extract autolinks."""
    for node in traverse_nodes(root_node):
        if node.type == "inline":
            try:
                raw_text = get_node_text(node)
                if not raw_text:
                    continue

                autolink_pattern = (
                    r"<(https?://[^>]+|mailto:[^>]+|[^@\s]+@[^@\s]+\.[^@\s]+)>"
                )
                matches = re.finditer(autolink_pattern, raw_text)

                for match in matches:
                    url = match.group(1) or ""
                    full_match = match.group(0)

                    autolink_signature = f"autolink|{url}"
                    if extracted_links is not None:
                        if autolink_signature in extracted_links:
                            continue
                        extracted_links.add(autolink_signature)

                    text_before_match = raw_text[: match.start()]
                    newlines_before = text_before_match.count("\n")
                    start_line = node.start_point[0] + 1 + newlines_before
                    end_line = start_line

                    from .extractor import MarkdownElement

                    link = MarkdownElement(
                        name=url or "Autolink",
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=full_match,
                        element_type="autolink",
                        url=url,
                    )
                    link.text = url or "Autolink"
                    link.type = "autolink"
                    links.append(link)

            except Exception as e:
                log_debug(f"Failed to extract autolink: {e}")


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

                    from .extractor import MarkdownElement

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

                    from .extractor import MarkdownElement

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
    image_refs_used: set[str] = set()
    # Iterate over node
    for node in traverse_nodes(root_node):
        # Check: node.type == "inline"
        if node.type == "inline":
            try:
                raw_text = get_node_text(node)
                # Check: not raw_text
                if not raw_text:
                    continue

                ref_image_pattern = r"!\[([^\]]*)\]\[([^\]]*)\]"
                matches = re.finditer(ref_image_pattern, raw_text)

                # Iterate over match
                for match in matches:
                    ref = match.group(2) or ""
                    # Check: ref
                    if ref:
                        image_refs_used.add(ref.lower())

            except Exception as e:
                log_debug(f"Failed to scan for image references: {e}")

    image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp"}

    # Iterate over node
    for node in traverse_nodes(root_node):
        # Check: node.type == "link_reference_definition"
        if node.type == "link_reference_definition":
            try:
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                raw_text = get_node_text(node)

                ref_pattern = r'^\[([^\]]+)\]:\s*([^\s]+)(?:\s+"([^"]*)")?'
                ref_match: re.Match[str] | None = re.match(
                    ref_pattern, raw_text.strip()
                )

                # Check: ref_match
                if ref_match:
                    label = ref_match.group(1) or ""
                    url = ref_match.group(2) or ""
                    title = ref_match.group(3) or ""

                    is_used_by_image = label.lower() in image_refs_used
                    is_image_url = any(
                        url.lower().endswith(ext) for ext in image_extensions
                    )

                    # Check: is_used_by_image or is_image_url
                    if is_used_by_image or is_image_url:
                        from .extractor import MarkdownElement

                        image_ref = MarkdownElement(
                            name=f"Image Reference Definition: {label}",
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            element_type="image_reference_definition",
                            url=url,
                            alt_text=label,
                            title=title,
                        )
                        image_ref.alt = label
                        image_ref.type = "image_reference_definition"
                        images.append(image_ref)

            except Exception as e:
                log_debug(f"Failed to extract image reference definition: {e}")



