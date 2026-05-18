"""Compatibility facade for legacy table formatter helpers."""

from __future__ import annotations

from ._legacy_table_formatter_common import (
    clean_csv_text,
    convert_visibility,
    create_full_signature,
    extract_doc_summary,
    get_platform_newline,
    get_visibility_symbol,
    shorten_type,
)
from ._legacy_table_formatter_compact import (
    append_compact_fields_section,
    append_compact_info_section,
    append_compact_methods_section,
    compact_table_header,
)
from ._legacy_table_formatter_csv import format_csv
from ._legacy_table_formatter_detail import (
    append_detail_fields_section,
    append_detailed_methods_section,
    detail_method_groups,
)
from ._legacy_table_formatter_full import (
    append_full_class_info_section,
    append_full_imports_section,
    append_full_package_section,
    append_multi_class_full_sections,
    append_single_class_full_sections,
    format_simple_field_row,
    format_simple_method_row,
    full_table_header,
)
from ._legacy_table_formatter_members import get_class_fields, get_class_methods

__all__ = [
    "append_compact_fields_section",
    "append_compact_info_section",
    "append_compact_methods_section",
    "append_detail_fields_section",
    "append_detailed_methods_section",
    "append_full_class_info_section",
    "append_full_imports_section",
    "append_full_package_section",
    "append_multi_class_full_sections",
    "append_single_class_full_sections",
    "clean_csv_text",
    "compact_table_header",
    "convert_visibility",
    "create_full_signature",
    "detail_method_groups",
    "extract_doc_summary",
    "format_csv",
    "format_simple_field_row",
    "format_simple_method_row",
    "full_table_header",
    "get_class_fields",
    "get_class_methods",
    "get_platform_newline",
    "get_visibility_symbol",
    "shorten_type",
]
