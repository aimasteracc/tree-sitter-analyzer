#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.languages.python_plugin module.

This module tests the PythonPlugin class which provides Python language
support in the new plugin architecture.
"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.python_plugin import (
    PythonElementExtractor,
    PythonPlugin,
)
from tree_sitter_analyzer.models import Class, Function, Import, Variable
from tree_sitter_analyzer.plugins import ElementExtractorBase
from tree_sitter_analyzer.plugins.base import ElementExtractor, LanguagePlugin


class TestPythonElementExtractor:
    """Test cases for PythonElementExtractor class"""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        """Create a PythonElementExtractor instance for testing"""
        return PythonElementExtractor()

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
    def sample_python_code(self) -> str:
        """Sample Python code for testing"""
        return '''
import os
import sys
from typing import List, Optional
from dataclasses import dataclass

@dataclass
class Person:
    """A person with name and age"""
    name: str
    age: int = 0

class Calculator:
    """Calculator class for basic arithmetic operations"""

    def __init__(self, initial_value: int = 0):
        """Initialize calculator with initial value"""
        self.value = initial_value
        self._history = []

    def add(self, number: int) -> int:
        """Add a number to the current value"""
        self.value += number
        self._history.append(f"add {number}")
        return self.value

    def subtract(self, number: int) -> int:
        """Subtract a number from the current value"""
        self.value -= number
        self._history.append(f"subtract {number}")
        return self.value

    @property
    def history(self) -> List[str]:
        """Get calculation history"""
        return self._history.copy()

    @staticmethod
    def validate_number(value) -> bool:
        """Validate if value is a number"""
        return isinstance(value, (int, float))

    @classmethod
    def from_string(cls, value_str: str) -> 'Calculator':
        """Create calculator from string value"""
        return cls(int(value_str))

def main():
    """Main function"""
    calc = Calculator(10)
    result = calc.add(5)
    print(f"Result: {result}")

if __name__ == "__main__":
    main()
'''

    def test_extractor_initialization(self, extractor: PythonElementExtractor) -> None:
        """Test PythonElementExtractor initialization"""
        assert extractor is not None
        assert isinstance(extractor, ElementExtractorBase)
        assert hasattr(extractor, "extract_functions")
        assert hasattr(extractor, "extract_classes")
        assert hasattr(extractor, "extract_variables")
        assert hasattr(extractor, "extract_imports")

    def test_extract_functions_success(
        self, extractor: PythonElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful function extraction"""
        # Mock the language query
        mock_query = Mock()
        mock_tree.language.query.return_value = mock_query
        mock_query.captures.return_value = {"function.definition": []}

        functions = extractor.extract_functions(mock_tree, "test code")

        assert isinstance(functions, list)

    def test_extract_functions_no_language(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test function extraction when language is not available"""
        mock_tree = Mock()
        mock_tree.language = None
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        functions = extractor.extract_functions(mock_tree, "test code")

        assert isinstance(functions, list)
        assert len(functions) == 0

    def test_extract_classes_success(
        self, extractor: PythonElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful class extraction"""
        # Mock the language query
        mock_query = Mock()
        mock_tree.language.query.return_value = mock_query
        mock_query.captures.return_value = {"class.definition": []}

        classes = extractor.extract_classes(mock_tree, "test code")

        assert isinstance(classes, list)

    def test_extract_variables_success(
        self, extractor: PythonElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful variable extraction"""
        # Mock the language query
        mock_query = Mock()
        mock_tree.language.query.return_value = mock_query
        mock_query.captures.return_value = {"variable.assignment": []}

        variables = extractor.extract_variables(mock_tree, "test code")

        assert isinstance(variables, list)

    def test_extract_imports_success(
        self, extractor: PythonElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful import extraction"""
        # Mock the language query
        mock_query = Mock()
        mock_tree.language.query.return_value = mock_query
        mock_query.captures.return_value = {"import.statement": []}

        imports = extractor.extract_imports(mock_tree, "test code")

        assert isinstance(imports, list)

    def test_extract_detailed_function_info(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test detailed function information extraction"""
        mock_node = Mock()
        mock_node.type = "function_definition"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (10, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 100
        mock_node.children = []

        with (
            patch.object(extractor, "_extract_name_from_node") as mock_extract_name,
            patch.object(
                extractor, "_extract_parameters_from_node"
            ) as mock_extract_params,
            patch.object(
                extractor, "_extract_decorators_from_node"
            ) as mock_extract_decorators,
            patch.object(
                extractor, "_extract_return_type_from_node"
            ) as mock_extract_return,
            patch.object(
                extractor, "_extract_docstring_from_node"
            ) as mock_extract_docstring,
            patch.object(extractor, "_extract_function_body") as mock_extract_body,
        ):
            mock_extract_name.return_value = "test_function"
            mock_extract_params.return_value = ["param1: int", "param2: str"]
            mock_extract_decorators.return_value = ["property"]
            mock_extract_return.return_value = "int"
            mock_extract_docstring.return_value = "Test function"
            mock_extract_body.return_value = "return value"

            result = extractor._extract_detailed_function_info(mock_node, "test code")

            assert result is not None
            assert isinstance(result, Function)
            assert result.name == "test_function"
            assert result.parameters == ["param1: int", "param2: str"]
            assert result.modifiers == ["property"]
            assert result.return_type == "int"

    def test_extract_detailed_class_info(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test detailed class information extraction"""
        mock_node = Mock()
        mock_node.type = "class_definition"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (10, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 100
        mock_node.children = []

        with (
            patch.object(extractor, "_extract_name_from_node") as mock_extract_name,
            patch.object(
                extractor, "_extract_superclasses_from_node"
            ) as mock_extract_super,
            patch.object(
                extractor, "_extract_decorators_from_node"
            ) as mock_extract_decorators,
            patch.object(
                extractor, "_extract_docstring_from_node"
            ) as mock_extract_docstring,
        ):
            mock_extract_name.return_value = "TestClass"
            mock_extract_super.return_value = ["BaseClass", "Mixin"]
            mock_extract_decorators.return_value = ["dataclass"]
            mock_extract_docstring.return_value = "Test class"

            result = extractor._extract_detailed_class_info(mock_node, "test code")

            assert result is not None
            assert isinstance(result, Class)
            assert result.name == "TestClass"
            assert result.superclass == "BaseClass"
            assert result.interfaces == ["Mixin"]
            assert result.modifiers == ["dataclass"]

    def test_extract_variable_info(self, extractor: PythonElementExtractor) -> None:
        """Test variable information extraction"""
        mock_node = Mock()
        mock_node.type = "assignment"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 20
        mock_node.children = []

        with patch.object(extractor, "_validate_node") as mock_validate:
            mock_validate.return_value = True

            result = extractor._extract_variable_info(
                mock_node, "test_var = 42", "assignment"
            )

            assert result is not None
            assert isinstance(result, Variable)
            assert result.name == "test_var"

    def test_extract_import_info(self, extractor: PythonElementExtractor) -> None:
        """Test import information extraction"""
        mock_node = Mock()
        mock_node.type = "import_statement"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 9
        mock_node.children = []

        with patch.object(extractor, "_validate_node") as mock_validate:
            mock_validate.return_value = True

            result = extractor._extract_import_info(mock_node, "import os", "import")

            assert result is not None
            assert isinstance(result, Import)
            assert "os" in result.name

    def test_extract_name_from_node(self, extractor: PythonElementExtractor) -> None:
        """Test name extraction from node"""
        mock_node = Mock()
        mock_identifier = Mock()
        mock_identifier.type = "identifier"
        mock_identifier.start_byte = 0
        mock_identifier.end_byte = 9
        mock_node.children = [mock_identifier]

        name = extractor._extract_name_from_node(mock_node, "test_name")

        assert name == "test_name"

    def test_extract_name_from_node_no_identifier(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test name extraction when no identifier is found"""
        mock_node = Mock()
        mock_node.children = []

        name = extractor._extract_name_from_node(mock_node, "test code")

        assert name is None

    def test_extract_parameters_from_node(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test parameter extraction from function node"""
        mock_node = Mock()
        mock_params_node = Mock()
        mock_param1 = Mock()
        mock_param1.type = "identifier"
        mock_param1.start_byte = 0
        mock_param1.end_byte = 10
        mock_param2 = Mock()
        mock_param2.type = "typed_parameter"
        mock_param2.start_byte = 12
        mock_param2.end_byte = 22
        mock_params_node.children = [mock_param1, mock_param2]
        mock_params_node.type = "parameters"
        mock_node.children = [mock_params_node]

        parameters = extractor._extract_parameters_from_node(
            mock_node, "param1: int, param2: str"
        )

        assert isinstance(parameters, list)
        assert len(parameters) == 2

    def test_extract_decorators_from_node(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test decorator extraction from node"""
        mock_node = Mock()
        mock_node.parent = None

        decorators = extractor._extract_decorators_from_node(mock_node, "test code")

        assert isinstance(decorators, list)

    def test_extract_return_type_from_node(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test return type extraction from function node"""
        mock_node = Mock()
        mock_type_node = Mock()
        mock_type_node.type = "type"
        mock_type_node.start_byte = 0
        mock_type_node.end_byte = 3
        mock_node.children = [mock_type_node]

        return_type = extractor._extract_return_type_from_node(mock_node, "int")

        assert return_type == "int"

    def test_extract_docstring_from_node(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test docstring extraction from node"""
        mock_node = Mock()
        mock_block = Mock()
        mock_block.type = "block"
        mock_stmt = Mock()
        mock_stmt.type = "expression_statement"
        mock_expr = Mock()
        mock_expr.type = "string"
        mock_expr.start_byte = 0
        mock_expr.end_byte = 25
        mock_stmt.children = [mock_expr]
        mock_block.children = [mock_stmt]
        mock_node.children = [mock_block]

        with patch.object(extractor, "_validate_node") as mock_validate:
            mock_validate.return_value = True

            docstring = extractor._extract_docstring_from_node(
                mock_node, '"""This is a docstring"""'
            )

            assert docstring == "This is a docstring"

    def test_calculate_complexity(self, extractor: PythonElementExtractor) -> None:
        """Test complexity calculation"""
        simple_body = "return value"
        complex_body = """
if condition:
    for item in items:
        while running:
            try:
                process(item)
            except Exception:
                handle_error()
            finally:
                cleanup()
"""

        simple_complexity = extractor._calculate_complexity(simple_body)
        complex_complexity = extractor._calculate_complexity(complex_body)

        assert isinstance(simple_complexity, int)
        assert isinstance(complex_complexity, int)
        assert complex_complexity > simple_complexity


class TestPythonPlugin:
    """Test cases for PythonPlugin class"""

    @pytest.fixture
    def plugin(self) -> PythonPlugin:
        """Create a PythonPlugin instance for testing"""
        return PythonPlugin()

    def test_plugin_initialization(self, plugin: PythonPlugin) -> None:
        """Test PythonPlugin initialization"""
        assert plugin is not None
        assert isinstance(plugin, LanguagePlugin)
        assert hasattr(plugin, "get_language_name")
        assert hasattr(plugin, "get_file_extensions")
        assert hasattr(plugin, "create_extractor")

    def test_get_language_name(self, plugin: PythonPlugin) -> None:
        """Test getting language name"""
        language_name = plugin.get_language_name()

        assert language_name == "python"

    def test_get_file_extensions(self, plugin: PythonPlugin) -> None:
        """Test getting file extensions"""
        extensions = plugin.get_file_extensions()

        assert isinstance(extensions, list)
        assert ".py" in extensions
        assert ".pyi" in extensions

    def test_create_extractor(self, plugin: PythonPlugin) -> None:
        """Test creating element extractor"""
        extractor = plugin.create_extractor()

        assert isinstance(extractor, PythonElementExtractor)
        assert isinstance(extractor, ElementExtractorBase)

    def test_is_applicable_python_file(self, plugin: PythonPlugin) -> None:
        """Test applicability check for Python file"""
        assert plugin.is_applicable("test.py") is True
        assert plugin.is_applicable("test.pyi") is True
        assert plugin.is_applicable("test.pyw") is True

    def test_is_applicable_non_python_file(self, plugin: PythonPlugin) -> None:
        """Test applicability check for non-Python file"""
        assert plugin.is_applicable("test.java") is False
        assert plugin.is_applicable("test.js") is False

    def test_get_plugin_info(self, plugin: PythonPlugin) -> None:
        """Test getting plugin information"""
        info = plugin.get_plugin_info()

        assert isinstance(info, dict)
        assert "language" in info
        assert "extensions" in info
        assert info["language"] == "python"

    def test_get_tree_sitter_language(self, plugin: PythonPlugin) -> None:
        """Test getting tree-sitter language"""
        with (
            patch("tree_sitter_python.language") as mock_language,
            patch("tree_sitter.Language") as mock_tree_sitter_language,
        ):
            mock_capsule = Mock()
            mock_language.return_value = mock_capsule

            mock_lang_obj = Mock()
            mock_tree_sitter_language.return_value = mock_lang_obj

            language = plugin.get_tree_sitter_language()

            assert language is mock_lang_obj
            mock_tree_sitter_language.assert_called_once_with(mock_capsule)

    def test_get_tree_sitter_language_caching(self, plugin: PythonPlugin) -> None:
        """Test tree-sitter language caching"""
        with (
            patch("tree_sitter_python.language") as mock_language,
            patch("tree_sitter.Language") as mock_tree_sitter_language,
        ):
            mock_capsule = Mock()
            mock_language.return_value = mock_capsule

            mock_lang_obj = Mock()
            mock_tree_sitter_language.return_value = mock_lang_obj

            # First call
            language1 = plugin.get_tree_sitter_language()

            # Second call (should use cache)
            language2 = plugin.get_tree_sitter_language()

            assert language1 is language2
            # Should only be called once due to caching
            mock_language.assert_called_once()

    def test_execute_query(self, plugin: PythonPlugin) -> None:
        """Test query execution"""
        mock_tree = Mock()

        with patch.object(plugin, "get_tree_sitter_language") as mock_get_language:
            # Mock will cause Query() to fail, so we expect an error
            mock_get_language.return_value = Mock()

            result = plugin.execute_query(mock_tree, "function")

            assert isinstance(result, dict)
            # When using Mock as Language, Query() will fail and return error
            # The result should contain either 'error' or 'captures' key
            assert "error" in result or "captures" in result

    @pytest.mark.asyncio
    async def test_analyze_file_success(self, plugin: PythonPlugin) -> None:
        """Test successful file analysis"""
        python_code = """
class TestClass:
    def test_method(self):
        print("Hello")
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(python_code)
            temp_path = f.name

        try:
            # Mock AnalysisRequest
            mock_request = Mock()
            mock_request.file_path = temp_path
            mock_request.language = "python"
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
    async def test_analyze_file_nonexistent(self, plugin: PythonPlugin) -> None:
        """Test analysis of non-existent file"""
        mock_request = Mock()
        mock_request.file_path = "/nonexistent/file.py"
        mock_request.language = "python"

        result = await plugin.analyze_file("/nonexistent/file.py", mock_request)

        # Should return an AnalysisResult with success=False instead of raising
        assert result is not None
        assert hasattr(result, "success")
        assert result.success is False


class TestPythonPluginErrorHandling:
    """Test error handling in PythonPlugin"""

    @pytest.fixture
    def plugin(self) -> PythonPlugin:
        """Create a PythonPlugin instance for testing"""
        return PythonPlugin()

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        """Create a PythonElementExtractor instance for testing"""
        return PythonElementExtractor()

    def test_extract_functions_with_exception(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test function extraction with exception"""
        mock_tree = Mock()
        mock_tree.language = None  # This will cause the extraction to fail gracefully
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        functions = extractor.extract_functions(mock_tree, "test code")

        # Should handle gracefully
        assert isinstance(functions, list)
        assert len(functions) == 0

    def test_extract_classes_with_exception(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test class extraction with exception"""
        mock_tree = Mock()
        mock_tree.language = None  # This will cause the extraction to fail gracefully
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        classes = extractor.extract_classes(mock_tree, "test code")

        # Should handle gracefully
        assert isinstance(classes, list)
        assert len(classes) == 0

    def test_extract_detailed_function_info_with_exception(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test detailed function info extraction with exception"""
        mock_node = Mock()

        with patch.object(extractor, "_extract_name_from_node") as mock_extract_name:
            mock_extract_name.side_effect = Exception("Extraction error")

            result = extractor._extract_detailed_function_info(mock_node, "test code")

            # Should handle gracefully
            assert result is None

    def test_get_tree_sitter_language_failure(self, plugin: PythonPlugin) -> None:
        """Test tree-sitter language loading failure"""
        with patch("tree_sitter_python.language") as mock_language:
            mock_language.side_effect = ImportError("Module not found")

            language = plugin.get_tree_sitter_language()

            assert language is None

    def test_execute_query_with_exception(self, plugin: PythonPlugin) -> None:
        """Test query execution with exception"""
        mock_tree = Mock()

        with patch.object(plugin, "get_tree_sitter_language") as mock_get_language:
            mock_get_language.return_value = None

            result = plugin.execute_query(mock_tree, "function")

            assert isinstance(result, dict)
            assert "error" in result

    @pytest.mark.asyncio
    async def test_analyze_file_with_exception(self, plugin: PythonPlugin) -> None:
        """Test file analysis with exception"""
        python_code = "class Test: pass"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(python_code)
            temp_path = f.name

        try:
            mock_request = Mock()
            mock_request.file_path = temp_path
            mock_request.language = "python"

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


class TestPythonPluginIntegration:
    """Integration tests for PythonPlugin"""

    @pytest.fixture
    def plugin(self) -> PythonPlugin:
        """Create a PythonPlugin instance for testing"""
        return PythonPlugin()

    def test_full_extraction_workflow(self, plugin: PythonPlugin) -> None:
        """Test complete extraction workflow"""
        # Test that plugin can handle complex Python code

        # Test that plugin can handle complex Python code
        extractor = plugin.create_extractor()
        assert isinstance(extractor, PythonElementExtractor)

        # Test applicability
        assert plugin.is_applicable("calculator.py") is True
        assert plugin.is_applicable("calculator.java") is False

        # Test plugin info
        info = plugin.get_plugin_info()
        assert info["language"] == "python"
        assert ".py" in info["extensions"]

    def test_plugin_consistency(self, plugin: PythonPlugin) -> None:
        """Test plugin consistency across multiple calls"""
        # Multiple calls should return consistent results
        for _ in range(5):
            assert plugin.get_language_name() == "python"
            assert ".py" in plugin.get_file_extensions()
            assert isinstance(plugin.create_extractor(), PythonElementExtractor)

    def test_extractor_consistency(self, plugin: PythonPlugin) -> None:
        """Test extractor consistency"""
        # Multiple extractors should be independent
        extractor1 = plugin.create_extractor()
        extractor2 = plugin.create_extractor()

        assert extractor1 is not extractor2
        assert isinstance(extractor1, PythonElementExtractor)
        assert isinstance(extractor2, PythonElementExtractor)

    def test_plugin_with_various_python_files(self, plugin: PythonPlugin) -> None:
        """Test plugin with various Python file types"""
        python_files = [
            "test.py",
            "test.pyi",
            "test.pyw",
            "src/test.py",
            "package/__init__.py",
            "TEST.PY",  # Case variations
            "test.Py",
        ]

        for python_file in python_files:
            assert plugin.is_applicable(python_file) is True

        non_python_files = [
            "test.java",
            "test.js",
            "test.cpp",
            "test.txt",
            "python.txt",  # Contains 'python' but wrong extension
        ]

        for non_python_file in non_python_files:
            assert plugin.is_applicable(non_python_file) is False

    def test_python_specific_features(self, plugin: PythonPlugin) -> None:
        """Test Python-specific features"""
        extractor = plugin.create_extractor()

        # Test that extractor has Python-specific methods
        assert hasattr(extractor, "_extract_decorators_from_node")
        assert hasattr(extractor, "_extract_docstring_from_node")
        assert hasattr(extractor, "_extract_return_type_from_node")

        # Test complexity calculation with Python-specific constructs
        python_complex_code = """
async def async_function():
    async with context_manager():
        async for item in async_iterator():
            if condition:
                try:
                    await process(item)
                except Exception as e:
                    logger.error(f"Error: {e}")
                finally:
                    cleanup()
"""

        complexity = extractor._calculate_complexity(python_complex_code)
        assert isinstance(complexity, int)
        assert complexity > 1  # Should detect complexity

    def test_python_import_variations(self, plugin: PythonPlugin) -> None:
        """Test Python import statement variations"""
        extractor = plugin.create_extractor()

        # Test different import patterns
        # Test different import patterns (simplified for testing)

        # Each pattern should be recognizable by the extractor
        # (This would require actual tree parsing in a real test)
        assert extractor is not None


class TestPythonExtractorOptimizedMethods:
    """Tests for optimized extraction methods on PythonElementExtractor.

    These tests cover _extract_function_optimized, _extract_class_optimized,
    _extract_docstring_for_line, _reset_caches, _detect_file_characteristics,
    _traverse_and_extract_iterative, and edge cases for None/empty inputs.
    """

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        """Create a PythonElementExtractor instance for testing"""
        return PythonElementExtractor()

    def test_reset_caches(self, extractor: PythonElementExtractor) -> None:
        """Test that _reset_caches clears all internal caches"""
        extractor._node_text_cache[1] = "test"
        extractor._processed_nodes.add(1)
        extractor._element_cache[(1, "test")] = "value"
        extractor._docstring_cache[1] = "doc"
        extractor._complexity_cache[1] = 5

        extractor._reset_caches()

        assert len(extractor._node_text_cache) == 0
        assert len(extractor._processed_nodes) == 0
        assert len(extractor._element_cache) == 0
        assert len(extractor._docstring_cache) == 0
        assert len(extractor._complexity_cache) == 0

    def test_detect_file_characteristics_frameworks(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test framework detection for Django, Flask, and FastAPI"""
        # Django detection
        extractor.source_code = (
            "from django.db import models\nclass MyModel(models.Model): pass"
        )
        extractor._detect_file_characteristics()
        assert extractor.framework_type == "django"

        # Flask detection
        extractor.source_code = "from flask import Flask\napp = Flask(__name__)"
        extractor._detect_file_characteristics()
        assert extractor.framework_type == "flask"

        # FastAPI detection
        extractor.source_code = "from fastapi import FastAPI\napp = FastAPI()"
        extractor._detect_file_characteristics()
        assert extractor.framework_type == "fastapi"

    def test_detect_file_characteristics_empty_source(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test file characteristics detection with empty source"""
        extractor.source_code = ""
        extractor._detect_file_characteristics()
        assert extractor.is_module is False
        assert extractor.framework_type == ""

    def test_extract_docstring_for_line_single_line(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test single-line docstring extraction via _extract_docstring_for_line"""
        extractor.content_lines = [
            "def test_function():",
            '    """This is a single line docstring"""',
            "    pass",
        ]
        result = extractor._extract_docstring_for_line(1)
        assert result == "This is a single line docstring"

    def test_extract_docstring_for_line_multi_line(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test multi-line docstring extraction via _extract_docstring_for_line"""
        extractor.content_lines = [
            "def test_function():",
            '    """',
            "    This is a multi-line",
            "    docstring with details",
            '    """',
            "    pass",
        ]
        result = extractor._extract_docstring_for_line(1)
        expected = "\n    This is a multi-line\n    docstring with details\n    "
        assert result == expected

    def test_extract_docstring_for_line_malformed(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test docstring extraction with unclosed triple quotes"""
        extractor.content_lines = [
            "def test_function():",
            '    """Unclosed docstring',
            "    pass",
        ]
        result = extractor._extract_docstring_for_line(1)
        assert result is None

    def test_extract_function_optimized_complete(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _extract_function_optimized with full mock setup"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 0)

        extractor.content_lines = [
            "def test_function(param1: str, param2: int = 0) -> str:",
            '    """Test function docstring"""',
            "    return param1 * param2",
            "",
            "",
        ]
        extractor.current_module = "test_module"
        extractor.framework_type = "django"

        with (
            patch.object(
                extractor, "_parse_function_signature_optimized"
            ) as mock_parse,
            patch.object(
                extractor, "_extract_docstring_for_line"
            ) as mock_docstring,
            patch.object(
                extractor, "_calculate_complexity_optimized"
            ) as mock_complexity,
        ):
            mock_parse.return_value = (
                "test_function",
                ["param1: str", "param2: int = 0"],
                False,
                ["property"],
                "str",
            )
            mock_docstring.return_value = "Test function docstring"
            mock_complexity.return_value = 3

            result = extractor._extract_function_optimized(mock_node)

            assert isinstance(result, Function)
            assert result.name == "test_function"
            assert result.parameters == ["param1: str", "param2: int = 0"]
            assert result.return_type == "str"
            assert result.docstring == "Test function docstring"
            assert result.complexity_score == 3
            assert result.is_property is True

    def test_extract_function_optimized_signature_failure(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _extract_function_optimized when signature parsing fails"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        extractor.content_lines = ["def test():", "    pass"]

        with patch.object(
            extractor, "_parse_function_signature_optimized"
        ) as mock_parse:
            mock_parse.return_value = None
            result = extractor._extract_function_optimized(mock_node)
            assert result is None

    def test_extract_class_optimized_exception_class(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _extract_class_optimized detects exception superclass"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (3, 0)
        mock_node.parent = None

        mock_identifier = Mock()
        mock_identifier.type = "identifier"
        mock_identifier.text = b"CustomError"

        mock_arg_list = Mock()
        mock_arg_list.type = "argument_list"
        mock_superclass = Mock()
        mock_superclass.type = "identifier"
        mock_superclass.text = b"Exception"
        mock_arg_list.children = [mock_superclass]

        mock_node.children = [mock_identifier, mock_arg_list]

        extractor.content_lines = ["class CustomError(Exception):", "    pass"]

        with (
            patch.object(extractor, "_get_node_text_optimized") as mock_get_text,
            patch.object(
                extractor, "_extract_docstring_for_line"
            ) as mock_docstring,
        ):
            mock_get_text.side_effect = [
                "class CustomError(Exception):\n    pass",
                "Exception",
            ]
            mock_docstring.return_value = None

            result = extractor._extract_class_optimized(mock_node)

            assert isinstance(result, Class)
            assert result.name == "CustomError"
            assert result.superclass == "Exception"
            assert result.is_exception is True

    def test_extract_class_optimized_no_name(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _extract_class_optimized when no identifier child exists"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        mock_node.parent = None
        mock_node.children = []

        result = extractor._extract_class_optimized(mock_node)
        assert result is None

    def test_traverse_and_extract_iterative(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _traverse_and_extract_iterative with function and class nodes"""
        mock_root = Mock()
        mock_child1 = Mock()
        mock_child1.type = "function_definition"
        mock_child1.children = []
        mock_child2 = Mock()
        mock_child2.type = "class_definition"
        mock_child2.children = []
        mock_root.children = [mock_child1, mock_child2]

        mock_func_extractor = Mock(
            return_value=Function(
                name="test_func",
                start_line=1,
                end_line=3,
                raw_text="def test_func(): pass",
                language="python",
            )
        )
        mock_class_extractor = Mock(
            return_value=Class(
                name="TestClass",
                start_line=5,
                end_line=10,
                raw_text="class TestClass: pass",
                language="python",
            )
        )

        extractors = {
            "function_definition": mock_func_extractor,
            "class_definition": mock_class_extractor,
        }
        results: list = []

        extractor._traverse_and_extract_iterative(
            mock_root, extractors, results, "mixed"
        )

        assert len(results) == 2
        assert isinstance(results[0], Function)
        assert isinstance(results[1], Class)

    def test_traverse_and_extract_iterative_with_none_root(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _traverse_and_extract_iterative with None root node"""
        extractors = {"function_definition": Mock()}
        results: list = []

        extractor._traverse_and_extract_iterative(
            None, extractors, results, "function"
        )

        assert len(results) == 0

    def test_extract_functions_with_none_tree(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test function extraction with None tree input"""
        result = extractor.extract_functions(None, "def test(): pass")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_extract_functions_with_none_source(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test function extraction with None source code"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        result = extractor.extract_functions(mock_tree, None)
        assert isinstance(result, list)
        assert extractor.source_code == ""
        assert extractor.content_lines == [""]

    def test_extract_variables_with_query_exception(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test variable extraction when tree-sitter query raises exception"""
        mock_tree = Mock()
        mock_tree.language = Mock()
        mock_tree.language.query.side_effect = Exception("Query error")

        result = extractor.extract_variables(mock_tree, "x = 1")
        assert isinstance(result, list)
        assert len(result) == 0


# ============================================================================
# Targeted coverage tests for uncovered code paths
# ============================================================================


class TestExtractFunctionsErrorPaths:
    """Tests covering error/exception paths in extract_functions and extract_classes."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        return PythonElementExtractor()

    def test_extract_functions_traversal_exception(self, extractor):
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        with patch.object(extractor, "_traverse_and_extract_iterative", side_effect=RuntimeError("boom")):
            result = extractor.extract_functions(mock_tree, "def foo(): pass")
            assert result == []

    def test_extract_classes_traversal_exception(self, extractor):
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        with patch.object(extractor, "_traverse_and_extract_iterative", side_effect=RuntimeError("boom")):
            result = extractor.extract_classes(mock_tree, "class Foo: pass")
            assert result == []


class TestTraverseEdgeCases:
    """Tests for _traverse_and_extract_iterative edge cases."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        return PythonElementExtractor()

    def test_max_depth_exceeded(self, extractor):
        current = Mock()
        current.type = "module"
        current.children = []
        for _ in range(55):
            parent = Mock()
            parent.type = "block"
            parent.children = [current]
            current = parent
        results = []
        extractor._traverse_and_extract_iterative(current, {"function_definition": Mock()}, results, "function")
        assert isinstance(results, list)

    def test_cache_hit_returns_cached(self, extractor):
        mock_child = Mock()
        mock_child.type = "function_definition"
        mock_child.children = []
        cached_func = Function(name="cached", start_line=1, end_line=3, raw_text="def cached(): pass", language="python")
        extractor._element_cache[(id(mock_child), "function")] = cached_func
        mock_root = Mock()
        mock_root.type = "module"
        mock_root.children = [mock_child]
        results = []
        extractor._traverse_and_extract_iterative(mock_root, {"function_definition": Mock()}, results, "function")
        assert len(results) == 1
        assert results[0].name == "cached"

    def test_cache_hit_with_list(self, extractor):
        mock_child = Mock()
        mock_child.type = "function_definition"
        mock_child.children = []
        cached_list = [
            Function(name="f1", start_line=1, end_line=2, raw_text="x", language="python"),
            Function(name="f2", start_line=3, end_line=4, raw_text="y", language="python"),
        ]
        extractor._element_cache[(id(mock_child), "function")] = cached_list
        mock_root = Mock()
        mock_root.type = "module"
        mock_root.children = [mock_child]
        results = []
        extractor._traverse_and_extract_iterative(mock_root, {"function_definition": Mock()}, results, "function")
        assert len(results) == 2

    def test_already_processed_skipped(self, extractor):
        mock_child = Mock()
        mock_child.type = "function_definition"
        mock_child.children = []
        extractor._processed_nodes.add(id(mock_child))
        mock_root = Mock()
        mock_root.type = "module"
        mock_root.children = [mock_child]
        mock_fn = Mock()
        results = []
        extractor._traverse_and_extract_iterative(mock_root, {"function_definition": mock_fn}, results, "function")
        mock_fn.assert_not_called()

    def test_extractor_exception_marks_processed(self, extractor):
        mock_child = Mock()
        mock_child.type = "function_definition"
        mock_child.children = []
        mock_root = Mock()
        mock_root.type = "module"
        mock_root.children = [mock_child]
        results = []
        extractor._traverse_and_extract_iterative(mock_root, {"function_definition": Mock(side_effect=Exception("err"))}, results, "function")
        assert id(mock_child) in extractor._processed_nodes


class TestGetNodeTextOptimizedPaths:
    """Tests for _get_node_text_optimized fallback paths."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        ext = PythonElementExtractor()
        ext.source_code = "def foo():\n    pass\n    return 42"
        ext.content_lines = ext.source_code.split("\n")
        return ext

    def test_cache_hit(self, extractor):
        extractor._node_text_cache[(0, 10)] = "cached_text"
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        assert extractor._get_node_text_optimized(mock_node) == "cached_text"

    def test_fallback_single_line(self, extractor):
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        mock_node.start_point = (0, 4)
        mock_node.end_point = (0, 10)
        with patch("tree_sitter_analyzer.languages.python_plugin.extract_text_slice", return_value=""):
            result = extractor._get_node_text_optimized(mock_node)
            assert "foo():" in result

    def test_fallback_out_of_bounds(self, extractor):
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        mock_node.start_point = (100, 0)
        mock_node.end_point = (101, 0)
        with patch("tree_sitter_analyzer.languages.python_plugin.extract_text_slice", return_value=""):
            result = extractor._get_node_text_optimized(mock_node)
            assert result == ""


class TestExtractFunctionOptimizedVisibility:
    """Tests for visibility detection in _extract_function_optimized."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        ext = PythonElementExtractor()
        ext.content_lines = ["def _private_func():", "    pass"]
        ext.framework_type = ""
        return ext

    def test_private_visibility(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        with (
            patch.object(extractor, "_parse_function_signature_optimized", return_value=("_private_func", [], False, [], None)),
            patch.object(extractor, "_extract_docstring_for_line", return_value=None),
            patch.object(extractor, "_calculate_complexity_optimized", return_value=1),
        ):
            result = extractor._extract_function_optimized(mock_node)
            assert result is not None
            assert result.is_private is True

    def test_magic_method(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        with (
            patch.object(extractor, "_parse_function_signature_optimized", return_value=("__init__", ["self"], False, [], None)),
            patch.object(extractor, "_extract_docstring_for_line", return_value=None),
            patch.object(extractor, "_calculate_complexity_optimized", return_value=1),
        ):
            result = extractor._extract_function_optimized(mock_node)
            assert result is not None
            assert result.is_private is False
            assert result.is_public is False

    def test_static_and_classmethod(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        with (
            patch.object(extractor, "_parse_function_signature_optimized", return_value=("func", [], False, ["staticmethod"], None)),
            patch.object(extractor, "_extract_docstring_for_line", return_value=None),
            patch.object(extractor, "_calculate_complexity_optimized", return_value=1),
        ):
            result = extractor._extract_function_optimized(mock_node)
            assert result is not None
            assert result.is_static is True

    def test_exception_returns_none(self, extractor):
        bad_node = Mock()
        type(bad_node).start_point = property(lambda self: (_ for _ in ()).throw(Exception("bad")))
        result = extractor._extract_function_optimized(bad_node)
        assert result is None


class TestParseFunctionSignatureOptimizedPaths:
    """Tests for _parse_function_signature_optimized."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        ext = PythonElementExtractor()
        ext.source_code = ""
        ext.content_lines = []
        return ext

    def test_async_detection(self, extractor):
        mock_node = Mock()
        mock_node.parent = None
        mock_id = Mock(type="identifier", text=b"async_handler")
        mock_params = Mock(type="parameters", children=[])
        mock_node.children = [mock_id, mock_params]
        with patch.object(extractor, "_get_node_text_optimized", return_value="async def async_handler():"), \
             patch.object(extractor, "_extract_parameters_from_node_optimized", return_value=[]):
            result = extractor._parse_function_signature_optimized(mock_node)
            assert result is not None
            assert result[2] is True  # is_async

    def test_decorators_from_parent(self, extractor):
        mock_node = Mock()
        mock_parent = Mock(type="decorated_definition")
        mock_decorator = Mock(type="decorator")
        mock_node.parent = mock_parent
        mock_parent.children = [mock_decorator, mock_node]
        mock_id = Mock(type="identifier", text=b"my_func")
        mock_params = Mock(type="parameters", children=[])
        mock_node.children = [mock_id, mock_params]
        with patch.object(extractor, "_get_node_text_optimized", side_effect=lambda n: "@property" if n == mock_decorator else "def my_func():"), \
             patch.object(extractor, "_extract_parameters_from_node_optimized", return_value=[]):
            result = extractor._parse_function_signature_optimized(mock_node)
            assert result is not None
            assert "property" in result[3]  # decorators

    def test_exception_returns_none(self, extractor):
        mock_node = Mock()
        with patch.object(extractor, "_get_node_text_optimized", side_effect=Exception("boom")):
            result = extractor._parse_function_signature_optimized(mock_node)
            assert result is None


class TestExtractParameterTypes:
    """Tests for _extract_parameters_from_node_optimized."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        ext = PythonElementExtractor()
        ext.source_code = "def func(self, x: int, y=5, *args, **kwargs): pass"
        ext.content_lines = ext.source_code.split("\n")
        return ext

    def test_all_param_types(self, extractor):
        mock_params = Mock()
        mock_id = Mock(type="identifier")
        mock_typed = Mock(type="typed_parameter")
        mock_default = Mock(type="default_parameter")
        mock_splat = Mock(type="list_splat_pattern")
        mock_dict_splat = Mock(type="dictionary_splat_pattern")
        mock_params.children = [mock_id, mock_typed, mock_default, mock_splat, mock_dict_splat]
        values = ["self", "x: int", "y=5", "*args", "**kwargs"]
        call_count = [0]
        def side_effect(node):
            idx = call_count[0]
            call_count[0] += 1
            return values[idx] if idx < len(values) else ""
        with patch.object(extractor, "_get_node_text_optimized", side_effect=side_effect):
            result = extractor._extract_parameters_from_node_optimized(mock_params)
            assert len(result) == 5


class TestDocstringEdgeCases:
    """Tests for _extract_docstring_for_line edge cases."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        return PythonElementExtractor()

    def test_cache_hit(self, extractor):
        extractor._docstring_cache[5] = "cached"
        assert extractor._extract_docstring_for_line(5) == "cached"

    def test_not_found(self, extractor):
        extractor.content_lines = ["def func():", "    x = 1", "    y = 2", "    z = 3", "    w = 4", "    return x"]
        result = extractor._extract_docstring_for_line(1)
        assert result is None

    def test_exception(self, extractor):
        extractor.content_lines = None
        result = extractor._extract_docstring_for_line(0)
        assert result is None

    def test_out_of_bounds(self, extractor):
        extractor.content_lines = ["line 0"]
        result = extractor._extract_docstring_for_line(100)
        assert result is None


class TestComplexityOptimizedEdgeCases:
    """Tests for _calculate_complexity_optimized edge cases."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        ext = PythonElementExtractor()
        ext.source_code = "def func(): pass"
        ext.content_lines = ["def func(): pass"]
        return ext

    def test_cache_hit(self, extractor):
        mock_node = Mock()
        extractor._complexity_cache[id(mock_node)] = 7
        assert extractor._calculate_complexity_optimized(mock_node) == 7

    def test_exception(self, extractor):
        mock_node = Mock()
        with patch.object(extractor, "_get_node_text_optimized", side_effect=Exception("err")):
            assert extractor._calculate_complexity_optimized(mock_node) == 1


class TestExtractClassOptimizedPaths:
    """Tests for _extract_class_optimized edge cases."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        ext = PythonElementExtractor()
        ext.content_lines = ["class Foo:", "    pass"]
        ext.current_module = ""
        ext.framework_type = ""
        return ext

    def test_class_with_module_fqn(self, extractor):
        extractor.current_module = "my.package"
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        mock_node.parent = None
        mock_id = Mock(type="identifier", text=b"MyClass")
        mock_node.children = [mock_id]
        with patch.object(extractor, "_get_node_text_optimized", return_value="class MyClass:\n    pass"), \
             patch.object(extractor, "_extract_docstring_for_line", return_value=None):
            result = extractor._extract_class_optimized(mock_node)
            assert result is not None
            assert result.full_qualified_name == "my.package.MyClass"

    def test_class_with_multiple_superclasses(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        mock_node.parent = None
        mock_id = Mock(type="identifier", text=b"MyClass")
        mock_arg = Mock(type="argument_list")
        mock_s1 = Mock(type="identifier", text=b"Base")
        mock_s2 = Mock(type="identifier", text=b"MixinA")
        mock_arg.children = [mock_s1, mock_s2]
        mock_node.children = [mock_id, mock_arg]
        with patch.object(extractor, "_get_node_text_optimized", return_value="class MyClass(Base, MixinA):\n    pass"), \
             patch.object(extractor, "_extract_docstring_for_line", return_value=None):
            result = extractor._extract_class_optimized(mock_node)
            assert result is not None
            assert result.superclass == "Base"
            assert result.interfaces == ["MixinA"]

    def test_exception_returns_none(self, extractor):
        mock_node = Mock()
        type(mock_node).start_point = property(lambda self: (_ for _ in ()).throw(Exception("bad")))
        result = extractor._extract_class_optimized(mock_node)
        assert result is None


class TestIsFrameworkClassPaths:
    """Tests for _is_framework_class."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        return PythonElementExtractor()

    def test_django_model(self, extractor):
        extractor.framework_type = "django"
        with patch.object(extractor, "_get_node_text_optimized", return_value="class MyModel(Model):\n    pass"):
            assert extractor._is_framework_class(Mock(), "MyModel") is True

    def test_flask_framework(self, extractor):
        extractor.framework_type = "flask"
        extractor.source_code = "from flask import Flask"
        assert extractor._is_framework_class(Mock(), "MyApp") is True

    def test_no_framework(self, extractor):
        extractor.framework_type = ""
        assert extractor._is_framework_class(Mock(), "MyClass") is False


class TestExtractClassAttributes:
    """Tests for _extract_class_attributes."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        return PythonElementExtractor()

    def test_expression_statement_assignment(self, extractor):
        mock_assignment = Mock(type="assignment", start_byte=16, end_byte=22, start_point=(1, 4), end_point=(1, 10))
        mock_expr = Mock(type="expression_statement", children=[mock_assignment])
        mock_body = Mock(children=[mock_expr])
        result = extractor._extract_class_attributes(mock_body, "class Foo:\n    x = 10")
        assert len(result) == 1

    def test_exception_returns_empty(self, extractor):
        mock_body = Mock()
        type(mock_body).children = property(lambda self: (_ for _ in ()).throw(Exception("bad")))
        result = extractor._extract_class_attributes(mock_body, "x = 1")
        assert isinstance(result, list)


class TestExtractImportsPaths:
    """Tests for extract_imports paths."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        return PythonElementExtractor()

    def test_query_exception_fallback(self, extractor):
        mock_tree = Mock()
        mock_tree.language = Mock()
        mock_tree.root_node = Mock(children=[], type="module")
        with patch("tree_sitter_analyzer.languages.python_plugin.TreeSitterQueryCompat.safe_execute_query", side_effect=Exception("fail")):
            result = extractor.extract_imports(mock_tree, "import os")
            assert isinstance(result, list)

    def test_no_language(self, extractor):
        mock_tree = Mock()
        mock_tree.language = None
        mock_tree.root_node = Mock()
        result = extractor.extract_imports(mock_tree, "import os")
        assert isinstance(result, list)
        assert len(result) == 0


class TestPythonPluginMethods:
    """Tests for PythonPlugin methods."""

    @pytest.fixture
    def plugin(self) -> PythonPlugin:
        return PythonPlugin()

    def test_get_element_categories(self, plugin):
        categories = plugin.get_element_categories()
        assert isinstance(categories, dict)
        assert "function" in categories
        assert "class" in categories

    def test_extract_elements_delegates(self, plugin):
        mock_tree = Mock()
        mock_tree.root_node = Mock(children=[])
        mock_tree.language = None
        result = plugin.extract_elements(mock_tree, "def foo(): pass")
        assert isinstance(result, list)

    def test_extract_elements_exception(self, plugin):
        mock_tree = Mock()
        with patch.object(plugin, "get_extractor") as mock_get:
            mock_extractor = Mock()
            mock_extractor.extract_functions.side_effect = Exception("boom")
            mock_get.return_value = mock_extractor
            result = plugin.extract_elements(mock_tree, "def foo(): pass")
            assert isinstance(result, list)


# =============================================================================
# NEW TARGETED TESTS for uncovered lines (batch 2)
# Covering: _extract_function_optimized branches, _extract_class_optimized
# decorator paths, _parse_function_signature_optimized return_type branches,
# extract_imports manual fallback, _extract_class_attributes direct assignment,
# _extract_class_attribute_info typed/untyped, _is_framework_class fastapi,
# _extract_variable_info branches, _extract_import_info aliased_import,
# _extract_docstring_from_node single-quote, _extract_return_type_from_node
# fallback, _extract_superclasses_from_node, _extract_function_body,
# extract_packages, _get_node_text_optimized multi-line fallback,
# _extract_detailed_function_info visibility branches,
# _extract_detailed_class_info, _extract_imports_manual,
# PythonPlugin.execute_query_strategy, _get_node_type_for_element,
# PythonPlugin.analyze_file TREE_SITTER_AVAILABLE=False,
# PythonPlugin.get_tree_sitter_language exception path
# =============================================================================


try:
    import tree_sitter_python  # noqa: F401
    TREE_SITTER_PYTHON_AVAILABLE = True
except ImportError:
    TREE_SITTER_PYTHON_AVAILABLE = False


class TestExtractFunctionOptimizedBranches:
    """More branch coverage for _extract_function_optimized."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        ext = PythonElementExtractor()
        ext.framework_type = ""
        ext.current_module = ""
        return ext

    def test_generator_function(self, extractor):
        """Test is_generator detection when 'yield' is in raw_text (line 381)."""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (3, 0)
        extractor.content_lines = [
            "def gen():",
            "    yield 1",
            "    yield 2",
        ]
        with (
            patch.object(extractor, "_parse_function_signature_optimized",
                         return_value=("gen", [], False, [], None)),
            patch.object(extractor, "_extract_docstring_for_line", return_value=None),
            patch.object(extractor, "_calculate_complexity_optimized", return_value=1),
        ):
            result = extractor._extract_function_optimized(mock_node)
            assert result is not None
            assert result.is_generator is True

    def test_classmethod_detection(self, extractor):
        """Test is_classmethod flag (line 392)."""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        extractor.content_lines = ["def from_dict(cls, data):", "    return cls(**data)"]
        with (
            patch.object(extractor, "_parse_function_signature_optimized",
                         return_value=("from_dict", ["cls", "data"], False, ["classmethod"], None)),
            patch.object(extractor, "_extract_docstring_for_line", return_value=None),
            patch.object(extractor, "_calculate_complexity_optimized", return_value=1),
        ):
            result = extractor._extract_function_optimized(mock_node)
            assert result is not None
            assert result.is_classmethod is True
            assert result.is_static is False

    def test_async_with_return_type(self, extractor):
        """Test async function with explicit return type."""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        extractor.content_lines = ["async def fetch(url: str) -> dict:", "    pass"]
        with (
            patch.object(extractor, "_parse_function_signature_optimized",
                         return_value=("fetch", ["url: str"], True, [], "dict")),
            patch.object(extractor, "_extract_docstring_for_line", return_value=None),
            patch.object(extractor, "_calculate_complexity_optimized", return_value=1),
        ):
            result = extractor._extract_function_optimized(mock_node)
            assert result is not None
            assert result.is_async is True
            assert result.return_type == "dict"

    def test_framework_type_propagation(self, extractor):
        """Test framework_type is set on Function (line 390)."""
        extractor.framework_type = "fastapi"
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        extractor.content_lines = ["def endpoint():", "    pass"]
        with (
            patch.object(extractor, "_parse_function_signature_optimized",
                         return_value=("endpoint", [], False, [], None)),
            patch.object(extractor, "_extract_docstring_for_line", return_value=None),
            patch.object(extractor, "_calculate_complexity_optimized", return_value=1),
        ):
            result = extractor._extract_function_optimized(mock_node)
            assert result is not None
            assert result.framework_type == "fastapi"


class TestParseFunctionSignatureReturnType:
    """Tests for return_type parsing branches in _parse_function_signature_optimized."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        ext = PythonElementExtractor()
        ext.source_code = ""
        ext.content_lines = []
        return ext

    def test_return_type_with_arrow(self, extractor):
        """Test return type extracted from -> annotation (lines 417-438)."""
        mock_node = Mock()
        mock_node.parent = None
        mock_id = Mock(type="identifier", text=b"func")
        mock_params = Mock(type="parameters", children=[])
        mock_node.children = [mock_id, mock_params]
        with patch.object(extractor, "_get_node_text_optimized",
                         return_value="def func(x: int) -> str:\n    pass"), \
             patch.object(extractor, "_extract_parameters_from_node_optimized", return_value=["x: int"]):
            result = extractor._parse_function_signature_optimized(mock_node)
            assert result is not None
            name, params, is_async, decorators, return_type = result
            assert return_type == "str"

    def test_return_type_invalid_contains_def(self, extractor):
        """Test return type rejected when it contains 'def ' (lines 432-438)."""
        mock_node = Mock()
        mock_node.parent = None
        mock_id = Mock(type="identifier", text=b"func")
        mock_params = Mock(type="parameters", children=[])
        mock_node.children = [mock_id, mock_params]
        # Simulate a malformed -> that contains "def "
        with patch.object(extractor, "_get_node_text_optimized",
                         return_value="def func() -> def something:\n    pass"), \
             patch.object(extractor, "_extract_parameters_from_node_optimized", return_value=[]):
            result = extractor._parse_function_signature_optimized(mock_node)
            assert result is not None
            assert result[4] is None  # return_type should be None

    def test_return_type_dataclass_branch(self, extractor):
        """Test the != 'dataclass' branch is exercised (lines 429, 461).

        When the return type text after -> is 'dataclass', the condition
        `return_type != "dataclass"` is False, so the inner block is skipped.
        The 'type' child fallback (line 455) also checks != 'dataclass'.
        We exercise the type-child fallback here.
        """
        mock_node = Mock()
        mock_node.parent = None
        mock_id = Mock(type="identifier", text=b"func")
        mock_params = Mock(type="parameters", children=[])
        mock_type = Mock(type="type")
        mock_node.children = [mock_id, mock_params, mock_type]
        # No -> in text, so type child fallback is used.
        def side_effect(node):
            if node == mock_type:
                return "dataclass"
            return "def func():\n    pass"
        with patch.object(extractor, "_get_node_text_optimized", side_effect=side_effect), \
             patch.object(extractor, "_extract_parameters_from_node_optimized", return_value=[]):
            result = extractor._parse_function_signature_optimized(mock_node)
            assert result is not None
            # 'dataclass' from type child is rejected by != 'dataclass' check
            assert result[4] is None

    def test_type_child_fallback(self, extractor):
        """Test return type from 'type' child node (lines 455-463)."""
        mock_node = Mock()
        mock_node.parent = None
        mock_id = Mock(type="identifier", text=b"func")
        mock_params = Mock(type="parameters", children=[])
        mock_type = Mock(type="type")
        mock_node.children = [mock_id, mock_params, mock_type]
        # No -> in text, so type child should be used
        call_count = [0]
        def side_effect(node):
            call_count[0] += 1
            if node == mock_type:
                return "list[int]"
            return "def func():\n    pass"
        with patch.object(extractor, "_get_node_text_optimized", side_effect=side_effect), \
             patch.object(extractor, "_extract_parameters_from_node_optimized", return_value=[]):
            result = extractor._parse_function_signature_optimized(mock_node)
            assert result is not None
            assert result[4] == "list[int]"


class TestExtractClassOptimizedDecoratorPaths:
    """Test decorator extraction from decorated_definition parent (lines 597-605)."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        ext = PythonElementExtractor()
        ext.content_lines = ["@dataclass", "class MyClass:", "    pass"]
        ext.current_module = ""
        ext.framework_type = ""
        return ext

    def test_class_decorators_from_decorated_definition(self, extractor):
        """Test decorators extracted from decorated_definition parent (lines 597-605)."""
        mock_node = Mock()
        mock_node.start_point = (1, 0)
        mock_node.end_point = (2, 0)

        # Parent is a decorated_definition containing a decorator
        mock_decorated = Mock(type="decorated_definition")
        mock_decorator = Mock(type="decorator")
        mock_decorated.children = [mock_decorator, mock_node]
        # Sibling scan: parent has decorated_definition child
        mock_module = Mock()
        mock_module.children = [mock_decorated]
        mock_node.parent = mock_module

        mock_id = Mock(type="identifier", text=b"DataModel")
        mock_node.children = [mock_id]

        with patch.object(extractor, "_get_node_text_optimized",
                         side_effect=lambda n: "@dataclass" if n == mock_decorator
                         else "class DataModel:\n    pass"), \
             patch.object(extractor, "_extract_docstring_for_line", return_value=None):
            result = extractor._extract_class_optimized(mock_node)
            assert result is not None
            assert result.name == "DataModel"
            assert "dataclass" in result.modifiers
            assert result.is_dataclass is True

    def test_class_abstract_detection(self, extractor):
        """Test abstract class detection via ABC superclass (line 655)."""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        mock_node.parent = Mock()
        mock_node.parent.children = []

        mock_id = Mock(type="identifier", text=b"AbstractBase")
        mock_arg = Mock(type="argument_list")
        mock_sc = Mock(type="identifier", text=b"ABC")
        mock_arg.children = [mock_sc]
        mock_node.children = [mock_id, mock_arg]

        with patch.object(extractor, "_get_node_text_optimized",
                         return_value="class AbstractBase(ABC):\n    pass"), \
             patch.object(extractor, "_extract_docstring_for_line", return_value=None):
            result = extractor._extract_class_optimized(mock_node)
            assert result is not None
            assert result.is_abstract is True
            assert result.superclass == "ABC"


class TestExtractImportsManualPath:
    """Tests for _extract_imports_manual method (lines 801-911)."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        return PythonElementExtractor()

    def test_manual_import_statement(self, extractor):
        """Test manual import extraction for 'import os' (lines 819-842)."""
        mock_root = Mock(type="module")
        mock_import = Mock(type="import_statement")
        mock_import.start_point = (0, 0)
        mock_import.end_point = (0, 9)
        mock_import.start_byte = 0
        mock_import.end_byte = 9
        mock_dotted = Mock(type="dotted_name")
        mock_dotted.start_byte = 7
        mock_dotted.end_byte = 9
        mock_dotted.children = []  # leaf node
        mock_import.children = [mock_dotted]
        mock_root.children = [mock_import]

        source = "import os"
        imports = extractor._extract_imports_manual(mock_root, source)
        assert len(imports) >= 1
        assert imports[0].module_name == "os"

    def test_manual_from_import_statement(self, extractor):
        """Test manual from-import extraction (lines 843-901)."""
        mock_root = Mock(type="module")
        mock_from_import = Mock(type="import_from_statement")
        mock_from_import.start_point = (0, 0)
        mock_from_import.end_point = (0, 30)
        mock_from_import.start_byte = 0
        mock_from_import.end_byte = 30

        # "from typing import List, Dict"
        source = "from typing import List, Dict"
        mock_module = Mock(type="dotted_name")
        mock_module.start_byte = 5
        mock_module.end_byte = 11
        mock_module.children = []  # leaf node
        mock_import_list = Mock(type="import_list")
        mock_item1 = Mock(type="identifier")
        mock_item1.start_byte = 19
        mock_item1.end_byte = 23
        mock_item1.children = []  # leaf node
        mock_item2 = Mock(type="identifier")
        mock_item2.start_byte = 25
        mock_item2.end_byte = 29
        mock_item2.children = []  # leaf node
        mock_import_list.children = [mock_item1, mock_item2]
        mock_from_import.children = [mock_module, mock_import_list]
        mock_root.children = [mock_from_import]

        imports = extractor._extract_imports_manual(mock_root, source)
        assert len(imports) >= 1
        assert imports[0].module_name == "typing"
        assert "List" in imports[0].imported_names
        assert "Dict" in imports[0].imported_names

    def test_manual_import_exception(self, extractor):
        """Test manual import extraction handles exceptions (line 903-904)."""
        mock_root = Mock(type="module")
        mock_import = Mock(type="import_statement")
        # Cause an exception by removing start_point
        type(mock_import).start_point = property(
            lambda self: (_ for _ in ()).throw(AttributeError("no"))
        )
        mock_import.children = []
        mock_root.children = [mock_import]
        imports = extractor._extract_imports_manual(mock_root, "import os")
        assert isinstance(imports, list)


class TestExtractClassAttributesDirect:
    """Tests for _extract_class_attributes with direct assignment node (line 699-702)."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        return PythonElementExtractor()

    def test_direct_assignment_node(self, extractor):
        """Test direct 'assignment' child of class body (lines 699-702)."""
        mock_assignment = Mock(
            type="assignment",
            start_byte=0,
            end_byte=6,
            start_point=(0, 0),
            end_point=(0, 6),
        )
        mock_body = Mock(children=[mock_assignment])
        result = extractor._extract_class_attributes(mock_body, "x = 10")
        assert len(result) == 1
        assert result[0].name == "x"


class TestExtractClassAttributeInfo:
    """Tests for _extract_class_attribute_info typed and untyped (lines 709-742)."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        return PythonElementExtractor()

    def test_typed_attribute(self, extractor):
        """Test typed class attribute with annotation (lines 722-725)."""
        mock_node = Mock(
            start_byte=0,
            end_byte=16,
            start_point=(0, 0),
            end_point=(0, 16),
        )
        source = "name: str = 'hi'"
        result = extractor._extract_class_attribute_info(mock_node, source)
        assert result is not None
        assert result.name == "name"
        assert result.variable_type == "str"

    def test_untyped_attribute(self, extractor):
        """Test untyped class attribute (lines 726-728)."""
        mock_node = Mock(
            start_byte=0,
            end_byte=6,
            start_point=(0, 0),
            end_point=(0, 6),
        )
        source = "x = 42"
        result = extractor._extract_class_attribute_info(mock_node, source)
        assert result is not None
        assert result.name == "x"
        assert result.variable_type is None

    def test_no_equals(self, extractor):
        """Test attribute without = returns None (line 718)."""
        mock_node = Mock(
            start_byte=0,
            end_byte=4,
            start_point=(0, 0),
            end_point=(0, 4),
        )
        source = "name"
        result = extractor._extract_class_attribute_info(mock_node, source)
        assert result is None

    def test_exception_returns_none(self, extractor):
        """Test exception in attribute extraction returns None (line 739-741)."""
        mock_node = Mock()
        type(mock_node).start_byte = property(
            lambda self: (_ for _ in ()).throw(Exception("bad"))
        )
        result = extractor._extract_class_attribute_info(mock_node, "x = 1")
        assert result is None


class TestIsFrameworkClassFastAPI:
    """Test _is_framework_class for FastAPI (lines 676-679)."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        return PythonElementExtractor()

    def test_fastapi_framework(self, extractor):
        """Test FastAPI detection via APIRouter/BaseModel (lines 677-678)."""
        extractor.framework_type = "fastapi"
        extractor.source_code = "from pydantic import BaseModel"
        assert extractor._is_framework_class(Mock(), "Item") is True

    def test_fastapi_no_pattern(self, extractor):
        """Test FastAPI detection returns False when no patterns match."""
        extractor.framework_type = "fastapi"
        extractor.source_code = "import json"
        assert extractor._is_framework_class(Mock(), "Item") is False

    def test_django_no_pattern(self, extractor):
        """Test Django detection returns False when no patterns match."""
        extractor.framework_type = "django"
        with patch.object(extractor, "_get_node_text_optimized", return_value="class Plain:\n    pass"):
            assert extractor._is_framework_class(Mock(), "Plain") is False


class TestExtractVariableInfoBranches:
    """Test _extract_variable_info branches (lines 1070-1102)."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        return PythonElementExtractor()

    def test_invalid_node(self, extractor):
        """Test _extract_variable_info with invalid node (lines 1075-1076)."""
        mock_node = Mock()
        with patch.object(extractor, "_validate_node", return_value=False):
            result = extractor._extract_variable_info(mock_node, "x = 1", "assignment")
            assert result is None

    def test_multiple_assignment(self, extractor):
        """Test multiple assignment pattern (lines 1084-1085)."""
        mock_node = Mock(
            start_byte=0,
            end_byte=14,
            start_point=(0, 0),
            end_point=(0, 14),
        )
        with patch.object(extractor, "_validate_node", return_value=True):
            result = extractor._extract_variable_info(mock_node, "a, b = 1, 2   ", "multiple_assignment")
            assert result is not None
            assert result.name == "a"

    def test_no_equals(self, extractor):
        """Test variable without equals (lines 1088-1089)."""
        mock_node = Mock(
            start_byte=0,
            end_byte=4,
            start_point=(0, 0),
            end_point=(0, 4),
        )
        with patch.object(extractor, "_validate_node", return_value=True):
            result = extractor._extract_variable_info(mock_node, "name", "augmented")
            assert result is not None
            assert result.name == "variable"


class TestExtractImportInfoBranches:
    """Test _extract_import_info branches (lines 1104-1148)."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        ext = PythonElementExtractor()
        ext.source_code = ""
        ext.content_lines = []
        return ext

    def test_aliased_import(self, extractor):
        """Test aliased_import type (lines 1130-1132)."""
        mock_node = Mock(
            start_byte=0,
            end_byte=20,
            start_point=(0, 0),
            end_point=(0, 20),
        )
        with patch.object(extractor, "_validate_node", return_value=True):
            result = extractor._extract_import_info(mock_node, "import numpy as np  ", "aliased_import")
            assert result is not None
            assert result.module_name == ""

    def test_from_import_no_from_keyword(self, extractor):
        """Test from_import without 'from' keyword in text (lines 1127-1129)."""
        mock_node = Mock(
            start_byte=0,
            end_byte=10,
            start_point=(0, 0),
            end_point=(0, 10),
        )
        with patch.object(extractor, "_validate_node", return_value=True):
            result = extractor._extract_import_info(mock_node, "something ", "from_import")
            assert result is not None
            assert result.module_name == ""

    def test_import_info_exception(self, extractor):
        """Test _extract_import_info exception returns None (line 1147)."""
        mock_node = Mock()
        with patch.object(extractor, "_validate_node", side_effect=Exception("bad")):
            result = extractor._extract_import_info(mock_node, "import os", "import")
            assert result is None


class TestExtractDocstringFromNodeBranches:
    """Test _extract_docstring_from_node edge cases (lines 1234-1261)."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        return PythonElementExtractor()

    def test_single_quote_docstring(self, extractor):
        """Test single-quoted docstring (lines 1254-1257)."""
        mock_node = Mock()
        mock_block = Mock(type="block")
        mock_stmt = Mock(type="expression_statement")
        mock_expr = Mock(type="string")
        source = "'hello world'"
        mock_expr.start_byte = 0
        mock_expr.end_byte = len(source)
        mock_stmt.children = [mock_expr]
        mock_block.children = [mock_stmt]
        mock_node.children = [mock_block]
        with patch.object(extractor, "_validate_node", return_value=True):
            result = extractor._extract_docstring_from_node(mock_node, source)
            assert result == "hello world"

    def test_no_block_child(self, extractor):
        """Test function node with no block child returns None."""
        mock_node = Mock()
        mock_node.children = [Mock(type="identifier")]
        result = extractor._extract_docstring_from_node(mock_node, "def foo(): pass")
        assert result is None


class TestExtractReturnTypeFromNode:
    """Test _extract_return_type_from_node fallback paths (lines 1208-1232)."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        ext = PythonElementExtractor()
        ext.source_code = ""
        ext.content_lines = []
        return ext

    def test_return_type_starts_with_at(self, extractor):
        """Test decorator-like return type is rejected (line 1222)."""
        mock_node = Mock()
        mock_node.children = []
        with patch.object(extractor, "_get_node_text_optimized",
                         return_value="def func() -> @decorator:\n    pass"):
            result = extractor._extract_return_type_from_node(mock_node, "")
            # Should not return a type starting with @
            assert result is None or not result.startswith("@")

    def test_return_type_fallback_to_type_child(self, extractor):
        """Test fallback to type child node (lines 1226-1231)."""
        mock_type = Mock(type="type")
        mock_type.start_byte = 0
        mock_type.end_byte = 3
        mock_node = Mock()
        mock_node.children = [mock_type]
        with patch.object(extractor, "_get_node_text_optimized", return_value="def foo():\n    pass"):
            result = extractor._extract_return_type_from_node(mock_node, "int")
            assert result == "int"


class TestExtractFunctionBody:
    """Test _extract_function_body (lines 1263-1268)."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        return PythonElementExtractor()

    def test_extract_body(self, extractor):
        """Test body extraction from block child."""
        mock_block = Mock(type="block")
        mock_block.start_byte = 15
        mock_block.end_byte = 30
        mock_node = Mock()
        mock_node.children = [mock_block]
        source = "def foo():\n    return 42"
        result = extractor._extract_function_body(mock_node, source)
        assert isinstance(result, str)

    def test_no_block_returns_empty(self, extractor):
        """Test no block child returns empty string."""
        mock_node = Mock()
        mock_node.children = [Mock(type="identifier")]
        result = extractor._extract_function_body(mock_node, "def foo(): pass")
        assert result == ""


class TestExtractSuperclassesFromNode:
    """Test _extract_superclasses_from_node (lines 1270-1280)."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        return PythonElementExtractor()

    def test_multiple_superclasses(self, extractor):
        """Test extracting multiple superclasses."""
        mock_arg = Mock(type="argument_list")
        mock_s1 = Mock(type="identifier")
        mock_s1.start_byte = 0
        mock_s1.end_byte = 4
        mock_s2 = Mock(type="identifier")
        mock_s2.start_byte = 6
        mock_s2.end_byte = 11
        mock_arg.children = [mock_s1, mock_s2]
        mock_node = Mock()
        mock_node.children = [mock_arg]
        source = "Base, Mixin"
        result = extractor._extract_superclasses_from_node(mock_node, source)
        assert len(result) == 2


class TestExtractPackages:
    """Test extract_packages (lines 913-959)."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        return PythonElementExtractor()

    def test_extract_packages_no_current_file(self, extractor):
        """Test extract_packages with no current_file set."""
        mock_tree = Mock()
        result = extractor.extract_packages(mock_tree, "")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_extract_packages_with_file(self, extractor, tmp_path):
        """Test extract_packages with a file in a package structure."""
        # Create a minimal package structure
        pkg_dir = tmp_path / "my_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")
        test_file = pkg_dir / "module.py"
        test_file.write_text("x = 1")

        extractor.current_file = str(test_file)
        mock_tree = Mock()
        result = extractor.extract_packages(mock_tree, "x = 1")
        assert isinstance(result, list)
        if result:
            assert result[0].name == "my_pkg"
            assert extractor.current_module == "my_pkg"


class TestGetNodeTextOptimizedMultiLine:
    """Test _get_node_text_optimized multi-line fallback (lines 321-336)."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        ext = PythonElementExtractor()
        ext.source_code = "line0\nline1\nline2\nline3"
        ext.content_lines = ext.source_code.split("\n")
        return ext

    def test_multi_line_fallback(self, extractor):
        """Test multi-line text extraction fallback (lines 321-336)."""
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 100
        mock_node.start_point = (0, 2)
        mock_node.end_point = (2, 3)
        with patch("tree_sitter_analyzer.languages.python_plugin.extract_text_slice",
                   return_value=""):
            result = extractor._get_node_text_optimized(mock_node)
            # Should span from line 0, col 2 to line 2, col 3
            assert "ne0" in result  # "line0"[2:] = "ne0"
            assert "lin" in result  # "line2"[:3] = "lin"

    def test_end_point_negative_returns_empty(self, extractor):
        """Test end_point with negative row returns empty (line 311)."""
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        mock_node.start_point = (0, 0)
        mock_node.end_point = (-1, 0)
        with patch("tree_sitter_analyzer.languages.python_plugin.extract_text_slice",
                   return_value=""):
            result = extractor._get_node_text_optimized(mock_node)
            assert result == ""

    def test_both_fallbacks_fail(self, extractor):
        """Test when both byte and line fallbacks fail (line 338)."""
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        type(mock_node).start_point = property(
            lambda self: (_ for _ in ()).throw(Exception("fail"))
        )
        with patch("tree_sitter_analyzer.languages.python_plugin.extract_text_slice",
                   return_value=""):
            result = extractor._get_node_text_optimized(mock_node)
            assert result == ""


class TestExtractDetailedFunctionInfoVisibility:
    """Test _extract_detailed_function_info visibility branches (lines 990-994)."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        ext = PythonElementExtractor()
        ext.source_code = ""
        ext.content_lines = []
        return ext

    def test_magic_method_visibility(self, extractor):
        """Test magic method visibility detection (line 991)."""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 25
        mock_node.children = []

        with (
            patch.object(extractor, "_extract_name_from_node", return_value="__repr__"),
            patch.object(extractor, "_extract_parameters_from_node", return_value=["self"]),
            patch.object(extractor, "_extract_decorators_from_node", return_value=[]),
            patch.object(extractor, "_extract_return_type_from_node", return_value="str"),
        ):
            result = extractor._extract_detailed_function_info(mock_node, "def __repr__(self): pass")
            assert result is not None
            assert result.is_private is False
            assert result.is_public is False

    def test_private_method(self, extractor):
        """Test private method visibility (line 993)."""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 20
        mock_node.children = []

        with (
            patch.object(extractor, "_extract_name_from_node", return_value="_helper"),
            patch.object(extractor, "_extract_parameters_from_node", return_value=[]),
            patch.object(extractor, "_extract_decorators_from_node", return_value=[]),
            patch.object(extractor, "_extract_return_type_from_node", return_value=None),
        ):
            result = extractor._extract_detailed_function_info(mock_node, "def _helper(): pass ")
            assert result is not None
            assert result.is_private is True

    def test_no_name_returns_none(self, extractor):
        """Test None name returns None (line 968-969)."""
        mock_node = Mock()
        mock_node.children = []
        with patch.object(extractor, "_extract_name_from_node", return_value=None):
            result = extractor._extract_detailed_function_info(mock_node, "def (): pass")
            assert result is None


class TestExtractDetailedClassInfoBranches:
    """Test _extract_detailed_class_info (lines 1023-1068)."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        ext = PythonElementExtractor()
        ext.current_module = "my.module"
        return ext

    def test_detailed_class_with_module(self, extractor):
        """Test full_qualified_name with module (line 1044)."""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 20
        mock_node.children = []

        with (
            patch.object(extractor, "_extract_name_from_node", return_value="MyClass"),
            patch.object(extractor, "_extract_superclasses_from_node", return_value=["Base"]),
            patch.object(extractor, "_extract_decorators_from_node", return_value=[]),
        ):
            result = extractor._extract_detailed_class_info(mock_node, "class MyClass(Base):")
            assert result is not None
            assert result.full_qualified_name == "my.module.MyClass"

    def test_detailed_class_no_name(self, extractor):
        """Test _extract_detailed_class_info with no name returns None."""
        mock_node = Mock()
        mock_node.children = []
        with patch.object(extractor, "_extract_name_from_node", return_value=None):
            result = extractor._extract_detailed_class_info(mock_node, "class :")
            assert result is None

    def test_detailed_class_exception(self, extractor):
        """Test exception returns None (line 1066-1068)."""
        mock_node = Mock()
        with patch.object(extractor, "_extract_name_from_node", side_effect=Exception("bad")):
            result = extractor._extract_detailed_class_info(mock_node, "class Foo:")
            assert result is None


class TestPythonPluginExecuteQueryStrategy:
    """Test execute_query_strategy (lines 1426-1431)."""

    @pytest.fixture
    def plugin(self) -> PythonPlugin:
        return PythonPlugin()

    def test_execute_query_strategy_with_key(self, plugin):
        """Test execute_query_strategy returns query for known key."""
        result = plugin.execute_query_strategy("function", "python")
        # Returns query string or None depending on get_queries()
        assert result is None or isinstance(result, str)

    def test_execute_query_strategy_none_key(self, plugin):
        """Test execute_query_strategy with None key."""
        result = plugin.execute_query_strategy(None, "python")
        assert result is None


class TestPythonPluginGetNodeTypeForElement:
    """Test _get_node_type_for_element (lines 1433-1446)."""

    @pytest.fixture
    def plugin(self) -> PythonPlugin:
        return PythonPlugin()

    def test_function_element(self, plugin):
        """Test function type mapping."""
        func = Function(name="f", start_line=1, end_line=2, raw_text="x", language="python")
        assert plugin._get_node_type_for_element(func) == "function_definition"

    def test_class_element(self, plugin):
        """Test class type mapping."""
        cls = Class(name="C", start_line=1, end_line=2, raw_text="x", language="python")
        assert plugin._get_node_type_for_element(cls) == "class_definition"

    def test_variable_element(self, plugin):
        """Test variable type mapping."""
        var = Variable(name="v", start_line=1, end_line=1, raw_text="x", language="python")
        assert plugin._get_node_type_for_element(var) == "assignment"

    def test_import_element(self, plugin):
        """Test import type mapping."""
        imp = Import(name="i", start_line=1, end_line=1, raw_text="x", language="python")
        assert plugin._get_node_type_for_element(imp) == "import_statement"

    def test_unknown_element(self, plugin):
        """Test unknown element type (line 1446)."""
        result = plugin._get_node_type_for_element("string_element")
        assert result == "unknown"


class TestPythonPluginAnalyzeFileTreeSitterUnavailable:
    """Test analyze_file when TREE_SITTER_AVAILABLE is False (lines 1536-1542)."""

    @pytest.fixture
    def plugin(self) -> PythonPlugin:
        return PythonPlugin()

    @pytest.mark.asyncio
    async def test_analyze_file_no_tree_sitter(self, plugin):
        """Test analyze_file returns error when TREE_SITTER_AVAILABLE is False (lines 1536-1542)."""
        import tree_sitter_analyzer.languages.python_plugin as pymod
        original = pymod.TREE_SITTER_AVAILABLE
        try:
            pymod.TREE_SITTER_AVAILABLE = False
            mock_request = Mock()
            mock_request.file_path = "test.py"
            result = await plugin.analyze_file("test.py", mock_request)
            assert result.success is False
            assert "not available" in result.error_message
        finally:
            pymod.TREE_SITTER_AVAILABLE = original

    @pytest.mark.asyncio
    async def test_analyze_file_no_language(self, plugin):
        """Test analyze_file returns error when language is None (lines 1545-1551)."""
        with patch.object(plugin, "get_tree_sitter_language", return_value=None):
            mock_request = Mock()
            mock_request.file_path = "test.py"
            result = await plugin.analyze_file("test.py", mock_request)
            assert result.success is False


class TestPythonPluginGetTreeSitterLanguageException:
    """Test get_tree_sitter_language general exception path (lines 1367-1369)."""

    @pytest.fixture
    def plugin(self) -> PythonPlugin:
        p = PythonPlugin()
        p._language_cache = None
        return p

    def test_general_exception(self, plugin):
        """Test get_tree_sitter_language handles non-ImportError exceptions."""
        with patch("tree_sitter_python.language", side_effect=RuntimeError("broken")):
            result = plugin.get_tree_sitter_language()
            assert result is None


class TestExtractImportsDuplicateSkip:
    """Test extract_imports skips duplicate positions (lines 769-773)."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        return PythonElementExtractor()

    def test_duplicate_position_skipped(self, extractor):
        """Test that duplicate import positions are skipped (lines 769-773)."""
        mock_tree = Mock()
        mock_tree.language = Mock()
        mock_tree.root_node = Mock(children=[], type="module")

        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 9)
        mock_node.start_byte = 0
        mock_node.end_byte = 9

        # Return the same node twice to test dedup
        captures = [(mock_node, "import_stmt"), (mock_node, "import_stmt")]

        with patch("tree_sitter_analyzer.languages.python_plugin.TreeSitterQueryCompat.safe_execute_query",
                   return_value=captures), \
             patch.object(extractor, "_extract_import_info", return_value=Import(
                 name="os", start_line=1, end_line=1, raw_text="import os", language="python"
             )):
            result = extractor.extract_imports(mock_tree, "import os")
            # Should only have 1 import due to dedup
            assert len(result) == 1


class TestExtractImportsOuterException:
    """Test extract_imports outer exception fallback (lines 794-797)."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        return PythonElementExtractor()

    def test_outer_exception_fallback(self, extractor):
        """Test that outer exception triggers _extract_imports_manual fallback (lines 794-797)."""
        mock_tree = Mock()
        # Make hasattr(tree, 'language') raise exception
        type(mock_tree).language = property(lambda self: (_ for _ in ()).throw(Exception("fail")))
        mock_tree.root_node = Mock(children=[], type="module")

        result = extractor.extract_imports(mock_tree, "import os")
        assert isinstance(result, list)


@pytest.mark.skipif(not TREE_SITTER_PYTHON_AVAILABLE, reason="tree-sitter-python not installed")
class TestPythonPluginRealParsing:
    """Integration tests using real tree-sitter-python parsing."""

    @pytest.fixture
    def plugin(self) -> PythonPlugin:
        return PythonPlugin()

    @pytest.fixture
    def parser(self):
        import tree_sitter
        import tree_sitter_python as tspython
        lang = tree_sitter.Language(tspython.language())
        p = tree_sitter.Parser()
        p.language = lang
        return p

    def test_extract_functions_real(self, plugin, parser):
        """Test real function extraction."""
        code = "def hello(name: str) -> str:\n    return f'Hello {name}'\n\nasync def fetch(url):\n    pass\n"
        tree = parser.parse(code.encode("utf-8"))
        extractor = plugin.get_extractor()
        functions = extractor.extract_functions(tree, code)
        names = [f.name for f in functions]
        assert "hello" in names
        assert "fetch" in names
        hello = [f for f in functions if f.name == "hello"][0]
        assert hello.return_type == "str"
        fetch = [f for f in functions if f.name == "fetch"][0]
        assert fetch.is_async is True

    def test_extract_classes_real(self, plugin, parser):
        """Test real class extraction."""
        code = "class Animal:\n    pass\n\nclass Dog(Animal):\n    pass\n"
        tree = parser.parse(code.encode("utf-8"))
        extractor = plugin.get_extractor()
        classes = extractor.extract_classes(tree, code)
        names = [c.name for c in classes]
        assert "Animal" in names
        assert "Dog" in names
        dog = [c for c in classes if c.name == "Dog"][0]
        assert dog.superclass == "Animal"

    def test_extract_imports_real(self, plugin, parser):
        """Test real import extraction."""
        code = "import os\nimport sys\nfrom typing import List, Dict\n"
        tree = parser.parse(code.encode("utf-8"))
        extractor = plugin.get_extractor()
        imports = extractor.extract_imports(tree, code)
        assert len(imports) >= 2

    def test_extract_variables_real(self, plugin, parser):
        """Test real variable extraction from class body."""
        code = "class Config:\n    debug: bool = True\n    name = 'app'\n"
        tree = parser.parse(code.encode("utf-8"))
        extractor = plugin.get_extractor()
        variables = extractor.extract_variables(tree, code)
        assert isinstance(variables, list)

    def test_full_extract_elements(self, plugin, parser):
        """Test full extract_elements pipeline."""
        code = (
            "import os\n"
            "class MyClass:\n"
            "    x = 1\n"
            "    def method(self):\n"
            "        pass\n"
        )
        tree = parser.parse(code.encode("utf-8"))
        elements = plugin.extract_elements(tree, code)
        assert isinstance(elements, list)
        assert len(elements) >= 2  # At least class + function
