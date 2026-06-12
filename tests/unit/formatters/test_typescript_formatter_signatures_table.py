"""Tests for TypeScript signatures (lightweight method-directory) table rendering.

Covers:
1. _method_sig_line shape — name →returnType(Np) start-end
2. _shorten_return_type abbreviations
3. format_typescript_signatures_table: interface with 2 methods → exact lines
4. format_typescript_signatures_table: class with constructor + 2 methods
5. format_typescript_signatures_table: top-level function overload declarations
6. format_typescript_signatures_table: exported arrow function
7. TypeScriptTableFormatter.format_structure("signatures") dispatches correctly
8. FormatterRegistry works for typescript + signatures
9. Error message for unsupported language enumerates supported languages
10. Interfaces count as grouping containers
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.formatters._typescript_formatter_signatures_table import (
    _method_sig_line,
    _shorten_return_type,
    format_typescript_signatures_table,
)
from tree_sitter_analyzer.formatters.formatter_registry import FormatterRegistry
from tree_sitter_analyzer.formatters.typescript_formatter import (
    TypeScriptTableFormatter,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_method(
    name: str,
    return_type: str,
    n_params: int,
    start: int,
    end: int,
    *,
    is_constructor: bool = False,
) -> dict:
    """Build a minimal method dict matching TypeScript structure output."""
    return {
        "name": name,
        "return_type": return_type,
        "parameters": [{"name": f"p{i}", "type": "any"} for i in range(n_params)],
        "line_range": {"start": start, "end": end},
        "is_constructor": is_constructor,
    }


def _make_class(name: str, start: int, end: int, *, class_type: str = "class") -> dict:
    return {
        "name": name,
        "class_type": class_type,
        "visibility": "public",
        "line_range": {"start": start, "end": end},
    }


def _make_ts_data(
    *,
    file_path: str = "src/api.ts",
    classes: list | None = None,
    methods: list | None = None,
    stats: dict | None = None,
) -> dict:
    """Build minimal TypeScript structure data."""
    return {
        "file_path": file_path,
        "language": "typescript",
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
        (
            _make_method("constructor", "void", 0, 10, 12, is_constructor=True),
            ["constructor", "→void(0p)", "10-12"],
        ),
        (
            _make_method("add", "number", 2, 20, 25),
            ["add", "→number(2p)", "20-25"],
        ),
        (
            _make_method("greet", "string", 1, 30, 35),
            ["greet", "→string(1p)", "30-35"],
        ),
        (
            _make_method("findAll", "Promise<User[]>", 0, 40, 42),
            ["findAll", "→Promise(0p)", "40-42"],
        ),
    ],
)
def test_method_sig_line_shape(method: dict, expected_fragments: list[str]) -> None:
    line = _method_sig_line(method)
    for fragment in expected_fragments:
        assert fragment in line, f"Expected {fragment!r} in {line!r}"


# ---------------------------------------------------------------------------
# 2. _shorten_return_type abbreviations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ret, expected",
    [
        ("void", "void"),
        ("string", "string"),
        ("number", "number"),
        ("boolean", "boolean"),
        ("any", "any"),
        ("never", "never"),
        ("unknown", "unknown"),
        ("", "void"),
        ("Promise<User[]>", "Promise"),
        ("Map<string, number>", "Map"),
        ("MyCustomType", "MyCustomType"),
        ("Array<string>", "Array"),
    ],
)
def test_shorten_return_type(ret: str, expected: str) -> None:
    assert _shorten_return_type(ret) == expected


# ---------------------------------------------------------------------------
# Fixture: interface with 2 methods
# ---------------------------------------------------------------------------


def _interface_data() -> dict:
    """Interface IUserService with 2 methods."""
    iface = _make_class("IUserService", 1, 20, class_type="interface")
    methods = [
        _make_method("getUser", "User", 1, 3, 3),
        _make_method("saveUser", "void", 1, 4, 4),
    ]
    return _make_ts_data(
        file_path="src/iuser-service.ts",
        classes=[iface],
        methods=methods,
        stats={"method_count": 2, "class_count": 1},
    )


# ---------------------------------------------------------------------------
# 3. Interface grouping tests
# ---------------------------------------------------------------------------


def test_interface_block_header_present() -> None:
    output = format_typescript_signatures_table(_interface_data())
    assert "## IUserService" in output


def test_interface_class_type_shown() -> None:
    """Interface type should be visible in the header."""
    output = format_typescript_signatures_table(_interface_data())
    assert "## IUserService (1-20) [interface, 2 methods]" in output


def test_container_kind_read_from_type_key() -> None:
    """Real analysis data stores the container kind under 'type'
    (_convert_class), not 'class_type' — Codex P2 on #541: without the
    fallback every interface/enum/namespace renders as [class, ...]."""
    iface = _make_class("Window", 17, 22, class_type="interface")
    # Re-shape to the _convert_class spelling: kind under "type"
    iface["type"] = iface.pop("class_type")
    data = {
        "file_path": "globals.d.ts",
        "classes": [iface],
        "methods": [],
        "functions": [],
    }
    output = format_typescript_signatures_table(data)
    assert "## Window (17-22) [interface, 0 methods]" in output


def test_interface_method_count_exact() -> None:
    """Exactly 2 arrow lines for the interface's 2 methods."""
    output = format_typescript_signatures_table(_interface_data())
    arrow_lines = [ln for ln in output.splitlines() if "→" in ln]
    assert len(arrow_lines) == 2


def test_interface_getuser_line_exact() -> None:
    output = format_typescript_signatures_table(_interface_data())
    assert "  getUser →User(1p) 3-3" in output


def test_interface_saveuser_line_exact() -> None:
    output = format_typescript_signatures_table(_interface_data())
    assert "  saveUser →void(1p) 4-4" in output


# ---------------------------------------------------------------------------
# Fixture: class with constructor + 2 methods
# ---------------------------------------------------------------------------


def _class_with_constructor_data() -> dict:
    """UserService class: constructor + 2 methods."""
    cls = _make_class("UserService", 1, 50)
    methods = [
        _make_method("constructor", "void", 1, 5, 8, is_constructor=True),
        _make_method("findById", "User", 2, 10, 15),
        _make_method("delete", "boolean", 1, 17, 20),
    ]
    return _make_ts_data(
        file_path="src/user-service.ts",
        classes=[cls],
        methods=methods,
        stats={"method_count": 3, "class_count": 1},
    )


# ---------------------------------------------------------------------------
# 4. Class with constructor + 2 methods
# ---------------------------------------------------------------------------


def test_class_block_header_present() -> None:
    output = format_typescript_signatures_table(_class_with_constructor_data())
    assert "## UserService" in output


def test_class_method_count_exact() -> None:
    """Exactly 3 arrow lines for constructor + 2 methods."""
    output = format_typescript_signatures_table(_class_with_constructor_data())
    arrow_lines = [ln for ln in output.splitlines() if "→" in ln]
    assert len(arrow_lines) == 3


def test_class_constructor_line_exact() -> None:
    output = format_typescript_signatures_table(_class_with_constructor_data())
    assert "  constructor →void(1p) 5-8" in output


def test_class_findbyid_line_exact() -> None:
    output = format_typescript_signatures_table(_class_with_constructor_data())
    assert "  findById →User(2p) 10-15" in output


def test_class_delete_line_exact() -> None:
    output = format_typescript_signatures_table(_class_with_constructor_data())
    assert "  delete →boolean(1p) 17-20" in output


def test_class_methods_count_summary_line() -> None:
    output = format_typescript_signatures_table(_class_with_constructor_data())
    assert "methods: 3" in output


# ---------------------------------------------------------------------------
# 5. Top-level function overload declarations + regular implementation
#    Convention (matches #485/Java/Python):
#      Each overload is listed as a separate line with its own line range.
#      This is the natural output of the structure extractor — each overload
#      appears as a distinct method entry with different start/end lines.
# ---------------------------------------------------------------------------


def _overload_data() -> dict:
    """2 overload declarations + 1 implementation for 'process'."""
    # No classes — top-level functions
    methods = [
        _make_method("process", "string", 1, 5, 5),  # overload 1: (input: string)
        _make_method("process", "number", 1, 6, 6),  # overload 2: (input: number)
        _make_method("process", "string | number", 1, 7, 12),  # implementation
    ]
    return _make_ts_data(
        file_path="src/process.ts",
        methods=methods,
        stats={"method_count": 3, "class_count": 0},
    )


def test_overloads_each_appear_as_separate_line() -> None:
    """All 3 process lines (2 overloads + implementation) must appear."""
    output = format_typescript_signatures_table(_overload_data())
    arrow_lines = [ln for ln in output.splitlines() if "→" in ln and "process" in ln]
    assert len(arrow_lines) == 3


def test_overload_line_1_exact() -> None:
    output = format_typescript_signatures_table(_overload_data())
    assert "  process →string(1p) 5-5" in output


def test_overload_line_2_exact() -> None:
    output = format_typescript_signatures_table(_overload_data())
    assert "  process →number(1p) 6-6" in output


def test_overload_implementation_line_exact() -> None:
    output = format_typescript_signatures_table(_overload_data())
    assert "  process →string | number(1p) 7-12" in output


# ---------------------------------------------------------------------------
# 6. Exported arrow function (top-level, no class)
# ---------------------------------------------------------------------------


def _arrow_function_data() -> dict:
    """Exported arrow function: const greet = (name: string): string => ..."""
    methods = [
        _make_method("greet", "string", 1, 3, 3),
    ]
    return _make_ts_data(
        file_path="src/greet.ts",
        methods=methods,
        stats={"method_count": 1, "class_count": 0},
    )


def test_arrow_function_appears_in_module_block() -> None:
    output = format_typescript_signatures_table(_arrow_function_data())
    assert "greet" in output


def test_arrow_function_line_exact() -> None:
    output = format_typescript_signatures_table(_arrow_function_data())
    assert "  greet →string(1p) 3-3" in output


def test_module_functions_block_header_present() -> None:
    output = format_typescript_signatures_table(_arrow_function_data())
    assert "<module functions>" in output


# ---------------------------------------------------------------------------
# 7. TypeScriptTableFormatter.format_structure("signatures") dispatch
# ---------------------------------------------------------------------------


def test_typescript_formatter_signatures_dispatch() -> None:
    """TypeScriptTableFormatter with format_type='signatures' must not raise."""
    fmt = TypeScriptTableFormatter(format_type="signatures")
    output = fmt.format_structure(_class_with_constructor_data())
    assert isinstance(output, str)
    assert "[signatures]" in output


def test_typescript_formatter_signatures_not_raises() -> None:
    """Previously raised ValueError — must now succeed."""
    fmt = TypeScriptTableFormatter(format_type="signatures")
    data = _make_ts_data(
        classes=[_make_class("A", 1, 10)],
        methods=[_make_method("m", "void", 0, 2, 5)],
    )
    output = fmt.format_structure(data)
    assert "signatures" in output


def test_typescript_formatter_signatures_shorter_than_full() -> None:
    """signatures output should be shorter than full output."""
    data = _class_with_constructor_data()
    full_out = TypeScriptTableFormatter(format_type="full").format_structure(data)
    sig_out = TypeScriptTableFormatter(format_type="signatures").format_structure(data)
    assert len(sig_out) < len(full_out), (
        f"signatures ({len(sig_out)}) should be shorter than full ({len(full_out)})"
    )


# ---------------------------------------------------------------------------
# 8. FormatterRegistry.get_formatter_for_language("typescript", "signatures")
# ---------------------------------------------------------------------------


def test_formatter_registry_typescript_signatures() -> None:
    fmt = FormatterRegistry.get_formatter_for_language("typescript", "signatures")
    assert fmt is not None
    output = fmt.format_structure(_class_with_constructor_data())
    assert "[signatures]" in output
    assert "UserService" in output


# ---------------------------------------------------------------------------
# 9. Error message for unsupported language enumerates supported languages
# ---------------------------------------------------------------------------


def test_unsupported_language_error_enumerates_languages() -> None:
    """When a formatter doesn't support signatures, the error must list which ones do."""
    from typing import Any

    from tree_sitter_analyzer.formatters.base_formatter import BaseTableFormatter

    class _UnsupportedFmt(BaseTableFormatter):
        def _format_full_table(self, data: dict[str, Any]) -> str:
            return ""

        def _format_compact_table(self, data: dict[str, Any]) -> str:
            return ""

        def format_summary(self, data: dict[str, Any]) -> str:
            return ""

        def format_structure(self, data: dict[str, Any]) -> str:
            return super().format_structure(data)

        def format_advanced(
            self, data: dict[str, Any], output_format: str = "json"
        ) -> str:
            return ""

        def format_table(self, data: dict[str, Any], table_type: str = "full") -> str:
            return ""

    fmt = _UnsupportedFmt(format_type="signatures")
    with pytest.raises(ValueError) as exc_info:
        fmt.format_structure({})
    msg = str(exc_info.value)
    # Must list at least "python" and "java" (known supported languages)
    assert "python" in msg.lower() or "java" in msg.lower(), (
        f"Error message must enumerate supported languages, got: {msg!r}"
    )


def test_unsupported_language_error_includes_typescript() -> None:
    """After this fix, 'typescript' must appear in the supported list in the error."""
    from typing import Any

    from tree_sitter_analyzer.formatters.base_formatter import BaseTableFormatter

    class _UnsupportedFmt(BaseTableFormatter):
        def _format_full_table(self, data: dict[str, Any]) -> str:
            return ""

        def _format_compact_table(self, data: dict[str, Any]) -> str:
            return ""

        def format_summary(self, data: dict[str, Any]) -> str:
            return ""

        def format_structure(self, data: dict[str, Any]) -> str:
            return super().format_structure(data)

        def format_advanced(
            self, data: dict[str, Any], output_format: str = "json"
        ) -> str:
            return ""

        def format_table(self, data: dict[str, Any], table_type: str = "full") -> str:
            return ""

    fmt = _UnsupportedFmt(format_type="signatures")
    with pytest.raises(ValueError) as exc_info:
        fmt.format_structure({})
    msg = str(exc_info.value)
    assert "typescript" in msg.lower(), (
        f"'typescript' must appear in supported-language list, got: {msg!r}"
    )


# ---------------------------------------------------------------------------
# 10. Interfaces count as grouping containers
# ---------------------------------------------------------------------------


def test_interface_used_as_container_for_methods() -> None:
    """Methods inside an interface's line range appear under that interface."""
    iface = _make_class("IRepo", 1, 15, class_type="interface")
    methods = [
        _make_method("findAll", "User[]", 0, 3, 3),
        _make_method("save", "void", 1, 5, 5),
    ]
    data = _make_ts_data(classes=[iface], methods=methods)
    output = format_typescript_signatures_table(data)
    # Both methods should appear under the IRepo section
    assert "## IRepo" in output
    assert "  findAll →" in output
    assert "  save →" in output
    # No floating module-functions block for these (they're in the interface)
    assert "<module functions>" not in output


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_data_no_crash() -> None:
    """format_typescript_signatures_table with empty data must not crash."""
    output = format_typescript_signatures_table({})
    assert isinstance(output, str)
    assert "[signatures]" in output


def test_header_contains_signatures_marker() -> None:
    output = format_typescript_signatures_table(_class_with_constructor_data())
    assert "[signatures]" in output


def test_next_step_hint_present() -> None:
    output = format_typescript_signatures_table(_class_with_constructor_data())
    assert "next_step" in output


def test_dts_extension_stripped_from_module_name() -> None:
    """'.d.ts' extension should be stripped cleanly from the header."""
    data = _make_ts_data(file_path="types/lib.d.ts")
    output = format_typescript_signatures_table(data)
    assert "lib" in output
    # Should not show raw .d.ts in the header name
    lines = output.splitlines()
    header = lines[0] if lines else ""
    assert ".d.ts" not in header


def test_tsx_extension_stripped_from_module_name() -> None:
    """'.tsx' extension should be stripped cleanly from the header."""
    data = _make_ts_data(file_path="components/Button.tsx")
    output = format_typescript_signatures_table(data)
    assert "Button" in output
    lines = output.splitlines()
    header = lines[0] if lines else ""
    assert ".tsx" not in header


# ---------------------------------------------------------------------------
# Coverage gap-fillers
# ---------------------------------------------------------------------------


def test_mixed_class_and_module_functions() -> None:
    """Class methods AND module-level functions both appear — covers line 70."""
    cls = _make_class("Foo", 1, 20)
    methods = [
        _make_method("bar", "number", 1, 5, 8),  # inside Foo
        _make_method("topLevel", "void", 0, 30, 35),  # outside Foo (module level)
    ]
    data = _make_ts_data(classes=[cls], methods=methods)
    output = format_typescript_signatures_table(data)
    assert "## Foo" in output
    assert "  bar →number(1p) 5-8" in output
    assert "<module functions>" in output
    assert "  topLevel →void(0p) 30-35" in output


def test_module_name_bare_extension_only_falls_back_to_module() -> None:
    """A file named just '.ts' strips to empty basename → falls back to 'module'."""
    from tree_sitter_analyzer.formatters._typescript_formatter_signatures_table import (
        _module_name,
    )

    # This covers the `basename or "module"` branch (line 93/97)
    assert _module_name(".ts") == "module"


def test_class_with_zero_range_not_assigned_methods() -> None:
    """A class with start=0, end=0 is skipped — method falls through to module funcs."""
    # Covers the `not c_start and not c_end: continue` branch (lines 197-198)
    cls = _make_class("Empty", 0, 0)  # zero range
    methods = [_make_method("orphan", "void", 0, 5, 5)]
    data = _make_ts_data(classes=[cls], methods=methods)
    output = format_typescript_signatures_table(data)
    # orphan should end up in module functions (since the class range is zero)
    assert "orphan" in output


def test_nested_classes_innermost_wins() -> None:
    """Method inside nested class goes to innermost — covers the span < best_span branch."""
    outer = _make_class("Outer", 1, 50)
    inner = _make_class("Inner", 10, 20)
    methods = [
        _make_method("outerOnly", "void", 0, 3, 4),  # only in Outer
        _make_method(
            "innerMethod", "string", 1, 12, 15
        ),  # in both, but closer to Inner
    ]
    data = _make_ts_data(classes=[outer, inner], methods=methods)
    output = format_typescript_signatures_table(data)
    # innerMethod must appear under Inner only
    assert output.count("innerMethod") == 1
    # Get the Outer block text (before Inner block)
    outer_block = output.split("## Outer")[1].split("## Inner")[0]
    assert "innerMethod" not in outer_block


def test_trim_trailing_blank_lines() -> None:
    """_trim_trailing_blank_lines removes trailing empty strings — covers line 230."""
    from tree_sitter_analyzer.formatters._typescript_formatter_signatures_table import (
        _trim_trailing_blank_lines,
    )

    lines = ["a", "b", "", ""]
    _trim_trailing_blank_lines(lines)
    assert lines == ["a", "b"]


def test_trim_trailing_blank_lines_no_trailing() -> None:
    """_trim_trailing_blank_lines does nothing when no trailing blanks."""
    from tree_sitter_analyzer.formatters._typescript_formatter_signatures_table import (
        _trim_trailing_blank_lines,
    )

    lines = ["a", "b"]
    _trim_trailing_blank_lines(lines)
    assert lines == ["a", "b"]


def test_module_level_functions_excludes_class_members() -> None:
    """_module_level_functions correctly filters out methods inside a class range."""
    from tree_sitter_analyzer.formatters._typescript_formatter_signatures_table import (
        _module_level_functions,
    )

    classes = [{"line_range": {"start": 5, "end": 20}}]
    methods = [
        {"name": "inside", "line_range": {"start": 10, "end": 12}},
        {"name": "outside", "line_range": {"start": 25, "end": 30}},
    ]
    result = _module_level_functions(methods, classes)
    assert len(result) == 1
    assert result[0]["name"] == "outside"
