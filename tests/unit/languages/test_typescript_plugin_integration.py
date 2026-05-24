#!/usr/bin/env python3
"""
Integration tests for TypeScriptPlugin (analyze_file, language loading, plugin info).

Split from test_typescript_plugin_comprehensive.py for maintainability.
"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
from tree_sitter_analyzer.languages.typescript_plugin import TypeScriptPlugin


class TestTypeScriptPluginComprehensive:
    """Comprehensive tests for TypeScriptPlugin"""

    @pytest.fixture
    def plugin(self) -> TypeScriptPlugin:
        """Create a TypeScriptPlugin instance for testing"""
        return TypeScriptPlugin()

    @patch(
        "tree_sitter_analyzer.languages.typescript_plugin.plugin.TREE_SITTER_AVAILABLE",
        True,
    )
    @patch(
        "tree_sitter_analyzer.languages.typescript_plugin.extractor.loader.load_language"
    )
    @pytest.mark.asyncio
    async def test_analyze_file_success(self, mock_load_language, plugin):
        """Test successful file analysis"""
        # Mock language and parser
        mock_language = Mock()
        mock_load_language.return_value = mock_language

        # Create temporary TypeScript file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(
                """
function greet(name: string): string {
    return `Hello, ${name}!`;
}

class Person {
    constructor(public name: string) {}

    greet(): string {
        return greet(this.name);
    }
}

const person = new Person("World");
"""
            )
            temp_file = f.name

        try:
            # Mock parser and tree
            mock_parser = Mock()
            mock_tree = Mock()
            mock_root = Mock()
            mock_root.children = []
            mock_tree.root_node = mock_root

            with patch(
                "tree_sitter_analyzer.languages.typescript_plugin.extractor.tree_sitter.Parser"
            ) as mock_parser_class:
                mock_parser_class.return_value = mock_parser
                mock_parser.parse.return_value = mock_tree

                request = AnalysisRequest(file_path=temp_file)
                result = await plugin.analyze_file(temp_file, request)

                assert result.success is True
                assert result.file_path == temp_file
                assert result.language == "typescript"

        finally:
            os.unlink(temp_file)

    @patch(
        "tree_sitter_analyzer.languages.typescript_plugin.plugin.TREE_SITTER_AVAILABLE",
        True,
    )
    @patch(
        "tree_sitter_analyzer.languages.typescript_plugin.extractor.loader.load_language"
    )
    @pytest.mark.asyncio
    async def test_analyze_file_with_parsing_error(self, mock_load_language, plugin):
        """Test file analysis with parsing error"""
        mock_language = Mock()
        mock_load_language.return_value = mock_language

        # Create temporary file with invalid TypeScript
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write("invalid typescript syntax {{{")
            temp_file = f.name

        try:
            # Mock parser to raise exception
            with patch(
                "tree_sitter_analyzer.languages.typescript_plugin.extractor.tree_sitter.Parser"
            ) as mock_parser_class:
                mock_parser = Mock()
                mock_parser_class.return_value = mock_parser
                mock_parser.parse.side_effect = Exception("Parsing failed")

                request = AnalysisRequest(file_path=temp_file)
                result = await plugin.analyze_file(temp_file, request)

                assert result.success is False
                assert "Parsing failed" in result.error_message

        finally:
            os.unlink(temp_file)

    @patch(
        "tree_sitter_analyzer.languages.typescript_plugin.plugin.TREE_SITTER_AVAILABLE",
        True,
    )
    @patch(
        "tree_sitter_analyzer.languages.typescript_plugin.extractor.loader.load_language"
    )
    @pytest.mark.asyncio
    async def test_analyze_file_with_extraction_error(self, mock_load_language, plugin):
        """Test file analysis with extraction error"""
        mock_language = Mock()
        mock_load_language.return_value = mock_language

        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write("function test() {}")
            temp_file = f.name

        try:
            # Mock parser and tree
            mock_parser = Mock()
            mock_tree = Mock()
            mock_root = Mock()
            mock_root.children = []
            mock_tree.root_node = mock_root

            with patch(
                "tree_sitter_analyzer.languages.typescript_plugin.extractor.tree_sitter.Parser"
            ) as mock_parser_class:
                mock_parser_class.return_value = mock_parser
                mock_parser.parse.return_value = mock_tree

                # Mock extractor to raise exception
                with patch.object(plugin, "create_extractor") as mock_create_extractor:
                    mock_extractor = Mock()
                    mock_extractor.extract_functions.side_effect = Exception(
                        "Extraction failed"
                    )
                    mock_create_extractor.return_value = mock_extractor

                    request = AnalysisRequest(file_path=temp_file)
                    result = await plugin.analyze_file(temp_file, request)

                    assert result.success is False
                    assert "Extraction failed" in result.error_message

        finally:
            os.unlink(temp_file)

    def test_get_tree_sitter_language_no_tree_sitter(self, plugin):
        """Test tree-sitter language getter when tree-sitter is not available"""
        with patch(
            "tree_sitter_analyzer.languages.typescript_plugin.plugin.TREE_SITTER_AVAILABLE",
            False,
        ):
            result = plugin.get_tree_sitter_language()
            assert result is None

    def test_get_tree_sitter_language_load_failure(self, plugin):
        """Test tree-sitter language getter when language loading fails"""
        with patch(
            "tree_sitter_analyzer.languages.typescript_plugin.plugin.TREE_SITTER_AVAILABLE",
            True,
        ):
            with patch(
                "tree_sitter_analyzer.languages.typescript_plugin.extractor.loader.load_language",
                return_value=None,
            ):
                result = plugin.get_tree_sitter_language()
                assert result is None

    @patch(
        "tree_sitter_analyzer.languages.typescript_plugin.plugin.TREE_SITTER_AVAILABLE",
        True,
    )
    @patch(
        "tree_sitter_analyzer.languages.typescript_plugin.extractor.loader.load_language"
    )
    @pytest.mark.asyncio
    async def test_analyze_file_with_node_counting(self, mock_load_language, plugin):
        """Test file analysis with node counting"""
        mock_language = Mock()
        mock_load_language.return_value = mock_language

        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write("function test() { return 42; }")
            temp_file = f.name

        try:
            # Create mock tree with nested nodes
            mock_parser = Mock()
            mock_tree = Mock()

            # Create a tree structure for node counting
            root = Mock()
            root.type = "program"

            func_node = Mock()
            func_node.type = "function_declaration"
            func_node.children = []

            body_node = Mock()
            body_node.type = "statement_block"
            body_node.children = []

            return_node = Mock()
            return_node.type = "return_statement"
            return_node.children = []

            body_node.children = [return_node]
            func_node.children = [body_node]
            root.children = [func_node]

            mock_tree.root_node = root

            with patch(
                "tree_sitter_analyzer.languages.typescript_plugin.extractor.tree_sitter.Parser"
            ) as mock_parser_class:
                mock_parser_class.return_value = mock_parser
                mock_parser.parse.return_value = mock_tree

                request = AnalysisRequest(file_path=temp_file)
                result = await plugin.analyze_file(temp_file, request)

                assert result.success is True
                assert hasattr(result, "node_count")

        finally:
            os.unlink(temp_file)

    def test_plugin_info_comprehensive(self, plugin):
        """Test comprehensive plugin information"""
        info = plugin.get_plugin_info()

        # Verify all expected keys are present
        expected_keys = [
            "name",
            "language",
            "extensions",
            "version",
            "supported_queries",
            "features",
        ]
        for key in expected_keys:
            assert key in info

        # Verify features list is comprehensive
        features = info["features"]
        expected_features = [
            "TypeScript syntax support",
            "Interface declarations",
            "Type aliases",
            "Enums",
            "Generics",
            "Decorators",
            "TSX/JSX support",
            "React component detection",
            "Angular component detection",
            "Vue component detection",
            "Async/await support",
            "Arrow functions",
            "Method signatures",
            "Type annotations",
            "Import/export statements",
        ]

        for feature in expected_features:
            assert feature in features
