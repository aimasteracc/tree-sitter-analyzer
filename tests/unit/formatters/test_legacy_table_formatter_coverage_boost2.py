#!/usr/bin/env python3
"""
Coverage boost 2 tests for LegacyTableFormatter.

Targets uncovered branches in:
- _get_platform_newline (Windows), _convert_to_platform_newlines
- _format_full_table header edge cases (package+no classes, no file_path+package)
- _format_full_table multi-class param types (string, fallback)
- _format_full_table multi-class fields section
- _format_class_details with fields/constructors/methods + include_javadoc
- _format_method_row_detailed, _create_compact_signature
- _abbreviate_type generics + arrays
- _get_visibility_symbol
- _format_csv field rows, method rows
- _create_full_signature string/fallback params, is_static
- _shorten_type Map, List, array, None, non-string
- _convert_visibility, _extract_doc_summary, _clean_csv_text
- _format_compact_table classes=None, package branch
"""

from test_legacy_table_coverage_format_utils import (
    TestAbbreviateType,
    TestCleanCsvText,
    TestCompactTableEdgeCases,
    TestConvertVisibility,
    TestCreateCompactSignature,
    TestCreateFullSignature,
    TestCsvFormat,
    TestExtractDocSummary,
    TestFormatMethodRowDetailed,
    TestGetVisibilitySymbol,
    TestShortenType,
)
from test_legacy_table_coverage_platform_header import (
    TestFormatClassDetails,
    TestFullTableHeaderEdgeCases,
    TestFullTableMultiClassParamTypes,
    TestPlatformNewlineWindows,
)

__all__ = [
    "TestPlatformNewlineWindows",
    "TestFullTableHeaderEdgeCases",
    "TestFullTableMultiClassParamTypes",
    "TestFormatClassDetails",
    "TestFormatMethodRowDetailed",
    "TestCreateCompactSignature",
    "TestAbbreviateType",
    "TestGetVisibilitySymbol",
    "TestCompactTableEdgeCases",
    "TestCsvFormat",
    "TestCreateFullSignature",
    "TestShortenType",
    "TestConvertVisibility",
    "TestExtractDocSummary",
    "TestCleanCsvText",
]
