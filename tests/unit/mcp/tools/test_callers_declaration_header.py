"""PR-2: the name line of a declaration recorded at its first annotation / decorator
is the declaration itself, unless the name occurs on it again."""

from __future__ import annotations

import re

import pytest

from tree_sitter_analyzer.mcp.tools.callers_declaration_header import (
    name_lines,
    sole_occurrence,
    without_header_names,
)

_PATTERN = re.compile(r"(?<![\w$])target(?![\w$])")
_PY = (
    "import functools\n"
    "\n"
    "\n"
    "@functools.lru_cache(maxsize=None)\n"
    "def target(x):\n"
    "    return x\n"
)
#: A parameter default on the name line names the target a second time.
_PY_DEFAULT = (
    "def target():\n"
    "    return 1\n"
    "\n"
    "\n"
    "@functools.lru_cache(maxsize=None)\n"
    "def target(fallback=target):\n"
    "    return fallback\n"
)
_JAVA = (
    "class A {\n"
    "  @Deprecated\n"
    '  @SuppressWarnings("x")\n'
    "  public\n"
    "  void target(\n"
    "      int target) {}\n"
    "  void other() {}\n"
    "}\n"
)


def test_python_decorator_row_yields_the_def_line() -> None:
    assert name_lines(_PY, [4], "python", "target") == frozenset({5})


def test_recorded_name_line_adds_nothing() -> None:
    assert name_lines(_PY, [5], "python", "target") == frozenset()
    assert name_lines(_PY, [], "python", "target") == frozenset()


def test_other_names_and_unparsable_text_add_nothing() -> None:
    assert name_lines(_PY, [4], "python", "other") == frozenset()
    assert name_lines("@x\ndef target(:\n", [1], "python", "target") == frozenset()
    assert name_lines("x", [1], "no-such-language", "target") == frozenset()


def test_java_annotation_row_yields_the_name_line_not_the_parameters() -> None:
    assert name_lines(_JAVA, [2], "java", "target") == frozenset({5})


def test_sole_occurrence_counts_the_name() -> None:
    assert sole_occurrence("def target(x):", _PATTERN) is True
    assert sole_occurrence("def target(fallback=target):", _PATTERN) is False
    assert sole_occurrence("targets = 1", _PATTERN) is False


@pytest.mark.parametrize(
    ("text", "recorded", "lines", "kept"),
    [
        (_PY, [4], [5], []),
        # The default value is a reference: the name line stays.
        (_PY_DEFAULT, [1, 5], [6], [6]),
        # A line after the name (parameters / body) is never skipped.
        (_JAVA, [2], [6], [6]),
    ],
)
def test_without_header_names(text: str, recorded, lines, kept) -> None:
    language = "java" if text is _JAVA else "python"

    result = without_header_names(
        lines, text, text.encode("utf-8"), language, recorded, _PATTERN, "target"
    )

    assert result == kept
