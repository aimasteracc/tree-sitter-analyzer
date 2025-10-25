#!/usr/bin/env python3
"""
Output format parameter validation for search_content tool.

Ensures mutual exclusion of output format parameters to prevent conflicts.
"""

from typing import Any


class OutputFormatValidator:
    """Validator for output format parameters mutual exclusion."""

    # Output format parameters that are mutually exclusive
    OUTPUT_FORMAT_PARAMS = {
        "total_only",
        "count_only_matches",
        "summary_only",
        "group_by_file",
        "optimize_paths"
    }

    def validate_output_format_exclusion(self, arguments: dict[str, Any]) -> None:
        """
        Validate that only one output format parameter is specified.

        Args:
            arguments: Tool arguments dictionary

        Raises:
            ValueError: If multiple output format parameters are specified
        """
        specified_formats = []

        for param in self.OUTPUT_FORMAT_PARAMS:
            if arguments.get(param, False):
                specified_formats.append(param)

        if len(specified_formats) > 1:
            format_list = ", ".join(specified_formats)
            raise ValueError(
                f"出力形式パラメータは排他的です。複数指定できません: {format_list}. "
                f"次のうち1つのみ指定してください: {', '.join(self.OUTPUT_FORMAT_PARAMS)}"
            )

    def get_active_format(self, arguments: dict[str, Any]) -> str:
        """
        Get the active output format from arguments.

        Args:
            arguments: Tool arguments dictionary

        Returns:
            Active format name or "normal" if none specified
        """
        for param in self.OUTPUT_FORMAT_PARAMS:
            if arguments.get(param, False):
                return param
        return "normal"


# Global validator instance
_default_validator = None


def get_default_validator() -> OutputFormatValidator:
    """Get the default output format validator instance."""
    global _default_validator
    if _default_validator is None:
        _default_validator = OutputFormatValidator()
    return _default_validator
