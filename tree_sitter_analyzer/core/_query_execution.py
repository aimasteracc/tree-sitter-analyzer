"""Execution helpers for ``QueryExecutor``."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

SafeExecuteQuery = Callable[[Any, str, Any], Any]


def execute_query_by_name(
    executor: Any,
    tree: Any,
    language: Any,
    query_name: str,
    source_code: str,
    safe_execute_query: SafeExecuteQuery,
) -> dict[str, Any]:
    """Execute a named query while preserving QueryExecutor's legacy contract."""
    start_time = time.time()
    executor.execution_stats["total_queries"] += 1

    try:
        error_result = _input_error(executor, tree, language, query_name=query_name)
        if error_result is not None:
            return error_result

        language_name = _language_name_from_object(language)
        query_string = executor.query_loader.get_query(language_name, query_name)
        if query_string is None:
            return executor.create_error_result(
                f"Query '{query_name}' not found", query_name=query_name
            )

        return _execute_query_string(
            executor,
            tree,
            language,
            query_string,
            source_code,
            safe_execute_query,
            start_time,
            query_name=query_name,
        )
    except Exception as exc:
        logger.error(f"Unexpected error in execute_query: {exc}")
        executor.execution_stats["failed_queries"] += 1
        return executor.create_error_result(
            f"Unexpected error: {str(exc)}", query_name=query_name
        )


def execute_query_by_explicit_language(
    executor: Any,
    tree: Any,
    language: Any,
    query_name: str,
    source_code: str,
    language_name: str,
    safe_execute_query: SafeExecuteQuery,
) -> dict[str, Any]:
    """Execute a named query using a caller-provided language name."""
    start_time = time.time()
    executor.execution_stats["total_queries"] += 1

    try:
        error_result = _input_error(executor, tree, language, query_name=query_name)
        if error_result is not None:
            return error_result

        lang_name = language_name.strip().lower() if language_name else "unknown"
        query_string = executor.query_loader.get_query(lang_name, query_name)
        if query_string is None:
            return executor.create_error_result(
                f"Query '{query_name}' not found", query_name=query_name
            )

        return _execute_query_string(
            executor,
            tree,
            language,
            query_string,
            source_code,
            safe_execute_query,
            start_time,
            query_name=query_name,
        )
    except Exception as exc:
        logger.error(f"Unexpected error in execute_query: {exc}")
        executor.execution_stats["failed_queries"] += 1
        return executor.create_error_result(
            f"Unexpected error: {str(exc)}", query_name=query_name
        )


def execute_raw_query_string(
    executor: Any,
    tree: Any,
    language: Any,
    query_string: str,
    source_code: str,
    safe_execute_query: SafeExecuteQuery,
) -> dict[str, Any]:
    """Execute a raw tree-sitter query string."""
    start_time = time.time()
    executor.execution_stats["total_queries"] += 1

    try:
        error_result = _input_error(executor, tree, language)
        if error_result is not None:
            return error_result

        return _execute_query_string(
            executor,
            tree,
            language,
            query_string,
            source_code,
            safe_execute_query,
            start_time,
            query_string_field=query_string,
        )
    except Exception as exc:
        logger.error(f"Unexpected error in execute_query_string: {exc}")
        executor.execution_stats["failed_queries"] += 1
        return executor.create_error_result(f"Unexpected error: {str(exc)}")


def _input_error(
    executor: Any,
    tree: Any,
    language: Any,
    query_name: str | None = None,
) -> dict[str, Any] | None:
    if tree is None:
        return executor.create_error_result("Tree is None", query_name=query_name)
    if language is None:
        return executor.create_error_result("Language is None", query_name=query_name)
    return None


def _language_name_from_object(language: Any) -> str:
    language_name = getattr(language, "name", None)
    if not language_name:
        language_name = getattr(language, "_name", None)
    if not language_name:
        language_name = (
            str(language).split(".")[-1] if hasattr(language, "__class__") else None
        )

    if not language_name or language_name.strip() == "" or language_name == "None":
        return "unknown"
    return language_name.strip().lower()


def _execute_query_string(
    executor: Any,
    tree: Any,
    language: Any,
    query_string: str,
    source_code: str,
    safe_execute_query: SafeExecuteQuery,
    start_time: float,
    query_name: str | None = None,
    query_string_field: str | None = None,
) -> dict[str, Any]:
    try:
        captures = safe_execute_query(
            language, query_string, tree.root_node, fallback_result=[]
        )
        processed_captures = _process_captures_or_error(
            executor, captures, source_code, query_name=query_name
        )
        if isinstance(processed_captures, dict):
            return processed_captures

        executor.execution_stats["successful_queries"] += 1
        execution_time = time.time() - start_time
        executor.execution_stats["total_execution_time"] += execution_time
        return _success_result(
            processed_captures,
            query_string,
            execution_time,
            query_name=query_name,
            query_string_field=query_string_field,
        )
    except Exception as exc:
        if query_name is not None:
            logger.error(f"Error executing query '{query_name}': {exc}")
            return executor.create_error_result(
                f"Query execution failed: {str(exc)}", query_name=query_name
            )

        logger.error(f"Error executing query string: {exc}")
        return executor.create_error_result(
            f"Query execution failed: {str(exc)}", query_string=query_string
        )


def _process_captures_or_error(
    executor: Any,
    captures: Any,
    source_code: str,
    query_name: str | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    try:
        return executor.process_captures(captures, source_code)
    except Exception as exc:
        if query_name is not None:
            return executor.create_error_result(
                f"Capture processing failed: {str(exc)}", query_name=query_name
            )
        return executor.create_error_result(f"Capture processing failed: {str(exc)}")


def _success_result(
    processed_captures: list[dict[str, Any]],
    query_string: str,
    execution_time: float,
    query_name: str | None = None,
    query_string_field: str | None = None,
) -> dict[str, Any]:
    result = {
        "captures": processed_captures,
        "query_string": query_string,
        "execution_time": execution_time,
        "success": True,
    }
    if query_name is not None:
        result["query_name"] = query_name
    if query_string_field is not None:
        result["query_string"] = query_string_field
    return result
