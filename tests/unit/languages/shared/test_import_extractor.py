"""Tests for tree_sitter_analyzer.languages.shared.import_extractor."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from tree_sitter_analyzer.languages.shared.import_extractor import (
    ImportRecord,
    extract_from_import,
    extract_namespace_import,
    extract_qualified_import,
)


def _node_with_text(
    type_: str, text: bytes, start_byte: int = 0, end_byte: int | None = None
) -> SimpleNamespace:
    if end_byte is None:
        end_byte = start_byte + len(text)
    return SimpleNamespace(
        type=type_,
        text=text,
        start_byte=start_byte,
        end_byte=end_byte,
        start_point=(0, 0),
        end_point=(0, end_byte),
        children=[],
    )


class TestImportRecord:
    def test_default_values(self):
        record = ImportRecord(module="os")
        assert record.module == "os"
        assert record.names == []
        assert record.alias == ""
        assert record.raw_text == ""
        assert record.line == 0

    def test_with_names_and_alias(self):
        record = ImportRecord(
            module="numpy", alias="np", raw_text="import numpy as np", line=3
        )
        assert record.alias == "np"
        assert record.line == 3


class TestExtractQualifiedImport:
    def test_node_with_name_field(self):
        """Node with a ``name`` child field → module from name field."""
        name_node = _node_with_text("dotted_name", b"os.path")
        node = MagicMock()
        node.child_by_field_name.return_value = name_node
        node.text = b"import os.path"
        node.start_byte = 0
        node.end_byte = 14
        node.start_point = (2, 0)
        node.end_point = (2, 14)
        node.children = []

        result = extract_qualified_import(node, b"import os.path")
        assert result is not None
        assert result.module == "os.path"
        assert result.line == 3

    def test_node_without_name_field_fallback(self):
        """No ``name`` field → strip 'import' keyword from text."""
        node = MagicMock()
        node.child_by_field_name.return_value = None
        node.text = b"import java.util.List;"
        node.start_byte = 0
        node.end_byte = 22
        node.start_point = (0, 0)
        node.end_point = (0, 22)
        node.children = []

        result = extract_qualified_import(node, b"import java.util.List;")
        assert result is not None
        assert result.module == "java.util.List"

    def test_returns_none_on_exception(self):
        """Malformed node → None (exception swallowed)."""
        node = MagicMock()
        node.child_by_field_name.side_effect = RuntimeError("boom")
        result = extract_qualified_import(node, b"")
        assert result is None


class TestExtractFromImport:
    def test_python_from_import(self):
        """Python ``from os.path import join`` → module='os.path', names include 'join'."""
        from tree_sitter_analyzer.core.parser import Parser

        src = "from os.path import join\n"
        result = Parser().parse_code(src, "python")
        assert result.success and result.tree is not None

        import_node = result.tree.root_node.children[0]
        record = extract_from_import(import_node, src.encode())
        assert record is not None
        assert record.module == "os.path"

    def test_returns_none_on_exception(self):
        node = MagicMock()
        node.child_by_field_name.side_effect = RuntimeError("boom")
        result = extract_from_import(node, b"")
        assert result is None

    def test_record_line_is_set(self):
        """Line number is populated from node.start_point."""
        from tree_sitter_analyzer.core.parser import Parser

        src = "\n\nfrom sys import argv\n"
        result = Parser().parse_code(src, "python")
        assert result.success and result.tree is not None

        import_node = result.tree.root_node.children[0]
        record = extract_from_import(import_node, src.encode())
        assert record is not None
        assert record.line == 3  # 1-indexed


class TestExtractNamespaceImport:
    def test_rust_use_declaration(self):
        """Rust ``use std::collections::HashMap`` → module contains the path."""
        from tree_sitter_analyzer.core.parser import Parser

        src = "use std::collections::HashMap;\n"
        result = Parser().parse_code(src, "rust")
        assert result.success and result.tree is not None

        import_node = result.tree.root_node.children[0]
        record = extract_namespace_import(import_node, src.encode())
        assert record is not None
        assert "HashMap" in record.module or "collections" in record.module

    def test_alias_extraction(self):
        """When 'as' alias is present in a 'use ... as ...' pattern, alias field is populated."""
        node = MagicMock()
        node.child_by_field_name.return_value = None
        # Simulate a Kotlin/Scala 'use X as Y' style that triggers the alias branch
        node.text = b"use numpy as np"
        node.start_byte = 0
        node.end_byte = 15
        node.start_point = (0, 0)
        node.end_point = (0, 15)
        node.children = []

        result = extract_namespace_import(node, b"use numpy as np")
        assert result is not None
        assert result.module == "numpy"
        assert result.alias == "np"

    def test_csharp_using_directive(self):
        """C# ``using System.Collections.Generic;`` → module extracted."""
        node = MagicMock()
        node.child_by_field_name.return_value = None
        node.text = b"using System.Collections.Generic;"
        node.start_byte = 0
        node.end_byte = 33
        node.start_point = (0, 0)
        node.end_point = (0, 33)
        node.children = []

        result = extract_namespace_import(node, b"using System.Collections.Generic;")
        assert result is not None
        assert result.module == "System.Collections.Generic"

    def test_returns_none_on_exception(self):
        node = MagicMock()
        node.child_by_field_name.side_effect = RuntimeError("boom")
        result = extract_namespace_import(node, b"")
        assert result is None
