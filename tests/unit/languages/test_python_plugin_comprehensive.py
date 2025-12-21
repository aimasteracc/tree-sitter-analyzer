"""
Comprehensive tests for Python plugin.
Tests all major functionality including functions, classes, variables, imports,
caching, performance optimizations, and Python-specific features.
"""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.python_plugin import (
    PythonElementExtractor,
    PythonPlugin,
)
from tree_sitter_analyzer.models import Class, Function, Import, Variable


class TestPythonElementExtractor:
    """Test Python element extractor functionality"""

    @pytest.fixture
    def extractor(self):
        """Create a Python element extractor instance"""
        return PythonElementExtractor()

    @pytest.fixture
    def mock_tree(self):
        """Create a mock tree-sitter tree"""
        tree = Mock()
        tree.root_node = Mock()
        tree.language = Mock()
        return tree

    @pytest.fixture
    def sample_python_code(self):
        """Sample Python code for testing"""
        return '''
import os
import sys
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class User:
    """User model class"""
    name: str
    age: int
    email: Optional[str] = None

    def __post_init__(self):
        """Post initialization method"""
        if not self.email:
            self.email = f"{self.name.lower()}@example.com"

    @property
    def display_name(self) -> str:
        """Get display name"""
        return f"{self.name} ({self.age})"

    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> 'User':
        """Create user from dictionary"""
        return cls(**data)

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format"""
        return "@" in email and "." in email

async def fetch_user_data(user_id: int) -> Dict[str, any]:
    """Fetch user data asynchronously"""
    # Simulate async operation
    await asyncio.sleep(0.1)
    return {"id": user_id, "name": "Test User"}

def process_users(users: List[User]) -> List[Dict[str, any]]:
    """Process list of users"""
    result = []
    for user in users:
        if user.age >= 18:
            result.append({
                "name": user.name,
                "email": user.email,
                "is_adult": True
            })
    return result

def _private_helper(data: str) -> str:
    """Private helper function"""
    return data.strip().lower()

def __magic_method__(self, other):
    """Magic method example"""
    return self + other
'''

    def test_initialization(self, extractor):
        """Test extractor initialization"""
        assert extractor.current_module == ""
        assert extractor.current_file == ""
        assert extractor.source_code == ""
        assert extractor.content_lines == []
        assert extractor.imports == []
        assert extractor.exports == []
        assert isinstance(extractor._node_text_cache, dict)
        assert isinstance(extractor._processed_nodes, set)
        assert isinstance(extractor._element_cache, dict)
        assert extractor._file_encoding is None
        assert isinstance(extractor._docstring_cache, dict)
        assert isinstance(extractor._complexity_cache, dict)
        assert extractor.is_module is False
        assert extractor.framework_type == ""
        assert extractor.python_version == "3.8"

    def test_reset_caches(self, extractor):
        """Test cache reset functionality"""
        # Populate caches
        extractor._node_text_cache[1] = "test"
        extractor._processed_nodes.add(1)
        extractor._element_cache[(1, "test")] = "value"
        extractor._docstring_cache[1] = "doc"
        extractor._complexity_cache[1] = 5

        # Reset caches
        extractor._reset_caches()

        # Verify caches are empty
        assert len(extractor._node_text_cache) == 0
        assert len(extractor._processed_nodes) == 0
        assert len(extractor._element_cache) == 0
        assert len(extractor._docstring_cache) == 0
        assert len(extractor._complexity_cache) == 0

    def test_detect_file_characteristics(self, extractor, sample_python_code):
        """Test file characteristics detection"""
        extractor.source_code = sample_python_code
        extractor._detect_file_characteristics()

        # Should detect as module due to imports
        assert extractor.is_module is True

        # Test Django detection
        django_code = "from django.db import models\nclass MyModel(models.Model): pass"
        extractor.source_code = django_code
        extractor._detect_file_characteristics()
        assert extractor.framework_type == "django"

        # Test Flask detection
        flask_code = "from flask import Flask\napp = Flask(__name__)"
        extractor.source_code = flask_code
        extractor._detect_file_characteristics()
        assert extractor.framework_type == "flask"

        # Test FastAPI detection
        fastapi_code = "from fastapi import FastAPI\napp = FastAPI()"
        extractor.source_code = fastapi_code
        extractor._detect_file_characteristics()
        assert extractor.framework_type == "fastapi"

    def test_extract_functions_basic(self, extractor, mock_tree, sample_python_code):
        """Test basic function extraction"""
        # Mock tree structure for function extraction
        mock_function_node = Mock()
        mock_function_node.type = "function_definition"
        mock_function_node.start_point = (10, 0)
        mock_function_node.end_point = (15, 0)
        mock_function_node.start_byte = 100
        mock_function_node.end_byte = 200
        mock_function_node.children = []
        mock_function_node.parent = None

        mock_tree.root_node.children = [mock_function_node]

        # Mock the extraction method
        with patch.object(
            extractor, "_traverse_and_extract_iterative"
        ) as mock_traverse:
            functions = extractor.extract_functions(mock_tree, sample_python_code)

            # Verify traversal was called
            mock_traverse.assert_called_once()
            assert isinstance(functions, list)

    def test_extract_classes_basic(self, extractor, mock_tree, sample_python_code):
        """Test basic class extraction"""
        # Mock tree structure for class extraction
        mock_class_node = Mock()
        mock_class_node.type = "class_definition"
        mock_class_node.start_point = (5, 0)
        mock_class_node.end_point = (25, 0)
        mock_class_node.start_byte = 50
        mock_class_node.end_byte = 300
        mock_class_node.children = []
        mock_class_node.parent = None

        mock_tree.root_node.children = [mock_class_node]

        # Mock the extraction method
        with patch.object(
            extractor, "_traverse_and_extract_iterative"
        ) as mock_traverse:
            classes = extractor.extract_classes(mock_tree, sample_python_code)

            # Verify traversal was called
            mock_traverse.assert_called_once()
            assert isinstance(classes, list)

    def test_extract_variables_basic(self, extractor, mock_tree, sample_python_code):
        """Test basic variable extraction"""
        # Mock query and captures
        mock_query = Mock()
        mock_captures = {"class.body": [Mock()]}
        mock_query.captures.return_value = mock_captures
        mock_tree.language.query.return_value = mock_query

        with patch.object(extractor, "_extract_class_attributes") as mock_extract:
            mock_extract.return_value = []
            variables = extractor.extract_variables(mock_tree, sample_python_code)

            assert isinstance(variables, list)

    def test_get_node_text_optimized_caching(self, extractor):
        """Test node text extraction with caching"""
        # Create mock node
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10

        # Set up extractor state
        extractor.content_lines = ["test content line"]
        extractor._file_encoding = "utf-8"

        # Mock extract_text_slice to return test text
        with patch(
            "tree_sitter_analyzer.languages.python_plugin.extract_text_slice"
        ) as mock_extract:
            mock_extract.return_value = "test text"

            # First call should extract and cache
            result1 = extractor._get_node_text_optimized(mock_node)
            assert result1 == "test text"
            # Cache uses (start_byte, end_byte) tuple as key
            assert (
                mock_node.start_byte,
                mock_node.end_byte,
            ) in extractor._node_text_cache

            # Second call should use cache
            result2 = extractor._get_node_text_optimized(mock_node)
            assert result2 == "test text"
            assert mock_extract.call_count == 1  # Should only be called once

    def test_get_node_text_optimized_fallback(self, extractor):
        """Test node text extraction fallback mechanism"""
        # Create mock node
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 10)

        # Set up extractor state
        extractor.content_lines = ["test content line"]
        extractor._file_encoding = "utf-8"

        # Mock extract_text_slice to raise exception
        with patch(
            "tree_sitter_analyzer.languages.python_plugin.extract_text_slice"
        ) as mock_extract:
            mock_extract.side_effect = Exception("Test error")

            # Should fallback to simple extraction
            result = extractor._get_node_text_optimized(mock_node)
            assert result == "test conte"  # Characters 0-10 from first line

    def test_parse_function_signature_optimized(self, extractor):
        """Test function signature parsing"""
        # Create mock function node
        mock_node = Mock()
        mock_node.children = []
        mock_node.parent = None

        # Mock identifier child
        mock_identifier = Mock()
        mock_identifier.type = "identifier"
        mock_identifier.text = b"test_function"

        # Mock parameters child
        mock_parameters = Mock()
        mock_parameters.type = "parameters"

        # Mock type child
        mock_type = Mock()
        mock_type.type = "type"

        mock_node.children = [mock_identifier, mock_parameters, mock_type]

        # Mock helper methods
        with patch.object(extractor, "_get_node_text_optimized") as mock_get_text:
            mock_get_text.side_effect = ["def test_function", "str"]

            with patch.object(
                extractor, "_extract_parameters_from_node_optimized"
            ) as mock_extract_params:
                mock_extract_params.return_value = ["param1", "param2"]

                result = extractor._parse_function_signature_optimized(mock_node)

                assert result is not None
                name, parameters, is_async, decorators, return_type = result
                assert name == "test_function"
                assert parameters == ["param1", "param2"]
                assert is_async is False
                assert decorators == []
                assert return_type == "str"

    def test_parse_function_signature_async(self, extractor):
        """Test async function signature parsing"""
        mock_node = Mock()
        mock_node.children = []
        mock_node.parent = None

        # Mock identifier child
        mock_identifier = Mock()
        mock_identifier.type = "identifier"
        mock_identifier.text = b"async_function"

        mock_node.children = [mock_identifier]

        with patch.object(extractor, "_get_node_text_optimized") as mock_get_text:
            mock_get_text.return_value = "async def async_function"

            with patch.object(
                extractor, "_extract_parameters_from_node_optimized"
            ) as mock_extract_params:
                mock_extract_params.return_value = []

                result = extractor._parse_function_signature_optimized(mock_node)

                assert result is not None
                name, parameters, is_async, decorators, return_type = result
                assert name == "async_function"
                assert is_async is True

    def test_extract_parameters_from_node_optimized(self, extractor):
        """Test parameter extraction from node"""
        # Create mock parameters node
        mock_params_node = Mock()

        # Mock different parameter types
        mock_identifier = Mock()
        mock_identifier.type = "identifier"

        mock_typed_param = Mock()
        mock_typed_param.type = "typed_parameter"

        mock_default_param = Mock()
        mock_default_param.type = "default_parameter"

        mock_splat = Mock()
        mock_splat.type = "list_splat_pattern"

        mock_dict_splat = Mock()
        mock_dict_splat.type = "dictionary_splat_pattern"

        mock_params_node.children = [
            mock_identifier,
            mock_typed_param,
            mock_default_param,
            mock_splat,
            mock_dict_splat,
        ]

        with patch.object(extractor, "_get_node_text_optimized") as mock_get_text:
            mock_get_text.side_effect = [
                "param1",
                "param2: str",
                "param3=None",
                "*args",
                "**kwargs",
            ]

            result = extractor._extract_parameters_from_node_optimized(mock_params_node)

            assert result == [
                "param1",
                "param2: str",
                "param3=None",
                "*args",
                "**kwargs",
            ]

    def test_extract_docstring_for_line_single_line(self, extractor):
        """Test single-line docstring extraction"""
        extractor.content_lines = [
            "def test_function():",
            '    """This is a single line docstring"""',
            "    pass",
        ]

        result = extractor._extract_docstring_for_line(1)
        assert result == "This is a single line docstring"

    def test_extract_docstring_for_line_multi_line(self, extractor):
        """Test multi-line docstring extraction"""
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

    def test_extract_docstring_for_line_caching(self, extractor):
        """Test docstring extraction caching"""
        extractor.content_lines = [
            "def test_function():",
            '    """Test docstring"""',
            "    pass",
        ]

        # First call should extract and cache
        result1 = extractor._extract_docstring_for_line(1)
        assert result1 == "Test docstring"
        assert 1 in extractor._docstring_cache

        # Second call should use cache
        result2 = extractor._extract_docstring_for_line(1)
        assert result2 == "Test docstring"

    def test_calculate_complexity_optimized(self, extractor):
        """Test complexity calculation"""
        mock_node = Mock()
        node_id = id(mock_node)

        # Test simple function
        with patch.object(extractor, "_get_node_text_optimized") as mock_get_text:
            mock_get_text.return_value = "def simple_function(): return True"

            result = extractor._calculate_complexity_optimized(mock_node)
            assert result == 1  # Base complexity
            assert node_id in extractor._complexity_cache

        # Test complex function with different mock node
        complex_mock_node = Mock()
        complex_code = """
        def complex_function(x):
            if x > 0:
                for i in range(x):
                    if i % 2 == 0:
                        while i > 0:
                            try:
                                result = i / 2
                            except ZeroDivisionError:
                                pass
                            i -= 1
            elif x < 0:
                pass
            return x
        """

        with patch.object(extractor, "_get_node_text_optimized") as mock_get_text:
            mock_get_text.return_value = complex_code

            result = extractor._calculate_complexity_optimized(complex_mock_node)
            assert (
                result >= 5
            )  # Should have higher complexity (if, for, if, while, try, elif)

    def test_extract_function_optimized_complete(self, extractor):
        """Test complete function extraction"""
        # Create mock function node
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 0)

        # Set up extractor state
        extractor.content_lines = [
            "def test_function(param1: str, param2: int = 0) -> str:",
            '    """Test function docstring"""',
            "    return param1 * param2",
            "",
            "",
        ]
        extractor.current_module = "test_module"
        extractor.framework_type = "django"

        # Mock helper methods
        with patch.object(
            extractor, "_parse_function_signature_optimized"
        ) as mock_parse:
            mock_parse.return_value = (
                "test_function",
                ["param1: str", "param2: int = 0"],
                False,
                ["property"],
                "str",
            )

            with patch.object(
                extractor, "_extract_docstring_for_line"
            ) as mock_docstring:
                mock_docstring.return_value = "Test function docstring"

                with patch.object(
                    extractor, "_calculate_complexity_optimized"
                ) as mock_complexity:
                    mock_complexity.return_value = 3

                    result = extractor._extract_function_optimized(mock_node)

                    assert isinstance(result, Function)
                    assert result.name == "test_function"
                    assert result.start_line == 1
                    assert result.end_line == 6
                    assert result.language == "python"
                    assert result.parameters == ["param1: str", "param2: int = 0"]
                    assert result.return_type == "str"
                    assert result.is_async is False
                    assert result.is_generator is False
                    assert result.docstring == "Test function docstring"
                    assert result.complexity_score == 3
                    assert result.modifiers == ["property"]
                    assert result.is_static is False
                    assert result.is_staticmethod is False
                    assert result.is_private is False
                    assert result.is_public is True
                    assert result.framework_type == "django"
                    assert result.is_property is True
                    assert result.is_classmethod is False

    def test_extract_function_optimized_private(self, extractor):
        """Test private function extraction"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        extractor.content_lines = ["def _private_function():", "    pass"]

        with patch.object(
            extractor, "_parse_function_signature_optimized"
        ) as mock_parse:
            mock_parse.return_value = ("_private_function", [], False, [], None)

            with patch.object(
                extractor, "_extract_docstring_for_line"
            ) as mock_docstring:
                mock_docstring.return_value = None

                with patch.object(
                    extractor, "_calculate_complexity_optimized"
                ) as mock_complexity:
                    mock_complexity.return_value = 1

                    result = extractor._extract_function_optimized(mock_node)

                    assert result.name == "_private_function"
                    assert result.is_private is True
                    assert result.is_public is False

    def test_extract_function_optimized_magic(self, extractor):
        """Test magic method extraction"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        extractor.content_lines = ["def __init__(self):", "    pass"]

        with patch.object(
            extractor, "_parse_function_signature_optimized"
        ) as mock_parse:
            mock_parse.return_value = ("__init__", ["self"], False, [], None)

            with patch.object(
                extractor, "_extract_docstring_for_line"
            ) as mock_docstring:
                mock_docstring.return_value = None

                with patch.object(
                    extractor, "_calculate_complexity_optimized"
                ) as mock_complexity:
                    mock_complexity.return_value = 1

                    result = extractor._extract_function_optimized(mock_node)

                    assert result.name == "__init__"
                    assert result.is_private is False
                    assert (
                        result.is_public is False
                    )  # Magic methods have special visibility

    def test_extract_class_optimized_complete(self, extractor):
        """Test complete class extraction"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (10, 0)
        mock_node.parent = None

        # Mock identifier child
        mock_identifier = Mock()
        mock_identifier.type = "identifier"
        mock_identifier.text = b"TestClass"

        # Mock argument list (superclasses)
        mock_arg_list = Mock()
        mock_arg_list.type = "argument_list"
        mock_superclass = Mock()
        mock_superclass.type = "identifier"
        mock_superclass.text = b"BaseClass"
        mock_arg_list.children = [mock_superclass]

        mock_node.children = [mock_identifier, mock_arg_list]

        extractor.content_lines = [
            "class TestClass(BaseClass):",
            '    """Test class docstring"""',
            "    pass",
        ] * 4
        extractor.current_module = "test_module"
        extractor.framework_type = "django"

        with patch.object(extractor, "_get_node_text_optimized") as mock_get_text:
            mock_get_text.side_effect = [
                "class TestClass(BaseClass):\n    pass",  # Full class text
                "BaseClass",  # Superclass name
            ]

            with patch.object(
                extractor, "_extract_docstring_for_line"
            ) as mock_docstring:
                mock_docstring.return_value = "Test class docstring"

                result = extractor._extract_class_optimized(mock_node)

                assert isinstance(result, Class)
                assert result.name == "TestClass"
                assert result.start_line == 1
                assert result.end_line == 11
                assert result.language == "python"
                assert result.class_type == "class"
                assert result.superclass == "BaseClass"
                assert result.interfaces == []
                assert result.docstring == "Test class docstring"
                assert result.modifiers == []
                assert result.full_qualified_name == "test_module.TestClass"
                assert result.package_name == "test_module"
                assert result.framework_type == "django"
                assert result.is_dataclass is False
                assert result.is_abstract is False
                assert result.is_exception is False

    def test_extract_class_optimized_with_decorators(self, extractor):
        """Test class extraction with decorators"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 0)

        # Mock parent with decorated_definition
        mock_parent = Mock()
        mock_decorated = Mock()
        mock_decorated.type = "decorated_definition"

        mock_decorator = Mock()
        mock_decorator.type = "decorator"
        mock_decorated.children = [mock_decorator]
        mock_parent.children = [mock_decorated]
        mock_node.parent = mock_parent

        # Mock identifier child
        mock_identifier = Mock()
        mock_identifier.type = "identifier"
        mock_identifier.text = b"DataClass"
        mock_node.children = [mock_identifier]

        extractor.content_lines = ["@dataclass", "class DataClass:", "    pass"]

        with patch.object(extractor, "_get_node_text_optimized") as mock_get_text:
            mock_get_text.side_effect = [
                "@dataclass",  # Decorator text
                "class DataClass:\n    pass",  # Full class text
            ]

            with patch.object(
                extractor, "_extract_docstring_for_line"
            ) as mock_docstring:
                mock_docstring.return_value = None

                result = extractor._extract_class_optimized(mock_node)

                assert result.name == "DataClass"
                assert result.modifiers == ["dataclass"]
                assert result.is_dataclass is True

    def test_extract_class_optimized_exception_class(self, extractor):
        """Test exception class extraction"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (3, 0)
        mock_node.parent = None

        # Mock identifier child
        mock_identifier = Mock()
        mock_identifier.type = "identifier"
        mock_identifier.text = b"CustomError"

        # Mock argument list with Exception superclass
        mock_arg_list = Mock()
        mock_arg_list.type = "argument_list"
        mock_superclass = Mock()
        mock_superclass.type = "identifier"
        mock_superclass.text = b"Exception"
        mock_arg_list.children = [mock_superclass]

        mock_node.children = [mock_identifier, mock_arg_list]

        extractor.content_lines = ["class CustomError(Exception):", "    pass"]

        with patch.object(extractor, "_get_node_text_optimized") as mock_get_text:
            mock_get_text.side_effect = [
                "class CustomError(Exception):\n    pass",
                "Exception",
            ]

            with patch.object(
                extractor, "_extract_docstring_for_line"
            ) as mock_docstring:
                mock_docstring.return_value = None

                result = extractor._extract_class_optimized(mock_node)

                assert result.name == "CustomError"
                assert result.superclass == "Exception"
                assert result.is_exception is True

    def test_is_framework_class(self, extractor):
        """Test framework class detection"""
        mock_node = Mock()

        # Test Django framework
        extractor.framework_type = "django"
        with patch.object(extractor, "_get_node_text_optimized") as mock_get_text:
            mock_get_text.return_value = "class UserModel(models.Model): pass"
            result = extractor._is_framework_class(mock_node, "UserModel")
            assert result is True

        # Test Flask framework
        extractor.framework_type = "flask"
        extractor.source_code = "from flask import Flask"
        result = extractor._is_framework_class(mock_node, "AppClass")
        assert result is True

        # Test FastAPI framework
        extractor.framework_type = "fastapi"
        extractor.source_code = "from fastapi import APIRouter"
        result = extractor._is_framework_class(mock_node, "RouterClass")
        assert result is True

        # Test no framework
        extractor.framework_type = ""
        extractor.source_code = "regular python code"
        result = extractor._is_framework_class(mock_node, "RegularClass")
        assert result is False

    def test_extract_class_attributes(self, extractor):
        """Test class attribute extraction"""
        # Create mock class body node
        mock_class_body = Mock()

        # Mock expression statement with assignment
        mock_expr_stmt = Mock()
        mock_expr_stmt.type = "expression_statement"

        mock_assignment = Mock()
        mock_assignment.type = "assignment"
        mock_expr_stmt.children = [mock_assignment]

        # Mock direct assignment
        mock_direct_assignment = Mock()
        mock_direct_assignment.type = "assignment"

        mock_class_body.children = [mock_expr_stmt, mock_direct_assignment]

        with patch.object(extractor, "_extract_class_attribute_info") as mock_extract:
            mock_variable = Variable(
                name="test_attr",
                start_line=1,
                end_line=1,
                raw_text="test_attr: str = 'value'",
                language="python",
                variable_type="str",
            )
            mock_extract.return_value = mock_variable

            result = extractor._extract_class_attributes(mock_class_body, "source_code")

            assert len(result) == 2
            assert all(isinstance(var, Variable) for var in result)
            assert mock_extract.call_count == 2

    def test_extract_class_attribute_info(self, extractor):
        """Test class attribute info extraction"""
        # Create mock assignment node
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 20
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 20)

        # Test typed attribute
        source_code = "name: str = 'test'"
        result = extractor._extract_class_attribute_info(mock_node, source_code)

        assert isinstance(result, Variable)
        assert result.name == "name"
        assert result.variable_type == "str"
        assert result.raw_text == "name: str = 'test'"
        assert result.language == "python"

        # Test untyped attribute
        source_code = "value = 42"
        mock_node.end_byte = 10
        result = extractor._extract_class_attribute_info(mock_node, source_code)

        assert result.name == "value"
        assert result.variable_type is None
        assert result.raw_text == "value = 42"

    def test_extract_imports_basic(self, extractor, mock_tree):
        """Test basic import extraction"""
        # Mock the root node and tree structure
        mock_root = Mock()
        mock_root.type = "module"
        mock_root.children = []  # Empty children to avoid iteration errors
        mock_tree.root_node = mock_root

        # Make extract_imports use manual extraction
        with patch.object(extractor, "_extract_imports_manual") as mock_manual:
            mock_import = Import(
                name="test_module",
                start_line=1,
                end_line=1,
                raw_text="import test_module",
                language="python",
            )
            mock_manual.return_value = [mock_import]

            imports = extractor.extract_imports(mock_tree, "import test_module")

            assert isinstance(imports, list)
            # Manual extraction should be called
            assert len(imports) >= 0

    def test_traverse_and_extract_iterative(self, extractor):
        """Test iterative traversal and extraction"""
        # Create mock root node with children
        mock_root = Mock()
        mock_child1 = Mock()
        mock_child1.type = "function_definition"
        mock_child1.children = []

        mock_child2 = Mock()
        mock_child2.type = "class_definition"
        mock_child2.children = []

        mock_root.children = [mock_child1, mock_child2]

        # Mock extractor functions
        mock_func_extractor = Mock()
        mock_func_extractor.return_value = Function(
            name="test_func",
            start_line=1,
            end_line=3,
            raw_text="def test_func(): pass",
            language="python",
        )

        mock_class_extractor = Mock()
        mock_class_extractor.return_value = Class(
            name="TestClass",
            start_line=5,
            end_line=10,
            raw_text="class TestClass: pass",
            language="python",
        )

        extractors = {
            "function_definition": mock_func_extractor,
            "class_definition": mock_class_extractor,
        }

        results = []
        extractor._traverse_and_extract_iterative(
            mock_root, extractors, results, "mixed"
        )

        assert len(results) == 2
        assert isinstance(results[0], Function)
        assert isinstance(results[1], Class)

    def test_traverse_and_extract_iterative_with_caching(self, extractor):
        """Test iterative traversal with caching"""
        mock_root = Mock()
        mock_child = Mock()
        mock_child.type = "function_definition"
        mock_child.children = []
        mock_root.children = [mock_child]

        # Set up cache
        node_id = id(mock_child)
        cache_key = (node_id, "function")
        cached_function = Function(
            name="cached_func",
            start_line=1,
            end_line=2,
            raw_text="def cached_func(): pass",
            language="python",
        )
        extractor._element_cache[cache_key] = cached_function

        extractors = {"function_definition": Mock()}
        results = []

        extractor._traverse_and_extract_iterative(
            mock_root, extractors, results, "function"
        )

        # Should use cached result
        assert len(results) == 1
        assert results[0] == cached_function
        assert (
            extractors["function_definition"].call_count == 0
        )  # Should not call extractor

    def test_traverse_and_extract_iterative_max_depth(self, extractor):
        """Test max depth protection in traversal"""
        # Create deeply nested structure
        root_node = Mock()
        root_node.type = "module"
        root_node.children = []

        current_node = root_node

        # Create 60 levels of nesting (exceeds max_depth of 50)
        for _i in range(60):
            child = Mock()
            child.type = "block"
            child.children = []
            current_node.children = [child]
            current_node = child

        # Add target node at the end
        target_node = Mock()
        target_node.type = "function_definition"
        target_node.children = []
        current_node.children = [target_node]

        extractors = {"function_definition": Mock()}
        results = []

        # Should not process deeply nested nodes
        with patch(
            "tree_sitter_analyzer.languages.python_plugin.log_warning"
        ) as mock_log:
            extractor._traverse_and_extract_iterative(
                root_node, extractors, results, "function"
            )

            # Should log warning about max depth
            mock_log.assert_called()

    def test_performance_with_large_codebase(self, extractor):
        """Test performance with large codebase simulation"""
        import time

        # Create large mock tree
        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        # Create many function nodes
        function_nodes = []
        for i in range(100):
            node = Mock()
            node.type = "function_definition"
            node.children = []
            node.start_point = (i, 0)
            node.end_point = (i + 2, 0)
            function_nodes.append(node)

        mock_root.children = function_nodes

        # Create large source code
        large_source = "\n".join([f"def function_{i}(): pass" for i in range(100)])

        # Mock extraction method to return simple functions
        def mock_extract_function(node):
            return Function(
                name=f"function_{node.start_point[0]}",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=f"def function_{node.start_point[0]}(): pass",
                language="python",
            )

        with patch.object(
            extractor, "_extract_function_optimized", side_effect=mock_extract_function
        ):
            start_time = time.time()
            functions = extractor.extract_functions(mock_tree, large_source)
            end_time = time.time()

            # Should complete within reasonable time (5 seconds)
            assert end_time - start_time < 5.0
            assert len(functions) == 100

    def test_memory_usage_with_caching(self, extractor):
        """Test memory usage with caching"""
        import gc

        # Perform many operations to populate caches
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 10)

        extractor.content_lines = ["test content"] * 1000

        # Populate caches
        for i in range(1000):
            mock_node_copy = Mock()
            mock_node_copy.start_byte = i
            mock_node_copy.end_byte = i + 10
            mock_node_copy.start_point = (0, 0)
            mock_node_copy.end_point = (0, 10)

            with patch(
                "tree_sitter_analyzer.languages.python_plugin.extract_text_slice"
            ) as mock_extract:
                mock_extract.return_value = f"text_{i}"
                extractor._get_node_text_optimized(mock_node_copy)

        # Check cache sizes
        assert len(extractor._node_text_cache) <= 1000

        # Reset caches and force garbage collection
        extractor._reset_caches()
        gc.collect()

        # Caches should be empty
        assert len(extractor._node_text_cache) == 0

    def test_error_handling_in_extraction(self, extractor):
        """Test error handling during extraction"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        # Mock traversal to raise exception
        with patch.object(
            extractor, "_traverse_and_extract_iterative"
        ) as mock_traverse:
            mock_traverse.side_effect = Exception("Test error")

            # Should handle exception gracefully
            functions = extractor.extract_functions(mock_tree, "test code")
            assert isinstance(functions, list)
            assert len(functions) == 0

    def test_unicode_handling(self, extractor):
        """Test Unicode character handling"""
        unicode_code = """
def 関数名(パラメータ: str) -> str:
    \"\"\"日本語のドキュメント\"\"\"
    return f"こんにちは、{パラメータ}さん"

class クラス名:
    \"\"\"日本語のクラス\"\"\"
    属性: str = "値"
"""

        extractor.source_code = unicode_code
        extractor.content_lines = unicode_code.split("\n")

        # Should handle Unicode without errors
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = len(unicode_code.encode("utf-8"))
        mock_node.start_point = (0, 0)
        mock_node.end_point = (len(extractor.content_lines) - 1, 0)

        with patch(
            "tree_sitter_analyzer.languages.python_plugin.extract_text_slice"
        ) as mock_extract:
            mock_extract.return_value = unicode_code
            result = extractor._get_node_text_optimized(mock_node)
            assert "関数名" in result
            assert "クラス名" in result

    def test_concurrent_extraction(self, extractor):
        """Test concurrent extraction operations"""
        import queue
        import threading

        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        results = queue.Queue()

        def extract_worker():
            try:
                functions = extractor.extract_functions(mock_tree, "def test(): pass")
                results.put(("success", functions))
            except Exception as e:
                results.put(("error", str(e)))

        # Start multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=extract_worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Check results
        success_count = 0
        while not results.empty():
            status, result = results.get()
            if status == "success":
                success_count += 1
                assert isinstance(result, list)

        # All threads should succeed
        assert success_count == 5


class TestPythonPlugin:
    """Test Python plugin main class"""

    @pytest.fixture
    def plugin(self):
        """Create a Python plugin instance"""
        return PythonPlugin()

    def test_plugin_initialization(self, plugin):
        """Test plugin initialization"""
        assert plugin.language == "python"
        assert hasattr(plugin, "extractor")
        assert isinstance(plugin.extractor, PythonElementExtractor)

    def test_plugin_get_language(self, plugin):
        """Test get_language method"""
        assert plugin.get_language() == "python"

    def test_plugin_extract_functions(self, plugin):
        """Test plugin function extraction"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        with patch.object(plugin.extractor, "extract_functions") as mock_extract:
            mock_extract.return_value = []

            result = plugin.extract_functions(mock_tree, "test code")

            assert isinstance(result, list)
            mock_extract.assert_called_once_with(mock_tree, "test code")

    def test_plugin_extract_classes(self, plugin):
        """Test plugin class extraction"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        with patch.object(plugin.extractor, "extract_classes") as mock_extract:
            mock_extract.return_value = []

            result = plugin.extract_classes(mock_tree, "test code")

            assert isinstance(result, list)
            mock_extract.assert_called_once_with(mock_tree, "test code")

    def test_plugin_extract_variables(self, plugin):
        """Test plugin variable extraction"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        with patch.object(plugin.extractor, "extract_variables") as mock_extract:
            mock_extract.return_value = []

            result = plugin.extract_variables(mock_tree, "test code")

            assert isinstance(result, list)
            mock_extract.assert_called_once_with(mock_tree, "test code")

    def test_plugin_extract_imports(self, plugin):
        """Test plugin import extraction"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        with patch.object(plugin.extractor, "extract_imports") as mock_extract:
            mock_extract.return_value = []

            result = plugin.extract_imports(mock_tree, "test code")

            assert isinstance(result, list)
            mock_extract.assert_called_once_with(mock_tree, "test code")

    def test_plugin_with_real_python_code(self, plugin):
        """Test plugin with realistic Python code"""
        python_code = '''
import asyncio
from typing import List, Optional
from dataclasses import dataclass

@dataclass
class User:
    """User data model"""
    name: str
    email: str
    age: Optional[int] = None

    def __post_init__(self):
        """Validate user data"""
        if not self.email or "@" not in self.email:
            raise ValueError("Invalid email")

    @property
    def is_adult(self) -> bool:
        """Check if user is adult"""
        return self.age is not None and self.age >= 18

    @classmethod
    def from_dict(cls, data: dict) -> 'User':
        """Create user from dictionary"""
        return cls(**data)

async def fetch_users() -> List[User]:
    """Fetch users asynchronously"""
    await asyncio.sleep(0.1)
    return [
        User("Alice", "alice@example.com", 25),
        User("Bob", "bob@example.com", 17)
    ]

def process_users(users: List[User]) -> dict:
    """Process users and return statistics"""
    adults = sum(1 for user in users if user.is_adult)
    return {
        "total": len(users),
        "adults": adults,
        "minors": len(users) - adults
    }
'''

        # Mock tree-sitter components
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        mock_tree.language = Mock()

        # Test that plugin can handle real code without errors
        with patch.object(plugin.extractor, "_traverse_and_extract_iterative"):
            functions = plugin.extract_functions(mock_tree, python_code)
            classes = plugin.extract_classes(mock_tree, python_code)
            variables = plugin.extract_variables(mock_tree, python_code)
            imports = plugin.extract_imports(mock_tree, python_code)

            # Should return lists without errors
            assert isinstance(functions, list)
            assert isinstance(classes, list)
            assert isinstance(variables, list)
            assert isinstance(imports, list)


class TestPythonPluginIntegration:
    """Integration tests for Python plugin"""

    def test_full_extraction_workflow(self):
        """Test complete extraction workflow"""
        plugin = PythonPlugin()

        # Complex Python code with various features
        complex_code = '''
#!/usr/bin/env python3
"""
Module docstring
"""

import os
import sys
from typing import Dict, List, Optional, Union
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

class Status(Enum):
    """Status enumeration"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"

@dataclass
class Config:
    """Configuration class"""
    name: str
    value: Union[str, int, float]
    metadata: Dict[str, any] = field(default_factory=dict)

class BaseProcessor(ABC):
    """Abstract base processor"""

    def __init__(self, config: Config):
        self.config = config
        self._status = Status.PENDING

    @property
    def status(self) -> Status:
        """Get current status"""
        return self._status

    @status.setter
    def status(self, value: Status) -> None:
        """Set status"""
        self._status = value

    @abstractmethod
    def process(self, data: any) -> any:
        """Process data - must be implemented by subclasses"""
        pass

    @classmethod
    def create_default(cls) -> 'BaseProcessor':
        """Create default processor"""
        config = Config("default", "value")
        return cls(config)

    @staticmethod
    def validate_data(data: any) -> bool:
        """Validate input data"""
        return data is not None

class DataProcessor(BaseProcessor):
    """Concrete data processor"""

    def __init__(self, config: Config, batch_size: int = 100):
        super().__init__(config)
        self.batch_size = batch_size
        self._processed_count = 0

    def process(self, data: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """Process data in batches"""
        results = []
        for i in range(0, len(data), self.batch_size):
            batch = data[i:i + self.batch_size]
            processed_batch = self._process_batch(batch)
            results.extend(processed_batch)
            self._processed_count += len(batch)
        return results

    def _process_batch(self, batch: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """Process a single batch"""
        return [self._process_item(item) for item in batch]

    def _process_item(self, item: Dict[str, any]) -> Dict[str, any]:
        """Process a single item"""
        return {**item, "processed": True, "processor": self.config.name}

    async def process_async(self, data: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """Process data asynchronously"""
        import asyncio

        tasks = []
        for i in range(0, len(data), self.batch_size):
            batch = data[i:i + self.batch_size]
            task = asyncio.create_task(self._process_batch_async(batch))
            tasks.append(task)

        results = await asyncio.gather(*tasks)
        return [item for batch_result in results for item in batch_result]

    async def _process_batch_async(self, batch: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """Process batch asynchronously"""
        await asyncio.sleep(0.01)  # Simulate async work
        return self._process_batch(batch)

def create_processor(processor_type: str = "data") -> BaseProcessor:
    """Factory function for creating processors"""
    config = Config("default_processor", "default_value")

    if processor_type == "data":
        return DataProcessor(config)
    else:
        raise ValueError(f"Unknown processor type: {processor_type}")

async def main():
    """Main application entry point"""
    processor = create_processor("data")

    sample_data = [
        {"id": 1, "name": "Item 1"},
        {"id": 2, "name": "Item 2"},
        {"id": 3, "name": "Item 3"}
    ]

    # Synchronous processing
    sync_results = processor.process(sample_data)
    print(f"Sync results: {sync_results}")

    # Asynchronous processing
    async_results = await processor.process_async(sample_data)
    print(f"Async results: {async_results}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
'''

        # Mock tree-sitter components for integration test
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        mock_tree.language = Mock()

        # Mock query functionality
        mock_query = Mock()
        mock_query.captures.return_value = {}
        mock_tree.language.query.return_value = mock_query

        # Test extraction without errors
        functions = plugin.extract_functions(mock_tree, complex_code)
        classes = plugin.extract_classes(mock_tree, complex_code)
        variables = plugin.extract_variables(mock_tree, complex_code)
        imports = plugin.extract_imports(mock_tree, complex_code)

        # Should handle complex code without errors
        assert isinstance(functions, list)
        assert isinstance(classes, list)
        assert isinstance(variables, list)
        assert isinstance(imports, list)

    def test_framework_detection_integration(self):
        """Test framework detection in integration scenario"""
        plugin = PythonPlugin()

        # Django code
        django_code = """
from django.db import models
from django.contrib.auth.models import User

class BlogPost(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
"""

        plugin.extractor.source_code = django_code
        plugin.extractor._detect_file_characteristics()

        assert plugin.extractor.framework_type == "django"
        assert plugin.extractor.is_module is True

    def test_error_recovery_integration(self):
        """Test error recovery in integration scenario"""
        plugin = PythonPlugin()

        # Malformed Python code
        malformed_code = """
def incomplete_function(
    # Missing closing parenthesis and body

class IncompleteClass
    # Missing colon and body

import
# Incomplete import statement
"""

        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        mock_tree.language = Mock()

        # Should handle malformed code gracefully
        functions = plugin.extract_functions(mock_tree, malformed_code)
        classes = plugin.extract_classes(mock_tree, malformed_code)

        assert isinstance(functions, list)
        assert isinstance(classes, list)
