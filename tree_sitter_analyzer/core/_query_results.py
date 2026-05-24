"""Capture/result helpers for ``QueryExecutor``."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from tree_sitter import Node

logger = logging.getLogger(__name__)

TextExtractor = Callable[[Node, str], str]


def process_captures(
    captures: Any,
    source_code: str,
    create_result_dict: Callable[[Any, str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Process query captures into standardized dictionaries."""
    processed = []

    try:
        for capture in captures:
            result_dict = _process_capture(capture, source_code, create_result_dict)
            if result_dict is not None:
                processed.append(result_dict)
    except Exception as exc:
        logger.error(f"Error in _process_captures: {exc}")

    return processed


def _process_capture(
    capture: Any,
    source_code: str,
    create_result_dict: Callable[[Any, str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    try:
        unpacked = _unpack_capture(capture)
        if unpacked is None:
            return None

        node, name = unpacked
        if node is None:
            return None
        return create_result_dict(node, name, source_code)
    except Exception as exc:
        logger.error(f"Error processing capture: {exc}")
        return None


def _unpack_capture(capture: Any) -> tuple[Any, str] | None:
    if isinstance(capture, tuple) and len(capture) == 2:
        node, name = capture
        return node, name
    if isinstance(capture, dict) and "node" in capture and "name" in capture:
        return capture["node"], capture["name"]

    logger.warning(f"Unexpected capture format: {type(capture)}")
    return None


def create_result_dict(
    node: Node, capture_name: str, source_code: str, get_node_text: TextExtractor
) -> dict[str, Any]:
    """Create a result dictionary from a Tree-sitter node."""
    try:
        node_text = get_node_text(node, source_code)
        return {
            "capture_name": capture_name,
            "node_type": getattr(node, "type", "unknown"),
            "start_point": getattr(node, "start_point", (0, 0)),
            "end_point": getattr(node, "end_point", (0, 0)),
            "start_byte": getattr(node, "start_byte", 0),
            "end_byte": getattr(node, "end_byte", 0),
            "text": node_text,
            "line_number": getattr(node, "start_point", (0, 0))[0] + 1,
            "column_number": getattr(node, "start_point", (0, 0))[1],
        }
    except Exception as exc:
        logger.error(f"Error creating result dict: {exc}")
        return {"capture_name": capture_name, "node_type": "error", "error": str(exc)}


def create_error_result(
    error_message: str, query_name: str | None = None, **kwargs: Any
) -> dict[str, Any]:
    """Create an error result dictionary."""
    result = {"captures": [], "error": error_message, "success": False}

    if query_name:
        result["query_name"] = query_name

    result.update(kwargs)
    return result


def query_statistics(stats: dict[str, Any]) -> dict[str, Any]:
    """Return query execution statistics with derived rates."""
    result = stats.copy()

    if result["total_queries"] > 0:
        result["success_rate"] = result["successful_queries"] / result["total_queries"]
        result["average_execution_time"] = (
            result["total_execution_time"] / result["total_queries"]
        )
    else:
        result["success_rate"] = 0.0
        result["average_execution_time"] = 0.0

    return result
