"""Tests for Python edge extractor — first-party import detection."""
from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.utils.edge_extractors.python import (
    PythonEdgeExtractor,
    _is_first_party,
)


class TestIsFirstParty:
    """Unit tests for _is_first_party helper."""

    def test_stdlib_os_is_not_first_party(self) -> None:
        assert _is_first_party("os") is False

    def test_stdlib_sys_is_not_first_party(self) -> None:
        assert _is_first_party("sys") is False

    def test_stdlib_json_is_not_first_party(self) -> None:
        assert _is_first_party("json") is False

    def test_stdlib_submodule_is_not_first_party(self) -> None:
        assert _is_first_party("os.path") is False

    def test_unknown_module_is_first_party(self) -> None:
        assert _is_first_party("my_local_module") is True


class TestPythonEdgeExtractorExtract:
    """Tests for the extract() method."""

    def test_from_import_with_pascal_case(self) -> None:
        src = "from myapp.models import User"
        ext = PythonEdgeExtractor()
        edges = ext.extract(src, "models.py", "/project")
        assert ("models.py", "User") in edges

    def test_from_import_filters_stdlib(self) -> None:
        src = "from os.path import join"
        ext = PythonEdgeExtractor()
        edges = ext.extract(src, "main.py", "/project")
        assert len(edges) == 0

    def test_from_import_filters_lowercase(self) -> None:
        src = "from myapp.utils import helper"
        ext = PythonEdgeExtractor()
        edges = ext.extract(src, "main.py", "/project")
        assert len(edges) == 0  # lowercase names are not class references

    def test_from_import_multiple_classes(self) -> None:
        src = "from myapp.models import User, Product, Order"
        ext = PythonEdgeExtractor()
        edges = ext.extract(src, "service.py", "/project")
        assert ("service.py", "User") in edges
        assert ("service.py", "Product") in edges
        assert ("service.py", "Order") in edges

    def test_bare_import_with_class(self) -> None:
        src = "import myapp.models.User"
        ext = PythonEdgeExtractor()
        edges = ext.extract(src, "main.py", "/project")
        assert ("main.py", "User") in edges

    def test_bare_import_filters_stdlib(self) -> None:
        src = "import os.path"
        ext = PythonEdgeExtractor()
        edges = ext.extract(src, "main.py", "/project")
        assert len(edges) == 0

    def test_empty_source(self) -> None:
        ext = PythonEdgeExtractor()
        edges = ext.extract("", "empty.py", "/project")
        assert edges == []

    def test_no_imports(self) -> None:
        src = "x = 1\ny = 2\n"
        ext = PythonEdgeExtractor()
        edges = ext.extract(src, "script.py", "/project")
        assert edges == []
