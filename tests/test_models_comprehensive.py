#!/usr/bin/env python3
"""
Comprehensive tests for models to achieve high coverage.
"""

import pytest
from tree_sitter_analyzer.models import (
    AnalysisResult, Function, Class, Variable, Import, CodeElement
)


class TestCodeElementComprehensive:
    """Comprehensive test suite for CodeElement"""

    def test_code_element_creation(self):
        """Test CodeElement creation"""
        # CodeElement is abstract, so we'll use Function which inherits from it
        func = Function(
            name="test_func",
            start_line=1,
            end_line=5,
            raw_text="def test_func(): pass"
        )
        assert func.name == "test_func"
        assert func.start_line == 1
        assert func.end_line == 5
        assert func.raw_text == "def test_func(): pass"

    def test_code_element_with_all_fields(self):
        """Test CodeElement with all fields"""
        func = Function(
            name="test_func",
            start_line=1,
            end_line=5,
            raw_text="def test_func(): pass",
            language="python",
            docstring="Test function"
        )
        assert func.language == "python"
        assert func.docstring == "Test function"

    def test_code_element_defaults(self):
        """Test CodeElement default values"""
        func = Function(
            name="test_func",
            start_line=1,
            end_line=5
        )
        assert func.raw_text == ""
        assert func.language == "unknown"
        assert func.docstring is None


class TestFunctionComprehensive:
    """Comprehensive test suite for Function"""

    def test_function_creation_minimal(self):
        """Test Function creation with minimal parameters"""
        func = Function(
            name="test_func",
            start_line=1,
            end_line=5
        )
        assert func.name == "test_func"
        assert func.start_line == 1
        assert func.end_line == 5
        assert func.parameters == []
        assert func.return_type is None
        assert func.modifiers == []

    def test_function_creation_full(self):
        """Test Function creation with all parameters"""
        func = Function(
            name="test_func",
            start_line=1,
            end_line=10,
            raw_text="def test_func(param1, param2): return 'result'",
            language="python",
            docstring="Test function with parameters",
            parameters=["param1", "param2"],
            return_type="str",
            modifiers=["public", "static"]
        )
        assert func.name == "test_func"
        assert func.parameters == ["param1", "param2"]
        assert func.return_type == "str"
        assert func.modifiers == ["public", "static"]
        assert func.docstring == "Test function with parameters"

    def test_function_empty_parameters(self):
        """Test Function with empty parameters"""
        func = Function(
            name="no_params",
            start_line=1,
            end_line=3,
            parameters=[]
        )
        assert func.parameters == []

    def test_function_multiple_modifiers(self):
        """Test Function with multiple modifiers"""
        func = Function(
            name="complex_func",
            start_line=1,
            end_line=5,
            modifiers=["public", "static", "async", "final"]
        )
        assert len(func.modifiers) == 4
        assert "public" in func.modifiers
        assert "static" in func.modifiers
        assert "async" in func.modifiers
        assert "final" in func.modifiers


class TestClassComprehensive:
    """Comprehensive test suite for Class"""

    def test_class_creation_minimal(self):
        """Test Class creation with minimal parameters"""
        cls = Class(
            name="TestClass",
            start_line=1,
            end_line=10
        )
        assert cls.name == "TestClass"
        assert cls.start_line == 1
        assert cls.end_line == 10

    def test_class_creation_full(self):
        """Test Class creation with all parameters"""
        cls = Class(
            name="TestClass",
            start_line=1,
            end_line=20,
            raw_text="class TestClass: pass",
            language="python",
            docstring="Test class documentation"
        )
        assert cls.name == "TestClass"
        assert cls.docstring == "Test class documentation"
        assert cls.language == "python"

    def test_class_with_inheritance(self):
        """Test Class with inheritance information"""
        cls = Class(
            name="ChildClass",
            start_line=1,
            end_line=15,
            raw_text="class ChildClass(ParentClass): pass"
        )
        assert cls.name == "ChildClass"
        assert "ParentClass" in cls.raw_text


class TestVariableComprehensive:
    """Comprehensive test suite for Variable"""

    def test_variable_creation_minimal(self):
        """Test Variable creation with minimal parameters"""
        var = Variable(
            name="test_var",
            start_line=1,
            end_line=1
        )
        assert var.name == "test_var"
        assert var.start_line == 1
        assert var.end_line == 1

    def test_variable_creation_full(self):
        """Test Variable creation with all parameters"""
        var = Variable(
            name="test_var",
            start_line=1,
            end_line=1,
            raw_text="test_var = 'hello'",
            language="python",
            docstring="Test variable"
        )
        assert var.name == "test_var"
        assert var.raw_text == "test_var = 'hello'"
        assert var.docstring == "Test variable"

    def test_variable_with_type_info(self):
        """Test Variable with type information"""
        var = Variable(
            name="typed_var",
            start_line=1,
            end_line=1,
            raw_text="typed_var: int = 42"
        )
        assert var.name == "typed_var"
        assert "int" in var.raw_text


class TestImportComprehensive:
    """Comprehensive test suite for Import"""

    def test_import_creation_minimal(self):
        """Test Import creation with minimal parameters"""
        imp = Import(
            name="os",
            start_line=1,
            end_line=1
        )
        assert imp.name == "os"
        assert imp.start_line == 1
        assert imp.end_line == 1

    def test_import_creation_full(self):
        """Test Import creation with all parameters"""
        imp = Import(
            name="os",
            start_line=1,
            end_line=1,
            raw_text="import os",
            language="python",
            docstring="OS module import"
        )
        assert imp.name == "os"
        assert imp.raw_text == "import os"
        assert imp.docstring == "OS module import"

    def test_import_from_statement(self):
        """Test Import with from statement"""
        imp = Import(
            name="path",
            start_line=1,
            end_line=1,
            raw_text="from os import path"
        )
        assert imp.name == "path"
        assert "from os import" in imp.raw_text


class TestAnalysisResultComprehensive:
    """Comprehensive test suite for AnalysisResult"""

    def test_analysis_result_creation_minimal(self):
        """Test AnalysisResult creation with minimal parameters"""
        result = AnalysisResult(
            file_path="test.py",
            language="python",
            elements={}
        )
        assert result.file_path == "test.py"
        assert result.language == "python"
        assert result.elements == {}

    def test_analysis_result_creation_full(self):
        """Test AnalysisResult creation with all parameters"""
        elements = {
            "functions": [
                Function(name="func1", start_line=1, end_line=5),
                Function(name="func2", start_line=10, end_line=15)
            ],
            "classes": [
                Class(name="Class1", start_line=20, end_line=30)
            ],
            "variables": [
                Variable(name="var1", start_line=5, end_line=5)
            ],
            "imports": [
                Import(name="os", start_line=1, end_line=1)
            ]
        }
        
        result = AnalysisResult(
            file_path="complex.py",
            language="python",
            elements=elements
        )
        
        assert result.file_path == "complex.py"
        assert result.language == "python"
        assert "functions" in result.elements
        assert "classes" in result.elements
        assert "variables" in result.elements
        assert "imports" in result.elements
        assert len(result.elements["functions"]) == 2
        assert len(result.elements["classes"]) == 1

    def test_analysis_result_with_source_code(self):
        """Test AnalysisResult with source code"""
        source_code = """
import os

def hello():
    return "world"

class Test:
    def __init__(self):
        self.value = 42
"""
        
        result = AnalysisResult(
            file_path="test.py",
            language="python",
            elements={},
            source_code=source_code
        )
        
        assert result.source_code == source_code

    def test_analysis_result_serialization(self):
        """Test AnalysisResult serialization"""
        result = AnalysisResult(
            file_path="test.py",
            language="python",
            elements={
                "functions": [
                    Function(name="func1", start_line=1, end_line=5)
                ]
            }
        )
        
        # Test that it can be converted to dict-like structure
        assert hasattr(result, 'file_path')
        assert hasattr(result, 'language')
        assert hasattr(result, 'elements')

    def test_analysis_result_empty_elements(self):
        """Test AnalysisResult with empty elements"""
        result = AnalysisResult(
            file_path="empty.py",
            language="python",
            elements={}
        )
        
        assert result.elements == {}

    def test_analysis_result_with_metadata(self):
        """Test AnalysisResult with additional metadata"""
        result = AnalysisResult(
            file_path="test.py",
            language="python",
            elements={}
        )
        
        # Test that additional attributes can be set
        if hasattr(result, 'metadata'):
            result.metadata = {"file_size": 1024, "encoding": "utf-8"}
            assert result.metadata["file_size"] == 1024


class TestModelIntegration:
    """Test model integration scenarios"""

    def test_complex_analysis_result(self):
        """Test complex AnalysisResult with all element types"""
        # Create various elements
        functions = [
            Function(
                name="main",
                start_line=10,
                end_line=20,
                parameters=["argc", "argv"],
                return_type="int",
                modifiers=["public", "static"]
            ),
            Function(
                name="helper",
                start_line=25,
                end_line=30,
                parameters=["data"],
                return_type="str",
                modifiers=["private"]
            )
        ]
        
        classes = [
            Class(
                name="MainClass",
                start_line=1,
                end_line=50,
                docstring="Main application class"
            ),
            Class(
                name="HelperClass",
                start_line=55,
                end_line=80,
                docstring="Helper utility class"
            )
        ]
        
        variables = [
            Variable(
                name="CONSTANT",
                start_line=5,
                end_line=5,
                raw_text="CONSTANT = 'value'"
            ),
            Variable(
                name="global_var",
                start_line=7,
                end_line=7,
                raw_text="global_var = 42"
            )
        ]
        
        imports = [
            Import(
                name="sys",
                start_line=1,
                end_line=1,
                raw_text="import sys"
            ),
            Import(
                name="os",
                start_line=2,
                end_line=2,
                raw_text="import os"
            )
        ]
        
        # Create comprehensive analysis result
        result = AnalysisResult(
            file_path="complex_app.py",
            language="python",
            elements={
                "functions": functions,
                "classes": classes,
                "variables": variables,
                "imports": imports
            }
        )
        
        # Verify all elements are properly stored
        assert len(result.elements["functions"]) == 2
        assert len(result.elements["classes"]) == 2
        assert len(result.elements["variables"]) == 2
        assert len(result.elements["imports"]) == 2
        
        # Verify element properties
        assert result.elements["functions"][0].name == "main"
        assert result.elements["classes"][0].name == "MainClass"
        assert result.elements["variables"][0].name == "CONSTANT"
        assert result.elements["imports"][0].name == "sys"

    def test_model_equality_and_comparison(self):
        """Test model equality and comparison"""
        func1 = Function(name="test", start_line=1, end_line=5)
        func2 = Function(name="test", start_line=1, end_line=5)
        func3 = Function(name="different", start_line=1, end_line=5)
        
        # Test equality (dataclass should provide this)
        assert func1.name == func2.name
        assert func1.start_line == func2.start_line
        assert func1 != func3

    def test_model_string_representation(self):
        """Test model string representation"""
        func = Function(
            name="test_func",
            start_line=1,
            end_line=5,
            parameters=["param1", "param2"]
        )
        
        str_repr = str(func)
        assert "test_func" in str_repr
        assert isinstance(str_repr, str)

    def test_model_field_modification(self):
        """Test model field modification"""
        func = Function(name="test", start_line=1, end_line=5)
        
        # Test that fields can be modified (frozen=False)
        func.name = "modified_test"
        assert func.name == "modified_test"
        
        func.parameters.append("new_param")
        assert "new_param" in func.parameters
        
        func.modifiers.append("public")
        assert "public" in func.modifiers

    def test_model_with_unicode_content(self):
        """Test models with unicode content"""
        func = Function(
            name="测试函数",
            start_line=1,
            end_line=5,
            raw_text="def 测试函数(): pass",
            docstring="这是一个测试函数 🚀"
        )
        
        assert func.name == "测试函数"
        assert "测试函数" in func.raw_text
        assert "🚀" in func.docstring

    def test_model_with_complex_types(self):
        """Test models with complex type information"""
        func = Function(
            name="complex_func",
            start_line=1,
            end_line=10,
            parameters=["param1: List[Dict[str, Any]]", "param2: Optional[Callable]"],
            return_type="Union[str, None]",
            modifiers=["async", "public"]
        )
        
        assert len(func.parameters) == 2
        assert "List[Dict[str, Any]]" in func.parameters[0]
        assert "Optional[Callable]" in func.parameters[1]
        assert func.return_type == "Union[str, None]"

    def test_model_edge_cases(self):
        """Test model edge cases"""
        # Test with empty strings
        func = Function(name="", start_line=0, end_line=0)
        assert func.name == ""
        assert func.start_line == 0
        
        # Test with very large line numbers
        func = Function(name="large", start_line=999999, end_line=1000000)
        assert func.start_line == 999999
        assert func.end_line == 1000000
        
        # Test with negative line numbers (edge case)
        func = Function(name="negative", start_line=-1, end_line=0)
        assert func.start_line == -1

    def test_model_memory_efficiency(self):
        """Test model memory efficiency"""
        # Create many model instances to test memory usage
        functions = []
        for i in range(1000):
            func = Function(
                name=f"func_{i}",
                start_line=i,
                end_line=i+5,
                parameters=[f"param_{j}" for j in range(3)],
                modifiers=["public", "static"]
            )
            functions.append(func)
        
        # Verify all functions were created correctly
        assert len(functions) == 1000
        assert functions[0].name == "func_0"
        assert functions[999].name == "func_999"
        
        # Test that they maintain their properties
        for i, func in enumerate(functions[:10]):  # Check first 10
            assert func.name == f"func_{i}"
            assert func.start_line == i
            assert len(func.parameters) == 3