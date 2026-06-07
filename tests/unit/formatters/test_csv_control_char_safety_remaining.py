"""CSV control-character safety for the two remaining CSV writers.

Companion to ``test_csv_control_char_safety.py``, covering the two writers that
PR #381 left out:

1. ``BaseTableFormatter._format_csv`` (the public ``format_type="csv"`` path,
   exercised here via ``PythonTableFormatter``). It previously used
   ``escapechar="\\"`` — which doubled literal backslashes in ordinary fields
   (Windows paths, regex) — now switched to the strip-via-``csv_safe_row``
   approach.
2. ``_legacy_table_formatter_csv.format_csv`` (the ``--table csv`` CLI path).

Guards the same Python 3.10 vs 3.11+ ``csv`` divergence: on 3.10 a NULL byte
raises ``_csv.Error: need to escape, but no escapechar set`` and a bare ``\\r``
is written unquoted (producing an unreadable CSV). These tests assert the
contract version-independently — RED on Python 3.10 before the fix, GREEN after.
"""

from __future__ import annotations

import csv
import io

import pytest

from tree_sitter_analyzer._legacy_table_formatter_csv import (
    format_csv as legacy_format_csv,
)
from tree_sitter_analyzer.formatters.python_formatter import PythonTableFormatter

# Control chars that trip a no-escapechar csv.writer on Python 3.10.
CONTROL_NAMES = ["\x00", "\x00abc", "a\x00b", "\x01\x02"]
# CR variants: a bare \r is emitted unquoted on 3.10 -> unreadable CSV.
CR_NAMES = ["a\rb", "a\r\nb", "\r", "line1\rline2"]


def _base_csv(name: str) -> str:
    """Run ``name`` through the base_formatter CSV path (method + field)."""
    data = {
        "classes": [],
        "methods": [
            {
                "name": name,
                "return_type": "void",
                "parameters": [],
                "visibility": "public",
                "line_range": {"start": 1, "end": 2},
            }
        ],
        "fields": [
            {
                "name": name,
                "type": "int",
                "visibility": "private",
                "line_range": {"start": 3, "end": 3},
            }
        ],
    }
    return PythonTableFormatter(format_type="csv").format_structure(data)


def _legacy_csv(name: str) -> str:
    """Run ``name`` through the legacy ``--table csv`` path (class/method/field)."""
    data = {
        "classes": [
            {
                "type": "class",
                "name": name,
                "visibility": "public",
                "modifiers": [],
                "line_range": {"start": 1, "end": 9},
            }
        ],
        "methods": [
            {
                "name": name,
                "return_type": "void",
                "parameters": [],
                "visibility": "public",
                "line_range": {"start": 2, "end": 3},
            }
        ],
        "fields": [
            {
                "name": name,
                "type": "int",
                "visibility": "private",
                "line_range": {"start": 4, "end": 4},
            }
        ],
    }
    return legacy_format_csv(data)


# --- base_formatter (_format_csv) -----------------------------------------


@pytest.mark.parametrize("name", CONTROL_NAMES)
def test_base_formatter_handles_control_chars(name: str) -> None:
    """base_formatter CSV must serialize a control-char name without raising."""
    result = _base_csv(name)
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.parametrize("name", CR_NAMES)
def test_base_formatter_output_is_readable_with_cr(name: str) -> None:
    """base_formatter CSV must round-trip through csv.reader for CR-laden names."""
    result = _base_csv(name)
    rows = list(csv.reader(io.StringIO(result)))
    assert len(rows) >= 2  # header + at least one data row
    assert "\r" not in result


def test_base_formatter_preserves_backslashes() -> None:
    """Literal backslashes must NOT be doubled (the escapechar regression)."""
    result = _base_csv(r"C:\tmp\Foo")
    assert r"C:\tmp\Foo" in result
    assert r"C:\\tmp" not in result


def test_base_formatter_preserves_regex_backslashes() -> None:
    """A regex-like name keeps its backslashes intact."""
    result = _base_csv(r"\d+\w*")
    assert r"\d+\w*" in result
    assert r"\\d" not in result


# --- legacy --table csv (format_csv) --------------------------------------


@pytest.mark.parametrize("name", CONTROL_NAMES)
def test_legacy_csv_handles_control_chars(name: str) -> None:
    """legacy CSV must serialize a control-char name without raising."""
    result = _legacy_csv(name)
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.parametrize("name", CR_NAMES)
def test_legacy_csv_output_is_readable_with_cr(name: str) -> None:
    """legacy CSV must round-trip through csv.reader for CR-laden names."""
    result = _legacy_csv(name)
    rows = list(csv.reader(io.StringIO(result)))
    assert len(rows) >= 2  # header + at least one data row
    assert "\r" not in result


def test_legacy_csv_preserves_backslashes() -> None:
    """Literal backslashes must NOT be doubled in the legacy path."""
    result = _legacy_csv(r"C:\tmp\Foo")
    assert r"C:\tmp\Foo" in result
    assert r"C:\\tmp" not in result


def test_legacy_csv_preserves_regex_backslashes() -> None:
    """A regex-like name keeps its backslashes intact in the legacy path."""
    result = _legacy_csv(r"\d+\w*")
    assert r"\d+\w*" in result
    assert r"\\d" not in result
