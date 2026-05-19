"""Tests for typescript_plugin/_function_helpers.py — 100% coverage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

from tree_sitter_analyzer.languages.typescript_plugin._function_helpers import (
    extract_arrow_function,
    extract_function,
    extract_generator_function,
    extract_method,
    extract_method_signature,
)
from tree_sitter_analyzer.languages.typescript_plugin._signature_helpers import (
    FunctionSignature,
    MethodSignature,
)


@dataclass
class FakeNode:
    type: str = "function_declaration"
    start_point: tuple[int, int] = (0, 0)
    end_point: tuple[int, int] = (5, 0)
    children: list[Any] = field(default_factory=list)
    parent: Any = None

    def child_by_field_name(self, name: str) -> Any:
        return None


def _make_function_sig(
    name: str | None = "myFunc",
    parameters: list[str] | None = None,
    is_async: bool = False,
    is_generator: bool = False,
    return_type: str | None = "void",
    generics: list[str] | None = None,
) -> FunctionSignature:
    return (
        name,
        parameters or ["a: number"],
        is_async,
        is_generator,
        return_type,
        generics or [],
    )


def _make_method_sig(
    name: str | None = "myMethod",
    parameters: list[str] | None = None,
    is_async: bool = False,
    is_static: bool = False,
    is_getter: bool = False,
    is_setter: bool = False,
    is_constructor: bool = False,
    return_type: str | None = "void",
    visibility: str = "public",
    generics: list[str] | None = None,
) -> MethodSignature:
    return (
        name,
        parameters or ["x: number"],
        is_async,
        is_static,
        is_getter,
        is_setter,
        is_constructor,
        return_type,
        visibility,
        generics or [],
    )


class TestExtractFunction:
    def test_basic_function_extraction(self):
        node = FakeNode(
            start_point=(2, 0), end_point=(5, 10), type="function_declaration"
        )
        content_lines = [
            "line0",
            "line1",
            "function myFunc(a: number): void {",
            "  return a;",
            "}",
            "line5",
        ]
        result = extract_function(
            node=node,
            parse_signature=lambda n: _make_function_sig(),
            extract_tsdoc=lambda line: "/** doc */",
            calculate_complexity=lambda n: 3,
            content_lines=content_lines,
            framework_type="react",
        )
        assert result is not None
        assert result.name == "myFunc"
        assert result.start_line == 3
        assert result.end_line == 6
        assert result.parameters == ["a: number"]
        assert result.return_type == "void"
        assert result.is_async is False
        assert result.is_generator is False
        assert result.is_arrow is False
        assert result.is_method is False
        assert result.framework_type == "react"
        assert result.docstring == "/** doc */"
        assert result.complexity_score == 3

    def test_async_function(self):
        node = FakeNode(start_point=(0, 0), end_point=(2, 0))
        result = extract_function(
            node=node,
            parse_signature=lambda n: _make_function_sig(is_async=True),
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 1,
            content_lines=["async function f(): Promise<void> {}"],
            framework_type="vanilla",
        )
        assert result is not None
        assert result.is_async is True

    def test_none_signature_returns_none(self):
        node = FakeNode()
        result = extract_function(
            node=node,
            parse_signature=lambda n: None,
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            content_lines=[""],
            framework_type="angular",
        )
        assert result is None

    def test_none_name_returns_none(self):
        node = FakeNode()
        result = extract_function(
            node=node,
            parse_signature=lambda n: _make_function_sig(name=None),
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            content_lines=[""],
            framework_type="angular",
        )
        assert result is None

    def test_none_return_type_defaults_to_any(self):
        node = FakeNode(start_point=(0, 0), end_point=(1, 0))
        result = extract_function(
            node=node,
            parse_signature=lambda n: _make_function_sig(return_type=None),
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            content_lines=["function f() {}"],
            framework_type="vue",
        )
        assert result is not None
        assert result.return_type == "any"

    def test_exception_returns_none(self):
        node = FakeNode()
        result = extract_function(
            node=node,
            parse_signature=lambda n: (_ for _ in ()).throw(ValueError("boom")),
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            content_lines=[""],
            framework_type="react",
        )
        assert result is None

    def test_content_lines_boundary_clamping(self):
        node = FakeNode(start_point=(100, 0), end_point=(200, 0))
        content_lines = ["only one line"]
        result = extract_function(
            node=node,
            parse_signature=lambda n: _make_function_sig(),
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            content_lines=content_lines,
            framework_type="react",
        )
        assert result is not None

    def test_generator_function_flag(self):
        node = FakeNode(start_point=(0, 0), end_point=(2, 0))
        result = extract_function(
            node=node,
            parse_signature=lambda n: _make_function_sig(is_generator=True),
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 5,
            content_lines=["function* gen() {}"],
            framework_type="react",
        )
        assert result is not None
        assert result.is_generator is True


class TestExtractArrowFunction:
    def test_basic_arrow_with_variable_declarator(self):
        parent = FakeNode(type="variable_declarator", children=[])
        identifier_child = FakeNode(type="identifier", start_point=(0, 0), end_point=(0, 5))
        parent.children = [identifier_child]

        node = FakeNode(
            start_point=(0, 0),
            end_point=(2, 0),
            type="arrow_function",
            parent=parent,
            children=[
                FakeNode(type="formal_parameters"),
                FakeNode(type="type_annotation"),
            ],
        )

        def get_text(n):
            if n.type == "identifier":
                return "myArrow"
            if n.type == "type_annotation":
                return ": string"
            return "(x) => x"

        result = extract_arrow_function(
            node=node,
            get_node_text=get_text,
            extract_parameters=lambda n: ["x: string"],
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 1,
            framework_type="react",
        )
        assert result is not None
        assert result.name == "myArrow"
        assert result.is_arrow is True
        assert result.is_method is False
        assert result.return_type == "string"

    def test_anonymous_arrow_no_parent(self):
        node = FakeNode(
            start_point=(0, 0),
            end_point=(1, 0),
            type="arrow_function",
            parent=None,
            children=[],
        )

        result = extract_arrow_function(
            node=node,
            get_node_text=lambda n: "() => 42",
            extract_parameters=lambda n: [],
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            framework_type="react",
        )
        assert result is not None
        assert result.name == "anonymous"

    def test_arrow_with_single_identifier_param(self):
        parent = FakeNode(type="variable_declarator", children=[])
        parent.children = [FakeNode(type="identifier")]

        node = FakeNode(
            start_point=(0, 0),
            end_point=(1, 0),
            type="arrow_function",
            parent=parent,
            children=[FakeNode(type="identifier")],
        )

        result = extract_arrow_function(
            node=node,
            get_node_text=lambda n: "x => x",
            extract_parameters=lambda n: ["x"],
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            framework_type="vue",
        )
        assert result is not None

    def test_arrow_async_detection(self):
        parent = FakeNode(type="variable_declarator", children=[])
        parent.children = [FakeNode(type="identifier")]

        node = FakeNode(
            start_point=(0, 0),
            end_point=(2, 0),
            parent=parent,
            children=[],
        )

        result = extract_arrow_function(
            node=node,
            get_node_text=lambda n: "async () => await fetch()",
            extract_parameters=lambda n: [],
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 1,
            framework_type="react",
        )
        assert result is not None
        assert result.is_async is True

    def test_arrow_no_return_type_defaults_to_any(self):
        parent = FakeNode(type="variable_declarator", children=[])
        parent.children = [FakeNode(type="identifier")]

        node = FakeNode(
            start_point=(0, 0),
            end_point=(1, 0),
            parent=parent,
            children=[],
        )

        result = extract_arrow_function(
            node=node,
            get_node_text=lambda n: "() => 42",
            extract_parameters=lambda n: [],
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            framework_type="react",
        )
        assert result is not None
        assert result.return_type == "any"

    def test_arrow_exception_returns_none(self):
        node = MagicMock()
        node.start_point = property(lambda self: (_ for _ in ()).throw(RuntimeError("err")))

        result = extract_arrow_function(
            node=node,
            get_node_text=lambda n: "",
            extract_parameters=lambda n: [],
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            framework_type="react",
        )
        assert result is None

    def test_arrow_parent_not_variable_declarator(self):
        parent = FakeNode(type="expression_statement", children=[])
        node = FakeNode(
            start_point=(0, 0),
            end_point=(1, 0),
            parent=parent,
            children=[],
        )

        result = extract_arrow_function(
            node=node,
            get_node_text=lambda n: "() => 1",
            extract_parameters=lambda n: [],
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            framework_type="react",
        )
        assert result is not None
        assert result.name == "anonymous"

    def test_arrow_with_type_annotation_child(self):
        parent = FakeNode(type="variable_declarator", children=[])
        parent.children = [FakeNode(type="identifier")]

        type_ann = FakeNode(type="type_annotation")
        node = FakeNode(
            start_point=(0, 0),
            end_point=(1, 0),
            parent=parent,
            children=[type_ann],
        )

        result = extract_arrow_function(
            node=node,
            get_node_text=lambda n: ": string" if n.type == "type_annotation" else "() => x",
            extract_parameters=lambda n: [],
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            framework_type="react",
        )
        assert result is not None
        assert result.return_type == "string"

    def test_arrow_parent_no_identifier_child(self):
        parent = FakeNode(type="variable_declarator", children=[FakeNode(type="number")])
        node = FakeNode(
            start_point=(0, 0),
            end_point=(1, 0),
            parent=parent,
            children=[],
        )

        result = extract_arrow_function(
            node=node,
            get_node_text=lambda n: "() => 1",
            extract_parameters=lambda n: [],
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            framework_type="react",
        )
        assert result is not None
        assert result.name == "anonymous"


class TestExtractMethod:
    def test_basic_method(self):
        node = FakeNode(start_point=(0, 0), end_point=(3, 0))
        result = extract_method(
            node=node,
            parse_signature=lambda n: _make_method_sig(),
            extract_tsdoc=lambda line: "/** method doc */",
            calculate_complexity=lambda n: 2,
            get_node_text=lambda n: "public myMethod(x: number): void {}",
            framework_type="angular",
        )
        assert result is not None
        assert result.name == "myMethod"
        assert result.is_method is True
        assert result.visibility == "public"
        assert result.docstring == "/** method doc */"

    def test_static_constructor_method(self):
        node = FakeNode(start_point=(0, 0), end_point=(2, 0))
        result = extract_method(
            node=node,
            parse_signature=lambda n: _make_method_sig(
                is_static=True, is_constructor=True, visibility="private"
            ),
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            get_node_text=lambda n: "private constructor()",
            framework_type="react",
        )
        assert result is not None
        assert result.is_static is True
        assert result.is_constructor is True
        assert result.visibility == "private"

    def test_none_method_signature(self):
        node = FakeNode()
        result = extract_method(
            node=node,
            parse_signature=lambda n: None,
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            get_node_text=lambda n: "",
            framework_type="react",
        )
        assert result is None

    def test_none_method_name(self):
        node = FakeNode()
        result = extract_method(
            node=node,
            parse_signature=lambda n: _make_method_sig(name=None),
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            get_node_text=lambda n: "",
            framework_type="react",
        )
        assert result is None

    def test_method_exception_returns_none(self):
        node = MagicMock()
        node.start_point = property(lambda self: (_ for _ in ()).throw(RuntimeError("err")))

        result = extract_method(
            node=node,
            parse_signature=lambda n: _make_method_sig(),
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            get_node_text=lambda n: "",
            framework_type="react",
        )
        assert result is None

    def test_method_none_return_type_defaults_any(self):
        node = FakeNode(start_point=(0, 0), end_point=(1, 0))
        result = extract_method(
            node=node,
            parse_signature=lambda n: _make_method_sig(return_type=None),
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            get_node_text=lambda n: "method() {}",
            framework_type="react",
        )
        assert result is not None
        assert result.return_type == "any"


class TestExtractMethodSignature:
    def test_basic_method_signature(self):
        node = FakeNode(start_point=(0, 0), end_point=(1, 0))
        result = extract_method_signature(
            node=node,
            parse_signature=lambda n: _make_method_sig(),
            extract_tsdoc=lambda line: None,
            get_node_text=lambda n: "myMethod(x: number): void;",
            framework_type="angular",
        )
        assert result is not None
        assert result.name == "myMethod"
        assert result.is_method is True
        assert result.is_arrow is False
        assert result.complexity_score == 0

    def test_none_signature_returns_none(self):
        node = FakeNode()
        result = extract_method_signature(
            node=node,
            parse_signature=lambda n: None,
            extract_tsdoc=lambda line: None,
            get_node_text=lambda n: "",
            framework_type="react",
        )
        assert result is None

    def test_none_name_returns_none(self):
        node = FakeNode()
        result = extract_method_signature(
            node=node,
            parse_signature=lambda n: _make_method_sig(name=None),
            extract_tsdoc=lambda line: None,
            get_node_text=lambda n: "",
            framework_type="react",
        )
        assert result is None

    def test_exception_returns_none(self):
        node = MagicMock()
        node.start_point = property(lambda self: (_ for _ in ()).throw(RuntimeError("err")))

        result = extract_method_signature(
            node=node,
            parse_signature=lambda n: _make_method_sig(),
            extract_tsdoc=lambda line: None,
            get_node_text=lambda n: "",
            framework_type="react",
        )
        assert result is None

    def test_none_return_type_defaults_any(self):
        node = FakeNode(start_point=(0, 0), end_point=(1, 0))
        result = extract_method_signature(
            node=node,
            parse_signature=lambda n: _make_method_sig(return_type=None),
            extract_tsdoc=lambda line: None,
            get_node_text=lambda n: "method();",
            framework_type="react",
        )
        assert result is not None
        assert result.return_type == "any"


class TestExtractGeneratorFunction:
    def test_basic_generator(self):
        node = FakeNode(start_point=(0, 0), end_point=(3, 0))
        result = extract_generator_function(
            node=node,
            parse_signature=lambda n: _make_function_sig(is_generator=True, return_type=None),
            extract_tsdoc=lambda line: "/** gen doc */",
            calculate_complexity=lambda n: 4,
            get_node_text=lambda n: "function* gen() { yield 1; }",
            framework_type="react",
        )
        assert result is not None
        assert result.is_generator is True
        assert result.return_type == "Generator"
        assert result.docstring == "/** gen doc */"

    def test_generator_none_signature(self):
        node = FakeNode()
        result = extract_generator_function(
            node=node,
            parse_signature=lambda n: None,
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            get_node_text=lambda n: "",
            framework_type="react",
        )
        assert result is None

    def test_generator_none_name(self):
        node = FakeNode()
        result = extract_generator_function(
            node=node,
            parse_signature=lambda n: _make_function_sig(name=None),
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            get_node_text=lambda n: "",
            framework_type="react",
        )
        assert result is None

    def test_generator_exception_returns_none(self):
        node = MagicMock()
        node.start_point = property(lambda self: (_ for _ in ()).throw(RuntimeError("err")))

        result = extract_generator_function(
            node=node,
            parse_signature=lambda n: _make_function_sig(),
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            get_node_text=lambda n: "",
            framework_type="react",
        )
        assert result is None

    def test_generator_async_flag(self):
        node = FakeNode(start_point=(0, 0), end_point=(1, 0))
        result = extract_generator_function(
            node=node,
            parse_signature=lambda n: _make_function_sig(is_async=True),
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            get_node_text=lambda n: "async function* gen() {}",
            framework_type="react",
        )
        assert result is not None
        assert result.is_async is True

    def test_generator_none_return_type_defaults_generator(self):
        node = FakeNode(start_point=(0, 0), end_point=(1, 0))
        result = extract_generator_function(
            node=node,
            parse_signature=lambda n: _make_function_sig(return_type=None),
            extract_tsdoc=lambda line: None,
            calculate_complexity=lambda n: 0,
            get_node_text=lambda n: "function* gen() {}",
            framework_type="react",
        )
        assert result is not None
        assert result.return_type == "Generator"
