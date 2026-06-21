#!/usr/bin/env python3
"""Tests for the AST path navigator (codegraph_ast_path)."""

import pytest

from tree_sitter_analyzer.ast_path import ASTPathNavigator

_PYTHON_SAMPLE = '''\
"""Module docstring."""

import os

class MyClass:
    """A sample class."""

    def __init__(self, name: str):
        self.name = name
        self._data = []

    def process(self, items: list) -> list:
        """Process items."""
        result = []
        for item in items:
            if item:
                result.append(item.upper())
        return result

    @property
    def count(self) -> int:
        return len(self._data)


def standalone(x: int) -> int:
    """A standalone function."""
    return x * 2
'''

_JAVA_SAMPLE = """\
package com.example;

public class Calculator {
    private int value;

    public Calculator(int initial) {
        this.value = initial;
    }

    public int add(int x, int y) {
        return x + y;
    }

    public static int multiply(int a, int b) {
        return a * b;
    }
}
"""


@pytest.fixture
def python_file(tmp_path):
    p = tmp_path / "sample.py"
    p.write_text(_PYTHON_SAMPLE, encoding="utf-8")
    return str(p)


@pytest.fixture
def java_file(tmp_path):
    p = tmp_path / "Calc.java"
    p.write_text(_JAVA_SAMPLE, encoding="utf-8")
    return str(p)


class TestPathAtLine:
    def test_line_inside_method(self, python_file):
        nav = ASTPathNavigator()
        result = nav.path_at_line(python_file, 16)
        assert result.target_line == 16
        scope_names = [n.name for n in result.path if n.name]
        assert "MyClass" in scope_names
        assert "process" in scope_names

    def test_line_at_class_def(self, python_file):
        nav = ASTPathNavigator()
        result = nav.path_at_line(python_file, 6)
        scope_names = [n.name for n in result.path if n.name]
        assert "MyClass" in scope_names

    def test_line_at_standalone_function(self, python_file):
        nav = ASTPathNavigator()
        # Line 26 is inside standalone (the docstring line), line 23 is an empty gap
        result = nav.path_at_line(python_file, 26)
        scope_names = [n.name for n in result.path if n.name]
        assert "standalone" in scope_names

    def test_line_in_init(self, python_file):
        nav = ASTPathNavigator()
        result = nav.path_at_line(python_file, 9)
        scope_names = [n.name for n in result.path if n.name]
        assert "__init__" in scope_names

    def test_line_out_of_range(self, python_file):
        nav = ASTPathNavigator()
        result = nav.path_at_line(python_file, 999)
        assert len(result.path) == 0

    def test_java_line_in_method(self, java_file):
        nav = ASTPathNavigator()
        result = nav.path_at_line(java_file, 10)
        scope_names = [n.name for n in result.path if n.name]
        assert "Calculator" in scope_names
        assert "add" in scope_names

    def test_file_not_found(self):
        nav = ASTPathNavigator()
        with pytest.raises(FileNotFoundError):
            nav.path_at_line("/nonexistent/file.py", 1)


class TestScopeAt:
    def test_scope_inside_method(self, python_file):
        nav = ASTPathNavigator()
        result = nav.scope_at(python_file, 16)
        assert result.enclosing_scope is not None
        assert result.enclosing_scope.name == "process"

    def test_scope_inside_class_not_method(self, python_file):
        nav = ASTPathNavigator()
        result = nav.scope_at(python_file, 6)
        assert result.enclosing_scope is not None
        assert result.enclosing_scope.name == "MyClass"

    def test_scope_at_standalone(self, python_file):
        nav = ASTPathNavigator()
        # Line 26 is inside standalone body; line 23 is an empty gap before it
        result = nav.scope_at(python_file, 26)
        assert result.enclosing_scope is not None
        assert result.enclosing_scope.name == "standalone"


class TestOutline:
    def test_python_outline(self, python_file):
        nav = ASTPathNavigator()
        result = nav.outline(python_file)
        names = [n.name for n in result.path if n.name]
        assert "MyClass" in names
        assert "standalone" in names

    def test_outline_max_depth(self, python_file):
        nav = ASTPathNavigator()
        result = nav.outline(python_file, max_depth=1)
        names = [n.name for n in result.path if n.name]
        assert "MyClass" in names
        assert "__init__" not in names

    def test_java_outline(self, java_file):
        nav = ASTPathNavigator()
        result = nav.outline(java_file)
        names = [n.name for n in result.path if n.name]
        assert "Calculator" in names


class TestToDict:
    def test_result_to_dict(self, python_file):
        nav = ASTPathNavigator()
        result = nav.path_at_line(python_file, 16)
        d = result.to_dict()
        assert "path" in d
        assert "target_line" in d
        assert d["target_line"] == 16
        assert isinstance(d["path"], list)
        assert all("type" in item for item in d["path"])
        assert all("name" in item for item in d["path"])

    def test_node_to_dict(self, python_file):
        nav = ASTPathNavigator()
        result = nav.path_at_line(python_file, 16)
        node = result.path[0]
        d = node.to_dict()
        assert "type" in d
        assert "start_line" in d
        assert "end_line" in d


class TestEdgeCases:
    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.py"
        p.write_text("", encoding="utf-8")
        nav = ASTPathNavigator()
        result = nav.path_at_line(str(p), 1)
        assert isinstance(result.path, list)
        assert result.target_line == 1

    def test_comment_only_file(self, tmp_path):
        p = tmp_path / "comments.py"
        p.write_text("# just a comment\n# another\n", encoding="utf-8")
        nav = ASTPathNavigator()
        result = nav.path_at_line(str(p), 1)
        assert isinstance(result.path, list)
        assert result.target_line == 1
