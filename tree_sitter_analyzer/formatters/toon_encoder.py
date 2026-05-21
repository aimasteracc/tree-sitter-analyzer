#!/usr/bin/env python3
"""
TOON (Token-Oriented Object Notation) Encoder

Low-level encoding primitives for TOON format.
Provides efficient encoding of data structures for LLM consumption.

Uses iterative approach (explicit stack) instead of recursion for safety.
"""

import json
import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from ._toon_encoder_string_helpers import escape_string, needs_quotes
from ._toon_encoder_table_helpers import (
    encode_array_table_lines,
    encode_public_array_table,
)
from ._toon_encoder_task_helpers import build_task_handlers

logger = logging.getLogger(__name__)


class ToonEncodeError(Exception):
    """
    Exception raised when TOON encoding fails.

    Attributes:
        message: Description of the error
        data: The data that caused the error (if available)
        cause: The original exception that caused this error
    """

    def __init__(self, message: str, data: Any = None, cause: Exception | None = None):
        """
        Initialize ToonEncodeError.

        Args:
            message: Error message
            data: Data that caused the error (optional)
            cause: Original exception (optional)
        """
        super().__init__(message)
        self.message = message
        self.data = data
        self.cause = cause

    def __str__(self) -> str:
        """Return string representation of the error."""
        base = f"ToonEncodeError: {self.message}"
        if self.cause:
            base += f" (caused by: {type(self.cause).__name__}: {self.cause})"
        return base


class _TaskType(Enum):
    """Types of encoding tasks for the iterative encoder."""

    ENCODE_VALUE = auto()  # Encode a primitive value
    ENCODE_DICT_START = auto()  # Start encoding a dict
    ENCODE_DICT_KEY = auto()  # Encode a dict key-value pair
    ENCODE_DICT_END = auto()  # Finish encoding a dict
    ENCODE_LIST_START = auto()  # Start encoding a list
    ENCODE_LIST_ITEM = auto()  # Encode a list item
    ENCODE_LIST_END = auto()  # Finish encoding a list
    ENCODE_ARRAY_TABLE = auto()  # Encode homogeneous array as table


@dataclass
class _Task:
    """A single encoding task for the iterative encoder."""

    task_type: _TaskType
    data: Any
    indent: int
    key: str | None = None  # For dict key-value pairs
    output_index: int = -1  # Index in output list where result goes
    is_inline: bool = False  # For inline list values


# Threshold above which a flat ``list[str]`` renders as a single-column
# TOON array-table instead of an inline ``[a,b,c]`` blob.
#
# Short lists (≤5) keep the inline form because they fit comfortably on one
# line and the table header (`[N]{col}:`) would cost more tokens than it
# saves. Long lists are switched to the table form so they don't collapse
# into a long, hard-to-scan, easy-to-truncate inline value.
#
# Round-14b bug M9: with the inline form, downstream tooling truncated
# ``downstream_files: [a,b,c,...,z]`` mid-content because it looked like
# a single long string. The table form makes one item per line, which is
# both more scannable and more truncation-friendly (truncates at row
# boundaries, not mid-string).
_FLAT_STR_LIST_THRESHOLD = 5


_LIST_STR_COLUMN_NAMES = {
    # Map common dict-key suffixes to the column label we use when the
    # value is a flat ``list[str]`` rendered as a single-column array-table.
    "files": "path",
    "_files": "path",
    "paths": "path",
    "_paths": "path",
    "modules": "module",
    "imports": "import",
}


def _pick_list_str_column_name(key: str | None) -> str:
    """Choose a single-column header for a flat ``list[str]`` value.

    Uses the parent dict key to pick a semantic label (``path`` for
    ``downstream_files``, ``import`` for ``imports``, etc.). Falls back
    to ``item`` for unknown keys so the schema is always well-formed.
    """
    if not key:
        return "item"
    for suffix, column in _LIST_STR_COLUMN_NAMES.items():
        if key.endswith(suffix):
            return column
    return "item"


class ToonEncoder:
    """
    Low-level encoder for TOON format.

    Uses iterative approach with explicit stack for safety.
    This prevents Python stack overflow on deeply nested structures.

    Features:
        - Circular reference detection
        - Maximum depth limit (enforced without recursion)
        - JSON fallback on encoding errors
        - Detailed error logging
    """

    MAX_DEPTH = 100

    def __init__(
        self,
        use_tabs: bool = False,
        fallback_to_json: bool = True,
        max_depth: int = 100,
        normalize_paths: bool = True,
    ):
        """
        Initialize TOON encoder.

        Args:
            use_tabs: Use tab delimiters instead of commas for further compression
            fallback_to_json: If True, fall back to JSON on encoding errors
            max_depth: Maximum nesting depth (default: 100)
            normalize_paths: If True, convert Windows backslashes to forward slashes
                           in file paths to reduce token consumption (~10% savings)
        """
        self.use_tabs = use_tabs
        self.delimiter = "\t" if use_tabs else ","
        self.fallback_to_json = fallback_to_json
        self.max_depth = max_depth
        self.normalize_paths = normalize_paths

    def encode(self, data: Any, indent: int = 0) -> str:
        """
        Encode arbitrary data as TOON format using iterative approach.

        This method uses an explicit stack instead of recursion to prevent
        Python stack overflow on deeply nested structures.

        Args:
            data: Data to encode (dict, list, or primitive)
            indent: Initial indentation level

        Returns:
            TOON-formatted string

        Raises:
            ToonEncodeError: If encoding fails and fallback_to_json is False
        """
        try:
            return self._encode_iterative(data, indent)
        except ToonEncodeError:
            if self.fallback_to_json:
                logger.warning("TOON encoding failed, falling back to JSON format")
                return self._fallback_to_json(data)
            raise
        except Exception as e:
            logger.error(f"TOON encoding failed: {e}", exc_info=True)
            if self.fallback_to_json:
                logger.warning("Falling back to JSON format")
                return self._fallback_to_json(data)
            raise ToonEncodeError(
                "Failed to encode data as TOON", data=data, cause=e
            ) from e

    def _encode_iterative(self, data: Any, initial_indent: int = 0) -> str:
        """
        Iterative encoding using explicit stack.

        Args:
            data: Data to encode
            initial_indent: Starting indentation level

        Returns:
            TOON-formatted string

        Raises:
            ToonEncodeError: On circular reference or max depth exceeded
        """
        seen_ids: set[int] = set()
        output: list[str] = []
        stack: list[_Task] = []

        if isinstance(data, dict):
            stack.append(_Task(_TaskType.ENCODE_DICT_START, data, initial_indent))
        elif isinstance(data, list):
            stack.append(_Task(_TaskType.ENCODE_LIST_START, data, initial_indent))
        else:
            return self.encode_value(data, seen_ids)

        task_handlers = build_task_handlers(_TaskType, self, stack, output, seen_ids)

        while stack:
            task = stack.pop()

            if task.indent > self.max_depth:
                raise ToonEncodeError(
                    f"Maximum nesting depth ({self.max_depth}) exceeded",
                    data="<truncated>",
                )

            task_handlers[task.task_type](task)

        return "\n".join(output)

    def _handle_dict_start(
        self,
        task: _Task,
        stack: list[_Task],
        output: list[str],
        seen_ids: set[int],
    ) -> None:
        """Handle start of dict encoding."""
        data = task.data
        obj_id = id(data)

        # Circular reference — degrade gracefully so the encoder still
        # produces a valid (truncated) TOON string instead of raising and
        # taking down the whole response. Callers that need the strict
        # behavior can still see ``"[...]"`` in the output.
        if obj_id in seen_ids:
            indent_str = "  " * task.indent
            output.append(f"{indent_str}[...]")
            return
        seen_ids.add(obj_id)

        # Add end task first (will be processed last)
        stack.append(_Task(_TaskType.ENCODE_DICT_END, data, task.indent))

        # Add key tasks in reverse order (so first key is processed first)
        items = list(data.items())
        for key, value in reversed(items):
            stack.append(
                _Task(
                    _TaskType.ENCODE_DICT_KEY,
                    value,
                    task.indent,
                    key=key,
                )
            )

    def _handle_dict_key(
        self,
        task: _Task,
        stack: list[_Task],
        output: list[str],
        seen_ids: set[int],
    ) -> None:
        """Handle encoding of a dict key-value pair."""
        key = task.key
        value = task.data
        indent = task.indent
        indent_str = "  " * indent

        if isinstance(value, dict):
            # Nested dict
            output.append(f"{indent_str}{key}:")
            stack.append(_Task(_TaskType.ENCODE_DICT_START, value, indent + 1))
        elif isinstance(value, list) and value and isinstance(value[0], dict):
            # Homogeneous array of dicts - use table format
            output.append(f"{indent_str}{key}:")
            stack.append(_Task(_TaskType.ENCODE_ARRAY_TABLE, value, indent + 1))
        elif (
            isinstance(value, list)
            and len(value) > _FLAT_STR_LIST_THRESHOLD
            and all(isinstance(item, str) for item in value)
        ):
            # Long flat list[str] — render as single-column TOON array-table
            # instead of an inline ``[a,b,c,...]`` blob. The inline form
            # collapses into one long, hard-to-scan, easy-to-truncate value
            # (round-14b M9). One item per line is both more scannable and
            # truncation-friendly (truncates at row boundaries).
            column = _pick_list_str_column_name(key)
            output.append(f"{indent_str}{key}:")
            child_indent_str = "  " * (indent + 1)
            output.append(f"{child_indent_str}[{len(value)}]{{{column}}}:")
            row_indent_str = "  " * (indent + 2)
            for item in value:
                output.append(f"{row_indent_str}{self.encode_value(item, seen_ids)}")
        elif isinstance(value, list):
            # Short list or non-string list - encode inline
            encoded_list = self._encode_simple_list(value, seen_ids)
            output.append(f"{indent_str}{key}: {encoded_list}")
        else:
            output.append(f"{indent_str}{key}: {self.encode_value(value, seen_ids)}")

    def _handle_list_start(
        self,
        task: _Task,
        stack: list[_Task],
        output: list[str],
        seen_ids: set[int],
    ) -> None:
        """Handle start of list encoding."""
        items = task.data

        if not items:
            output.append("[]")
            return

        # Use the array-table format ONLY for *homogeneous* dict arrays
        # (every item is a dict AND shares the same key set). A mixed-key
        # list like ``[{"a": 1}, {"b": 2}]`` would silently drop entries
        # under the table schema, so encode those inline instead.
        if items and all(isinstance(item, dict) for item in items):
            first_keys = tuple(items[0].keys())
            if all(tuple(item.keys()) == first_keys for item in items):
                stack.append(_Task(_TaskType.ENCODE_ARRAY_TABLE, items, task.indent))
                return

        obj_id = id(items)

        # Circular list — degrade gracefully (see _handle_dict_start).
        if obj_id in seen_ids:
            output.append("[...]")
            return
        seen_ids.add(obj_id)

        # For simple lists, encode inline
        encoded = self._encode_simple_list(items, seen_ids)
        output.append(encoded)

        seen_ids.discard(obj_id)

    def _handle_list_item(
        self,
        task: _Task,
        stack: list[_Task],
        output: list[str],
        seen_ids: set[int],
    ) -> None:
        """Handle encoding of a list item."""
        # This is used for complex nested structures
        item = task.data
        indent = task.indent
        indent_str = "  " * indent

        if isinstance(item, dict):
            stack.append(_Task(_TaskType.ENCODE_DICT_START, item, indent))
        elif isinstance(item, list):
            stack.append(_Task(_TaskType.ENCODE_LIST_START, item, indent))
        else:
            output.append(f"{indent_str}{self.encode_value(item, seen_ids)}")

    def _handle_array_table(
        self,
        task: _Task,
        output: list[str],
        seen_ids: set[int],
    ) -> None:
        """Handle encoding of homogeneous array as table."""
        items = task.data
        indent = task.indent

        if not items:
            output.append("[]")
            return

        obj_id = id(items)

        # Circular array-table — degrade gracefully (see _handle_dict_start).
        if obj_id in seen_ids:
            indent_str = "  " * indent
            output.append(f"{indent_str}[...]")
            return
        seen_ids.add(obj_id)

        try:
            schema = list(items[0].keys())
            indent_str = "  " * indent
            output.extend(
                encode_array_table_lines(
                    items,
                    schema,
                    self.delimiter,
                    indent_str,
                    self.encode_value,
                    seen_ids,
                )
            )
        finally:
            seen_ids.discard(obj_id)

    def _encode_simple_list(self, items: list[Any], seen_ids: set[int]) -> str:
        """
        Encode a simple list (non-homogeneous dicts) inline.

        Args:
            items: List items to encode
            seen_ids: Set of seen object IDs for circular reference detection

        Returns:
            Encoded list string like [item1,item2,item3]
        """
        if not items:
            return "[]"

        encoded_items = []
        for item in items:
            if not isinstance(item, list | dict):
                encoded_items.append(self.encode_value(item, seen_ids))
                continue

            obj_id = id(item)
            if obj_id in seen_ids:
                # Degrade gracefully on nested cycles (see _handle_dict_start).
                encoded_items.append("[...]")
                continue

            seen_ids.add(obj_id)
            try:
                if isinstance(item, list):
                    encoded_item = self._encode_simple_list(item, seen_ids)
                else:
                    encoded_item = self._encode_inline_dict(item, seen_ids)
                encoded_items.append(encoded_item)
            finally:
                seen_ids.discard(obj_id)

        return f"[{self.delimiter.join(encoded_items)}]"

    def _encode_inline_dict(self, data: dict[str, Any], seen_ids: set[int]) -> str:
        """
        Encode a dict inline (for dicts inside simple lists).

        Args:
            data: Dict to encode
            seen_ids: Set of seen object IDs

        Returns:
            Encoded dict string
        """
        if not data:
            return "{}"

        pairs = []
        for key, value in data.items():
            if not isinstance(value, dict | list):
                pairs.append(f"{key}:{self.encode_value(value, seen_ids)}")
                continue

            obj_id = id(value)
            if obj_id in seen_ids:
                pairs.append(f"{key}:<circular>")
                continue

            seen_ids.add(obj_id)
            try:
                if isinstance(value, dict):
                    encoded_value = self._encode_inline_dict(value, seen_ids)
                else:
                    encoded_value = self._encode_simple_list(value, seen_ids)
                pairs.append(f"{key}:{encoded_value}")
            finally:
                seen_ids.discard(obj_id)

        return "{" + self.delimiter.join(pairs) + "}"

    def _fallback_to_json(self, data: Any) -> str:
        """
        Fall back to JSON encoding when TOON encoding fails.

        Args:
            data: Data to encode as JSON

        Returns:
            JSON-formatted string
        """
        try:
            return json.dumps(data, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            logger.error(f"JSON fallback also failed: {e}")
            return f"# Encoding failed: {e}\n{{}}"

    def encode_value(self, value: Any, seen_ids: set[int] | None = None) -> str:
        """
        Encode single value for TOON output.

        Args:
            value: Value to encode
            seen_ids: Set of seen object IDs for circular reference detection

        Returns:
            String representation
        """
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int | float):
            return str(value)
        if isinstance(value, str):
            return self._encode_string(value)
        if isinstance(value, dict):
            if seen_ids is None:
                seen_ids = set()
            return self._encode_inline_dict(value, seen_ids)
        if isinstance(value, list):
            if seen_ids is None:
                seen_ids = set()
            return self._encode_simple_list(value, seen_ids)
        return str(value)

    def _encode_string(self, s: str) -> str:
        """
        Encode string with proper escaping.

        Quotes are added when the string contains TOON special characters.
        Escape sequences are applied to prevent format corruption.

        When normalize_paths is enabled, Windows-style backslash paths are
        converted to forward slashes to reduce token consumption (~10% savings).

        Args:
            s: String to encode

        Returns:
            Escaped and quoted string if necessary
        """
        # Normalize paths if enabled (convert Windows backslashes to forward slashes)
        # This reduces token consumption by ~10% for path-heavy outputs
        if self.normalize_paths:
            s = self._normalize_path_string(s)

        return escape_string(s) if needs_quotes(s, self.delimiter) else s

    def _normalize_path_string(self, s: str) -> str:
        """
        Normalize Windows-style paths to forward slashes.

        This is a token optimization that reduces ~10% token consumption
        by converting backslash escapes (\\\\) to single forward slashes (/).

        Detection heuristics (strict):
        - Must start with drive letter (C:\\) or UNC path (\\\\server)
        - Or be a relative path starting with .\\ or ..\

        Args:
            s: String that may contain Windows paths

        Returns:
            String with normalized paths
        """
        # Skip if no backslashes
        if "\\" not in s:
            return s

        # Detect if this looks like a Windows path (strict detection)
        # Only normalize paths that clearly look like file paths
        import re

        # Pattern for Windows paths (strict):
        # - Drive letter paths: C:\path, D:\folder\file.txt
        # - UNC paths: \\server\share
        # - Relative paths: .\file, ..\folder
        is_windows_path = bool(
            re.match(r"^[A-Za-z]:\\[A-Za-z0-9_\-\.\\/]+", s)  # C:\path\to\file
            or re.match(r"^\\\\[A-Za-z0-9_\-\.]+\\", s)  # \\server\share
            or re.match(r"^\.{1,2}\\[A-Za-z0-9_\-\.\\/]+", s)  # .\path or ..\path
        )

        if is_windows_path:
            # This looks like a Windows path, normalize it
            return s.replace("\\", "/")

        return s

    # Convenience methods for backward compatibility

    def encode_dict(self, data: dict[str, Any], indent: int = 0) -> str:
        """
        Encode dictionary as TOON object.

        This is a convenience method that delegates to the iterative encoder.

        Args:
            data: Dictionary to encode
            indent: Indentation level

        Returns:
            TOON-formatted string
        """
        return self._encode_iterative(data, indent)

    def encode_list(self, items: list[Any], indent: int = 0) -> str:
        """
        Encode list as TOON array.

        This is a convenience method that delegates to the iterative encoder.

        Args:
            items: List to encode
            indent: Indentation level

        Returns:
            TOON-formatted string
        """
        return self._encode_iterative(items, indent)

    def encode_array_header(self, count: int, schema: list[str] | None = None) -> str:
        """
        Generate array header with optional schema.

        Examples:
            - Simple array: [5]:
            - Typed array: [3]{name,visibility,lines}:

        Args:
            count: Number of items in array
            schema: Optional field schema

        Returns:
            Header string
        """
        if schema:
            schema_str = self.delimiter.join(schema)
            return f"[{count}]{{{schema_str}}}:"
        return f"[{count}]:"

    def encode_array_table(
        self,
        items: list[dict[str, Any]],
        schema: list[str] | None = None,
        indent: int = 0,
    ) -> str:
        """
        Encode homogeneous array as compact table.

        Format:
            [count]{field1,field2,field3}:
              value1,value2,value3
              value4,value5,value6

        Args:
            items: List of dictionaries with similar keys
            schema: Optional explicit schema order; if None, inferred from first item
            indent: Indentation level

        Returns:
            TOON-formatted table string
        """
        return encode_public_array_table(
            items,
            schema,
            indent,
            self.delimiter,
            self.encode_value,
            self._infer_schema,
        )

    def _infer_schema(self, items: list[dict[str, Any]]) -> list[str]:
        """
        Infer common schema from array items.

        Uses the keys from the first item as the schema.

        Args:
            items: List of dictionaries

        Returns:
            List of field names
        """
        if not items:
            return []

        # Use first item's keys as schema
        return list(items[0].keys())

    def encode_safe(self, data: Any, indent: int = 0) -> str:
        """
        Safely encode data, always returning a string.

        This method never raises exceptions - on any error it falls back to JSON
        or returns an error message.

        Args:
            data: Data to encode
            indent: Indentation level

        Returns:
            Encoded string (TOON, JSON, or error message)
        """
        try:
            return self.encode(data, indent)
        except ToonEncodeError as e:
            logger.error(f"TOON encoding error: {e}")
            if self.fallback_to_json:
                return self._fallback_to_json(data)
            return f"# ToonEncodeError: {e.message}\n{{}}"
        except Exception as e:
            logger.error(f"Unexpected error during TOON encoding: {e}", exc_info=True)
            if self.fallback_to_json:
                return self._fallback_to_json(data)
            return f"# Encoding error: {e}\n{{}}"

    @staticmethod
    def detect_circular_reference(data: Any, seen: set[int] | None = None) -> bool:
        """
        Check if data contains circular references using iterative approach.

        Args:
            data: Data to check
            seen: Set of already seen object IDs

        Returns:
            True if circular reference detected, False otherwise
        """
        if seen is None:
            seen = set()

        # Use explicit stack for iteration
        stack: list[Any] = [data]

        while stack:
            current = stack.pop()

            if isinstance(current, dict | list):
                obj_id = id(current)
                if obj_id in seen:
                    return True
                seen.add(obj_id)

                if isinstance(current, dict):
                    stack.extend(current.values())
                else:
                    stack.extend(current)

        return False
