"""CSV control-character safety regression tests.

Guards a Python 3.10 vs 3.11+ ``csv`` module divergence: on 3.10 a field
containing a NULL byte (``\\x00``) raises ``_csv.Error: need to escape, but no
escapechar set`` when the writer has no ``escapechar``; on 3.11+ it does not.

``base_formatter.py`` already set ``escapechar="\\"`` for this exact reason
("null bytes in some envs"), but three sibling CSV writers
(``CsvFormatter``, ``format_csv_output``, ``format_html_csv``) did not — so a
symbol name with a control char (which Hypothesis's ``st.text()`` generates)
flaked the property suite on the 3.10 CI axis and blocked the v1.21.0 release.

These tests assert the contract version-independently: every CSV formatter must
serialize control-character input without raising. They are RED on Python 3.10
before the fix and GREEN everywhere after it.
"""

from __future__ import annotations

import pytest

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
