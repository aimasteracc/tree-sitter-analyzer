"""
Markdown Formatter - Human-readable output format

This module provides Markdown formatting for human-readable output.

Features:
- Heading hierarchy (# ## ###)
- Bullet lists for arrays
- Tables for structured data
- Code blocks for signatures
- Clear visual structure
"""

from typing import Any


class MarkdownFormatter:
    """
    Markdown formatter for human-readable output.

    Converts analysis results to well-structured Markdown format with
    headings, lists, tables, and code blocks.
    """

    def __init__(self, heading_level: int = 1):
        """
        Initialize Markdown formatter.

        Args:
            heading_level: Starting heading level (1 for #, 2 for ##, etc.)
        """
        self.heading_level = heading_level

    def format(self, data: Any) -> str:
        """
        Format data to Markdown string.

        Args:
            data: Data to format (dict, list, or primitive)

        Returns:
            Markdown-formatted string
        """
        return self._encode(data, level=self.heading_level)

    def _encode(self, data: Any, level: int = 1) -> str:
        """
        Encode data to Markdown format recursively.

        Args:
            data: Data to encode
            level: Current heading level

        Returns:
            Markdown-formatted string
        """
        if data is None:
            return "_null_"
        elif isinstance(data, bool):
            return "Yes" if data else "No"
        elif isinstance(data, (int, float)):
            return str(data)
        elif isinstance(data, str):
            return data
        elif isinstance(data, dict):
            return self._encode_dict(data, level)
        elif isinstance(data, list):
            return self._encode_list(data, level)
        else:
            return str(data)

    def _encode_dict(self, data: dict[str, Any], level: int) -> str:
        """
        Encode dictionary to Markdown format.

        Args:
            data: Dictionary to encode
            level: Current heading level

        Returns:
            Markdown-formatted dictionary
        """
        if not data:
            return "_empty_"

        lines: list[str] = []

        for key, value in data.items():
            # Format key as heading or bold
            if isinstance(value, (dict, list)):
                # Complex value: use heading
                heading_prefix = "#" * min(level, 6)
                key_display = key.replace("_", " ").title()
                lines.append(f"{heading_prefix} {key_display}\n")

                # Encode value with increased level
                value_str = self._encode(value, level + 1)
                lines.append(value_str)
            else:
                # Simple value: use key-value format
                key_display = key.replace("_", " ").title()
                value_str = self._encode(value, level)
                lines.append(f"**{key_display}:** {value_str}\n")

        return "\n".join(lines)

    def _encode_list(self, data: list[Any], level: int) -> str:
        """
        Encode list to Markdown format.

        Args:
            data: List to encode
            level: Current heading level

        Returns:
            Markdown-formatted list
        """
        if not data:
            return "_empty list_"

        # Check if it's a list of dicts with same keys (table format)
        if self._is_homogeneous_dict_list(data):
            return self._encode_table(data)

        # Otherwise, use bullet list
        lines: list[str] = []

        for item in data:
            if isinstance(item, dict):
                # Dict item: format with sub-list
                item_str = self._encode_dict(item, level + 1)
                # Indent the dict output
                indented = "\n  ".join(item_str.split("\n"))
                lines.append(f"- {indented}")
            elif isinstance(item, list):
                # Nested list
                item_str = self._encode_list(item, level + 1)
                indented = "\n  ".join(item_str.split("\n"))
                lines.append(f"- {indented}")
            else:
                # Simple item
                item_str = self._encode(item, level)
                lines.append(f"- {item_str}")

        return "\n".join(lines)

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
        return len(data) > 1 and all(set(item.keys()) == first_keys for item in data)

    def _encode_table(self, data: list[dict[str, Any]]) -> str:
        """
        Encode homogeneous list of dicts as Markdown table.

        Args:
            data: List of dictionaries with same keys

        Returns:
            Markdown table
        """
        if not data:
            return "_empty table_"

        # Get column names from first dict
        columns = list(data[0].keys())

        # Build table header
        header_row = "| " + " | ".join(col.replace("_", " ").title() for col in columns) + " |"
        separator = "| " + " | ".join("---" for _ in columns) + " |"

        # Build table rows
        rows: list[str] = [header_row, separator]

        for item in data:
            cells = [str(self._encode(item[col], 0)) for col in columns]
            row = "| " + " | ".join(cells) + " |"
            rows.append(row)

        return "\n".join(rows)
