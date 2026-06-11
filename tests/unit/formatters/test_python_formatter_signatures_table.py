"""Tests for Python signatures (lightweight method-directory) table rendering.

Covers:
1. _method_sig_line shape — name →returnType(Np) start-end
2. _shorten_return_type abbreviations
3. format_python_signatures_table: single class with 3 methods → exact lines
4. format_python_signatures_table: module-level functions (no classes)
5. format_python_signatures_table: mixed class + module functions
6. PythonTableFormatter.format_structure("signatures") dispatches correctly
7. FormatterRegistry.get_formatter_for_language("python", "signatures") works
8. Auto-detect via AnalyzeCodeStructureTool._resolve_language (no explicit language)
9. structure facade description no longer says "default java"
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.formatters._python_formatter_signatures_table import (
    _method_sig_line,
    _shorten_return_type,
    format_python_signatures_table,
)
from tree_sitter_analyzer.formatters.formatter_registry import FormatterRegistry
from tree_sitter_analyzer.formatters.python_formatter import PythonTableFormatter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_method(
    name: str,
    return_type: str,
    n_params: int,
    start: int,
    end: int,
) -> dict:
    """Build a minimal method dict."""
    return {
        "name": name,
        "return_type": return_type,
        "parameters": [{"name": f"p{i}", "type": "Any"} for i in range(n_params)],
        "line_range": {"start": start, "end": end},
    }


def _make_class(name: str, start: int, end: int) -> dict:
    return {
        "name": name,
        "type": "class",
        "visibility": "public",
        "line_range": {"start": start, "end": end},
    }


def _make_python_data(
    *,
    file_path: str = "src/calculator.py",
    classes: list | None = None,
    methods: list | None = None,
    stats: dict | None = None,
) -> dict:
    """Build minimal Python structure data."""
    return {
        "file_path": file_path,
        "language": "python",
        "classes": classes or [],
        "methods": methods or [],
        "statistics": stats or {},
    }


# ---------------------------------------------------------------------------
# 1. _method_sig_line shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method, expected_fragments",
    [
        # No params, None return type
        (
            _make_method("__init__", "None", 0, 10, 12),
            ["__init__", "→None(0p)", "10-12"],
        ),
        # 2 params, str return
        (
            _make_method("add", "int", 2, 20, 25),
            ["add", "→int(2p)", "20-25"],
        ),
        # 3 params, complex return type kept as simple name
        (
            _make_method("transform", "list", 3, 30, 40),
            ["transform", "→list(3p)", "30-40"],
        ),
    ],
)
def test_method_sig_line_shape(method: dict, expected_fragments: list[str]) -> None:
    line = _method_sig_line(method)
    for fragment in expected_fragments:
        assert fragment in line, f"Expected {fragment!r} in {line!r}"


# ---------------------------------------------------------------------------
# 2. _shorten_return_type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ret, expected",
    [
        ("None", "None"),
        ("str", "str"),
        ("int", "int"),
        ("bool", "bool"),
        ("float", "float"),
        ("Any", "Any"),
        ("list", "list"),
        ("dict", "dict"),
        ("", "None"),
        ("Optional[str]", "str"),  # strips Optional wrapper
        ("List[int]", "List"),  # generic → base name
        ("MyCustomType", "MyCustomType"),
    ],
)
def test_shorten_return_type(ret: str, expected: str) -> None:
    assert _shorten_return_type(ret) == expected


# ---------------------------------------------------------------------------
# 3. Single class with exactly 3 methods — exact signature lines
# ---------------------------------------------------------------------------


def _three_method_data() -> dict:
    """A Python fixture class with 3 methods for exact-assertion tests."""
    cls = _make_class("Calculator", 1, 50)
    methods = [
        _make_method("__init__", "None", 1, 5, 8),
        _make_method("add", "int", 2, 10, 14),
        _make_method("reset", "None", 0, 16, 18),
    ]
    return _make_python_data(
        file_path="src/calculator.py",
        classes=[cls],
        methods=methods,
        stats={"method_count": 3, "class_count": 1},
    )


def test_signatures_header_contains_signatures_marker() -> None:
    output = format_python_signatures_table(_three_method_data())
    assert "[signatures]" in output


def test_signatures_module_name_in_header() -> None:
    output = format_python_signatures_table(_three_method_data())
    assert "calculator" in output


def test_signatures_class_block_header() -> None:
    output = format_python_signatures_table(_three_method_data())
    assert "## Calculator" in output


def test_signatures_method_lines_exact_count() -> None:
    """Exactly 3 method lines should appear (one per method)."""
    output = format_python_signatures_table(_three_method_data())
    arrow_lines = [ln for ln in output.splitlines() if "→" in ln]
    assert len(arrow_lines) == 3


def test_signatures_init_line_exact() -> None:
    output = format_python_signatures_table(_three_method_data())
    assert "  __init__ →None(1p) 5-8" in output


def test_signatures_add_line_exact() -> None:
    output = format_python_signatures_table(_three_method_data())
    assert "  add →int(2p) 10-14" in output


def test_signatures_reset_line_exact() -> None:
    output = format_python_signatures_table(_three_method_data())
    assert "  reset →None(0p) 16-18" in output


def test_signatures_next_step_hint_present() -> None:
    output = format_python_signatures_table(_three_method_data())
    assert "next_step" in output
    assert "action=read" in output


def test_signatures_methods_count_line() -> None:
    output = format_python_signatures_table(_three_method_data())
    assert "methods: 3" in output


def test_signatures_shorter_than_full() -> None:
    """signatures output should be shorter than full output."""
    from tree_sitter_analyzer.formatters.python_formatter import PythonTableFormatter

    data = _three_method_data()
    full_fmt = PythonTableFormatter(format_type="full")
    sig_fmt = PythonTableFormatter(format_type="signatures")
    full_out = full_fmt.format_structure(data)
    sig_out = sig_fmt.format_structure(data)
    assert len(sig_out) < len(full_out), (
        f"signatures ({len(sig_out)}) should be shorter than full ({len(full_out)})"
    )


# ---------------------------------------------------------------------------
# 4. Module-level functions only (no classes)
# ---------------------------------------------------------------------------


def test_signatures_flat_module_no_classes() -> None:
    """Module with no classes renders a <module functions> block."""
    methods = [
        _make_method("helper", "str", 1, 5, 10),
        _make_method("main", "None", 0, 12, 20),
    ]
    data = _make_python_data(methods=methods)
    output = format_python_signatures_table(data)
    assert "<module functions>" in output
    assert "  helper →str(1p) 5-10" in output
    assert "  main →None(0p) 12-20" in output


# ---------------------------------------------------------------------------
# 5. Mixed: class + module-level functions
# ---------------------------------------------------------------------------


def test_signatures_mixed_class_and_module_functions() -> None:
    """Class methods and module-level functions both appear, separated."""
    cls = _make_class("Foo", 1, 30)
    methods = [
        _make_method("bar", "int", 1, 5, 10),  # inside Foo
        _make_method("top_func", "None", 0, 35, 40),  # outside Foo
    ]
    data = _make_python_data(classes=[cls], methods=methods)
    output = format_python_signatures_table(data)
    assert "## Foo" in output
    assert "  bar →int(1p) 5-10" in output
    assert "<module functions>" in output
    assert "  top_func →None(0p) 35-40" in output


# ---------------------------------------------------------------------------
# 6. PythonTableFormatter.format_structure("signatures") dispatch
# ---------------------------------------------------------------------------


def test_python_formatter_format_structure_signatures() -> None:
    """PythonTableFormatter with format_type='signatures' must not raise."""
    fmt = PythonTableFormatter(format_type="signatures")
    output = fmt.format_structure(_three_method_data())
    assert isinstance(output, str)
    assert "[signatures]" in output


def test_python_formatter_signatures_not_raises() -> None:
    """Previously raised ValueError — must now succeed."""
    fmt = PythonTableFormatter(format_type="signatures")
    data = _make_python_data(
        classes=[_make_class("A", 1, 10)],
        methods=[_make_method("m", "None", 0, 2, 5)],
    )
    # Must NOT raise ValueError("signatures format not supported...")
    output = fmt.format_structure(data)
    assert "signatures" in output


# ---------------------------------------------------------------------------
# 7. FormatterRegistry.get_formatter_for_language("python", "signatures")
# ---------------------------------------------------------------------------


def test_formatter_registry_python_signatures() -> None:
    fmt = FormatterRegistry.get_formatter_for_language("python", "signatures")
    assert fmt is not None
    output = fmt.format_structure(_three_method_data())
    assert "[signatures]" in output
    assert "Calculator" in output


# ---------------------------------------------------------------------------
# 8. Auto-detect: no language param, .py file → Python signatures
# ---------------------------------------------------------------------------


def test_auto_detect_language_resolves_python_for_py_extension(tmp_path) -> None:
    """AnalyzeCodeStructureTool._resolve_language auto-detects 'python' for .py files."""
    from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
        AnalyzeCodeStructureTool,
    )

    # Create a temporary .py file so resolve works
    py_file = tmp_path / "sample.py"
    py_file.write_text("x = 1\n")

    tool = AnalyzeCodeStructureTool(project_root=str(tmp_path))
    detected = tool._resolve_language(None, str(py_file))
    assert detected == "python"


# ---------------------------------------------------------------------------
# 9. Structure facade description no longer says "default java"
# ---------------------------------------------------------------------------


def test_structure_facade_description_no_default_java() -> None:
    """'default java' must not appear in the signatures action description."""
    from tree_sitter_analyzer.mcp.tools.structure_facade import _STRUCTURE_DESCRIPTION

    # The old text contained "(default java)" — must now be absent
    assert "default java" not in _STRUCTURE_DESCRIPTION


def test_structure_facade_description_mentions_auto_detect() -> None:
    """Description should mention auto-detection for the signatures action."""
    from tree_sitter_analyzer.mcp.tools.structure_facade import _STRUCTURE_DESCRIPTION

    assert (
        "auto-detect" in _STRUCTURE_DESCRIPTION
        or "auto detect" in _STRUCTURE_DESCRIPTION
    )


# ---------------------------------------------------------------------------
# Coverage gap-fillers for edge cases in _python_formatter_signatures_table
# ---------------------------------------------------------------------------


def test_module_name_empty_file_path() -> None:
    """Empty file_path falls back to 'module'."""
    from tree_sitter_analyzer.formatters._python_formatter_signatures_table import (
        _module_name,
    )

    assert _module_name("") == "module"


def test_module_name_pyw_extension() -> None:
    """'.pyw' extension is stripped correctly."""
    from tree_sitter_analyzer.formatters._python_formatter_signatures_table import (
        _module_name,
    )

    assert _module_name("scripts/run.pyw") == "run"


def test_module_name_pyi_extension() -> None:
    """'.pyi' stub extension is stripped correctly."""
    from tree_sitter_analyzer.formatters._python_formatter_signatures_table import (
        _module_name,
    )

    assert _module_name("types/model.pyi") == "model"


def test_methods_in_range_zero_range_returns_empty() -> None:
    """A zero line_range (start=0, end=0) returns an empty list."""
    from tree_sitter_analyzer.formatters._python_formatter_signatures_table import (
        _methods_in_range,
    )

    methods = [{"name": "f", "line_range": {"start": 5, "end": 10}}]
    result = _methods_in_range(methods, {"start": 0, "end": 0})
    assert result == []


def test_trim_trailing_blank_lines_removes_blanks() -> None:
    """_trim_trailing_blank_lines removes trailing empty strings."""
    from tree_sitter_analyzer.formatters._python_formatter_signatures_table import (
        _trim_trailing_blank_lines,
    )

    lines = ["a", "b", "", ""]
    _trim_trailing_blank_lines(lines)
    assert lines == ["a", "b"]
