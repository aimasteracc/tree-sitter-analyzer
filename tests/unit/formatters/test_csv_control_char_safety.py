"""CSV control-character safety regression tests.

Guards a Python 3.10 vs 3.11+ ``csv`` module divergence: on 3.10 a field
containing a NULL byte (``\\x00``) raises ``_csv.Error: need to escape, but no
escapechar set`` when the writer has no ``escapechar``; on 3.11+ it does not.

The control char is stripped (not escaped): setting ``escapechar="\\"`` would
silence the 3.10 error but double literal backslashes in ordinary fields
(``C:\\tmp`` -> ``C:\\\\tmp``), a format regression for Windows paths and regex
strings. So the fix strips CSV-unrepresentable control chars and leaves the
dialect — and therefore backslashes — untouched.

These tests assert the contract version-independently: every CSV formatter must
serialize control-character input without raising, AND must preserve literal
backslashes. They are RED on Python 3.10 before the fix and GREEN after it.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.formatters._csv_safety import csv_safe_cell, csv_safe_row
from tree_sitter_analyzer.formatters._html_csv_formatter_helpers import (
    format_html_csv,
)
from tree_sitter_analyzer.formatters._markdown_formatter_rendering import (
    format_csv_output,
)
from tree_sitter_analyzer.formatters.formatter_registry import CsvFormatter
from tree_sitter_analyzer.models import CodeElement

# Characters that trip a no-escapechar csv.writer on Python 3.10.
CONTROL_NAMES = ["\x00", "\x00abc", "a\x00b", "\x01\x02"]


@pytest.mark.parametrize("name", CONTROL_NAMES)
def test_csv_formatter_handles_control_chars(name: str) -> None:
    """CsvFormatter must serialize a control-char name without raising."""
    element = CodeElement(
        name=name,
        element_type="class",
        start_line=1,
        end_line=10,
        language="python",
    )
    result = CsvFormatter().format([element])
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.parametrize("name", CONTROL_NAMES)
def test_csv_formatter_is_idempotent_on_control_chars(name: str) -> None:
    """Idempotency must hold for control-char input (the property that flaked)."""
    element = CodeElement(
        name=name,
        element_type="class",
        start_line=1,
        end_line=10,
        language="python",
    )
    formatter = CsvFormatter()
    assert formatter.format([element]) == formatter.format([element])


def test_html_csv_helper_handles_control_chars() -> None:
    """format_html_csv must not raise on a control-char element name."""
    element = CodeElement(
        name="\x00",
        element_type="class",
        start_line=1,
        end_line=10,
        language="html",
    )
    result = format_html_csv([element])
    assert isinstance(result, str)
    assert len(result) > 0


def test_markdown_csv_output_handles_control_chars() -> None:
    """format_csv_output must not raise on a control-char text field."""
    analysis_result = {
        "elements": [
            {
                "type": "heading",
                "text": "\x00",
                "level": 1,
                "line_range": {"start": 1, "end": 1},
            }
        ]
    }
    result = format_csv_output(analysis_result)
    assert isinstance(result, str)
    assert len(result) > 0


def test_csv_formatter_preserves_backslashes() -> None:
    """Literal backslashes (Windows paths, regex) must NOT be doubled.

    Regression guard for the escapechar approach Codex flagged (P2): a field
    like ``C:\\tmp\\Foo`` must round-trip unchanged, not become ``C:\\\\tmp``.
    """
    element = CodeElement(
        name=r"C:\tmp\Foo",
        element_type="class",
        start_line=1,
        end_line=10,
        language="python",
    )
    result = CsvFormatter().format([element])
    assert r"C:\tmp\Foo" in result
    assert r"C:\\tmp" not in result


def test_csv_safe_cell_strips_controls_keeps_tab_newline() -> None:
    """The sanitizer removes C0/DEL controls + bare CR, keeps tab and LF.

    CR is stripped because Python 3.10's csv.writer emits a bare \\r unquoted,
    producing an unreadable CSV; tab and LF are quoted correctly on all
    versions and so survive.
    """
    assert csv_safe_cell("a\x00b\x01c") == "abc"
    assert csv_safe_cell("a\tb\nc") == "a\tb\nc"  # tab + LF preserved
    assert csv_safe_cell("a\rb") == "ab"  # bare CR stripped
    assert csv_safe_cell("a\r\nb") == "a\nb"  # CRLF -> LF
    assert csv_safe_cell(r"C:\tmp") == r"C:\tmp"  # backslash untouched
    assert csv_safe_cell(42) == 42  # non-str passes through unchanged


@pytest.mark.parametrize("name", ["a\rb", "a\r\nb", "\r", "line1\rline2"])
def test_csv_formatter_output_is_readable_with_cr(name: str) -> None:
    """CSV output must round-trip through csv.reader even for CR-laden names.

    Guards the Python 3.10 'new-line character seen in unquoted field' failure
    Codex flagged: a bare CR in a cell must not survive into the output.
    """
    import csv
    import io

    element = CodeElement(
        name=name,
        element_type="class",
        start_line=1,
        end_line=10,
        language="python",
    )
    result = CsvFormatter().format([element])
    # Must parse back without raising on any Python version.
    rows = list(csv.reader(io.StringIO(result)))
    assert len(rows) >= 2  # header + at least one data row
    assert "\r" not in result


def test_csv_safe_row_only_touches_string_cells() -> None:
    """Numeric cells keep their type so csv.writer formats them normally."""
    assert csv_safe_row(["a\x00", 1, "b\x02", 10]) == ["a", 1, "b", 10]
