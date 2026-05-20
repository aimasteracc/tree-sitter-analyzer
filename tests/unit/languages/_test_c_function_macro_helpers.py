"""Tests for C function extraction, macro, and signature parsing helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tree_sitter_analyzer.languages._c_function_helpers import (
    _function_raw_text,
    extract_c_function,
)
from tree_sitter_analyzer.languages._c_macro_helpers import (
    _append_macro_params,
    _macro_function_parts,
    extract_macro_function,
)
from tree_sitter_analyzer.languages._c_signature_helpers import (
    _append_modifier,
    _find_function_declarator,
    _function_declarator_info,
    _pointer_return_type,
    parse_function_signature,
)


@dataclass
class FakeNode:
    type: str
    text: str = ""
    children: list[FakeNode] = field(default_factory=list)
    fields: dict[str, FakeNode] = field(default_factory=dict)
    start_point: tuple[int, int] = (0, 0)
    end_point: tuple[int, int] = (0, 0)
    start_byte: int = 0
    end_byte: int = 0
    parent: FakeNode | None = None

    def child_by_field_name(self, name: str) -> FakeNode | None:
        return self.fields.get(name)


def _get_node_text(node: Any) -> str:
    return node.text


class TestFunctionRawText:
    def test_basic_extraction(self) -> None:
        lines = ["int foo() {", "    return 0;", "}"]
        result = _function_raw_text(lines, 1, 3)
        assert "int foo() {" in result
        assert "return 0;" in result

    def test_single_line(self) -> None:
        lines = ["int x;"]
        result = _function_raw_text(lines, 1, 1)
        assert result == "int x;"

    def test_out_of_range_clamped(self) -> None:
        lines = ["line1", "line2"]
        result = _function_raw_text(lines, 1, 100)
        assert "line1" in result
        assert "line2" in result

    def test_empty_lines(self) -> None:
        result = _function_raw_text([], 1, 5)
        assert result == ""


class TestExtractCFunction:
    def test_basic_function(self) -> None:
        node = FakeNode(
            "function_definition",
            start_point=(0, 0),
            end_point=(2, 1),
        )
        def parse_sig(n: Any) -> tuple[str, str, list[str], list[str]]:
            return ("main", "int", [], [])
        def calc_complexity(n: Any) -> int:
            return 1
        def get_comment(line: int) -> str | None:
            return None

        result = extract_c_function(
            node, _get_node_text,
            ["int main() {", "    return 0;", "}"],
            parse_sig, calc_complexity, get_comment,
        )
        assert result is not None
        assert result.name == "main"
        assert result.return_type == "int"
        assert result.language == "c"

    def test_none_signature(self) -> None:
        node = FakeNode(
            "function_definition",
            start_point=(0, 0),
            end_point=(2, 1),
        )
        def parse_sig(n: Any) -> None:
            return None
        result = extract_c_function(
            node, _get_node_text, ["void foo() {}"],
            parse_sig, lambda n: 1, lambda _ln: None,
        )
        assert result is None

    def test_with_modifiers(self) -> None:
        node = FakeNode(
            "function_definition",
            start_point=(0, 0),
            end_point=(1, 1),
        )
        def parse_sig(n: Any) -> tuple[str, str, list[str], list[str]]:
            return ("helper", "void", ["int x"], ["static"])
        result = extract_c_function(
            node, _get_node_text, ["static void helper(int x) {", "}"],
            parse_sig, lambda n: 2, lambda _ln: None,
        )
        assert result is not None
        assert result.is_static is True
        assert "static" in result.modifiers

    def test_with_docstring(self) -> None:
        node = FakeNode(
            "function_definition",
            start_point=(3, 0),
            end_point=(5, 1),
        )
        def parse_sig(n: Any) -> tuple[str, str, list[str], list[str]]:
            return ("docced", "void", [], [])
        result = extract_c_function(
            node, _get_node_text,
            ["/// Doc", "", "void docced() {", "}"],
            parse_sig, lambda n: 1, lambda _ln: "/// Doc",
        )
        assert result is not None
        assert result.docstring == "/// Doc"

    def test_exception_returns_none(self) -> None:
        node = FakeNode("function_definition")
        node.start_point = None  # type: ignore[assignment]
        result = extract_c_function(
            node, _get_node_text, [],
            lambda n: ("f", "int", [], []),
            lambda n: 1,
            lambda _ln: None,
        )
        assert result is None


class TestMacroFunctionParts:
    def test_identifier_and_params(self) -> None:
        node = FakeNode("preproc_def", children=[
            FakeNode("identifier", text="MAX"),
            FakeNode("preproc_params", children=[
                FakeNode("identifier", text="x"),
                FakeNode("identifier", text="y"),
            ]),
        ])
        name, params = _macro_function_parts(node, _get_node_text)
        assert name == "MAX"
        assert params == ["x", "y"]

    def test_no_params(self) -> None:
        node = FakeNode("preproc_def", children=[
            FakeNode("identifier", text="FOO"),
        ])
        name, params = _macro_function_parts(node, _get_node_text)
        assert name == "FOO"
        assert params == []

    def test_no_identifier(self) -> None:
        node = FakeNode("preproc_def", children=[])
        name, params = _macro_function_parts(node, _get_node_text)
        assert name is None


class TestAppendMacroParams:
    def test_identifiers(self) -> None:
        node = FakeNode("preproc_params", children=[
            FakeNode("identifier", text="a"),
            FakeNode("identifier", text="b"),
        ])
        params: list[str] = []
        _append_macro_params(params, node, _get_node_text)
        assert params == ["a", "b"]

    def test_variadic(self) -> None:
        node = FakeNode("preproc_params", children=[
            FakeNode("identifier", text="fmt"),
            FakeNode("variadic_parameter"),
        ])
        params: list[str] = []
        _append_macro_params(params, node, _get_node_text)
        assert "..." in params

    def test_empty(self) -> None:
        node = FakeNode("preproc_params", children=[])
        params: list[str] = []
        _append_macro_params(params, node, _get_node_text)
        assert params == []


class TestExtractMacroFunction:
    def test_basic_macro(self) -> None:
        node = FakeNode(
            "preproc_def",
            text="#define FOO(x) ((x) + 1)",
            start_point=(0, 0),
            end_point=(0, 22),
            children=[
                FakeNode("identifier", text="FOO"),
                FakeNode("preproc_params", children=[
                    FakeNode("identifier", text="x"),
                ]),
            ],
        )
        result = extract_macro_function(node, _get_node_text)
        assert result is not None
        assert result.name == "FOO"
        assert result.return_type == "macro"
        assert "macro" in result.modifiers
        assert result.parameters == ["x"]
        assert result.complexity_score == 1

    def test_no_name_returns_none(self) -> None:
        node = FakeNode(
            "preproc_def",
            text="#define () stuff",
            start_point=(0, 0),
            end_point=(0, 16),
            children=[FakeNode("preproc_params")],
        )
        result = extract_macro_function(node, _get_node_text)
        assert result is None

    def test_variadic_macro(self) -> None:
        node = FakeNode(
            "preproc_def",
            text="#define LOG(fmt, ...) printf(fmt, __VA_ARGS__)",
            start_point=(2, 0),
            end_point=(2, 45),
            children=[
                FakeNode("identifier", text="LOG"),
                FakeNode("preproc_params", children=[
                    FakeNode("identifier", text="fmt"),
                    FakeNode("variadic_parameter"),
                ]),
            ],
        )
        result = extract_macro_function(node, _get_node_text)
        assert result is not None
        assert result.name == "LOG"
        assert "..." in result.parameters

    def test_line_numbers(self) -> None:
        node = FakeNode(
            "preproc_def",
            text="#define FOO 1",
            start_point=(4, 0),
            end_point=(4, 13),
            children=[FakeNode("identifier", text="FOO")],
        )
        result = extract_macro_function(node, _get_node_text)
        assert result is not None
        assert result.start_line == 5
        assert result.end_line == 5

    def test_exception_returns_none(self) -> None:
        node = FakeNode("preproc_def")
        node.start_point = None
        result = extract_macro_function(node, _get_node_text)
        assert result is None


class TestPointerReturnType:
    def test_adds_star(self) -> None:
        assert _pointer_return_type("int") == "int*"

    def test_already_has_star(self) -> None:
        assert _pointer_return_type("int*") == "int*"

    def test_double_pointer(self) -> None:
        assert _pointer_return_type("char**") == "char**"

    def test_empty_string(self) -> None:
        assert _pointer_return_type("") == ""


class TestSignatureAppendModifier:
    def test_appends(self) -> None:
        mods: list[str] = []
        _append_modifier(mods, FakeNode("storage_class_specifier", text="static"), _get_node_text)
        assert mods == ["static"]

    def test_empty_text_skipped(self) -> None:
        mods: list[str] = []
        _append_modifier(mods, FakeNode("type_qualifier", text=""), _get_node_text)
        assert mods == []


class TestFunctionDeclaratorInfo:
    def test_name_and_params(self) -> None:
        node = FakeNode("function_declarator", children=[
            FakeNode("identifier", text="foo"),
            FakeNode("parameter_list"),
        ])
        name, params = _function_declarator_info(node, _get_node_text, lambda n: ["int x"])
        assert name == "foo"
        assert params == ["int x"]

    def test_no_parameter_list(self) -> None:
        node = FakeNode("function_declarator", children=[
            FakeNode("identifier", text="bar"),
        ])
        name, params = _function_declarator_info(node, _get_node_text, lambda n: [])
        assert name == "bar"
        assert params == []


class TestFindFunctionDeclarator:
    def test_finds_nested_declarator(self) -> None:
        inner = FakeNode("function_declarator", children=[
            FakeNode("identifier", text="ptr_func"),
        ])
        outer = FakeNode("pointer_declarator", children=[inner])
        name, params = _find_function_declarator(outer, _get_node_text, lambda n: [])
        assert name == "ptr_func"

    def test_no_declarator(self) -> None:
        node = FakeNode("pointer_declarator", children=[
            FakeNode("identifier", text="x"),
        ])
        name, params = _find_function_declarator(node, _get_node_text, lambda n: [])
        assert name is None
        assert params == []

    def test_deeply_nested(self) -> None:
        innermost = FakeNode("function_declarator", children=[
            FakeNode("identifier", text="deep"),
        ])
        middle = FakeNode("pointer_declarator", children=[innermost])
        outer = FakeNode("pointer_declarator", children=[middle])
        name, params = _find_function_declarator(outer, _get_node_text, lambda n: [])
        assert name == "deep"


class TestParseFunctionSignature:
    def test_simple_function(self) -> None:
        node = FakeNode("function_definition", children=[
            FakeNode("primitive_type", text="void"),
            FakeNode("function_declarator", children=[
                FakeNode("identifier", text="init"),
                FakeNode("parameter_list"),
            ]),
        ])
        result = parse_function_signature(node, _get_node_text, lambda n: [])
        assert result is not None
        assert result[0] == "init"
        assert result[1] == "void"

    def test_static_function(self) -> None:
        node = FakeNode("function_definition", children=[
            FakeNode("storage_class_specifier", text="static"),
            FakeNode("primitive_type", text="int"),
            FakeNode("function_declarator", children=[
                FakeNode("identifier", text="helper"),
            ]),
        ])
        result = parse_function_signature(node, _get_node_text, lambda n: [])
        assert result is not None
        assert "static" in result[3]

    def test_pointer_return(self) -> None:
        node = FakeNode("function_definition", children=[
            FakeNode("primitive_type", text="char"),
            FakeNode("pointer_declarator", children=[
                FakeNode("function_declarator", children=[
                    FakeNode("identifier", text="get_str"),
                ]),
            ]),
        ])
        result = parse_function_signature(node, _get_node_text, lambda n: [])
        assert result is not None
        assert result[0] == "get_str"
        assert result[1] == "char*"

    def test_no_name_returns_none(self) -> None:
        node = FakeNode("function_definition", children=[
            FakeNode("primitive_type", text="int"),
        ])
        result = parse_function_signature(node, _get_node_text, lambda n: [])
        assert result is None

    def test_with_type_qualifier(self) -> None:
        node = FakeNode("function_definition", children=[
            FakeNode("type_qualifier", text="const"),
            FakeNode("primitive_type", text="int"),
            FakeNode("function_declarator", children=[
                FakeNode("identifier", text="f"),
            ]),
        ])
        result = parse_function_signature(node, _get_node_text, lambda n: [])
        assert result is not None
        assert "const" in result[3]

    def test_exception_returns_none(self) -> None:
        node = FakeNode("function_definition")
        node.children = None
        result = parse_function_signature(node, _get_node_text, lambda n: [])
        assert result is None
