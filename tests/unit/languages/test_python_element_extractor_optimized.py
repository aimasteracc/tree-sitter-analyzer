"""Python element extractor optimized extraction tests."""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.python_plugin import PythonElementExtractor
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
            assert imports
