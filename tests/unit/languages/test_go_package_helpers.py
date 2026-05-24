"""Tests for languages._go_package_helpers — Go package extraction."""

from unittest.mock import MagicMock

from tree_sitter_analyzer.languages._go_package_helpers import (
    _go_package_name,
    extract_go_package,
)
from tree_sitter_analyzer.models import Package


def _mock_node(children=None, start_row=0, end_row=0, text="package main"):
    node = MagicMock()
    node.children = children or []
    node.start_point = (start_row, 0)
    node.end_point = (end_row, 0)
    node.text = text.encode() if isinstance(text, str) else text
    return node


def _mock_identifier_child(name="main"):
    child = MagicMock()
    child.type = "package_identifier"
    child.text = name.encode()
    return child


def _get_text(node):
    if hasattr(node, "text") and isinstance(node.text, bytes):
        return node.text.decode()
    return str(node)


class TestExtractGoPackage:
    def test_extracts_package(self):
        node = _mock_node(children=[_mock_identifier_child("mypkg")], text="package mypkg")
        result = extract_go_package(node, _get_text)
        assert isinstance(result, Package)
        assert result.name == "mypkg"
        assert result.language == "go"
        assert result.start_line == 1

    def test_no_identifier_returns_none(self):
        other = MagicMock()
        other.type = "import_declaration"
        node = _mock_node(children=[other])
        result = extract_go_package(node, _get_text)
        assert result is None

    def test_exception_returns_none(self):
        node = MagicMock()
        node.children = [MagicMock()]
        node.start_point = None
        result = extract_go_package(node, _get_text)
        assert result is None


class TestGoPackageName:
    def test_finds_package_identifier(self):
        node = _mock_node(children=[_mock_identifier_child("cmd")])
        assert _go_package_name(node, _get_text) == "cmd"

    def test_no_identifier(self):
        node = _mock_node(children=[])
        assert _go_package_name(node, _get_text) is None

    def test_wrong_child_type(self):
        child = MagicMock()
        child.type = "identifier"
        node = _mock_node(children=[child])
        assert _go_package_name(node, _get_text) is None
