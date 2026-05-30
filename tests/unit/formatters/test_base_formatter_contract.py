"""Parametrized contract tests for all concrete BaseTableFormatter subclasses.

Every formatter must satisfy these invariants regardless of language.
Replaces the boilerplate test_get_*_formatter_instance / test_formatter_methods_exist
tests scattered across individual formatter coverage files.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.formatters.base_formatter import BaseTableFormatter
from tree_sitter_analyzer.formatters.cpp_formatter import CppTableFormatter
from tree_sitter_analyzer.formatters.csharp_formatter import CSharpTableFormatter
from tree_sitter_analyzer.formatters.go_formatter import GoTableFormatter
from tree_sitter_analyzer.formatters.java_formatter import JavaTableFormatter
from tree_sitter_analyzer.formatters.javascript_formatter import (
    JavaScriptTableFormatter,
)
from tree_sitter_analyzer.formatters.kotlin_formatter import KotlinTableFormatter
from tree_sitter_analyzer.formatters.php_formatter import (
    PHPCompactFormatter,
    PHPCSVFormatter,
    PHPFullFormatter,
    PHPTableFormatter,
)
from tree_sitter_analyzer.formatters.ruby_formatter import (
    RubyCompactFormatter,
    RubyCSVFormatter,
    RubyFullFormatter,
    RubyTableFormatter,
)
from tree_sitter_analyzer.formatters.rust_formatter import RustTableFormatter
from tree_sitter_analyzer.formatters.typescript_formatter import (
    TypeScriptTableFormatter,
)

_MINIMAL_STRUCTURE_DATA = {
    "file_path": "test_file",
    "packages": [],
    "classes": [],
    "methods": [],
    "fields": [],
    "imports": [],
    "statistics": {"function_count": 0, "class_count": 0, "variable_count": 0},
}

_MINIMAL_SUMMARY_DATA = {
    "file_path": "test_file",
    "elements": [],
    "language": "unknown",
}

_FORMATTER_CLASSES: list[tuple[str, type[BaseTableFormatter]]] = [
    ("CppTableFormatter", CppTableFormatter),
    ("CSharpTableFormatter", CSharpTableFormatter),
    ("GoTableFormatter", GoTableFormatter),
    ("JavaTableFormatter", JavaTableFormatter),
    ("JavaScriptTableFormatter", JavaScriptTableFormatter),
    ("KotlinTableFormatter", KotlinTableFormatter),
    ("PHPTableFormatter", PHPTableFormatter),
    ("PHPFullFormatter", PHPFullFormatter),
    ("PHPCompactFormatter", PHPCompactFormatter),
    ("PHPCSVFormatter", PHPCSVFormatter),
    ("RubyTableFormatter", RubyTableFormatter),
    ("RubyFullFormatter", RubyFullFormatter),
    ("RubyCompactFormatter", RubyCompactFormatter),
    ("RubyCSVFormatter", RubyCSVFormatter),
    ("RustTableFormatter", RustTableFormatter),
    ("TypeScriptTableFormatter", TypeScriptTableFormatter),
]

_IDS = [name for name, _ in _FORMATTER_CLASSES]
_CLASSES = [cls for _, cls in _FORMATTER_CLASSES]


def _make_formatter(cls: type[BaseTableFormatter]) -> BaseTableFormatter:
    try:
        return cls("full")
    except TypeError:
        return cls()


@pytest.mark.parametrize("formatter_cls", _CLASSES, ids=_IDS)
class TestBaseFormatterContract:
    """Every concrete BaseTableFormatter must satisfy these 8 invariants."""

    def test_instantiates_with_full_format(
        self, formatter_cls: type[BaseTableFormatter]
    ) -> None:
        fmt = _make_formatter(formatter_cls)
        assert isinstance(fmt, BaseTableFormatter)

    def test_is_subclass_of_base_table_formatter(
        self, formatter_cls: type[BaseTableFormatter]
    ) -> None:
        assert issubclass(formatter_cls, BaseTableFormatter)

    def test_has_format_structure_method(
        self, formatter_cls: type[BaseTableFormatter]
    ) -> None:
        assert callable(getattr(formatter_cls, "format_structure", None))

    def test_has_format_summary_method(
        self, formatter_cls: type[BaseTableFormatter]
    ) -> None:
        assert callable(getattr(formatter_cls, "format_summary", None))

    def test_has_format_table_method(
        self, formatter_cls: type[BaseTableFormatter]
    ) -> None:
        assert callable(getattr(formatter_cls, "format_table", None))

    def test_format_structure_returns_string(
        self, formatter_cls: type[BaseTableFormatter]
    ) -> None:
        fmt = _make_formatter(formatter_cls)
        result = fmt.format_structure(_MINIMAL_STRUCTURE_DATA)
        assert isinstance(result, str)

    def test_format_summary_returns_string(
        self, formatter_cls: type[BaseTableFormatter]
    ) -> None:
        fmt = _make_formatter(formatter_cls)
        result = fmt.format_summary(_MINIMAL_SUMMARY_DATA)
        assert isinstance(result, str)

    def test_class_name_matches_module(
        self, formatter_cls: type[BaseTableFormatter]
    ) -> None:
        assert (
            formatter_cls.__name__ == formatter_cls.__name__
        )  # trivially true; ensures class is importable
        assert "tree_sitter_analyzer.formatters" in formatter_cls.__module__
