"""
Test Python language parser implementation.

Following TDD: Write tests FIRST to define the contract.
This is T1.5: First Three Languages - Python
"""


class TestPythonParserBasics:
    """Test basic Python parser functionality."""

    def test_parser_can_be_imported(self):
        """Test that PythonParser can be imported."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        assert PythonParser is not None

    def test_parser_initialization(self):
        """Test creating a parser instance."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        assert parser is not None

    def test_parse_simple_code(self):
        """Test parsing simple Python code."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = "x = 1"

        result = parser.parse(code)

        assert result is not None
        assert "ast" in result
        assert "metadata" in result


class TestPythonFunctionExtraction:
    """Test extracting functions from Python code."""

    def test_extract_simple_function(self):
        """Test extracting a simple function."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = """
def hello():
    print("Hello, World!")
"""

        result = parser.parse(code)

        assert "functions" in result
        assert len(result["functions"]) == 1

        func = result["functions"][0]
        assert func["name"] == "hello"
        assert func["parameters"] == []

    def test_extract_function_with_parameters(self):
        """Test extracting function with parameters."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = """
def greet(name, greeting="Hello"):
    print(f"{greeting}, {name}!")
"""

        result = parser.parse(code)
        func = result["functions"][0]

        assert func["name"] == "greet"
        assert len(func["parameters"]) == 2
        assert "name" in func["parameters"]
        assert "greeting" in func["parameters"]

    def test_extract_function_with_type_hints(self):
        """Test extracting function with type hints."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = """
def add(a: int, b: int) -> int:
    return a + b
"""

        result = parser.parse(code)
        func = result["functions"][0]

        assert func["name"] == "add"
        assert func["return_type"] == "int"

    def test_extract_multiple_functions(self):
        """Test extracting multiple functions."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = """
def foo():
    pass

def bar():
    pass

def baz():
    pass
"""

        result = parser.parse(code)

        assert len(result["functions"]) == 3
        names = [f["name"] for f in result["functions"]]
        assert "foo" in names
        assert "bar" in names
        assert "baz" in names


class TestPythonClassExtraction:
    """Test extracting classes from Python code."""

    def test_extract_simple_class(self):
        """Test extracting a simple class."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = """
class Calculator:
    pass
"""

        result = parser.parse(code)

        assert "classes" in result
        assert len(result["classes"]) == 1

        cls = result["classes"][0]
        assert cls["name"] == "Calculator"

    def test_extract_class_with_methods(self):
        """Test extracting class with methods."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = """
class Calculator:
    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b
"""

        result = parser.parse(code)
        cls = result["classes"][0]

        assert cls["name"] == "Calculator"
        assert "methods" in cls
        assert len(cls["methods"]) == 2

        method_names = [m["name"] for m in cls["methods"]]
        assert "add" in method_names
        assert "subtract" in method_names

    def test_extract_class_with_inheritance(self):
        """Test extracting class with base classes."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = """
class Animal:
    pass

class Dog(Animal):
    pass
"""

        result = parser.parse(code)

        assert len(result["classes"]) == 2

        dog_class = next(c for c in result["classes"] if c["name"] == "Dog")
        assert "bases" in dog_class
        assert "Animal" in dog_class["bases"]

    def test_extract_class_with_docstring(self):
        """Test extracting class with docstring."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = '''
class Calculator:
    """A simple calculator class."""

    def add(self, a, b):
        """Add two numbers."""
        return a + b
'''

        result = parser.parse(code)
        cls = result["classes"][0]

        assert "docstring" in cls
        assert "calculator" in cls["docstring"].lower()


class TestPythonImportExtraction:
    """Test extracting imports from Python code."""

    def test_extract_simple_import(self):
        """Test extracting simple import statement."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = """
import os
import sys
"""

        result = parser.parse(code)

        assert "imports" in result
        assert len(result["imports"]) == 2

        import_names = [imp["module"] for imp in result["imports"]]
        assert "os" in import_names
        assert "sys" in import_names

    def test_extract_from_import(self):
        """Test extracting from...import statement."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = """
from pathlib import Path
from typing import Optional, List
"""

        result = parser.parse(code)

        assert len(result["imports"]) == 2

        pathlib_import = next(imp for imp in result["imports"] if imp["module"] == "pathlib")
        assert "names" in pathlib_import
        assert "Path" in pathlib_import["names"]

    def test_extract_aliased_import(self):
        """Test extracting import with alias."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = """
import numpy as np
from typing import Dict as D
"""

        result = parser.parse(code)

        np_import = next(imp for imp in result["imports"] if imp["module"] == "numpy")
        assert "alias" in np_import
        assert np_import["alias"] == "np"


class TestPythonMetadata:
    """Test metadata extraction."""

    def test_metadata_includes_line_numbers(self):
        """Test that extracted items include line numbers."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = """
import os

def hello():
    pass

class Foo:
    pass
"""

        result = parser.parse(code)

        # Functions should have line numbers
        func = result["functions"][0]
        assert "line_start" in func
        assert "line_end" in func
        assert func["line_start"] > 0

        # Classes should have line numbers
        cls = result["classes"][0]
        assert "line_start" in cls
        assert "line_end" in cls

    def test_metadata_includes_complexity(self):
        """Test that metadata includes complexity metrics."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = """
def complex_function(x):
    if x > 0:
        if x > 10:
            return "large"
        else:
            return "small"
    else:
        return "negative"
"""

        result = parser.parse(code)

        assert "metadata" in result
        # Should track some complexity metric
        assert "total_functions" in result["metadata"]
        assert result["metadata"]["total_functions"] == 1


class TestPythonEdgeCases:
    """Test edge cases and error handling."""

    def test_parse_empty_file(self):
        """Test parsing empty Python file."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        result = parser.parse("")

        assert result is not None
        assert result["functions"] == []
        assert result["classes"] == []
        assert result["imports"] == []

    def test_parse_syntax_error(self):
        """Test parsing code with syntax errors."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = "def broken("

        result = parser.parse(code)

        # Should still return result, but mark errors
        assert result is not None
        assert "errors" in result
        assert result["errors"] is True

    def test_parse_nested_classes(self):
        """Test parsing nested classes."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = """
class Outer:
    class Inner:
        pass
"""

        result = parser.parse(code)

        # Should extract both classes
        assert len(result["classes"]) >= 1
        assert any(c["name"] == "Outer" for c in result["classes"])


class TestPythonEnhancements:
    """Tests for enhanced Python features (T7.1)."""

    def test_extract_decorators(self):
        """Test extracting function decorators."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = """
@decorator1
@decorator2(arg="value")
def my_function():
    pass
"""

        result = parser.parse(code)

        assert len(result["functions"]) == 1
        func = result["functions"][0]
        assert func["name"] == "my_function"
        assert "decorators" in func
        assert len(func["decorators"]) == 2
        assert "decorator1" in func["decorators"]
        assert "decorator2" in func["decorators"]

    def test_extract_class_decorators(self):
        """Test extracting class decorators."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = """
@dataclass
@frozen
class MyClass:
    pass
"""

        result = parser.parse(code)

        assert len(result["classes"]) == 1
        cls = result["classes"][0]
        assert cls["name"] == "MyClass"
        assert "decorators" in cls
        assert len(cls["decorators"]) == 2
        assert "dataclass" in cls["decorators"]
        assert "frozen" in cls["decorators"]

    def test_extract_class_attributes(self):
        """Test extracting class-level attributes."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = """
class MyClass:
    class_var = "value"
    count = 0

    def __init__(self):
        self.instance_var = "instance"
"""

        result = parser.parse(code)

        assert len(result["classes"]) == 1
        cls = result["classes"][0]
        assert "attributes" in cls
        # Should extract class-level attributes
        assert len(cls["attributes"]) >= 2
        attr_names = [a["name"] for a in cls["attributes"]]
        assert "class_var" in attr_names
        assert "count" in attr_names

    def test_detect_async_function(self):
        """Test detecting async functions."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = """
async def async_function():
    await something()
    return result

def sync_function():
    return result
"""

        result = parser.parse(code)

        assert len(result["functions"]) == 2

        async_func = next(f for f in result["functions"] if f["name"] == "async_function")
        sync_func = next(f for f in result["functions"] if f["name"] == "sync_function")

        assert "is_async" in async_func
        assert async_func["is_async"] is True

        assert "is_async" in sync_func
        assert sync_func["is_async"] is False

    def test_detect_main_block(self):
        """Test detecting if __name__ == '__main__' block."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = """
def helper():
    pass

if __name__ == "__main__":
    main()
    print("Running as script")
"""

        result = parser.parse(code)

        # Should detect main block
        assert "has_main_block" in result["metadata"]
        assert result["metadata"]["has_main_block"] is True

    def test_no_main_block(self):
        """Test file without main block."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = """
def helper():
    pass

class MyClass:
    pass
"""

        result = parser.parse(code)

        # Should not detect main block
        assert "has_main_block" in result["metadata"]
        assert result["metadata"]["has_main_block"] is False

    def test_async_class_method(self):
        """Test detecting async methods in classes."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = """
class MyClass:
    async def async_method(self):
        await something()
        return result

    def sync_method(self):
        return result
"""

        result = parser.parse(code)

        assert len(result["classes"]) == 1
        cls = result["classes"][0]
        assert len(cls["methods"]) == 2

        async_method = next(m for m in cls["methods"] if m["name"] == "async_method")
        sync_method = next(m for m in cls["methods"] if m["name"] == "sync_method")

        assert "is_async" in async_method
        assert async_method["is_async"] is True

        assert "is_async" in sync_method
        assert sync_method["is_async"] is False

    def test_property_decorator(self):
        """Test extracting @property decorators."""
        from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

        parser = PythonParser()
        code = """
class MyClass:
    @property
    def my_property(self):
        return self._value

    @my_property.setter
    def my_property(self, value):
        self._value = value
"""

        result = parser.parse(code)

        assert len(result["classes"]) == 1
        cls = result["classes"][0]
        assert len(cls["methods"]) == 2

        # Both methods should have decorators
        for method in cls["methods"]:
            assert "decorators" in method
            assert len(method["decorators"]) > 0
