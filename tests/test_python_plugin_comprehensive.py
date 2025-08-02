#!/usr/bin/env python3
"""
Comprehensive Tests for Python Plugin

This module provides comprehensive test coverage for the Python plugin,
including all extraction methods, helper functions, and edge cases.
Follows TDD principles and .roo-config.json requirements.
"""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.models import Class, Function, Import, Variable

# Import the modules under test
from tree_sitter_analyzer.plugins.python_plugin import (
    PythonElementExtractor,
    PythonPlugin,
)


@pytest.fixture
def plugin() -> PythonPlugin:
    """Fixture providing PythonPlugin instance"""
    return PythonPlugin()


@pytest.fixture
def extractor() -> PythonElementExtractor:
    """Fixture providing PythonElementExtractor instance"""
    return PythonElementExtractor()


@pytest.fixture
def mock_tree() -> Mock:
    """Fixture providing mock tree-sitter tree"""
    tree = Mock()
    tree.language = Mock()
    tree.root_node = Mock()
    return tree


@pytest.fixture
def mock_node() -> Mock:
    """Fixture providing mock tree-sitter node"""
    node = Mock()
    node.start_point = (10, 0)  # line 11, column 0
    node.end_point = (20, 0)  # line 21, column 0
    node.start_byte = 100
    node.end_byte = 200
    node.type = "function_definition"
    node.children = []
    return node


@pytest.fixture
def sample_python_code() -> str:
    """Fixture providing sample Python code for testing"""
    return '''
"""Module docstring"""
import os
import sys
from typing import List, Optional
from collections import defaultdict as dd

class TestClass:
    """Test class docstring"""

    def __init__(self, name: str) -> None:
        """Constructor docstring"""
        self.name = name
        self._private_var = "private"

    @property
    def name_property(self) -> str:
        """Property docstring"""
        return self.name

    @staticmethod
    def static_method() -> str:
        """Static method docstring"""
        return "static"

    def _private_method(self) -> None:
        """Private method docstring"""
        pass

def public_function(param1: str, param2: int = 10) -> bool:
    """Public function docstring"""
    if param1:
        for i in range(param2):
            try:
                result = param1 + str(i)
            except Exception:
                pass
    return True

async def async_function() -> None:
    """Async function docstring"""
    await some_operation()

# Global variables
GLOBAL_CONSTANT = "constant"
global_var = 42
x, y = 1, 2
z += 5
'''


class TestPythonPluginInitialization:
    """Test cases for PythonPlugin initialization and properties"""

    def test_plugin_initialization(self, plugin: PythonPlugin) -> None:
        """Test plugin initializes correctly"""
        assert plugin is not None
        assert hasattr(plugin, "_extractor")
        assert hasattr(plugin, "_language")
        assert plugin._language is None  # Initially None

    def test_language_name_property(self, plugin: PythonPlugin) -> None:
        """Test language_name property"""
        assert plugin.language_name == "python"

    def test_file_extensions_property(self, plugin: PythonPlugin) -> None:
        """Test file_extensions property"""
        extensions = plugin.file_extensions
        assert isinstance(extensions, list)
        assert ".py" in extensions
        assert ".pyw" in extensions
        assert ".pyi" in extensions
        assert len(extensions) == 3

    def test_get_language_name_method(self, plugin: PythonPlugin) -> None:
        """Test get_language_name method"""
        assert plugin.get_language_name() == "python"

    def test_get_file_extensions_method(self, plugin: PythonPlugin) -> None:
        """Test get_file_extensions method"""
        extensions = plugin.get_file_extensions()
        assert isinstance(extensions, list)
        assert ".py" in extensions
        assert ".pyw" in extensions
        assert ".pyi" in extensions

    def test_create_extractor_method(self, plugin: PythonPlugin) -> None:
        """Test create_extractor method"""
        extractor = plugin.create_extractor()
        assert isinstance(extractor, PythonElementExtractor)
        assert extractor is not plugin._extractor  # Should create new instance

    def test_get_extractor_method(self, plugin: PythonPlugin) -> None:
        """Test get_extractor method"""
        extractor = plugin.get_extractor()
        assert isinstance(extractor, PythonElementExtractor)
        assert extractor is plugin._extractor  # Should return same instance


class TestPythonPluginTreeSitterIntegration:
    """Test cases for tree-sitter integration"""

    def test_get_tree_sitter_language_first_call(self, plugin: PythonPlugin) -> None:
        """Test get_tree_sitter_language loads language on first call"""
        with patch("tree_sitter_analyzer.plugins.python_plugin.loader") as mock_loader:
            mock_language = Mock()
            mock_loader.load_language.return_value = mock_language

            result = plugin.get_tree_sitter_language()

            mock_loader.load_language.assert_called_once_with("python")
            assert result is mock_language
            assert plugin._language is mock_language

    def test_get_tree_sitter_language_cached(self, plugin: PythonPlugin) -> None:
        """Test get_tree_sitter_language returns cached language"""
        mock_language = Mock()
        plugin._language = mock_language

        with patch("tree_sitter_analyzer.plugins.python_plugin.loader") as mock_loader:
            result = plugin.get_tree_sitter_language()

            mock_loader.load_language.assert_not_called()
            assert result is mock_language

    def test_get_supported_queries(self, plugin: PythonPlugin) -> None:
        """Test get_supported_queries method"""
        with patch(
            "tree_sitter_analyzer.plugins.python_plugin.ALL_QUERIES"
        ) as mock_queries:
            mock_queries.keys.return_value = [
                "functions",
                "classes",
                "variables",
                "imports",
            ]

            result = plugin.get_supported_queries()

            assert isinstance(result, list)
            mock_queries.keys.assert_called_once()

    def test_execute_query_success(self, plugin: PythonPlugin, mock_tree: Mock) -> None:
        """Test execute_query with successful execution"""
        mock_language = Mock()
        mock_query = Mock()
        mock_captures = {"function.definition": []}

        plugin._language = mock_language
        mock_language.query.return_value = mock_query
        mock_query.captures.return_value = mock_captures

        with patch(
            "tree_sitter_analyzer.plugins.python_plugin.get_query"
        ) as mock_get_query:
            mock_get_query.return_value = "query_string"

            result = plugin.execute_query(mock_tree, "functions")

            assert result == mock_captures
            mock_get_query.assert_called_once_with("functions")
            mock_language.query.assert_called_once_with("query_string")
            mock_query.captures.assert_called_once_with(mock_tree.root_node)

    def test_execute_query_failure(self, plugin: PythonPlugin, mock_tree: Mock) -> None:
        """Test execute_query with exception handling"""
        with patch(
            "tree_sitter_analyzer.plugins.python_plugin.get_query"
        ) as mock_get_query:
            mock_get_query.side_effect = Exception("Query error")

            result = plugin.execute_query(mock_tree, "functions")

            assert result == {}

    def test_execute_query_no_language(
        self, plugin: PythonPlugin, mock_tree: Mock
    ) -> None:
        """Test execute_query when language is None"""
        plugin._language = None

        with patch.object(plugin, "get_tree_sitter_language", return_value=None):
            result = plugin.execute_query(mock_tree, "functions")

            assert result == {}


class TestPythonElementExtractorInitialization:
    """Test cases for PythonElementExtractor initialization"""

    def test_extractor_initialization(self, extractor: PythonElementExtractor) -> None:
        """Test extractor initializes correctly"""
        assert extractor is not None
        assert extractor.current_module == ""
        assert extractor.current_file == ""
        assert extractor.source_code == ""
        assert extractor.imports == []

    def test_extractor_has_required_methods(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extractor has all required extraction methods"""
        assert hasattr(extractor, "extract_functions")
        assert hasattr(extractor, "extract_classes")
        assert hasattr(extractor, "extract_variables")
        assert hasattr(extractor, "extract_imports")
        assert callable(extractor.extract_functions)
        assert callable(extractor.extract_classes)
        assert callable(extractor.extract_variables)
        assert callable(extractor.extract_imports)


class TestPythonElementExtractorFunctions:
    """Test cases for function extraction"""

    def test_extract_functions_no_language(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extract_functions when tree has no language"""
        mock_tree = Mock()
        mock_tree.language = None

        result = extractor.extract_functions(mock_tree, "code")

        assert isinstance(result, list)
        assert len(result) == 0

    def test_extract_functions_with_language_no_captures(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extract_functions with language but no captures"""
        mock_tree = Mock()
        mock_language = Mock()
        mock_query = Mock()

        mock_tree.language = mock_language
        mock_language.query.return_value = mock_query
        mock_query.captures.return_value = None

        with patch(
            "tree_sitter_analyzer.plugins.python_plugin.get_query"
        ) as mock_get_query:
            mock_get_query.return_value = "query_string"

            result = extractor.extract_functions(mock_tree, "code")

            assert isinstance(result, list)
            assert len(result) == 0

    def test_extract_functions_with_captures(
        self, extractor: PythonElementExtractor, mock_node: Mock
    ) -> None:
        """Test extract_functions with valid captures"""
        mock_tree = Mock()
        mock_language = Mock()
        mock_query = Mock()
        mock_function = Mock(spec=Function)

        mock_tree.language = mock_language
        mock_language.query.return_value = mock_query
        mock_query.captures.return_value = {
            "function.definition": [mock_node],
            "function.async": [],
        }

        with (
            patch(
                "tree_sitter_analyzer.plugins.python_plugin.get_query"
            ) as mock_get_query,
            patch.object(
                extractor, "_extract_detailed_function_info", return_value=mock_function
            ),
        ):
            mock_get_query.return_value = "query_string"

            result = extractor.extract_functions(mock_tree, "code")

            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0] is mock_function

    def test_extract_functions_with_async_captures(
        self, extractor: PythonElementExtractor, mock_node: Mock
    ) -> None:
        """Test extract_functions with async function captures"""
        mock_tree = Mock()
        mock_language = Mock()
        mock_query = Mock()
        mock_function = Mock(spec=Function)

        mock_tree.language = mock_language
        mock_language.query.return_value = mock_query
        mock_query.captures.return_value = {
            "function.definition": [],
            "function.async": [mock_node],
        }

        with (
            patch(
                "tree_sitter_analyzer.plugins.python_plugin.get_query"
            ) as mock_get_query,
            patch.object(
                extractor, "_extract_detailed_function_info", return_value=mock_function
            ),
        ):
            mock_get_query.return_value = "query_string"

            result = extractor.extract_functions(mock_tree, "code")

            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0] is mock_function

    def test_extract_functions_exception_handling(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extract_functions exception handling"""
        mock_tree = Mock()
        mock_tree.language = Mock()
        mock_tree.language.query.side_effect = Exception("Query error")

        with patch("tree_sitter_analyzer.plugins.python_plugin.get_query"):
            result = extractor.extract_functions(mock_tree, "code")

            assert isinstance(result, list)
            assert len(result) == 0


class TestPythonElementExtractorClasses:
    """Test cases for class extraction"""

    def test_extract_classes_no_language(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extract_classes when tree has no language"""
        mock_tree = Mock()
        mock_tree.language = None

        result = extractor.extract_classes(mock_tree, "code")

        assert isinstance(result, list)
        assert len(result) == 0

    def test_extract_classes_with_captures(
        self, extractor: PythonElementExtractor, mock_node: Mock
    ) -> None:
        """Test extract_classes with valid captures"""
        mock_tree = Mock()
        mock_language = Mock()
        mock_query = Mock()
        mock_class = Mock(spec=Class)

        mock_tree.language = mock_language
        mock_language.query.return_value = mock_query
        mock_query.captures.return_value = {"class.definition": [mock_node]}

        with (
            patch(
                "tree_sitter_analyzer.plugins.python_plugin.get_query"
            ) as mock_get_query,
            patch.object(
                extractor, "_extract_detailed_class_info", return_value=mock_class
            ),
        ):
            mock_get_query.return_value = "query_string"

            result = extractor.extract_classes(mock_tree, "code")

            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0] is mock_class

    def test_extract_classes_exception_handling(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extract_classes exception handling"""
        mock_tree = Mock()
        mock_tree.language = Mock()
        mock_tree.language.query.side_effect = Exception("Query error")

        with patch("tree_sitter_analyzer.plugins.python_plugin.get_query"):
            result = extractor.extract_classes(mock_tree, "code")

            assert isinstance(result, list)
            assert len(result) == 0


class TestPythonElementExtractorVariables:
    """Test cases for variable extraction"""

    def test_extract_variables_with_captures(
        self, extractor: PythonElementExtractor, mock_node: Mock
    ) -> None:
        """Test extract_variables with valid captures"""
        mock_tree = Mock()
        mock_language = Mock()
        mock_query = Mock()
        mock_variable = Mock(spec=Variable)

        mock_tree.language = mock_language
        mock_language.query.return_value = mock_query
        mock_query.captures.return_value = {
            "variable.assignment": [mock_node],
            "variable.multiple": [mock_node],
            "variable.augmented": [mock_node],
        }

        with (
            patch(
                "tree_sitter_analyzer.plugins.python_plugin.get_query"
            ) as mock_get_query,
            patch.object(
                extractor, "_extract_variable_info", return_value=mock_variable
            ),
        ):
            mock_get_query.return_value = "query_string"

            result = extractor.extract_variables(mock_tree, "code")

            assert isinstance(result, list)
            assert len(result) == 3  # One for each type
            assert all(var is mock_variable for var in result)

    def test_extract_variables_exception_handling(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extract_variables exception handling"""
        mock_tree = Mock()
        mock_tree.language = Mock()
        mock_tree.language.query.side_effect = Exception("Query error")

        with patch("tree_sitter_analyzer.plugins.python_plugin.get_query"):
            result = extractor.extract_variables(mock_tree, "code")

            assert isinstance(result, list)
            assert len(result) == 0


class TestPythonElementExtractorImports:
    """Test cases for import extraction"""

    def test_extract_imports_with_captures(
        self, extractor: PythonElementExtractor, mock_node: Mock
    ) -> None:
        """Test extract_imports with valid captures"""
        mock_tree = Mock()
        mock_language = Mock()
        mock_query = Mock()
        mock_import = Mock(spec=Import)

        mock_tree.language = mock_language
        mock_language.query.return_value = mock_query
        mock_query.captures.return_value = {
            "import.statement": [mock_node],
            "import.from": [mock_node],
            "import.from_list": [mock_node],
            "import.aliased": [mock_node],
        }

        with (
            patch(
                "tree_sitter_analyzer.plugins.python_plugin.get_query"
            ) as mock_get_query,
            patch.object(extractor, "_extract_import_info", return_value=mock_import),
        ):
            mock_get_query.return_value = "query_string"

            result = extractor.extract_imports(mock_tree, "code")

            assert isinstance(result, list)
            assert len(result) == 4  # One for each type
            assert all(imp is mock_import for imp in result)

    def test_extract_imports_exception_handling(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extract_imports exception handling"""
        mock_tree = Mock()
        mock_tree.language = Mock()
        mock_tree.language.query.side_effect = Exception("Query error")

        with patch("tree_sitter_analyzer.plugins.python_plugin.get_query"):
            result = extractor.extract_imports(mock_tree, "code")

            assert isinstance(result, list)
            assert len(result) == 0


class TestPythonElementExtractorHelperMethods:
    """Test cases for helper methods"""

    def test_extract_name_from_node_with_identifier(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _extract_name_from_node with identifier child"""
        mock_node = Mock()
        mock_child = Mock()
        mock_child.type = "identifier"
        mock_child.start_byte = 0
        mock_child.end_byte = 8
        mock_node.children = [mock_child]

        result = extractor._extract_name_from_node(mock_node, "function_name")

        assert result == "function"

    def test_extract_name_from_node_without_identifier(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _extract_name_from_node without identifier child"""
        mock_node = Mock()
        mock_child = Mock()
        mock_child.type = "other"
        mock_node.children = [mock_child]

        result = extractor._extract_name_from_node(mock_node, "code")

        assert result is None

    def test_extract_parameters_from_node(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _extract_parameters_from_node"""
        mock_node = Mock()
        mock_params_node = Mock()
        mock_param1 = Mock()
        mock_param2 = Mock()

        mock_params_node.type = "parameters"
        mock_param1.type = "identifier"
        mock_param1.start_byte = 0
        mock_param1.end_byte = 5
        mock_param2.type = "typed_parameter"
        mock_param2.start_byte = 7
        mock_param2.end_byte = 15

        mock_params_node.children = [mock_param1, mock_param2]
        mock_node.children = [mock_params_node]

        result = extractor._extract_parameters_from_node(
            mock_node, "param1, param2: int"
        )

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0] == "param"
        assert result[1] == " param2:"

    def test_extract_decorators_from_node_with_parent(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _extract_decorators_from_node with parent node"""
        mock_node = Mock()
        mock_parent = Mock()
        mock_decorator = Mock()

        mock_decorator.type = "decorator"
        mock_decorator.start_point = (5, 0)
        mock_decorator.end_point = (5, 10)
        mock_decorator.start_byte = 0
        mock_decorator.end_byte = 10

        mock_node.start_point = (10, 0)
        mock_node.parent = mock_parent
        mock_parent.children = [mock_decorator, mock_node]

        result = extractor._extract_decorators_from_node(mock_node, "@decorator")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0] == "decorator"

    def test_extract_decorators_from_node_without_parent(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _extract_decorators_from_node without parent node"""
        mock_node = Mock()
        mock_node.parent = None

        result = extractor._extract_decorators_from_node(mock_node, "code")

        assert isinstance(result, list)
        assert len(result) == 0

    def test_extract_return_type_from_node(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _extract_return_type_from_node"""
        mock_node = Mock()
        mock_type_child = Mock()
        mock_type_child.type = "type"
        mock_type_child.start_byte = 0
        mock_type_child.end_byte = 3
        mock_node.children = [mock_type_child]

        result = extractor._extract_return_type_from_node(mock_node, "int")

        assert result == "int"

    def test_extract_return_type_from_node_no_type(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _extract_return_type_from_node without type annotation"""
        mock_node = Mock()
        mock_child = Mock()
        mock_child.type = "other"
        mock_node.children = [mock_child]

        result = extractor._extract_return_type_from_node(mock_node, "code")

        assert result is None

    def test_extract_function_body(self, extractor: PythonElementExtractor) -> None:
        """Test _extract_function_body"""
        mock_node = Mock()
        mock_block = Mock()
        mock_block.type = "block"
        mock_block.start_byte = 0
        mock_block.end_byte = 10
        mock_node.children = [mock_block]

        result = extractor._extract_function_body(mock_node, "    pass\n")

        assert result == "    pass\n"

    def test_extract_function_body_no_block(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _extract_function_body without block"""
        mock_node = Mock()
        mock_child = Mock()
        mock_child.type = "other"
        mock_node.children = [mock_child]

        result = extractor._extract_function_body(mock_node, "code")

        assert result == ""

    def test_extract_superclasses_from_node(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _extract_superclasses_from_node"""
        mock_node = Mock()
        mock_arg_list = Mock()
        mock_arg1 = Mock()
        mock_arg2 = Mock()

        mock_arg_list.type = "argument_list"
        mock_arg1.type = "identifier"
        mock_arg1.start_byte = 0
        mock_arg1.end_byte = 4
        mock_arg2.type = "identifier"
        mock_arg2.start_byte = 6
        mock_arg2.end_byte = 10

        mock_arg_list.children = [mock_arg1, mock_arg2]
        mock_node.children = [mock_arg_list]

        result = extractor._extract_superclasses_from_node(mock_node, "Base, Mixin")

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0] == "Base"
        assert result[1] == "Mixi"

    def test_calculate_complexity_simple(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _calculate_complexity with simple code"""
        body = "return True"

        result = extractor._calculate_complexity(body)

        assert result == 1  # Base complexity

    def test_calculate_complexity_with_keywords(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _calculate_complexity with control flow keywords"""
        body = """
        if condition:
            for item in items:
                while running:
                    try:
                        pass
                    except Exception:
                        pass
        elif other:
            pass
        """

        result = extractor._calculate_complexity(body)

        assert result > 1  # Should be higher than base complexity


class TestPythonElementExtractorDetailedExtraction:
    """Test cases for detailed extraction methods"""

    def test_extract_detailed_function_info_success(
        self, extractor: PythonElementExtractor, mock_node: Mock
    ) -> None:
        """Test _extract_detailed_function_info successful extraction"""
        with (
            patch.object(
                extractor, "_extract_name_from_node", return_value="test_function"
            ),
            patch.object(
                extractor,
                "_extract_parameters_from_node",
                return_value=["param1", "param2"],
            ),
            patch.object(
                extractor, "_extract_decorators_from_node", return_value=["decorator1"]
            ),
            patch.object(
                extractor, "_extract_return_type_from_node", return_value="str"
            ),
            patch.object(
                extractor, "_extract_docstring_from_node", return_value="Test docstring"
            ),
            patch.object(extractor, "_extract_function_body", return_value="    pass"),
            patch.object(extractor, "_calculate_complexity", return_value=2),
        ):
            result = extractor._extract_detailed_function_info(
                mock_node, "code", is_async=True
            )

            # Verify the result
            assert result is not None
            assert result.name == "test_function"
            assert result.parameters == ["param1", "param2"]
            assert result.modifiers == ["decorator1"]
            assert result.return_type == "str"

    def test_extract_detailed_function_info_no_name(
        self, extractor: PythonElementExtractor, mock_node: Mock
    ) -> None:
        """Test _extract_detailed_function_info with no name"""
        with patch.object(extractor, "_extract_name_from_node", return_value=None):
            result = extractor._extract_detailed_function_info(mock_node, "code")

            assert result is None

    def test_extract_detailed_function_info_exception(
        self, extractor: PythonElementExtractor, mock_node: Mock
    ) -> None:
        """Test _extract_detailed_function_info exception handling"""
        with patch.object(
            extractor, "_extract_name_from_node", side_effect=Exception("Error")
        ):
            result = extractor._extract_detailed_function_info(mock_node, "code")

            assert result is None

    def test_extract_detailed_class_info_success(
        self, extractor: PythonElementExtractor, mock_node: Mock
    ) -> None:
        """Test _extract_detailed_class_info successful extraction"""
        extractor.current_module = "test_module"

        with (
            patch.object(
                extractor, "_extract_name_from_node", return_value="TestClass"
            ),
            patch.object(
                extractor,
                "_extract_superclasses_from_node",
                return_value=["BaseClass", "Mixin"],
            ),
            patch.object(
                extractor, "_extract_decorators_from_node", return_value=["dataclass"]
            ),
            patch.object(
                extractor, "_extract_docstring_from_node", return_value="Test class"
            ),
        ):
            result = extractor._extract_detailed_class_info(mock_node, "code")

            # Verify the result
            assert result is not None
            assert result.name == "TestClass"
            assert result.superclass == "BaseClass"
            assert result.interfaces == ["Mixin"]
            assert result.modifiers == ["dataclass"]

    def test_extract_detailed_class_info_no_name(
        self, extractor: PythonElementExtractor, mock_node: Mock
    ) -> None:
        """Test _extract_detailed_class_info with no name"""
        with patch.object(extractor, "_extract_name_from_node", return_value=None):
            result = extractor._extract_detailed_class_info(mock_node, "code")

            assert result is None

    def test_extract_detailed_class_info_exception(
        self, extractor: PythonElementExtractor, mock_node: Mock
    ) -> None:
        """Test _extract_detailed_class_info exception handling"""
        with patch.object(
            extractor, "_extract_name_from_node", side_effect=Exception("Error")
        ):
            result = extractor._extract_detailed_class_info(mock_node, "code")

            assert result is None


class TestPythonElementExtractorVariableExtraction:
    """Test cases for variable extraction details"""

    def test_extract_variable_info_success(
        self, extractor: PythonElementExtractor, mock_node: Mock
    ) -> None:
        """Test _extract_variable_info successful extraction"""
        result = extractor._extract_variable_info(mock_node, "variable = 42")

        assert isinstance(result, Variable)
        assert result.name == "variable"
        assert result.variable_type == "assignment"

    def test_extract_variable_info_multiple(
        self, extractor: PythonElementExtractor, mock_node: Mock
    ) -> None:
        """Test _extract_variable_info with multiple assignment"""
        result = extractor._extract_variable_info(
            mock_node, "x, y = 1, 2", is_multiple=True
        )

        assert isinstance(result, Variable)
        assert result.name == "variable"
        assert result.variable_type == "multiple"

    def test_extract_variable_info_augmented(
        self, extractor: PythonElementExtractor, mock_node: Mock
    ) -> None:
        """Test _extract_variable_info with augmented assignment"""
        result = extractor._extract_variable_info(
            mock_node, "counter += 1", is_augmented=True
        )

        assert isinstance(result, Variable)
        assert result.name == "variable"
        assert result.variable_type == "augmented"

    def test_extract_variable_info_missing_attributes(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _extract_variable_info with missing node attributes"""
        mock_node = Mock()
        del mock_node.start_byte  # Remove required attribute

        result = extractor._extract_variable_info(mock_node, "variable = 42")

        assert result is None

    def test_extract_variable_info_none_attributes(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _extract_variable_info with None node attributes"""
        mock_node = Mock()
        mock_node.start_byte = None
        mock_node.end_byte = None
        mock_node.start_point = None
        mock_node.end_point = None

        result = extractor._extract_variable_info(mock_node, "variable = 42")

        assert result is None

    def test_extract_variable_info_exception(
        self, extractor: PythonElementExtractor, mock_node: Mock
    ) -> None:
        """Test _extract_variable_info exception handling"""
        mock_node.start_byte = "invalid"  # Invalid type

        result = extractor._extract_variable_info(mock_node, "variable = 42")

        assert result is None


class TestPythonElementExtractorImportExtraction:
    """Test cases for import extraction details"""

    def test_extract_import_info_regular_import(
        self, extractor: PythonElementExtractor, mock_node: Mock
    ) -> None:
        """Test _extract_import_info with regular import"""
        result = extractor._extract_import_info(
            mock_node, "import os", is_from=False, is_from_list=False, is_aliased=False
        )

        # Verify the result
        assert result is not None
        assert result.name == "import os"  # 完全なインポート文を期待
        assert result.language == "python"

    def test_extract_import_info_from_import(
        self, extractor: PythonElementExtractor, mock_node: Mock
    ) -> None:
        """Test _extract_import_info with from import"""
        result = extractor._extract_import_info(
            mock_node,
            "from os import path",
            is_from=True,
            is_from_list=False,
            is_aliased=False,
        )

        # Verify the result
        assert result is not None
        assert result.name == "from os import path"  # 完全なインポート文を期待
        assert result.module_name == "os"

    def test_extract_import_info_aliased_import(
        self, extractor: PythonElementExtractor, mock_node: Mock
    ) -> None:
        """Test _extract_import_info with aliased import"""
        result = extractor._extract_import_info(
            mock_node,
            "import numpy as np",
            is_from=False,
            is_from_list=False,
            is_aliased=True,
        )

        # Verify the result
        assert result is not None
        assert result.name == "import numpy as np"  # 完全なインポート文を期待
        assert result.language == "python"

    def test_extract_import_info_missing_attributes(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _extract_import_info with missing node attributes"""
        mock_node = Mock()
        del mock_node.start_byte  # Remove required attribute

        result = extractor._extract_import_info(mock_node, "import os")

        assert result is None

    def test_extract_import_info_exception(
        self, extractor: PythonElementExtractor, mock_node: Mock
    ) -> None:
        """Test _extract_import_info exception handling"""
        mock_node.start_byte = "invalid"  # Invalid type

        result = extractor._extract_import_info(mock_node, "import os")

        assert result is None


class TestPythonElementExtractorDocstringExtraction:
    """Test cases for docstring extraction"""

    def test_extract_docstring_from_node_triple_quotes(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _extract_docstring_from_node with triple quotes"""
        mock_node = Mock()
        mock_block = Mock()
        mock_stmt = Mock()
        mock_expr = Mock()
        mock_string = Mock()

        mock_block.type = "block"
        mock_stmt.type = "expression_statement"
        mock_expr.type = "string"
        mock_string.type = "string"
        mock_string.start_byte = 0
        mock_string.end_byte = 20

        # exprがstringノードとして直接使用されるように設定
        mock_expr.start_byte = 0
        mock_expr.end_byte = 20
        mock_expr.children = [mock_string]
        mock_stmt.children = [mock_expr]
        mock_block.children = [mock_stmt]
        mock_node.children = [mock_block]

        result = extractor._extract_docstring_from_node(
            mock_node, '"""Test docstring"""'
        )

        assert result == "Test docstring"

    def test_extract_docstring_from_node_single_quotes(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _extract_docstring_from_node with single quotes"""
        mock_node = Mock()
        mock_block = Mock()
        mock_stmt = Mock()
        mock_expr = Mock()
        mock_string = Mock()

        mock_block.type = "block"
        mock_stmt.type = "expression_statement"
        mock_expr.type = "string"
        mock_string.type = "string"
        mock_string.start_byte = 0
        mock_string.end_byte = 16

        # exprがstringノードとして直接使用されるように設定
        mock_expr.start_byte = 0
        mock_expr.end_byte = 20
        mock_expr.children = [mock_string]
        mock_stmt.children = [mock_expr]
        mock_block.children = [mock_stmt]
        mock_node.children = [mock_block]

        result = extractor._extract_docstring_from_node(mock_node, '"Test docstring"')

        assert result == "Test docstring"

    def test_extract_docstring_from_node_no_docstring(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test _extract_docstring_from_node with no docstring"""
        mock_node = Mock()
        mock_child = Mock()
        mock_child.type = "other"
        mock_node.children = [mock_child]

        result = extractor._extract_docstring_from_node(mock_node, "code")

        assert result is None


class TestPythonElementExtractorEdgeCases:
    """Test cases for edge cases and error conditions"""

    def test_extract_with_empty_source_code(
        self, extractor: PythonElementExtractor, mock_tree: Mock
    ) -> None:
        """Test extraction with empty source code"""
        mock_tree.language = None

        functions = extractor.extract_functions(mock_tree, "")
        classes = extractor.extract_classes(mock_tree, "")
        variables = extractor.extract_variables(mock_tree, "")
        imports = extractor.extract_imports(mock_tree, "")

        assert isinstance(functions, list) and len(functions) == 0
        assert isinstance(classes, list) and len(classes) == 0
        assert isinstance(variables, list) and len(variables) == 0
        assert isinstance(imports, list) and len(imports) == 0

    def test_extract_with_malformed_captures(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extraction with malformed captures"""
        mock_tree = Mock()
        mock_language = Mock()
        mock_query = Mock()

        mock_tree.language = mock_language
        mock_language.query.return_value = mock_query
        mock_query.captures.return_value = "not_a_dict"  # Invalid return type

        with patch("tree_sitter_analyzer.plugins.python_plugin.get_query"):
            result = extractor.extract_functions(mock_tree, "code")

            assert isinstance(result, list)
            assert len(result) == 0


# Additional test markers for categorization
pytestmark = [
    pytest.mark.unit,
]
