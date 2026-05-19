#!/usr/bin/env python3
"""
Comprehensive tests for LegacyTableFormatter to improve coverage to 70%+.

Tests cover:
- Full table format
- Compact table format
- CSV format
- Multiple classes handling
- Methods and fields extraction
- Platform-specific newlines
- Edge cases and error handling
"""

from tests.unit.formatters.test_legacy_table_formatter_advanced import (
    TestAbbreviateTypeAdvanced,
    TestCompactTableClassesNone,
    TestCreateFullSignatureBranches,
    TestCSVFieldAndParamCoverage,
    TestDetailedFormatting,
    TestDocSummaryAndCSVText,
    TestEdgeCases,
    TestFullTableMultiClassParamTypes,
    TestLanguageSpecificFormatting,
    TestPlatformNewlines,
    TestShortenTypeBranches,
)
from tests.unit.formatters.test_legacy_table_formatter_core import (
    TestCompactTableFormat,
    TestCSVFormat,
    TestFullTableFormat,
    TestLegacyTableFormatterBasic,
    TestMultipleClassesFormat,
)

__all__ = [
    "TestAbbreviateTypeAdvanced",
    "TestCompactTableClassesNone",
    "TestCompactTableFormat",
    "TestCreateFullSignatureBranches",
    "TestCSVFieldAndParamCoverage",
    "TestCSVFormat",
    "TestDetailedFormatting",
    "TestDocSummaryAndCSVText",
    "TestEdgeCases",
    "TestFullTableFormat",
    "TestFullTableMultiClassParamTypes",
    "TestLanguageSpecificFormatting",
    "TestLegacyTableFormatterBasic",
    "TestMultipleClassesFormat",
    "TestPlatformNewlines",
    "TestShortenTypeBranches",
]
