"""Tests for the signatures (lightweight method-directory) table mode.

Covers:
1. _method_sig_line helper output shape
2. JavaTableFormatterSignaturesMixin._format_signatures_table on single-class data
3. Multi-class grouping
4. BaseTableFormatter.format_structure dispatch for "signatures"
5. DefaultTableFormatter dispatch for "signatures"
6. FormatterRegistry.get_formatter_for_language("java", "signatures") returns
   a formatter that can format_structure without error
7. _validate_format_type now accepts "signatures"
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.default_table_formatter import DefaultTableFormatter
from tree_sitter_analyzer.formatters._java_formatter_signatures_mixin import (
    _method_sig_line,
    _shorten_return_type,
)
from tree_sitter_analyzer.formatters.formatter_registry import FormatterRegistry
from tree_sitter_analyzer.formatters.go_formatter import GoTableFormatter
from tree_sitter_analyzer.formatters.java_formatter import JavaTableFormatter
from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    _validate_format_type,
)

# ---------------------------------------------------------------------------
# Helper: _method_sig_line
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method, expected_contains",
    [
        # Basic void method, no params
        (
            {
                "name": "init",
                "return_type": "void",
                "parameters": [],
                "line_range": {"start": 10, "end": 15},
            },
            ["init", "→void(0p)", "10-15"],
        ),
        # 2 params
        (
            {
                "name": "createSession",
                "return_type": "String",
                "parameters": [{"name": "a"}, {"name": "b"}],
                "line_range": {"start": 100, "end": 120},
            },
            ["createSession", "→String(2p)", "100-120"],
        ),
        # Return type abbreviation
        (
            {
                "name": "isAlive",
                "return_type": "boolean",
                "parameters": [],
                "line_range": {"start": 50, "end": 52},
            },
            ["isAlive", "→bool(0p)", "50-52"],
        ),
        # Complex generic return type (kept as-is from simple name)
        (
            {
                "name": "getMap",
                "return_type": "Map<String, Object>",
                "parameters": [{"name": "k"}],
                "line_range": {"start": 200, "end": 205},
            },
            ["getMap", "(1p)", "200-205"],
        ),
    ],
)
def test_method_sig_line_shape(method: dict, expected_contains: list[str]) -> None:
    line = _method_sig_line(method)
    for fragment in expected_contains:
        assert fragment in line, f"Expected {fragment!r} in {line!r}"


@pytest.mark.parametrize(
    "return_type, expected",
    [
        ("void", "void"),
        ("boolean", "bool"),
        ("Boolean", "bool"),
        ("int", "int"),
        ("Integer", "int"),
        ("long", "long"),
        ("String", "String"),
        ("Object", "Object"),
        ("SomeCustomType", "SomeCustomType"),
        ("", "void"),
        # Fully qualified class → simple name
        ("java.util.List", "List"),
    ],
)
def test_shorten_return_type(return_type: str, expected: str) -> None:
    assert _shorten_return_type(return_type) == expected


# ---------------------------------------------------------------------------
# Shared fixture factory
# ---------------------------------------------------------------------------


def _make_simple_data(
    *,
    package: str = "com.example",
    class_name: str = "MyClass",
    n_methods: int = 3,
    n_fields: int = 2,
) -> dict:
    """Build minimal structure data for the formatter."""
    cls = {
        "name": class_name,
        "type": "class",
        "visibility": "public",
        "line_range": {"start": 1, "end": 100},
    }
    methods = [
        {
            "name": f"method{i}",
            "return_type": "void" if i % 2 == 0 else "int",
            "parameters": [{"name": "p", "type": "String"}] * (i % 3),
            "is_constructor": False,
            "is_static": False,
            "complexity_score": 1,
            "line_range": {"start": 10 + i * 5, "end": 14 + i * 5},
            "javadoc": "",
        }
        for i in range(n_methods)
    ]
    fields = [
        {
            "name": f"field{i}",
            "type": "int",
            "visibility": "private",
            "line_range": {"start": 5 + i, "end": 5 + i},
        }
        for i in range(n_fields)
    ]
    return {
        "file_path": f"src/{class_name}.java",
        "language": "java",
        "line_count": 100,
        "package": {"name": package},
        "classes": [cls],
        "methods": methods,
        "fields": fields,
        "imports": [],
        "statistics": {"method_count": n_methods, "field_count": n_fields},
    }


# ---------------------------------------------------------------------------
# JavaTableFormatterSignaturesMixin via JavaTableFormatter
# ---------------------------------------------------------------------------


class TestJavaSignaturesMode:
    def test_header_contains_signatures_marker(self) -> None:
        fmt = JavaTableFormatter(format_type="signatures")
        output = fmt.format_structure(_make_simple_data())
        assert "[signatures]" in output

    def test_method_lines_present(self) -> None:
        fmt = JavaTableFormatter(format_type="signatures")
        output = fmt.format_structure(_make_simple_data(n_methods=3))
        # Each method should have an arrow signature line
        assert "→void" in output or "→int" in output

    def test_param_count_not_types(self) -> None:
        """Signatures mode must show Np, not full type lists."""
        fmt = JavaTableFormatter(format_type="signatures")
        data = _make_simple_data(n_methods=2)
        # Give method0 one param of type "HttpServletRequest"
        data["methods"][0]["parameters"] = [
            {"name": "req", "type": "HttpServletRequest"}
        ]
        output = fmt.format_structure(data)
        # Should show (1p) not the full type
        assert "(1p)" in output
        assert "HttpServletRequest" not in output

    def test_class_group_header_present(self) -> None:
        fmt = JavaTableFormatter(format_type="signatures")
        output = fmt.format_structure(_make_simple_data(class_name="FooBar"))
        assert "## FooBar" in output

    def test_line_range_in_method_output(self) -> None:
        fmt = JavaTableFormatter(format_type="signatures")
        output = fmt.format_structure(_make_simple_data(n_methods=1))
        # method0 starts at 10, ends at 14
        assert "10-14" in output

    def test_next_step_hint_present(self) -> None:
        fmt = JavaTableFormatter(format_type="signatures")
        output = fmt.format_structure(_make_simple_data())
        assert "next_step" in output
        assert "--partial-read" in output

    def test_fields_shown_when_few(self) -> None:
        fmt = JavaTableFormatter(format_type="signatures")
        output = fmt.format_structure(_make_simple_data(n_fields=2))
        assert "fields:" in output
        assert "field0" in output

    def test_no_full_signatures_bloat(self) -> None:
        """Ensure signatures output is shorter than full output."""
        full_fmt = JavaTableFormatter(format_type="full")
        sig_fmt = JavaTableFormatter(format_type="signatures")
        data = _make_simple_data(n_methods=20, n_fields=5)
        full_output = full_fmt.format_structure(data)
        sig_output = sig_fmt.format_structure(data)
        assert len(sig_output) < len(full_output), (
            f"signatures ({len(sig_output)}) should be shorter than full ({len(full_output)})"
        )

    def test_multi_class_grouping(self) -> None:
        """Each top-level class gets its own block (non-overlapping ranges)."""
        fmt = JavaTableFormatter(format_type="signatures")
        data = _make_simple_data(n_methods=0, n_fields=0)
        # MyClass spans 1-100; put Helper completely outside that range
        data["classes"].append(
            {
                "name": "HelperClass",
                "type": "class",
                "visibility": "public",
                "line_range": {"start": 110, "end": 200},
            }
        )
        output = fmt.format_structure(data)
        assert "## MyClass" in output
        assert "## HelperClass" in output

    def test_package_line_in_output(self) -> None:
        fmt = JavaTableFormatter(format_type="signatures")
        output = fmt.format_structure(_make_simple_data(package="org.apache.lucene"))
        assert "org.apache.lucene" in output


# ---------------------------------------------------------------------------
# BaseTableFormatter dispatch
# ---------------------------------------------------------------------------


def test_base_formatter_signatures_dispatch_to_mixin() -> None:
    """format_structure("signatures") routes to _format_signatures_table when present."""
    fmt = JavaTableFormatter(format_type="signatures")
    # Should not raise
    output = fmt.format_structure(_make_simple_data())
    assert isinstance(output, str)
    assert len(output) > 0


def test_base_formatter_signatures_raises_for_unsupported() -> None:
    """A formatter without _format_signatures_table raises ValueError."""
    fmt = GoTableFormatter(format_type="signatures")
    # GoTableFormatter does not inherit SignaturesMixin → should raise
    with pytest.raises((ValueError, AttributeError)):
        fmt.format_structure(
            {"package": {}, "classes": [], "methods": [], "fields": []}
        )


# ---------------------------------------------------------------------------
# DefaultTableFormatter dispatch
# ---------------------------------------------------------------------------


def test_default_formatter_signatures_dispatch() -> None:
    fmt = DefaultTableFormatter(format_type="signatures")
    data = _make_simple_data()
    output = fmt.format_structure(data)
    assert "[signatures]" in output
    assert "next_step" in output


# ---------------------------------------------------------------------------
# FormatterRegistry
# ---------------------------------------------------------------------------


def test_formatter_registry_returns_formatter_for_signatures() -> None:
    fmt = FormatterRegistry.get_formatter_for_language("java", "signatures")
    assert fmt is not None
    output = fmt.format_structure(_make_simple_data())
    assert "[signatures]" in output


# ---------------------------------------------------------------------------
# analyze_code_structure_tool: _validate_format_type now accepts "signatures"
# ---------------------------------------------------------------------------


def test_validate_format_type_accepts_signatures() -> None:
    # Must not raise
    _validate_format_type({"format_type": "signatures"})


def test_validate_format_type_still_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="format_type must be one of"):
        _validate_format_type({"format_type": "unknown_mode"})
