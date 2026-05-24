#!/usr/bin/env python3
"""Compatibility exports for Markdown formatter helper functions."""

from ._markdown_formatter_counts import compute_robust_counts_from_file
from ._markdown_formatter_elements import collect_images
from ._markdown_formatter_payloads import (
    build_advanced_result,
    build_structure_result,
    build_summary_result,
)
from ._markdown_formatter_rendering import (
    calculate_document_complexity,
    format_advanced_text,
    format_compact_output,
    format_csv_output,
    format_json_output,
)

__all__ = [
    "build_advanced_result",
    "build_structure_result",
    "build_summary_result",
    "calculate_document_complexity",
    "collect_images",
    "compute_robust_counts_from_file",
    "format_advanced_text",
    "format_compact_output",
    "format_csv_output",
    "format_json_output",
]
