#!/usr/bin/env python3
"""
Integration tests for TypeScript language support.

This module provides comprehensive integration tests to ensure that
TypeScript support works correctly across all components of the system.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.formatters.formatter_factory import TableFormatterFactory
from tree_sitter_analyzer.language_detector import detector
from tree_sitter_analyzer.language_loader import get_loader
from tree_sitter_analyzer.languages.typescript_plugin import TypeScriptPlugin
from tree_sitter_analyzer.plugins.manager import PluginManager


class TestTypeScriptIntegration:
    """Integration tests for TypeScript support across the system"""

    def test_typescript_plugin_discovery(self):
        """Test that TypeScript plugin can be discovered by the plugin manager"""
        manager = PluginManager()
        typescript_plugin = TypeScriptPlugin()

        # Register the plugin directly (simulates discovery)
        manager.register_plugin(typescript_plugin)

        plugins = manager.load_plugins()

        # Find TypeScript plugin
        ts_plugin = None
        for plugin in plugins:
            if plugin.get_language_name() == "typescript":
                ts_plugin = plugin
                break

        assert ts_plugin is not None
        assert isinstance(ts_plugin, TypeScriptPlugin)
        assert ts_plugin.get_language_name() == "typescript"
        assert ".ts" in ts_plugin.get_file_extensions()
        assert ".tsx" in ts_plugin.get_file_extensions()
        assert ".d.ts" in ts_plugin.get_file_extensions()

    def test_typescript_language_detection(self):
        """Test TypeScript file detection across different extensions"""
        # Test .ts files
        assert detector.detect_from_extension("service.ts") == "typescript"
        assert detector.detect_from_extension("src/service.ts") == "typescript"

        # Test .tsx files
        assert detector.detect_from_extension("Component.tsx") == "typescript"
        assert (
            detector.detect_from_extension("src/components/Component.tsx")
            == "typescript"
        )

        # Test .d.ts files
        assert detector.detect_from_extension("types.d.ts") == "typescript"
        assert detector.detect_from_extension("@types/node/index.d.ts") == "typescript"

        # Test language support
        assert detector.is_supported("typescript") is True

    def test_typescript_language_loader_integration(self):
        """Test TypeScript integration with language loader"""
        loader = get_loader()

        # Test that TypeScript is in the language modules
        assert "typescript" in loader.LANGUAGE_MODULES
        assert loader.LANGUAGE_MODULES["typescript"] == "tree_sitter_typescript"

        # Test TypeScript dialect handling
        assert "typescript" in loader.TYPESCRIPT_DIALECTS
        assert "tsx" in loader.TYPESCRIPT_DIALECTS

        # Test availability check (may fail if tree-sitter-typescript not installed)
        try:
            is_available = loader.is_language_available("typescript")
            assert isinstance(is_available, bool)
        except Exception:
            # If tree-sitter-typescript is not available, that's OK for testing
            pass

    def test_typescript_formatter_integration(self):
        """Test TypeScript formatter integration with factory"""
        # Test creating TypeScript formatter
        formatter = TableFormatterFactory.create_formatter("typescript", "full")
        assert formatter is not None

        # Test TypeScript alias
        formatter_alias = TableFormatterFactory.create_formatter("ts", "compact")
        assert formatter_alias is not None

        # Test that TypeScript is in supported languages
        supported = TableFormatterFactory.get_supported_languages()
        assert "typescript" in supported or "ts" in supported

    def test_typescript_formatter_with_sample_data(self):
        """Test TypeScript formatter with realistic data"""
        formatter = TableFormatterFactory.create_formatter("typescript", "full")

        sample_data = {
            "file_path": "src/UserService.ts",
            "classes": [
                {
                    "name": "UserService",
                    "class_type": "class",
                    "superclass": "BaseService",
                    "interfaces": ["IUserService"],
                    "line_range": {"start": 10, "end": 50},
                    "generics": ["T"],
                    "is_exported": True,
                },
                {
                    "name": "IUser",
                    "class_type": "interface",
                    "line_range": {"start": 3, "end": 8},
                    "generics": [],
                    "is_exported": True,
                },
                {
                    "name": "Status",
                    "class_type": "type",
                    "line_range": {"start": 1, "end": 1},
                    "raw_text": "type Status = 'active' | 'inactive';",
                    "generics": [],
                },
            ],
            "functions": [
                {
                    "name": "fetchUser",
                    "return_type": "Promise<User>",
                    "parameters": ["id: string"],
                    "is_async": True,
                    "line_range": {"start": 52, "end": 60},
                    "generics": [],
                    "has_type_annotations": True,
                }
            ],
            "variables": [
                {
                    "name": "config",
                    "variable_type": "Config",
                    "declaration_kind": "const",
                    "line_range": {"start": 62, "end": 62},
                    "has_type_annotation": True,
                }
            ],
            "imports": [
                {
                    "name": "React",
                    "source": "react",
                    "is_type_import": False,
                }
            ],
            "exports": [],
            "statistics": {
                "function_count": 1,
                "variable_count": 1,
            },
        }

        result = formatter.format(sample_data)

        # Verify TypeScript-specific formatting
        assert "# TypeScript Module: UserService" in result
        assert "## Interfaces" in result
        assert "## Type Aliases" in result
        assert "| IUser |" in result
        assert "| Status |" in result
        assert "Promise<User>" in result
        assert (
            "has_type_annotations" not in result
        )  # Should be processed, not shown raw

    def test_typescript_plugin_file_applicability(self):
        """Test TypeScript plugin file applicability"""
        plugin = TypeScriptPlugin()

        # Test TypeScript files
        assert plugin.is_applicable("service.ts") is True
        assert plugin.is_applicable("src/service.ts") is True

        # Test TSX files
        assert plugin.is_applicable("Component.tsx") is True
        assert plugin.is_applicable("src/components/Component.tsx") is True

        # Test declaration files
        assert plugin.is_applicable("types.d.ts") is True
        assert plugin.is_applicable("node_modules/@types/react/index.d.ts") is True

        # Test non-TypeScript files
        assert plugin.is_applicable("script.js") is False
        assert plugin.is_applicable("main.py") is False
        assert plugin.is_applicable("App.java") is False
        assert plugin.is_applicable("README.md") is False

    def test_typescript_plugin_info(self):
        """Test TypeScript plugin information"""
        plugin = TypeScriptPlugin()
        info = plugin.get_plugin_info()

        assert info["name"] == "TypeScript Plugin"
        assert info["language"] == "typescript"
        assert info["version"] == "2.0.0"
        assert ".ts" in info["extensions"]
        assert ".tsx" in info["extensions"]
        assert ".d.ts" in info["extensions"]

        # Check TypeScript-specific features
        features = info["features"]
        assert "TypeScript syntax support" in features
        assert "Interface declarations" in features
        assert "Type aliases" in features
        assert "Enums" in features
        assert "Generics" in features
        assert "TSX/JSX support" in features

    def test_typescript_supported_queries(self):
        """Test TypeScript plugin supported queries"""
        plugin = TypeScriptPlugin()
        queries = plugin.get_supported_queries()

        # Check TypeScript-specific queries
        typescript_queries = [
            "interface",
            "type_alias",
            "enum",
            "generic",
            "decorator",
            "signature",
        ]

        for query in typescript_queries:
            assert query in queries, f"Query '{query}' not found in supported queries"

        # Check common queries
        common_queries = ["function", "class", "variable", "import", "export"]
        for query in common_queries:
            assert (
                query in queries
            ), f"Common query '{query}' not found in supported queries"

    @patch(
        "tree_sitter_analyzer.languages.typescript_plugin.TREE_SITTER_AVAILABLE", True
    )
    @patch("tree_sitter_analyzer.languages.typescript_plugin.loader.load_language")
    @pytest.mark.asyncio
    async def test_typescript_plugin_analyze_file_mock(self, mock_load_language):
        """Test TypeScript plugin file analysis with mocked dependencies"""
        # Mock tree-sitter language and parser
        mock_language = Mock()
        mock_load_language.return_value = mock_language

        mock_parser = Mock()
        mock_tree = Mock()
        mock_root_node = Mock()
        mock_root_node.children = []
        mock_tree.root_node = mock_root_node
        mock_parser.parse.return_value = mock_tree

        plugin = TypeScriptPlugin()

        # Create a temporary TypeScript file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(
                """
interface User {
    id: string;
    name: string;
}

class UserService {
    async getUser(id: string): Promise<User> {
        return { id, name: 'Test User' };
    }
}
"""
            )
            temp_file = f.name

        try:
            with patch("tree_sitter.Parser", return_value=mock_parser):
                from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest

                request = AnalysisRequest(file_path=temp_file)
                result = await plugin.analyze_file(temp_file, request)

                assert result.success is True
                assert result.language == "typescript"
                assert result.file_path == temp_file
                assert isinstance(result.elements, list)

        finally:
            # Clean up
            Path(temp_file).unlink()

    def test_typescript_extractor_characteristics_detection(self):
        """Test TypeScript extractor file characteristics detection"""
        from tree_sitter_analyzer.languages.typescript_plugin import (
            TypeScriptElementExtractor,
        )

        extractor = TypeScriptElementExtractor()

        # Test module detection
        extractor.source_code = "import React from 'react'; export default Component;"
        extractor._detect_file_characteristics()
        assert extractor.is_module is True
        assert extractor.framework_type == "react"

        # Test TSX detection
        extractor.current_file = "Component.tsx"
        extractor.source_code = "return <div>Hello</div>;"
        extractor._detect_file_characteristics()
        assert extractor.is_tsx is True

        # Test Angular detection
        extractor.source_code = "import { Component } from '@angular/core';"
        extractor._detect_file_characteristics()
        assert extractor.framework_type == "angular"

    def test_typescript_type_inference(self):
        """Test TypeScript type inference functionality"""
        from tree_sitter_analyzer.languages.typescript_plugin import (
            TypeScriptElementExtractor,
        )

        extractor = TypeScriptElementExtractor()

        # Test various type inferences
        assert extractor._infer_type_from_value('"hello"') == "string"
        assert extractor._infer_type_from_value("true") == "boolean"
        assert extractor._infer_type_from_value("42") == "number"
        assert extractor._infer_type_from_value("[]") == "array"
        assert extractor._infer_type_from_value("{}") == "object"
        assert extractor._infer_type_from_value("null") == "null"
        assert extractor._infer_type_from_value("undefined") == "undefined"
        assert extractor._infer_type_from_value("() => {}") == "function"

    def test_typescript_formatter_different_formats(self):
        """Test TypeScript formatter with different output formats"""
        sample_data = {
            "file_path": "test.ts",
            "classes": [
                {
                    "name": "Test",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 10},
                }
            ],
            "functions": [
                {
                    "name": "test",
                    "return_type": "void",
                    "line_range": {"start": 12, "end": 15},
                }
            ],
            "variables": [
                {
                    "name": "config",
                    "variable_type": "Config",
                    "line_range": {"start": 17, "end": 17},
                }
            ],
            "imports": [],
            "exports": [],
            "statistics": {"function_count": 1, "variable_count": 1},
        }

        # Test full format
        full_formatter = TableFormatterFactory.create_formatter("typescript", "full")
        full_result = full_formatter.format(sample_data)
        assert "# TypeScript Module: test" in full_result
        assert "## Classes" in full_result
        assert "## Functions" in full_result

        # Test compact format
        compact_formatter = TableFormatterFactory.create_formatter(
            "typescript", "compact"
        )
        compact_result = compact_formatter.format(sample_data)
        assert "# test.ts" in compact_result
        assert "## Summary" in compact_result

        # Test CSV format
        csv_formatter = TableFormatterFactory.create_formatter("typescript", "csv")
        csv_result = csv_formatter.format(sample_data)
        assert (
            "Type,Name,Kind,Return/Type,Lines,Visibility,Static,Async,Generic"
            in csv_result
        )
        assert "Class,Test,class" in csv_result

    def test_end_to_end_typescript_workflow(self):
        """Test complete TypeScript analysis workflow"""
        # 1. Language detection
        file_path = "src/UserService.ts"
        detected_language = detector.detect_from_extension(file_path)
        assert detected_language == "typescript"

        # 2. Plugin discovery
        manager = PluginManager()
        typescript_plugin = TypeScriptPlugin()
        manager.register_plugin(typescript_plugin)
        plugins = manager.load_plugins()

        ts_plugin = None
        for plugin in plugins:
            if plugin.get_language_name() == "typescript":
                ts_plugin = plugin
                break

        assert ts_plugin is not None

        # 3. File applicability
        assert ts_plugin.is_applicable(file_path) is True

        # 4. Formatter creation
        formatter = TableFormatterFactory.create_formatter("typescript", "full")
        assert formatter is not None

        # 5. Mock analysis result formatting
        mock_analysis_result = {
            "file_path": file_path,
            "classes": [
                {
                    "name": "UserService",
                    "class_type": "class",
                    "line_range": {"start": 1, "end": 20},
                    "generics": ["T"],
                }
            ],
            "functions": [
                {
                    "name": "getUser",
                    "return_type": "Promise<User>",
                    "is_async": True,
                    "line_range": {"start": 5, "end": 15},
                }
            ],
            "variables": [],
            "imports": [],
            "exports": [],
            "statistics": {"function_count": 1, "variable_count": 0},
        }

        formatted_result = formatter.format(mock_analysis_result)
        assert "# TypeScript Module: UserService" in formatted_result
        assert "Promise<User>" in formatted_result
        assert "✓" in formatted_result  # Async marker


if __name__ == "__main__":
    pytest.main([__file__])
