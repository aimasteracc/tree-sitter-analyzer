#!/usr/bin/env python3
"""Markdown element grouping and image helpers."""

from __future__ import annotations

import re
from typing import Any

LINK_TYPES = {"link", "autolink", "reference_link"}
LIST_TYPES = {"list", "task_list"}
IMAGE_TYPES = {"image", "reference_image", "image_reference_definition"}
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp")


def collect_markdown_groups(elements: list[dict[str, Any]]) -> dict[str, list[Any]]:
    """Group Markdown elements by the categories used in formatter outputs."""
    return {
        "headers": [e for e in elements if e.get("type") == "heading"],
        "links": [e for e in elements if e.get("type") in LINK_TYPES],
        "code_blocks": [e for e in elements if e.get("type") == "code_block"],
        "lists": [e for e in elements if e.get("type") in LIST_TYPES],
        "tables": [e for e in elements if e.get("type") == "table"],
    }


def collect_images(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collect explicit images and image-like reference definitions."""
    images: list[dict[str, Any]] = [e for e in elements if e.get("type") in IMAGE_TYPES]
    if has_image_reference_definitions(elements):
        return images
    return promote_image_reference_definitions(elements, images)


def has_image_reference_definitions(elements: list[dict[str, Any]]) -> bool:
    """Return whether elements already contain image reference definitions."""
    return any(e.get("type") == "image_reference_definition" for e in elements)


def promote_image_reference_definitions(
    elements: list[dict[str, Any]], images: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Promote reference definitions with image-like URLs into image entries."""
    try:
        for element in elements:
            promoted = promoted_image_definition(element)
            if promoted is not None:
                images.append(promoted)
    except Exception:
        return images

    return images


def promoted_image_definition(element: dict[str, Any]) -> dict[str, Any] | None:
    """Return a promoted image definition when a reference points at an image."""
    if element.get("type") != "reference_definition":
        return None

    url, alt = reference_definition_url_alt(element)
    if not is_image_url(url):
        return None

    return {
        **element,
        "type": "image_reference_definition",
        "url": url,
        "alt": alt,
    }


def reference_definition_url_alt(element: dict[str, Any]) -> tuple[str, str]:
    """Return URL and alt text from a reference definition element."""
    url = element.get("url") or ""
    alt = element.get("alt") or ""
    if url:
        return url, alt

    name_field = (element.get("name") or "").strip()
    match = re.match(r"^\[([^\]]+)\]:\s*([^\s]+)", name_field)
    if not match:
        return url, alt

    return match.group(2), alt or match.group(1)


def is_image_url(url: str) -> bool:
    """Return whether a URL has a Markdown image-like extension."""
    return bool(url) and any(url.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)
