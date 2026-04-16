"""Tests for TypeScript edge extractor — relative import detection."""
from __future__ import annotations

from tree_sitter_analyzer.mcp.utils.edge_extractors.typescript import (
    TypeScriptEdgeExtractor,
)


class TestTypeScriptEdgeExtractor:
    def test_relative_import_with_braces(self) -> None:
        src = "import { UserService } from './services/UserService'"
        ext = TypeScriptEdgeExtractor()
        edges = ext.extract(src, "app.ts", "/project")
        assert ("app.ts", "UserService") in edges

    def test_relative_import_parent_dir(self) -> None:
        src = "import { Config } from '../config'"
        ext = TypeScriptEdgeExtractor()
        edges = ext.extract(src, "app.ts", "/project")
        assert ("app.ts", "Config") in edges

    def test_type_import(self) -> None:
        src = "import type { UserDTO } from './types'"
        ext = TypeScriptEdgeExtractor()
        edges = ext.extract(src, "app.ts", "/project")
        assert ("app.ts", "UserDTO") in edges

    def test_absolute_import_ignored(self) -> None:
        src = "import { React } from 'react'"
        ext = TypeScriptEdgeExtractor()
        edges = ext.extract(src, "app.ts", "/project")
        assert len(edges) == 0

    def test_lowercase_import_ignored(self) -> None:
        src = "import { helper } from './utils'"
        ext = TypeScriptEdgeExtractor()
        edges = ext.extract(src, "app.ts", "/project")
        assert len(edges) == 0

    def test_multiple_classes_in_one_import(self) -> None:
        src = "import { User, Product, Order } from './models'"
        ext = TypeScriptEdgeExtractor()
        edges = ext.extract(src, "app.ts", "/project")
        assert ("app.ts", "User") in edges
        assert ("app.ts", "Product") in edges
        assert ("app.ts", "Order") in edges

    def test_empty_source(self) -> None:
        ext = TypeScriptEdgeExtractor()
        edges = ext.extract("", "app.ts", "/project")
        assert edges == []

    def test_no_relative_imports(self) -> None:
        src = "const x = 1;\nexport { x };"
        ext = TypeScriptEdgeExtractor()
        edges = ext.extract(src, "app.ts", "/project")
        assert edges == []
