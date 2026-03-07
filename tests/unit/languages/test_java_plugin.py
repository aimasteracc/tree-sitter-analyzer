#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.languages.java_plugin module.

This module tests the JavaPlugin class which provides Java language
support in the new plugin architecture.
"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor, JavaPlugin
from tree_sitter_analyzer.models import Class, Function, Import, Package, Variable
from tree_sitter_analyzer.plugins import ElementExtractorBase
from tree_sitter_analyzer.plugins.base import LanguagePlugin


class TestJavaElementExtractor:
    """Test cases for JavaElementExtractor class"""

    @pytest.fixture
    def extractor(self) -> JavaElementExtractor:
        """Create a JavaElementExtractor instance for testing"""
        return JavaElementExtractor()

    @pytest.fixture
    def mock_tree(self) -> Mock:
        """Create a mock tree-sitter tree"""
        tree = Mock()
        root_node = Mock()
        root_node.children = []
        tree.root_node = root_node
        tree.language = Mock()
        return tree

    @pytest.fixture
    def sample_java_code(self) -> str:
        """Sample Java code for testing"""
        return """
package com.example;

import java.util.List;
import java.util.ArrayList;

/**
 * Calculator class for basic arithmetic operations
 */
public class Calculator {
    private int value;
    private static final String VERSION = "1.0";

    /**
     * Constructor
     */
    public Calculator(int initialValue) {
        this.value = initialValue;
    }

    /**
     * Add a number to the current value
     */
    public int add(int number) {
        return value + number;
    }

    /**
     * Get the current value
     */
    public int getValue() {
        return value;
    }

    private void reset() {
        this.value = 0;
    }
}
"""

    def test_extractor_initialization(self, extractor: JavaElementExtractor) -> None:
        """Test JavaElementExtractor initialization"""
        assert extractor is not None
        assert isinstance(extractor, ElementExtractorBase)
        assert hasattr(extractor, "extract_functions")
        assert hasattr(extractor, "extract_classes")
        assert hasattr(extractor, "extract_variables")
        assert hasattr(extractor, "extract_imports")

    def test_extract_functions_success(
        self, extractor: JavaElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful function extraction"""
        # Mock the language query
        mock_query = Mock()
        mock_tree.language.query.return_value = mock_query
        mock_query.captures.return_value = {"method.declaration": []}

        functions = extractor.extract_functions(mock_tree, "test code")

        assert isinstance(functions, list)

    def test_extract_functions_no_language(
        self, extractor: JavaElementExtractor
    ) -> None:
        """Test function extraction when language is not available"""
        mock_tree = Mock()
        mock_tree.language = None
        # Mock root_node with children that can be reversed
        mock_root = Mock()
        mock_root.children = []  # Empty list that can be reversed
        mock_tree.root_node = mock_root

        functions = extractor.extract_functions(mock_tree, "test code")

        assert isinstance(functions, list)
        assert len(functions) == 0

    def test_extract_classes_success(
        self, extractor: JavaElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful class extraction"""
        # Mock the language query
        mock_query = Mock()
        mock_tree.language.query.return_value = mock_query
        mock_query.captures.return_value = {"class.declaration": []}

        classes = extractor.extract_classes(mock_tree, "test code")

        assert isinstance(classes, list)

    def test_extract_variables_success(
        self, extractor: JavaElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful variable extraction"""
        # Mock the language query
        mock_query = Mock()
        mock_tree.language.query.return_value = mock_query
        mock_query.captures.return_value = {"field.declaration": []}

        variables = extractor.extract_variables(mock_tree, "test code")

        assert isinstance(variables, list)

    def test_extract_imports_success(
        self, extractor: JavaElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful import extraction"""
        # Mock the language query
        mock_query = Mock()
        mock_tree.language.query.return_value = mock_query
        mock_query.captures.return_value = {"import.declaration": []}

        imports = extractor.extract_imports(mock_tree, "test code")

        assert isinstance(imports, list)

    def test_extract_method_optimized(self, extractor: JavaElementExtractor) -> None:
        """Test optimized method extraction"""
        mock_node = Mock()
        mock_node.type = "method_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (10, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 100
        mock_node.children = []

        result = extractor._extract_method_optimized(mock_node)

        # The method should handle the mock gracefully
        assert result is None or isinstance(result, Function)

    def test_extract_class_optimized(self, extractor: JavaElementExtractor) -> None:
        """Test optimized class extraction"""
        mock_node = Mock()
        mock_node.type = "class_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (10, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 100
        mock_node.children = []

        result = extractor._extract_class_optimized(mock_node)

        # The method should handle the mock gracefully
        assert result is None or isinstance(result, Class)

    def test_extract_field_optimized(self, extractor: JavaElementExtractor) -> None:
        """Test field information extraction"""
        mock_node = Mock()
        mock_node.type = "field_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 20
        mock_node.children = []

        result = extractor._extract_field_optimized(mock_node)

        # The method should handle the mock gracefully and return a list
        assert isinstance(result, list)

    def test_extract_import_info(self, extractor: JavaElementExtractor) -> None:
        """Test import information extraction"""
        mock_node = Mock()
        mock_node.type = "import_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 25
        mock_node.children = []

        result = extractor._extract_import_info(mock_node, "import java.util.List;")

        # The method should handle gracefully
        assert result is None or isinstance(result, Import)

    def test_extract_class_name(self, extractor: JavaElementExtractor) -> None:
        """Test class name extraction from node"""
        mock_node = Mock()
        mock_identifier = Mock()
        mock_identifier.type = "identifier"
        mock_identifier.text = b"TestClass"
        mock_node.children = [mock_identifier]

        # Mock the _get_node_text_optimized method to return our expected value
        with patch.object(
            extractor, "_get_node_text_optimized", return_value="TestClass"
        ):
            name = extractor._extract_class_name(mock_node)

            assert name == "TestClass"

    def test_extract_class_name_no_identifier(
        self, extractor: JavaElementExtractor
    ) -> None:
        """Test class name extraction when no identifier is found"""
        mock_node = Mock()
        mock_node.children = []

        name = extractor._extract_class_name(mock_node)

        assert name is None

    def test_calculate_complexity_optimized(
        self, extractor: JavaElementExtractor
    ) -> None:
        """Test complexity calculation"""
        # Create mock nodes for testing complexity
        simple_node = Mock()
        simple_node.type = "return_statement"
        simple_node.children = []

        complex_node = Mock()
        complex_node.type = "if_statement"
        complex_node.children = [
            Mock(),
            Mock(),
            Mock(),
        ]  # Multiple children for complexity

        simple_complexity = extractor._calculate_complexity_optimized(simple_node)
        complex_complexity = extractor._calculate_complexity_optimized(complex_node)

        assert isinstance(simple_complexity, int)
        assert isinstance(complex_complexity, int)
        assert simple_complexity >= 1
        assert complex_complexity >= 1


class TestJavaPlugin:
    """Test cases for JavaPlugin class"""

    @pytest.fixture
    def plugin(self) -> JavaPlugin:
        """Create a JavaPlugin instance for testing"""
        return JavaPlugin()

    def test_plugin_initialization(self, plugin: JavaPlugin) -> None:
        """Test JavaPlugin initialization"""
        assert plugin is not None
        assert isinstance(plugin, LanguagePlugin)
        assert hasattr(plugin, "get_language_name")
        assert hasattr(plugin, "get_file_extensions")
        assert hasattr(plugin, "create_extractor")

    def test_get_language_name(self, plugin: JavaPlugin) -> None:
        """Test getting language name"""
        language_name = plugin.get_language_name()

        assert language_name == "java"

    def test_get_file_extensions(self, plugin: JavaPlugin) -> None:
        """Test getting file extensions"""
        extensions = plugin.get_file_extensions()

        assert isinstance(extensions, list)
        assert ".java" in extensions

    def test_create_extractor(self, plugin: JavaPlugin) -> None:
        """Test creating element extractor"""
        extractor = plugin.create_extractor()

        assert isinstance(extractor, JavaElementExtractor)
        assert isinstance(extractor, ElementExtractorBase)

    def test_is_applicable_java_file(self, plugin: JavaPlugin) -> None:
        """Test applicability check for Java file"""
        is_applicable = plugin.is_applicable("test.java")

        assert is_applicable is True

    def test_is_applicable_non_java_file(self, plugin: JavaPlugin) -> None:
        """Test applicability check for non-Java file"""
        is_applicable = plugin.is_applicable("test.py")

        assert is_applicable is False

    def test_get_plugin_info(self, plugin: JavaPlugin) -> None:
        """Test getting plugin information"""
        info = plugin.get_plugin_info()

        assert isinstance(info, dict)
        assert "language" in info
        assert "extensions" in info
        assert info["language"] == "java"

    def test_get_tree_sitter_language(self, plugin: JavaPlugin) -> None:
        """Test getting tree-sitter language"""
        with (
            patch("tree_sitter_java.language") as mock_language,
            patch("tree_sitter.Language") as mock_language_constructor,
        ):
            mock_lang_obj = Mock()
            mock_language.return_value = mock_lang_obj
            mock_language_constructor.return_value = mock_lang_obj

            language = plugin.get_tree_sitter_language()

            assert language is mock_lang_obj

    def test_get_tree_sitter_language_caching(self, plugin: JavaPlugin) -> None:
        """Test tree-sitter language caching"""
        with (
            patch("tree_sitter_java.language") as mock_language,
            patch("tree_sitter.Language") as mock_language_constructor,
        ):
            mock_lang_obj = Mock()
            mock_language.return_value = mock_lang_obj
            mock_language_constructor.return_value = mock_lang_obj

            # First call
            language1 = plugin.get_tree_sitter_language()

            # Second call (should use cache)
            language2 = plugin.get_tree_sitter_language()

            assert language1 is language2
            # Should only be called once due to caching
            mock_language.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_file_success(self, plugin: JavaPlugin) -> None:
        """Test successful file analysis"""
        java_code = """
public class TestClass {
    public void testMethod() {
        System.out.println("Hello");
    }
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            # Mock AnalysisRequest
            mock_request = Mock()
            mock_request.file_path = temp_path
            mock_request.language = "java"
            mock_request.include_complexity = False
            mock_request.include_details = False

            result = await plugin.analyze_file(temp_path, mock_request)

            assert result is not None
            assert hasattr(result, "success")
            assert hasattr(result, "file_path")
            assert hasattr(result, "language")

        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_analyze_file_nonexistent(self, plugin: JavaPlugin) -> None:
        """Test analysis of non-existent file"""
        mock_request = Mock()
        mock_request.file_path = "/nonexistent/file.java"
        mock_request.language = "java"

        result = await plugin.analyze_file("/nonexistent/file.java", mock_request)

        # Should return an AnalysisResult with success=False instead of raising
        assert result is not None
        assert hasattr(result, "success")
        assert result.success is False


class TestJavaPluginErrorHandling:
    """Test error handling in JavaPlugin"""

    @pytest.fixture
    def plugin(self) -> JavaPlugin:
        """Create a JavaPlugin instance for testing"""
        return JavaPlugin()

    @pytest.fixture
    def extractor(self) -> JavaElementExtractor:
        """Create a JavaElementExtractor instance for testing"""
        return JavaElementExtractor()

    def test_extract_functions_with_exception(
        self, extractor: JavaElementExtractor
    ) -> None:
        """Test function extraction with exception"""
        mock_tree = Mock()
        mock_tree.language = None  # This will cause the extraction to fail gracefully
        # Mock root_node with children that can be reversed
        mock_root = Mock()
        mock_root.children = []  # Empty list that can be reversed
        mock_tree.root_node = mock_root

        functions = extractor.extract_functions(mock_tree, "test code")

        # Should handle gracefully
        assert isinstance(functions, list)
        assert len(functions) == 0

    def test_extract_classes_with_exception(
        self, extractor: JavaElementExtractor
    ) -> None:
        """Test class extraction with exception"""
        mock_tree = Mock()
        mock_tree.language = None  # This will cause the extraction to fail gracefully
        # Mock root_node with children that can be reversed
        mock_root = Mock()
        mock_root.children = []  # Empty list that can be reversed
        mock_tree.root_node = mock_root

        classes = extractor.extract_classes(mock_tree, "test code")

        # Should handle gracefully
        assert isinstance(classes, list)
        assert len(classes) == 0

    def test_extract_method_optimized_with_exception(
        self, extractor: JavaElementExtractor
    ) -> None:
        """Test optimized method extraction with exception"""
        mock_node = Mock()
        mock_node.type = "method_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (10, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 100
        mock_node.children = []

        # Mock an exception during processing
        with patch.object(extractor, "_extract_class_name") as mock_extract:
            mock_extract.side_effect = Exception("Extraction error")

            result = extractor._extract_method_optimized(mock_node)

            # Should handle gracefully
            assert result is None

    def test_get_tree_sitter_language_failure(self, plugin: JavaPlugin) -> None:
        """Test tree-sitter language loading failure"""
        with patch("tree_sitter_java.language") as mock_language:
            mock_language.side_effect = ImportError("Module not found")

            language = plugin.get_tree_sitter_language()

            assert language is None

    @pytest.mark.asyncio
    async def test_analyze_file_with_exception(self, plugin: JavaPlugin) -> None:
        """Test file analysis with exception"""
        java_code = "public class Test {}"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            mock_request = Mock()
            mock_request.file_path = temp_path
            mock_request.language = "java"

            with patch(
                "tree_sitter_analyzer.encoding_utils.read_file_safe_async"
            ) as mock_read:
                mock_read.side_effect = Exception("Read error")

                result = await plugin.analyze_file(temp_path, mock_request)

                # Should return error result instead of raising
                assert result is not None
                assert hasattr(result, "success")
                assert result.success is False

        finally:
            os.unlink(temp_path)


class TestJavaPluginIntegration:
    """Integration tests for JavaPlugin"""

    @pytest.fixture
    def plugin(self) -> JavaPlugin:
        """Create a JavaPlugin instance for testing"""
        return JavaPlugin()

    def test_full_extraction_workflow(self, plugin: JavaPlugin) -> None:
        """Test complete extraction workflow"""
        # Test that plugin can handle complex Java code

        # Test that plugin can handle complex Java code
        extractor = plugin.create_extractor()
        assert isinstance(extractor, JavaElementExtractor)

        # Test applicability
        assert plugin.is_applicable("Calculator.java") is True
        assert plugin.is_applicable("calculator.py") is False

        # Test plugin info
        info = plugin.get_plugin_info()
        assert info["language"] == "java"
        assert ".java" in info["extensions"]

    def test_plugin_consistency(self, plugin: JavaPlugin) -> None:
        """Test plugin consistency across multiple calls"""
        # Multiple calls should return consistent results
        for _ in range(5):
            assert plugin.get_language_name() == "java"
            assert ".java" in plugin.get_file_extensions()
            assert isinstance(plugin.create_extractor(), JavaElementExtractor)

    def test_extractor_consistency(self, plugin: JavaPlugin) -> None:
        """Test extractor consistency"""
        # Multiple extractors should be independent
        extractor1 = plugin.create_extractor()
        extractor2 = plugin.create_extractor()

        assert extractor1 is not extractor2
        assert isinstance(extractor1, JavaElementExtractor)
        assert isinstance(extractor2, JavaElementExtractor)

    def test_plugin_with_various_java_files(self, plugin: JavaPlugin) -> None:
        """Test plugin with various Java file types"""
        java_files = [
            "Test.java",
            "com/example/Test.java",
            "src/main/java/Test.java",
            "TEST.JAVA",  # Case variations
            "test.Java",
        ]

        for java_file in java_files:
            assert plugin.is_applicable(java_file) is True

        non_java_files = [
            "test.py",
            "test.js",
            "test.cpp",
            "test.txt",
            "java.txt",  # Contains 'java' but wrong extension
        ]

        for non_java_file in non_java_files:
            assert plugin.is_applicable(non_java_file) is False


class TestJavaExtractorCachesAndTraversal:
    """Tests for cache management, traversal, and batch processing.

    Merged from test_java_plugin_comprehensive.py and
    test_java_plugin_edge_cases.py.
    """

    @pytest.fixture
    def extractor(self) -> JavaElementExtractor:
        """Create a JavaElementExtractor instance for testing"""
        return JavaElementExtractor()

    def test_reset_caches(self, extractor: JavaElementExtractor) -> None:
        """Test cache reset functionality clears all internal caches"""
        # Populate caches
        extractor._node_text_cache[1] = "test"
        extractor._processed_nodes.add(1)
        extractor._element_cache[(1, "test")] = "value"
        extractor._annotation_cache[1] = [{"name": "Test"}]
        extractor._signature_cache[1] = "signature"
        extractor.annotations.append({"name": "Test"})

        extractor._reset_caches()

        assert len(extractor._node_text_cache) == 0
        assert len(extractor._processed_nodes) == 0
        assert len(extractor._element_cache) == 0
        assert len(extractor._annotation_cache) == 0
        assert len(extractor._signature_cache) == 0
        assert len(extractor.annotations) == 0

    def test_get_node_text_optimized_caching(
        self, extractor: JavaElementExtractor
    ) -> None:
        """Test that node text extraction caches results and avoids repeat work"""
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10

        extractor.content_lines = ["test content line"]
        extractor._file_encoding = "utf-8"

        with patch(
            "tree_sitter_analyzer.languages.java_plugin.extract_text_slice"
        ) as mock_extract:
            mock_extract.return_value = "test text"

            result1 = extractor._get_node_text_optimized(mock_node)
            assert result1 == "test text"
            assert (
                mock_node.start_byte,
                mock_node.end_byte,
            ) in extractor._node_text_cache

            result2 = extractor._get_node_text_optimized(mock_node)
            assert result2 == "test text"
            assert mock_extract.call_count == 1  # Only called once due to caching

    def test_traverse_and_extract_iterative(
        self, extractor: JavaElementExtractor
    ) -> None:
        """Test iterative traversal extracts both methods and classes"""
        mock_root = Mock()
        mock_child1 = Mock()
        mock_child1.type = "method_declaration"
        mock_child1.children = []

        mock_child2 = Mock()
        mock_child2.type = "class_declaration"
        mock_child2.children = []

        mock_root.children = [mock_child1, mock_child2]

        mock_method_extractor = Mock()
        mock_method_extractor.return_value = Function(
            name="test_method",
            start_line=1,
            end_line=3,
            raw_text="public void test_method() {}",
            language="java",
        )

        mock_class_extractor = Mock()
        mock_class_extractor.return_value = Class(
            name="TestClass",
            start_line=5,
            end_line=10,
            raw_text="public class TestClass {}",
            language="java",
        )

        extractors = {
            "method_declaration": mock_method_extractor,
            "class_declaration": mock_class_extractor,
        }

        results = []
        extractor._traverse_and_extract_iterative(
            mock_root, extractors, results, "mixed"
        )

        assert len(results) == 2
        assert isinstance(results[0], Function)
        assert isinstance(results[1], Class)

    def test_traverse_and_extract_iterative_with_caching(
        self, extractor: JavaElementExtractor
    ) -> None:
        """Test traversal uses element cache to skip repeated extraction"""
        mock_root = Mock()
        mock_child = Mock()
        mock_child.type = "method_declaration"
        mock_child.children = []
        mock_root.children = [mock_child]

        node_id = id(mock_child)
        cache_key = (node_id, "method")
        cached_method = Function(
            name="cached_method",
            start_line=1,
            end_line=2,
            raw_text="public void cached_method() {}",
            language="java",
        )
        extractor._element_cache[cache_key] = cached_method

        extractors = {"method_declaration": Mock()}
        results = []

        extractor._traverse_and_extract_iterative(
            mock_root, extractors, results, "method"
        )

        assert len(results) == 1
        assert results[0] == cached_method
        assert extractors["method_declaration"].call_count == 0

    def test_process_field_batch(self, extractor: JavaElementExtractor) -> None:
        """Test field batch processing handles multiple field nodes"""
        field_nodes = []
        for _i in range(5):
            node = Mock()
            node.type = "field_declaration"
            field_nodes.append(node)

        def mock_field_extractor(node):
            return [
                Variable(
                    name=f"field_{i}",
                    start_line=1,
                    end_line=1,
                    raw_text=f"private String field_{i};",
                    language="java",
                )
                for i in range(2)
            ]

        extractors = {"field_declaration": mock_field_extractor}
        results = []

        extractor._process_field_batch(field_nodes, extractors, results)

        # 5 nodes, each returning 2 variables = 10
        assert len(results) == 10


class TestJavaExtractorAdditionalElements:
    """Tests for packages, annotations, import fallback, and field extraction.

    Merged from test_java_plugin_comprehensive.py and
    test_java_plugin_edge_cases.py.
    """

    @pytest.fixture
    def extractor(self) -> JavaElementExtractor:
        """Create a JavaElementExtractor instance for testing"""
        return JavaElementExtractor()

    def test_extract_packages_basic(self, extractor: JavaElementExtractor) -> None:
        """Test basic package extraction via extract_packages"""
        mock_tree = Mock()
        mock_package_node = Mock()
        mock_package_node.type = "package_declaration"
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = [mock_package_node]

        with patch.object(extractor, "_extract_package_element") as mock_extract:
            mock_package = Package(
                name="com.example.service",
                start_line=1,
                end_line=1,
                raw_text="package com.example.service;",
                language="java",
            )
            mock_extract.return_value = mock_package

            packages = extractor.extract_packages(mock_tree, "package com.example.service;")

            assert isinstance(packages, list)
            mock_extract.assert_called_once()

    def test_extract_annotations_basic(self, extractor: JavaElementExtractor) -> None:
        """Test basic annotation extraction via extract_annotations"""
        mock_tree = Mock()
        mock_annotation_node = Mock()
        mock_annotation_node.type = "annotation"
        mock_annotation_node.children = []
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = [mock_annotation_node]

        with patch.object(
            extractor, "_traverse_and_extract_iterative"
        ) as mock_traverse:
            annotations = extractor.extract_annotations(mock_tree, "@Service\npublic class Foo {}")

            mock_traverse.assert_called_once()
            assert isinstance(annotations, list)

    def test_extract_imports_fallback_static_imports(
        self, extractor: JavaElementExtractor
    ) -> None:
        """Test fallback import extraction correctly parses static imports"""
        source_code = """
        import static java.util.Collections.emptyList;
        import static org.junit.Assert.*;
        import static com.example.Utils.helper;
        """

        imports = extractor._extract_imports_fallback(source_code)

        assert len(imports) == 3
        assert imports[0].name == "java.util.Collections"
        assert imports[0].is_static is True
        assert imports[0].is_wildcard is False
        assert imports[1].name == "org.junit.Assert"
        assert imports[1].is_static is True
        assert imports[1].is_wildcard is True
        assert imports[2].name == "com.example.Utils"
        assert imports[2].is_static is True
        assert imports[2].is_wildcard is False

    def test_extract_imports_fallback_normal_imports(
        self, extractor: JavaElementExtractor
    ) -> None:
        """Test fallback import extraction correctly parses normal and wildcard imports"""
        source_code = """
        import java.util.List;
        import java.util.*;
        import javax.annotation.Nullable;
        """

        imports = extractor._extract_imports_fallback(source_code)

        assert len(imports) == 3
        assert imports[0].name == "java.util.List"
        assert imports[0].is_static is False
        assert imports[0].is_wildcard is False
        assert imports[1].name == "java.util"
        assert imports[1].is_static is False
        assert imports[1].is_wildcard is True
        assert imports[2].name == "javax.annotation.Nullable"
        assert imports[2].is_static is False
        assert imports[2].is_wildcard is False

    def test_extract_field_optimized_complete(
        self, extractor: JavaElementExtractor
    ) -> None:
        """Test complete field extraction produces Variable with all attributes"""
        mock_node = Mock()
        mock_node.type = "field_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        extractor.content_lines = [
            "/**",
            " * User repository for data access",
            " */",
            "@Autowired",
            "private UserRepository userRepository;",
        ]

        with patch.object(
            extractor, "_parse_field_declaration_optimized"
        ) as mock_parse:
            mock_parse.return_value = (
                "UserRepository",
                ["userRepository"],
                ["private"],
            )

            with patch.object(extractor, "_determine_visibility") as mock_visibility:
                mock_visibility.return_value = "private"

                with patch.object(
                    extractor, "_find_annotations_for_line_cached"
                ) as mock_annotations:
                    mock_annotations.return_value = [{"name": "Autowired"}]

                    with patch.object(
                        extractor, "_extract_javadoc_for_line"
                    ) as mock_javadoc:
                        mock_javadoc.return_value = "User repository for data access"

                        result = extractor._extract_field_optimized(mock_node)

                        assert isinstance(result, list)
                        assert len(result) == 1
                        field = result[0]
                        assert isinstance(field, Variable)
                        assert field.name == "userRepository"
                        assert field.variable_type == "UserRepository"
                        assert field.modifiers == ["private"]
                        assert field.visibility == "private"
                        assert field.docstring == "User repository for data access"
                        assert field.annotations == [{"name": "Autowired"}]

    def test_extract_field_optimized_multiple_variables(
        self, extractor: JavaElementExtractor
    ) -> None:
        """Test field extraction when declaration contains multiple variable names"""
        mock_node = Mock()
        mock_node.type = "field_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 30)

        extractor.content_lines = ["private String firstName, lastName, email;"]

        with patch.object(
            extractor, "_parse_field_declaration_optimized"
        ) as mock_parse:
            mock_parse.return_value = (
                "String",
                ["firstName", "lastName", "email"],
                ["private"],
            )

            with patch.object(extractor, "_determine_visibility") as mock_visibility:
                mock_visibility.return_value = "private"

                with patch.object(
                    extractor, "_find_annotations_for_line_cached"
                ) as mock_annotations:
                    mock_annotations.return_value = []

                    with patch.object(
                        extractor, "_extract_javadoc_for_line"
                    ) as mock_javadoc:
                        mock_javadoc.return_value = None

                        result = extractor._extract_field_optimized(mock_node)

                        assert isinstance(result, list)
                        assert len(result) == 3
                        assert result[0].name == "firstName"
                        assert result[1].name == "lastName"
                        assert result[2].name == "email"
                        for field in result:
                            assert field.variable_type == "String"
                            assert field.modifiers == ["private"]


class TestJavaEdgeCasesMerged:
    """Edge case tests for empty input, Unicode, encoding, and malformed code.

    Merged from test_java_plugin_edge_cases.py.
    """

    @pytest.fixture
    def extractor(self) -> JavaElementExtractor:
        """Create a JavaElementExtractor instance for testing"""
        return JavaElementExtractor()

    @pytest.fixture
    def plugin(self) -> JavaPlugin:
        """Create a JavaPlugin instance for testing"""
        return JavaPlugin()

    def test_empty_source_code(self, extractor: JavaElementExtractor) -> None:
        """Test all extractors return empty lists for empty source code"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        assert extractor.extract_functions(mock_tree, "") == []
        assert extractor.extract_classes(mock_tree, "") == []
        assert extractor.extract_variables(mock_tree, "") == []
        assert extractor.extract_imports(mock_tree, "") == []
        assert extractor.extract_packages(mock_tree, "") == []
        assert extractor.extract_annotations(mock_tree, "") == []

    def test_unicode_and_special_characters(
        self, extractor: JavaElementExtractor
    ) -> None:
        """Test extraction does not crash on Unicode identifiers and special chars"""
        unicode_code = """
        package com.\u4f8b\u3048.\u30c6\u30b9\u30c8;
        import java.util.\u65e5\u672c\u8a9e;
        public class \u65e5\u672c\u8a9e\u30af\u30e9\u30b9 {
            private String \u540d\u524d = "\u5024";
            public String \u65e5\u672c\u8a9e\u30e1\u30bd\u30c3\u30c9(String \u30d1\u30e9\u30e1\u30fc\u30bf) {
                return "\u7d50\u679c";
            }
        }
        """

        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        assert isinstance(extractor.extract_functions(mock_tree, unicode_code), list)
        assert isinstance(extractor.extract_classes(mock_tree, unicode_code), list)
        assert isinstance(extractor.extract_variables(mock_tree, unicode_code), list)

    def test_encoding_edge_cases(self, extractor: JavaElementExtractor) -> None:
        """Test node text extraction with various file encodings"""
        encodings = ["utf-8", "latin1", "ascii", "utf-16"]

        for encoding in encodings:
            extractor._file_encoding = encoding
            mock_node = Mock()
            mock_node.start_byte = 0
            mock_node.end_byte = 5
            mock_node.start_point = (0, 0)
            mock_node.end_point = (0, 5)

            extractor.content_lines = ["test"]

            with patch(
                "tree_sitter_analyzer.languages.java_plugin.extract_text_slice"
            ) as mock_extract:
                mock_extract.return_value = "test"
                result = extractor._get_node_text_optimized(mock_node)
                assert isinstance(result, str)

    def test_plugin_extract_elements_with_none_tree(
        self, plugin: JavaPlugin
    ) -> None:
        """Test extract_elements gracefully handles None tree"""
        result = plugin.extract_elements(None, "public class Test {}")
        expected_keys = {
            "functions",
            "classes",
            "variables",
            "imports",
            "packages",
            "annotations",
        }
        assert set(result.keys()) == expected_keys
        for key in expected_keys:
            assert result[key] == []


# ====================================================================== #
# TARGETED TESTS for coverage boost (79.5% -> 80%+)
# ====================================================================== #


class TestJavaFallbackBranches:
    """Tests targeting specific uncovered fallback/exception branches."""

    @pytest.fixture
    def extractor(self) -> JavaElementExtractor:
        return JavaElementExtractor()

    @pytest.fixture
    def plugin(self) -> JavaPlugin:
        return JavaPlugin()

    def test_get_node_text_fallback_single_line(self, extractor):
        """Cover lines 487-491: fallback single-line text extraction"""
        node = Mock()
        node.start_byte = 0
        node.end_byte = 10
        node.start_point = (0, 2)
        node.end_point = (0, 7)
        extractor.content_lines = ["Hello World!"]

        with patch(
            "tree_sitter_analyzer.languages.java_plugin.extract_text_slice",
            side_effect=Exception("primary error"),
        ):
            result = extractor._get_node_text_optimized(node)
            assert result == "llo W"

    def test_get_node_text_fallback_multiline(self, extractor):
        """Cover lines 494-504: fallback multiline text extraction"""
        node = Mock()
        node.start_byte = 0
        node.end_byte = 30
        node.start_point = (0, 5)
        node.end_point = (2, 3)
        extractor.content_lines = ["Hello World!", "Middle line", "End text"]

        with patch(
            "tree_sitter_analyzer.languages.java_plugin.extract_text_slice",
            side_effect=Exception("primary error"),
        ):
            result = extractor._get_node_text_optimized(node)
            assert "World!" in result
            assert "Middle line" in result
            assert "End" in result

    def test_get_node_text_both_fallbacks_fail(self, extractor):
        """Cover lines 505-507: both primary and fallback fail"""
        node = Mock()
        node.start_byte = 0
        node.end_byte = 10
        type(node).start_point = property(
            lambda self: (_ for _ in ()).throw(Exception("bad"))
        )
        extractor.content_lines = ["test"]

        with patch(
            "tree_sitter_analyzer.languages.java_plugin.extract_text_slice",
            side_effect=Exception("primary error"),
        ):
            result = extractor._get_node_text_optimized(node)
            assert result == ""

    def test_extract_class_optimized_value_error(self, extractor):
        """Cover lines 589-591: ValueError in class extraction"""
        node = Mock()
        node.type = "class_declaration"
        node.start_point = (0, 0)
        node.end_point = (5, 0)
        node.children = []
        extractor.content_lines = ["public class Test {}"]
        extractor._get_node_text_optimized = Mock(side_effect=ValueError("bad"))
        result = extractor._extract_class_optimized(node)
        assert result is None

    def test_extract_class_optimized_unexpected_error(self, extractor):
        """Cover lines 592-594: unexpected error in class extraction"""
        node = Mock()
        node.type = "class_declaration"
        node.start_point = (0, 0)
        node.end_point = (5, 0)
        node.children = []
        extractor.content_lines = ["public class Test {}"]
        extractor._get_node_text_optimized = Mock(side_effect=RuntimeError("unexpected"))
        result = extractor._extract_class_optimized(node)
        assert result is None

    def test_extract_method_optimized_value_error(self, extractor):
        """Cover lines 647-649: ValueError in method extraction"""
        node = Mock()
        node.type = "method_declaration"
        node.start_point = (0, 0)
        node.end_point = (3, 0)
        node.children = []
        extractor.content_lines = ["public void test() {}"]
        extractor._parse_method_signature_optimized = Mock(
            side_effect=TypeError("bad")
        )
        result = extractor._extract_method_optimized(node)
        assert result is None

    def test_extract_method_optimized_unexpected_error(self, extractor):
        """Cover lines 650-652: unexpected error in method extraction"""
        node = Mock()
        node.type = "method_declaration"
        node.start_point = (0, 0)
        node.end_point = (3, 0)
        node.children = []
        extractor.content_lines = ["public void test() {}"]
        extractor._parse_method_signature_optimized = Mock(
            side_effect=RuntimeError("unexpected")
        )
        result = extractor._extract_method_optimized(node)
        assert result is None

    def test_extract_field_optimized_value_error(self, extractor):
        """Cover lines 700-701: ValueError in field extraction"""
        node = Mock()
        node.type = "field_declaration"
        node.start_point = (0, 0)
        node.end_point = (0, 20)
        node.children = []
        extractor.content_lines = ["private int x;"]
        extractor._parse_field_declaration_optimized = Mock(
            side_effect=AttributeError("bad")
        )
        result = extractor._extract_field_optimized(node)
        assert result == []

    def test_extract_field_optimized_unexpected_error(self, extractor):
        """Cover lines 702-703: unexpected error in field extraction"""
        node = Mock()
        node.type = "field_declaration"
        node.start_point = (0, 0)
        node.end_point = (0, 20)
        node.children = []
        extractor.content_lines = ["private int x;"]
        extractor._parse_field_declaration_optimized = Mock(
            side_effect=RuntimeError("unexpected")
        )
        result = extractor._extract_field_optimized(node)
        assert result == []

    def test_parse_method_signature_returns_none(self, extractor):
        """Cover line 762-763: method signature returns None when no name"""
        node = Mock()
        node.children = []
        extractor._get_node_text_optimized = Mock(return_value="")
        result = extractor._parse_method_signature_optimized(node)
        assert result is None

    def test_parse_field_declaration_no_type(self, extractor):
        """Cover line 785: field declaration with no type found"""
        node = Mock()
        node.children = []
        extractor._get_node_text_optimized = Mock(return_value="")
        result = extractor._parse_field_declaration_optimized(node)
        assert result is None

    def test_parse_field_declaration_no_names(self, extractor):
        """Cover lines 797-798: field declaration with type but no names"""
        node = Mock()
        type_child = Mock()
        type_child.type = "type_identifier"
        node.children = [type_child]
        extractor._get_node_text_optimized = Mock(return_value="String")
        result = extractor._parse_field_declaration_optimized(node)
        assert result is None

    def test_parse_field_declaration_exception(self, extractor):
        """Cover lines 804-805: exception in field declaration"""
        node = Mock()
        type(node).children = property(
            lambda self: (_ for _ in ()).throw(Exception("bad"))
        )
        result = extractor._parse_field_declaration_optimized(node)
        assert result is None

    def test_extract_modifiers_non_keyword_text(self, extractor):
        """Cover lines 825-838: modifiers extraction with non-keyword text"""
        node = Mock()
        modifiers_node = Mock()
        modifiers_node.type = "modifiers"
        non_keyword = Mock()
        non_keyword.type = "some_other_type"
        modifiers_node.children = [non_keyword]
        node.children = [modifiers_node]
        extractor._get_node_text_optimized = Mock(return_value="public")
        result = extractor._extract_modifiers_optimized(node)
        assert "public" in result

    def test_extract_package_info_error(self, extractor):
        """Cover lines 848-851: package extraction errors"""
        node = Mock()
        extractor._get_node_text_optimized = Mock(
            side_effect=ValueError("bad")
        )
        extractor._extract_package_info(node)
        assert extractor.current_package == ""

    def test_extract_package_info_unexpected_error(self, extractor):
        """Cover line 850-851: unexpected error in package extraction"""
        node = Mock()
        extractor._get_node_text_optimized = Mock(
            side_effect=RuntimeError("unexpected")
        )
        extractor._extract_package_info(node)
        assert extractor.current_package == ""

    def test_extract_package_element_error(self, extractor):
        """Cover lines 867-870: package element extraction errors"""
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (0, 20)
        extractor._get_node_text_optimized = Mock(
            side_effect=AttributeError("bad")
        )
        result = extractor._extract_package_element(node)
        assert result is None

    def test_extract_package_element_unexpected_error(self, extractor):
        """Cover lines 869-870: unexpected error in package element"""
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (0, 20)
        extractor._get_node_text_optimized = Mock(
            side_effect=RuntimeError("unexpected")
        )
        result = extractor._extract_package_element(node)
        assert result is None

    def test_extract_annotation_no_name_text_fallback(self, extractor):
        """Cover lines 958-961: annotation without identifier, falls back to regex"""
        node = Mock()
        node.type = "marker_annotation"
        node.start_point = (0, 0)
        node.end_point = (0, 10)
        node.children = []
        extractor._get_node_text_optimized = Mock(return_value="@Override")
        result = extractor._extract_annotation_optimized(node)
        assert result is not None
        assert result["name"] == "Override"

    def test_extract_annotation_exception(self, extractor):
        """Cover lines 970-971: exception in annotation extraction"""
        node = Mock()
        node.start_point = Mock(side_effect=Exception("err"))
        result = extractor._extract_annotation_optimized(node)
        assert result is None

    def test_is_nested_class_false(self, extractor):
        """Cover line 1011: not a nested class"""
        node = Mock()
        # parent is program, not a class
        parent = Mock()
        parent.type = "program"
        parent.parent = None
        node.parent = parent
        result = extractor._is_nested_class(node)
        assert result is False

    def test_find_parent_class_none(self, extractor):
        """Cover line 1026: no parent class found"""
        node = Mock()
        parent = Mock()
        parent.type = "program"
        parent.parent = None
        node.parent = parent
        result = extractor._find_parent_class(node)
        assert result is None

    def test_find_parent_class_found(self, extractor):
        """Cover lines 1017-1024: parent class found"""
        node = Mock()
        class_node = Mock()
        class_node.type = "class_declaration"
        class_node.parent = None
        id_node = Mock()
        id_node.type = "identifier"
        class_node.children = [id_node]
        node.parent = class_node
        extractor._get_node_text_optimized = Mock(return_value="ParentClass")
        result = extractor._find_parent_class(node)
        assert result == "ParentClass"

    def test_extract_javadoc_for_line_exception(self, extractor):
        """Cover lines 1075-1076: exception in javadoc extraction"""
        extractor.content_lines = None  # Will cause exception
        result = extractor._extract_javadoc_for_line(5)
        assert result is None

    def test_extract_class_name_exception(self, extractor):
        """Cover lines 1087-1089: exception in class name extraction"""
        node = Mock()
        type(node).children = property(
            lambda self: (_ for _ in ()).throw(Exception("bad"))
        )
        result = extractor._extract_class_name(node)
        assert result is None

    def test_count_tree_nodes_deprecated(self, plugin):
        """Cover lines 1216-1218: _count_tree_nodes method"""
        node = Mock()
        node.children = []
        result = plugin._count_tree_nodes(node)
        assert isinstance(result, int)
        assert result >= 1

    def test_supports_file(self, plugin):
        """Cover lines 1288-1292: supports_file method"""
        assert plugin.supports_file("Test.java") is True
        assert plugin.supports_file("Test.jsp") is True
        assert plugin.supports_file("Test.py") is False
        assert plugin.supports_file("Test.js") is False

    def test_extract_elements_with_exception(self, plugin):
        """Cover lines 1277-1286: extract_elements exception"""
        tree = Mock()
        tree.root_node = Mock()
        with patch.object(
            plugin, "create_extractor", side_effect=Exception("err")
        ):
            result = plugin.extract_elements(tree, "code")
            assert result["functions"] == []
            assert result["classes"] == []

    def test_extract_packages_fallback(self, extractor):
        """Cover lines 274-294: package extraction fallback via regex"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []  # No package_declaration in AST

        source = "package com.example.test;\n\npublic class Test {}"
        packages = extractor.extract_packages(mock_tree, source)
        assert len(packages) == 1
        assert packages[0].name == "com.example.test"

    def test_extract_import_info_static(self, extractor):
        """Cover lines 891-914: static import extraction"""
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (0, 40)
        node.start_byte = 0
        node.end_byte = 40
        extractor.content_lines = ["import static java.util.Collections.sort;"]
        extractor._get_node_text_optimized = Mock(
            return_value="import static java.util.Collections.sort;"
        )
        result = extractor._extract_import_info(
            node, "import static java.util.Collections.sort;"
        )
        assert result is not None
        assert result.is_static is True

    def test_extract_import_info_wildcard(self, extractor):
        """Cover lines 920-924: wildcard import (text without semicolon)"""
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (0, 22)
        # The endswith(".*") check needs text ending in ".*" (no semicolon)
        extractor._get_node_text_optimized = Mock(
            return_value="import java.util.*"
        )
        result = extractor._extract_import_info(node, "import java.util.*")
        assert result is not None
        assert result.is_wildcard is True
        assert result.name == "java.util"

    def test_extract_import_info_wildcard_with_dot_ending(self, extractor):
        """Cover line 923-924: import name ending with dot"""
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (0, 22)
        # Simulate text where regex captures trailing dot
        extractor._get_node_text_optimized = Mock(
            return_value="import java.util.*"
        )
        result = extractor._extract_import_info(node, "import java.util.*")
        assert result is not None
        assert result.is_wildcard is True

    def test_extract_import_info_exception(self, extractor):
        """Cover lines 937-938: exception in import extraction"""
        node = Mock()
        node.start_point = Mock(side_effect=Exception("err"))
        result = extractor._extract_import_info(node, "import test;")
        assert result is None

    def test_traversal_max_depth(self, extractor):
        """Cover lines 356-358: max depth exceeded"""
        root = Mock()
        root.type = "program"
        root.children = []

        # Create a deeply nested structure
        current = root
        for _i in range(55):
            child = Mock()
            child.type = "program"
            child.children = []
            current.children = [child]
            current = child

        extractors = {"method_declaration": Mock()}
        results = []
        extractor._traverse_and_extract_iterative(root, extractors, results, "method")
        assert results == []

    def test_field_batch_large(self, extractor):
        """Cover lines 413-415: field batch processing at size 10"""
        root = Mock()
        root.type = "program"

        field_nodes = []
        for _i in range(12):
            field = Mock()
            field.type = "field_declaration"
            field.children = []
            field_nodes.append(field)

        root.children = field_nodes

        def mock_extractor(node):
            return [Variable(
                name="field",
                start_line=1,
                end_line=1,
                raw_text="int field;",
                language="java",
            )]

        extractors = {"field_declaration": mock_extractor}
        results = []
        extractor._traverse_and_extract_iterative(root, extractors, results, "field")
        assert len(results) == 12

    @pytest.mark.asyncio
    async def test_analyze_file_no_language(self, plugin):
        """Cover lines 1131-1142: analyze_file when language is None"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write("public class Test {}")
            temp_path = f.name

        try:
            mock_request = Mock()
            mock_request.file_path = temp_path
            with patch.object(plugin, "get_tree_sitter_language", return_value=None):
                result = await plugin.analyze_file(temp_path, mock_request)
                assert result.success is False
                assert "Failed to load tree-sitter language" in result.error_message
        finally:
            os.unlink(temp_path)
