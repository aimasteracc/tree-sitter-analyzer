"""Python element extractor core tests."""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.python_plugin import PythonElementExtractor


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
            "tree_sitter_analyzer.languages.python_plugin.extractor.extract_text_slice"
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
            "tree_sitter_analyzer.languages.python_plugin.extractor.extract_text_slice"
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

