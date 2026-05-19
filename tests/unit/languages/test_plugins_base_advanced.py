#!/usr/bin/env python3
"""
Tests for plugins base functionality - integration and advanced tests
"""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.plugins.base import (
    DefaultExtractor,
    DefaultLanguagePlugin,
    ElementExtractor,
)


class TestLanguagePluginIntegration:
    """Integration tests for LanguagePlugin"""

    def test_plugin_workflow(self) -> None:
        """Test complete plugin workflow"""
        plugin = DefaultLanguagePlugin()

        # Test basic properties
        assert plugin.get_language_name() == "generic"
        assert isinstance(plugin.get_file_extensions(), list)

        # Test file applicability
        assert plugin.is_applicable("test.txt") is True
        assert plugin.is_applicable("test.py") is False

        # Test extractor creation
        extractor = plugin.create_extractor()
        assert isinstance(extractor, ElementExtractor)

        # Test plugin info
        info = plugin.get_plugin_info()
        assert isinstance(info, dict)
        assert "language" in info
        assert "extensions" in info

    def test_plugin_with_empty_extensions(self) -> None:
        """Test plugin behavior with empty extensions"""
        plugin = DefaultLanguagePlugin()

        # Temporarily override extensions
        original_method = plugin.get_file_extensions
        plugin.get_file_extensions = lambda: []

        try:
            # Should not match any files
            assert plugin.is_applicable("test.txt") is False
            assert plugin.is_applicable("test.py") is False
        finally:
            # Restore original method
            plugin.get_file_extensions = original_method


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def test_extractor_with_malformed_nodes(self) -> None:
        """Test extractor with malformed tree nodes"""
        extractor = DefaultExtractor()

        # Create mock tree with malformed nodes
        mock_tree = Mock()
        mock_tree.root_node = Mock()

        # Create node without required attributes
        mock_bad_node = Mock()
        mock_bad_node.type = "function_definition"
        # Missing start_point, end_point, etc.

        mock_tree.root_node.children = [mock_bad_node]

        source_code = "def test(): pass"

        # Should handle gracefully without crashing
        functions = extractor.extract_functions(mock_tree, source_code)
        assert isinstance(functions, list)

    def test_plugin_with_special_characters_in_filename(self) -> None:
        """Test plugin with special characters in filename"""
        plugin = DefaultLanguagePlugin()

        # Test with various special characters
        assert plugin.is_applicable("test file.txt") is True
        assert plugin.is_applicable("test-file.md") is True
        assert plugin.is_applicable("test_file.TXT") is True
        assert plugin.is_applicable("файл.txt") is True  # Cyrillic
        assert plugin.is_applicable("ファイル.md") is True  # Japanese

    def test_extractor_with_empty_source_code(self) -> None:
        """Test extractor with empty source code"""
        extractor = DefaultExtractor()

        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        # Test with empty source
        elements = extractor.extract_all_elements(mock_tree, "")
        assert isinstance(elements, list)
        assert len(elements) == 0

    def test_extractor_with_very_large_source_code(self) -> None:
        """Test extractor with large source code"""
        extractor = DefaultExtractor()

        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        # Test with large source (10MB of text)
        large_source = "# comment\n" * 500000

        # Should handle without memory issues
        elements = extractor.extract_all_elements(mock_tree, large_source)
        assert isinstance(elements, list)


class TestDefaultExtractorTraversal:
    """Direct tests for _traverse_for_* methods in DefaultExtractor"""

    @pytest.fixture
    def extractor(self):
        return DefaultExtractor()

    # ── _traverse_for_classes ──────────────────────────────────────

    def test_traverse_for_classes_creates_element(self, extractor):
        """_traverse_for_classes should create and append a Class element"""
        from tree_sitter_analyzer.models import Class as ModelClass

        mock_node = Mock()
        mock_node.type = "class_definition"
        mock_node.start_point = (5, 0)
        mock_node.end_point = (10, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 21
        mock_node.children = []

        classes: list = []
        source = "class MyClass:\n    pass\n"
        extractor._traverse_for_classes(mock_node, classes, source.splitlines(), source)

        assert len(classes) == 1
        assert isinstance(classes[0], ModelClass)

    def test_traverse_for_classes_error_handling(self, extractor):
        """_traverse_for_classes should not raise on extraction errors"""
        mock_node = Mock()
        mock_node.type = "class_definition"
        mock_node.children = []

        classes: list = []

        with patch.object(
            extractor, "_extract_node_name", side_effect=RuntimeError("boom")
        ):
            extractor._traverse_for_classes(mock_node, classes, [], "")

        assert len(classes) == 0

    def test_traverse_for_classes_recursive(self, extractor):
        """_traverse_for_classes should recurse into children"""
        from tree_sitter_analyzer.models import Class as ModelClass

        mock_child = Mock()
        mock_child.type = "class_definition"
        mock_child.start_point = (3, 0)
        mock_child.end_point = (5, 0)
        mock_child.start_byte = 0
        mock_child.end_byte = 18
        mock_child.children = []

        mock_parent = Mock()
        mock_parent.type = "block"  # non-class type
        mock_parent.children = [mock_child]

        classes: list = []
        source = "class Child:\n    pass\n"
        extractor._traverse_for_classes(
            mock_parent, classes, source.splitlines(), source
        )

        assert len(classes) == 1
        assert isinstance(classes[0], ModelClass)

    def test_traverse_for_classes_skips_non_class_nodes(self, extractor):
        """_traverse_for_classes should skip nodes that are not class-like"""
        mock_node = Mock()
        mock_node.type = "function_definition"
        mock_node.children = []

        classes: list = []
        extractor._traverse_for_classes(mock_node, classes, [], "")

        assert len(classes) == 0

    # ── _traverse_for_variables ────────────────────────────────────

    def test_traverse_for_variables_creates_element(self, extractor):
        """_traverse_for_variables should create and append a Variable element"""
        from tree_sitter_analyzer.models import Variable as ModelVariable

        mock_node = Mock()
        mock_node.type = "variable_declaration"
        mock_node.start_point = (7, 0)
        mock_node.end_point = (7, 10)
        mock_node.start_byte = 0
        mock_node.end_byte = 6
        mock_node.children = []

        variables: list = []
        source = "x = 42"
        extractor._traverse_for_variables(
            mock_node, variables, source.splitlines(), source
        )

        assert len(variables) == 1
        assert isinstance(variables[0], ModelVariable)

    def test_traverse_for_variables_recursive(self, extractor):
        """_traverse_for_variables should recurse into children"""
        from tree_sitter_analyzer.models import Variable as ModelVariable

        mock_child = Mock()
        mock_child.type = "variable_declaration"
        mock_child.start_point = (2, 0)
        mock_child.end_point = (2, 10)
        mock_child.start_byte = 0
        mock_child.end_byte = 6
        mock_child.children = []

        mock_parent = Mock()
        mock_parent.type = "block"
        mock_parent.children = [mock_child]

        variables: list = []
        source = "y = 1"
        extractor._traverse_for_variables(
            mock_parent, variables, source.splitlines(), source
        )

        assert len(variables) == 1
        assert isinstance(variables[0], ModelVariable)

    # ── _traverse_for_imports ──────────────────────────────────────

    def test_traverse_for_imports_creates_element(self, extractor):
        """_traverse_for_imports should create and append an Import element"""
        from tree_sitter_analyzer.models import Import as ModelImport

        mock_node = Mock()
        mock_node.type = "import_statement"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 20)
        mock_node.start_byte = 0
        mock_node.end_byte = 14
        mock_node.children = []

        imports: list = []
        source = "import os, sys"
        extractor._traverse_for_imports(mock_node, imports, source.splitlines(), source)

        assert len(imports) == 1
        assert isinstance(imports[0], ModelImport)

    def test_traverse_for_imports_recursive(self, extractor):
        """_traverse_for_imports should recurse into children"""
        from tree_sitter_analyzer.models import Import as ModelImport

        mock_child = Mock()
        mock_child.type = "import_declaration"
        mock_child.start_point = (0, 0)
        mock_child.end_point = (0, 15)
        mock_child.start_byte = 0
        mock_child.end_byte = 14
        mock_child.children = []

        mock_parent = Mock()
        mock_parent.type = "program"
        mock_parent.children = [mock_child]

        imports: list = []
        source = "import os, sys"
        extractor._traverse_for_imports(
            mock_parent, imports, source.splitlines(), source
        )

        assert len(imports) == 1
        assert isinstance(imports[0], ModelImport)


class TestDefaultExtractorErrorPaths:
    """Coverage for exception-handling branches in extractor methods"""

    @pytest.fixture
    def extractor(self):
        return DefaultExtractor()

    def test_traverse_for_classes_exception_logged(self, extractor):
        """Exception in _traverse_for_classes body is caught and logged"""
        mock_node = Mock()
        mock_node.type = "class_definition"
        mock_node.children = []

        classes: list = []

        with patch.object(
            extractor, "_extract_node_name", side_effect=RuntimeError("boom")
        ):
            extractor._traverse_for_classes(mock_node, classes, [], "")

        assert len(classes) == 0

    def test_traverse_for_variables_exception_logged(self, extractor):
        """Exception in _traverse_for_variables body is caught and logged"""
        mock_node = Mock()
        mock_node.type = "variable_declaration"
        mock_node.children = []

        variables: list = []

        with patch.object(
            extractor, "_extract_node_name", side_effect=RuntimeError("boom")
        ):
            extractor._traverse_for_variables(mock_node, variables, [], "")

        assert len(variables) == 0

    def test_traverse_for_imports_exception_logged(self, extractor):
        """Exception in _traverse_for_imports body is caught and logged"""
        mock_node = Mock()
        mock_node.type = "import_statement"
        mock_node.children = []

        imports: list = []

        with patch.object(
            extractor, "_extract_node_name", side_effect=RuntimeError("boom")
        ):
            extractor._traverse_for_imports(mock_node, imports, [], "")

        assert len(imports) == 0

    def test_traverse_for_functions_exception_logged(self, extractor):
        """Exception in _traverse_for_functions body is caught and logged"""
        mock_node = Mock()
        mock_node.type = "function_definition"
        mock_node.children = []

        functions: list = []

        with patch.object(
            extractor, "_extract_node_name", side_effect=RuntimeError("boom")
        ):
            extractor._traverse_for_functions(mock_node, functions, [], "")

        assert len(functions) == 0

    def test_extract_node_text_encoding_error(self, extractor):
        """_extract_node_text returns '' on encoding/decoding errors"""
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 5

        # Source code shorter than end_byte → slicing beyond bounds
        result = extractor._extract_node_text(mock_node, "abc")
        # Should handle gracefully without raising
        assert isinstance(result, str)

    def test_extract_node_text_missing_attrs(self, extractor):
        """_extract_node_text returns '' when node lacks start_byte/end_byte"""
        mock_node = Mock()
        # Deliberately omit start_byte/end_byte from the Mock spec
        del mock_node.start_byte
        del mock_node.end_byte

        result = extractor._extract_node_text(mock_node, "abc")
        assert isinstance(result, str)
