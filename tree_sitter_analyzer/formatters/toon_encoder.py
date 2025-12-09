#!/usr/bin/env python3
"""
TOON (Token-Oriented Object Notation) Encoder

Low-level encoding primitives for TOON format.
Provides efficient encoding of data structures for LLM consumption.
"""

from typing import Any


class ToonEncoder:
    """
    Low-level encoder for TOON format.

    Provides primitive encoding operations that can be composed
    to build complex TOON representations.
    """

    def __init__(self, use_tabs: bool = False):
        """
        Initialize TOON encoder.

        Args:
            use_tabs: Use tab delimiters instead of commas for further compression
        """
        self.use_tabs = use_tabs
        self.delimiter = "\t" if use_tabs else ","

    def encode(self, data: Any, indent: int = 0) -> str:
        """
        Encode arbitrary data as TOON format.

        Args:
            data: Data to encode (dict, list, or primitive)
            indent: Current indentation level

        Returns:
            TOON-formatted string
        """
        if isinstance(data, dict):
            return self.encode_dict(data, indent)
        elif isinstance(data, list):
            return self.encode_list(data, indent)
        else:
            return self.encode_value(data)

    def encode_dict(self, data: dict[str, Any], indent: int = 0) -> str:
        """
        Encode dictionary as TOON object.

        Format:
            key1: value1
            key2: value2
            nested_obj:
              sub_key: sub_value

        Args:
            data: Dictionary to encode
            indent: Indentation level

        Returns:
            TOON-formatted string
        """
        lines = []
        indent_str = "  " * indent

        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{indent_str}{key}:")
                lines.append(self.encode_dict(value, indent + 1))
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                # Homogeneous array - use table format
                lines.append(f"{indent_str}{key}:")
                lines.append(
                    self.encode_array_table(value, schema=None, indent=indent + 1)
                )
            elif isinstance(value, list):
                lines.append(f"{indent_str}{key}: {self.encode_list(value)}")
            else:
                lines.append(f"{indent_str}{key}: {self.encode_value(value)}")

        return "\n".join(lines)

    def encode_list(self, items: list[Any], indent: int = 0) -> str:
        """
        Encode list as TOON array.

        Format: [item1, item2, item3]

        Args:
            items: List to encode
            indent: Indentation level

        Returns:
            TOON-formatted string
        """
        if not items:
            return "[]"

        # Check if homogeneous array of dicts
        if all(isinstance(item, dict) for item in items):
            return self.encode_array_table(items, schema=None, indent=indent)

        # Simple array
        encoded_items = [self.encode_value(item) for item in items]
        return f"[{self.delimiter.join(encoded_items)}]"

    def encode_value(self, value: Any) -> str:
        """
        Encode single value for TOON output.

        Args:
            value: Value to encode

        Returns:
            String representation
        """
        if value is None:
            return "null"
        elif isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, int | float):
            return str(value)
        elif isinstance(value, str):
            return self._encode_string(value)
        else:
            return str(value)

    def _encode_string(self, s: str) -> str:
        """
        Encode string with proper escaping.

        Quotes are added when the string contains TOON special characters.
        Escape sequences are applied to prevent format corruption.

        Args:
            s: String to encode

        Returns:
            Escaped and quoted string if necessary
        """
        # Check if quoting is needed
        needs_quotes = any(
            c in s
            for c in [
                self.delimiter,
                "\n",
                "\r",
                "\t",
                "\\",
                ":",
                "{",
                "}",
                "[",
                "]",
                '"',
            ]
        )

        if needs_quotes:
            # Apply escape sequences (order matters: backslash first)
            escaped = (
                s.replace("\\", "\\\\")  # Backslash must be first
                .replace('"', '\\"')  # Quote
                .replace("\n", "\\n")  # Newline
                .replace("\r", "\\r")  # Carriage return
                .replace("\t", "\\t")
            )  # Tab
            return f'"{escaped}"'

        return s

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
        if not items:
            return "[]"

        # Infer schema from first item if not provided
        if schema is None:
            schema = self._infer_schema(items)

        lines = []
        indent_str = "  " * indent

        # Header
        header = self.encode_array_header(len(items), schema)
        lines.append(f"{indent_str}{header}")

        # Rows
        for item in items:
            row_values = [self.encode_value(item.get(key, "")) for key in schema]
            row = self.delimiter.join(row_values)
            lines.append(f"{indent_str}  {row}")

        return "\n".join(lines)

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
