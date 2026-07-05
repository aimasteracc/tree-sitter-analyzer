"""Loop helpers for Markdown link and image extraction."""

import re
from collections.abc import Callable, Iterator
from typing import Any

from ...utils import log_debug
from ._markdown_text_nodes import _iter_node_text
from .elements import MarkdownElement


def _remember_signature(signature: str, seen: set[str] | None) -> bool:
    """Return true when a signature has not been processed before."""
    if seen is None:
        return True
    if signature in seen:
        return False
    seen.add(signature)
    return True


def _append_inline_link_match(
    node: Any,
    match: re.Match[str],
    links: list[Any],
    extracted_links: set[str] | None,
) -> None:
    try:
        text = match.group(1) or ""
        url = match.group(2) or ""
        title = match.group(3) or ""

        link_signature = f"{text}|{url}"
        if not _remember_signature(link_signature, extracted_links):
            return

        link = MarkdownElement(
            name=text or "Link",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
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


def _extract_inline_links_process_items(
    root_node: Any,
    links: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
    extracted_links: set[str] | None,
) -> None:
    inline_pattern = r'(?<!\!)\[([^\]]*)\]\(([^)]*?)(?:\s+"([^"]*)")?\)'
    text_nodes = _iter_node_text(
        root_node,
        "inline",
        get_node_text,
        traverse_nodes,
        "Failed to extract inline link",
    )
    for node, raw_text in text_nodes:
        for match in re.finditer(inline_pattern, raw_text):
            _append_inline_link_match(node, match, links, extracted_links)


def _append_reference_link_match(
    node: Any,
    raw_text: str,
    match: re.Match[str],
    links: list[Any],
    processed_ref_links: set[tuple[str, str, int]],
) -> None:
    try:
        if match.start() > 0 and raw_text[match.start() - 1] == "!":
            return

        text = match.group(1) or ""
        ref = match.group(2) or ""
        newlines_before = raw_text[: match.start()].count("\n")
        start_line = node.start_point[0] + 1 + newlines_before
        ref_link_key = (text, ref, start_line)
        if ref_link_key in processed_ref_links:
            return
        processed_ref_links.add(ref_link_key)

        link = MarkdownElement(
            name=text or "Reference Link",
            start_line=start_line,
            end_line=start_line,
            raw_text=match.group(0),
            element_type="reference_link",
        )
        link.text = text or "Reference Link"
        link.type = "reference_link"
        links.append(link)
    except Exception as e:
        log_debug(f"Failed to extract reference link: {e}")


def _extract_reference_links_process_items(
    root_node: Any,
    links: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
    processed_ref_links: set[tuple[str, str, int]],
) -> None:
    ref_pattern = r"\[([^\]]*)\]\[([^\]]*)\]"
    text_nodes = _iter_node_text(
        root_node,
        "inline",
        get_node_text,
        traverse_nodes,
        "Failed to extract reference link",
    )
    for node, raw_text in text_nodes:
        for match in re.finditer(ref_pattern, raw_text):
            _append_reference_link_match(
                node, raw_text, match, links, processed_ref_links
            )


def _append_autolink_match(
    node: Any,
    raw_text: str,
    match: re.Match[str],
    links: list[Any],
    extracted_links: set[str] | None,
) -> None:
    try:
        url = match.group(1) or ""
        autolink_signature = f"autolink|{url}"
        if not _remember_signature(autolink_signature, extracted_links):
            return

        newlines_before = raw_text[: match.start()].count("\n")
        start_line = node.start_point[0] + 1 + newlines_before
        link = MarkdownElement(
            name=url or "Autolink",
            start_line=start_line,
            end_line=start_line,
            raw_text=match.group(0),
            element_type="autolink",
            url=url,
        )
        link.text = url or "Autolink"
        link.type = "autolink"
        links.append(link)
    except Exception as e:
        log_debug(f"Failed to extract autolink: {e}")


def _extract_autolinks_process_items(
    root_node: Any,
    links: list[Any],
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
    extracted_links: set[str] | None,
) -> None:
    autolink_pattern = r"<(https?://[^>]+|mailto:[^>]+|[^@\s]+@[^@\s]+\.[^@\s]+)>"
    text_nodes = _iter_node_text(
        root_node,
        "inline",
        get_node_text,
        traverse_nodes,
        "Failed to extract autolink",
    )
    for node, raw_text in text_nodes:
        for match in re.finditer(autolink_pattern, raw_text):
            _append_autolink_match(node, raw_text, match, links, extracted_links)
