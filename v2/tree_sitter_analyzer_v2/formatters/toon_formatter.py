"""
TOON Formatter - Token-Oriented Object Notation

This module provides TOON formatting for LLM-optimized output with 50-70% token reduction.

TOON Format Features:
- YAML-like key: value syntax for dictionaries
- Compact array notation: [1,2,3]
- Compact array table format for homogeneous arrays
- Unquoted simple strings
- Indentation for nested structures

Example:
    file_path: example.py
    language: python
    methods:
      [3]{name,visibility,lines}:
        init,public,1-10
        process,public,12-45
        validate,private,47-60
"""

from typing import Any


class ToonFormatter:
    """
    TOON formatter for LLM-optimized output.

    Converts analysis results to compact, human-readable TOON format that
    reduces token consumption by 50-70% compared to JSON.
    """

    def __init__(self, use_tabs: bool = False, compact_arrays: bool = True):
        """
        Initialize TOON formatter.

        Args:
            use_tabs: Use tab delimiters instead of commas (further optimization)
            compact_arrays: Use compact table format for homogeneous arrays
        """
        self.use_tabs = use_tabs
        self.compact_arrays = compact_arrays
        self.delimiter = "\t" if use_tabs else ","

    def format(self, data: Any) -> str:
        """
        Format data to TOON string.

        Args:
            data: Data to format (dict, list, or primitive)

        Returns:
            TOON-formatted string
        """
        return self._encode(data, indent=0)

    def _encode(self, data: Any, indent: int = 0) -> str:
        """
        Encode data to TOON format recursively.

        Args:
            data: Data to encode
            indent: Current indentation level

        Returns:
            TOON-formatted string
        """
        if data is None:
            return "null"
        elif isinstance(data, bool):
            return "true" if data else "false"
        elif isinstance(data, (int, float)):
            return str(data)
        elif isinstance(data, str):
            return self._encode_string(data)
        elif isinstance(data, dict):
            return self._encode_dict(data, indent)
        elif isinstance(data, list):
            return self._encode_list(data, indent)
        else:
            # Fallback for unknown types
            return str(data)

    def _encode_string(self, s: str) -> str:
        """
        Encode string value.

        Simple strings (alphanumeric, underscore, hyphen) are unquoted.
        Strings with special characters are quoted and escaped.

        Args:
            s: String to encode

        Returns:
            Encoded string
        """
        # Check if string needs quoting
        if self._needs_quoting(s):
            # Escape special characters
            escaped = (
                s.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
                .replace("\t", "\\t")
            )
            return f'"{escaped}"'
        else:
            return s

    def _needs_quoting(self, s: str) -> bool:
        """
        Check if string needs quoting.

        Args:
            s: String to check

        Returns:
            True if string needs quoting, False otherwise
        """
        if not s:
            return True

        # Check for special characters that require quoting
        special_chars = [" ", ":", ",", "[", "]", "{", "}", "\n", "\t", '"', "'"]
        return any(char in s for char in special_chars)

    def _encode_dict(self, data: dict[str, Any], indent: int) -> str:
        """
        Encode dictionary to TOON format.

        Args:
            data: Dictionary to encode
            indent: Current indentation level

        Returns:
            TOON-formatted dictionary
        """
        if not data:
            return "{}"

        lines: list[str] = []
        indent_str = "  " * indent

        for key, value in data.items():
            # Encode key
            key_str = self._encode_string(str(key))

            # Check if value is a simple type that can be inline
            if isinstance(value, (type(None), bool, int, float, str)):
                value_str = self._encode(value, indent)
                lines.append(f"{indent_str}{key_str}: {value_str}")
            elif isinstance(value, list):
                # Check if we can use compact array format
                if self._is_simple_list(value):
                    # Inline array: [1,2,3]
                    array_str = self._encode_simple_array(value)
                    lines.append(f"{indent_str}{key_str}: {array_str}")
                elif self.compact_arrays and self._is_homogeneous_dict_list(value):
                    # Compact table format
                    table_str = self._encode_array_table(value, indent + 1)
                    lines.append(f"{indent_str}{key_str}:")
                    lines.append(table_str)
                else:
                    # Nested list
                    lines.append(f"{indent_str}{key_str}:")
                    list_str = self._encode_list(value, indent + 1)
                    lines.append(list_str)
            elif isinstance(value, dict):
                # Nested dictionary
                lines.append(f"{indent_str}{key_str}:")
                dict_str = self._encode_dict(value, indent + 1)
                lines.append(dict_str)
            else:
                # Other types
                value_str = self._encode(value, indent)
                lines.append(f"{indent_str}{key_str}: {value_str}")

        return "\n".join(lines)

    def _encode_list(self, data: list[Any], indent: int) -> str:
        """
        Encode list to TOON format.

        Args:
            data: List to encode
            indent: Current indentation level

        Returns:
            TOON-formatted list
        """
        if not data:
            return "[]"

        # Simple list: use bracket notation
        if self._is_simple_list(data):
            return self._encode_simple_array(data)

        # Homogeneous dict list: use compact table
        if self.compact_arrays and self._is_homogeneous_dict_list(data):
            return self._encode_array_table(data, indent)

        # Complex list: encode each item on separate line
        lines: list[str] = []
        indent_str = "  " * indent

        for item in data:
            item_str = self._encode(item, indent + 1)
            lines.append(f"{indent_str}- {item_str}")

        return "\n".join(lines)

    def _is_simple_list(self, data: list[Any]) -> bool:
        """
        Check if list contains only simple values (primitives).

        Args:
            data: List to check

        Returns:
            True if list contains only primitives, False otherwise
        """
        return all(isinstance(item, (type(None), bool, int, float, str)) for item in data)

    def _encode_simple_array(self, data: list[Any]) -> str:
        """
        Encode simple array using bracket notation.

        Args:
            data: List of primitives

        Returns:
            TOON-formatted array: [item1,item2,item3]
        """
        items = [self._encode(item, 0) for item in data]
        return f"[{self.delimiter.join(items)}]"

    def _is_homogeneous_dict_list(self, data: list[Any]) -> bool:
        """
        Check if list is homogeneous array of dictionaries with same keys.

        Args:
            data: List to check

        Returns:
            True if homogeneous dict list, False otherwise
        """
        if not data or not all(isinstance(item, dict) for item in data):
            return False

        # Get keys from first dict
        first_keys = set(data[0].keys()) if data else set()

        # Check all dicts have same keys
        return all(set(item.keys()) == first_keys for item in data)

    def _encode_array_table(self, data: list[dict[str, Any]], indent: int) -> str:
        """
        Encode homogeneous array of dicts using compact table format.

        Format:
            [count]{field1,field2,field3}:
              value1,value2,value3
              value4,value5,value6

        Args:
            data: List of dictionaries with same keys
            indent: Current indentation level

        Returns:
            TOON-formatted compact table
        """
        if not data:
            return "[]"

        # Get field names from first dict
        fields = list(data[0].keys())
        count = len(data)

        # Build header: [count]{field1,field2,field3}:
        fields_str = self.delimiter.join(fields)
        header = f"[{count}]{{{fields_str}}}:"

        # Build rows
        lines: list[str] = [header]
        indent_str = "  " * indent

        for item in data:
            values = [self._encode(item[field], 0) for field in fields]
            row = self.delimiter.join(values)
            lines.append(f"{indent_str}{row}")

        return "\n".join(lines)
