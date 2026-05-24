"""Tests for languages/_go_function_helpers.py — 100% coverage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

from tree_sitter_analyzer.languages._go_function_helpers import (
    extract_go_function,
    extract_go_method,
)


@dataclass
class FakeNode:
    type: str = "function_declaration"
    start_point: tuple[int, int] = (2, 0)
    end_point: tuple[int, int] = (5, 0)
    children: list[Any] = field(default_factory=list)
    _name_text: str = "MyFunc"

    def child_by_field_name(self, name: str) -> Any:
        if name == "name":
            return _NameNode(self._name_text)
        if name == "parameters":
            return _ParamsNode([])
        if name == "result":
            return _TextNode("error")
        return None


@dataclass
class _NameNode:
    text: str
    type: str = "identifier"

    def child_by_field_name(self, name: str) -> Any:
        return None


@dataclass
class _TextNode:
    text: str
    type: str = "type_identifier"
    children: list[Any] = field(default_factory=list)

    def child_by_field_name(self, name: str) -> Any:
        return None


@dataclass
class _ParamsNode:
    children: list[Any]
    type: str = "parameter_list"

    def child_by_field_name(self, name: str) -> Any:
        return None


class TestExtractGoFunction:
    def test_basic_function_extraction(self):
        node = FakeNode()
        content_lines = [
            "// Package main",
            "// doc comment",
            "func MyFunc(x int) error {",
            "  return nil",
            "}",
        ]

        def get_text(n):
            if hasattr(n, "text"):
                return n.text
            return "func MyFunc(x int) error {\n  return nil\n}"

        result = extract_go_function(
            node=node,
            get_node_text=get_text,
            content_lines=content_lines,
        )
        assert result is not None
        assert result.name == "MyFunc"
        assert result.language == "go"
        assert result.start_line == 3
        assert result.end_line == 6
        assert result.visibility == "public"
        assert result.is_public is True
        assert result.return_type == "error"
        assert result.is_method is False

    def test_private_function(self):
        node = FakeNode(_name_text="privateFunc")

        def get_text(n):
            if hasattr(n, "text"):
                return n.text
            return "func privateFunc() {}"

        result = extract_go_function(
            node=node,
            get_node_text=get_text,
            content_lines=["func privateFunc() {}"],
        )
        assert result is not None
        assert result.visibility == "private"
        assert result.is_public is False

    def test_no_name_node_returns_none(self):
        node = MagicMock()
        node.child_by_field_name.return_value = None

        result = extract_go_function(
            node=node,
            get_node_text=lambda n: "",
            content_lines=[""],
        )
        assert result is None

    def test_empty_name_returns_none(self):
        name_node = MagicMock()
        name_node.type = "identifier"
        name_node.children = []

        def get_text(n):
            return ""

        node = MagicMock()
        node.child_by_field_name.side_effect = (
            lambda f: name_node if f == "name" else None
        )
        node.start_point = (0, 0)
        node.end_point = (1, 0)
        node.children = []

        result = extract_go_function(
            node=node,
            get_node_text=get_text,
            content_lines=[""],
        )
        assert result is None

    def test_exception_returns_none(self):
        node = MagicMock()
        node.child_by_field_name.side_effect = RuntimeError("tree-sitter error")

        result = extract_go_function(
            node=node,
            get_node_text=lambda n: "",
            content_lines=[""],
        )
        assert result is None

    def test_no_docstring(self):
        node = FakeNode()
        content_lines = ["func MyFunc() {}"]
        result = extract_go_function(
            node=node,
            get_node_text=lambda n: "func MyFunc() {}",
            content_lines=content_lines,
        )
        assert result is not None
        assert result.docstring is None

    def test_with_docstring(self):
        node = FakeNode(start_point=(3, 0), end_point=(5, 0))
        content_lines = [
            "package main",
            "",
            "// MyFunc does something",
            "func MyFunc() {",
            "}",
        ]
        result = extract_go_function(
            node=node,
            get_node_text=lambda n: n.text if hasattr(n, "text") else "func MyFunc() {}",
            content_lines=content_lines,
        )
        assert result is not None
        assert result.docstring is not None
        assert "MyFunc does something" in result.docstring

    def test_no_result_node(self):
        node = FakeNode()
        node._name_text = "NoReturn"
        original = node.child_by_field_name

        def patched(name):
            if name == "result":
                return None
            return original(name)

        node.child_by_field_name = patched
        result = extract_go_function(
            node=node,
            get_node_text=lambda n: n.text if hasattr(n, "text") else "func NoReturn() {}",
            content_lines=["func NoReturn() {}"],
        )
        assert result is not None
        assert result.return_type == ""


class TestExtractGoMethod:
    def test_basic_method_extraction(self):
        node = FakeNode(_name_text="DoStuff")
        content_lines = [
            "package main",
            "",
            "// DoStuff does stuff",
            "func (s *Service) DoStuff() error {",
            "  return nil",
            "}",
        ]

        def mock_receiver_extractor(n, get_text):
            return ("s *Service", "*Service")

        import tree_sitter_analyzer.languages._go_function_helpers as mod

        original = mod.extract_method_receiver
        mod.extract_method_receiver = mock_receiver_extractor
        try:
            result = extract_go_method(
                node=node,
                get_node_text=lambda n: n.text if hasattr(n, "text") else "func (s *Service) DoStuff() error {\n  return nil\n}",
                content_lines=content_lines,
            )
        finally:
            mod.extract_method_receiver = original

        assert result is not None
        assert result.name == "DoStuff"
        assert result.is_method is True
        assert result.receiver == "s *Service"
        assert result.receiver_type == "*Service"

    def test_method_no_name_returns_none(self):
        node = MagicMock()
        node.child_by_field_name.return_value = None

        result = extract_go_method(
            node=node,
            get_node_text=lambda n: "",
            content_lines=[""],
        )
        assert result is None

    def test_method_exception_returns_none(self):
        node = MagicMock()
        node.child_by_field_name.side_effect = RuntimeError("boom")

        result = extract_go_method(
            node=node,
            get_node_text=lambda n: "",
            content_lines=[""],
        )
        assert result is None

    def test_method_receiver_extraction(self):
        node = FakeNode(_name_text="Process")

        import tree_sitter_analyzer.languages._go_function_helpers as mod

        original = mod.extract_method_receiver
        mod.extract_method_receiver = lambda n, gt: ("r *Reader", "*Reader")
        try:
            result = extract_go_method(
                node=node,
                get_node_text=lambda n: n.text if hasattr(n, "text") else "func (r *Reader) Process() {}",
                content_lines=["func (r *Reader) Process() {}"],
            )
        finally:
            mod.extract_method_receiver = original

        assert result is not None
        assert result.receiver == "r *Reader"
        assert result.receiver_type == "*Reader"
        assert result.is_method is True
