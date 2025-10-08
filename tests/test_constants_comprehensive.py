#!/usr/bin/env python3
"""
Comprehensive tests for constants module to achieve high coverage.
"""

import pytest
from tree_sitter_analyzer.constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_VARIABLE,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_PACKAGE,
    ELEMENT_TYPE_ANNOTATION,
    ELEMENT_TYPE_MAPPING,
    LEGACY_CLASS_MAPPING,
    get_element_type,
    is_element_of_type
)
from tree_sitter_analyzer.models import Function, Class, Variable, Import


class TestConstants:
    """Test constants values"""

    def test_element_type_constants(self):
        """Test element type constants"""
        assert ELEMENT_TYPE_CLASS == "class"
        assert ELEMENT_TYPE_FUNCTION == "function"
        assert ELEMENT_TYPE_VARIABLE == "variable"
        assert ELEMENT_TYPE_IMPORT == "import"
        assert ELEMENT_TYPE_PACKAGE == "package"
        assert ELEMENT_TYPE_ANNOTATION == "annotation"

    def test_element_type_mapping(self):
        """Test element type mapping"""
        assert ELEMENT_TYPE_MAPPING["Class"] == ELEMENT_TYPE_CLASS
        assert ELEMENT_TYPE_MAPPING["Function"] == ELEMENT_TYPE_FUNCTION
        assert ELEMENT_TYPE_MAPPING["Variable"] == ELEMENT_TYPE_VARIABLE
        assert ELEMENT_TYPE_MAPPING["Import"] == ELEMENT_TYPE_IMPORT
        assert ELEMENT_TYPE_MAPPING["Package"] == ELEMENT_TYPE_PACKAGE
        assert ELEMENT_TYPE_MAPPING["Annotation"] == ELEMENT_TYPE_ANNOTATION

    def test_legacy_class_mapping(self):
        """Test legacy class mapping"""
        assert LEGACY_CLASS_MAPPING["Class"] == ELEMENT_TYPE_CLASS
        assert LEGACY_CLASS_MAPPING["Function"] == ELEMENT_TYPE_FUNCTION
        assert LEGACY_CLASS_MAPPING["Variable"] == ELEMENT_TYPE_VARIABLE
        assert LEGACY_CLASS_MAPPING["Import"] == ELEMENT_TYPE_IMPORT
        assert LEGACY_CLASS_MAPPING["Package"] == ELEMENT_TYPE_PACKAGE
        assert LEGACY_CLASS_MAPPING["Annotation"] == ELEMENT_TYPE_ANNOTATION


class TestGetElementType:
    """Test get_element_type function"""

    def test_get_element_type_with_element_type_attribute(self):
        """Test get_element_type with element_type attribute"""
        class MockElement:
            element_type = "custom_type"
        
        element = MockElement()
        result = get_element_type(element)
        assert result == "custom_type"

    def test_get_element_type_with_class_name(self):
        """Test get_element_type with class name"""
        func = Function(name="test", start_line=1, end_line=5)
        result = get_element_type(func)
        assert result == ELEMENT_TYPE_FUNCTION
        
        cls = Class(name="test", start_line=1, end_line=10)
        result = get_element_type(cls)
        assert result == ELEMENT_TYPE_CLASS
        
        var = Variable(name="test", start_line=1, end_line=1)
        result = get_element_type(var)
        assert result == ELEMENT_TYPE_VARIABLE
        
        imp = Import(name="test", start_line=1, end_line=1)
        result = get_element_type(imp)
        assert result == ELEMENT_TYPE_IMPORT

    def test_get_element_type_unknown_class(self):
        """Test get_element_type with unknown class"""
        class UnknownElement:
            pass
        
        element = UnknownElement()
        result = get_element_type(element)
        assert result == "unknown"

    def test_get_element_type_no_class_attribute(self):
        """Test get_element_type with no class attribute"""
        class NoClassElement:
            def __init__(self):
                # Remove __class__ attribute if possible
                pass
        
        element = NoClassElement()
        # This should still work because all Python objects have __class__
        result = get_element_type(element)
        assert result == "unknown"

    def test_get_element_type_none_input(self):
        """Test get_element_type with None input"""
        result = get_element_type(None)
        assert result == "unknown"

    def test_get_element_type_primitive_input(self):
        """Test get_element_type with primitive input"""
        result = get_element_type("string")
        assert result == "unknown"
        
        result = get_element_type(42)
        assert result == "unknown"
        
        result = get_element_type([])
        assert result == "unknown"


class TestIsElementOfType:
    """Test is_element_of_type function"""

    def test_is_element_of_type_function(self):
        """Test is_element_of_type with Function"""
        func = Function(name="test", start_line=1, end_line=5)
        
        assert is_element_of_type(func, ELEMENT_TYPE_FUNCTION) is True
        assert is_element_of_type(func, ELEMENT_TYPE_CLASS) is False
        assert is_element_of_type(func, ELEMENT_TYPE_VARIABLE) is False

    def test_is_element_of_type_class(self):
        """Test is_element_of_type with Class"""
        cls = Class(name="test", start_line=1, end_line=10)
        
        assert is_element_of_type(cls, ELEMENT_TYPE_CLASS) is True
        assert is_element_of_type(cls, ELEMENT_TYPE_FUNCTION) is False
        assert is_element_of_type(cls, ELEMENT_TYPE_VARIABLE) is False

    def test_is_element_of_type_variable(self):
        """Test is_element_of_type with Variable"""
        var = Variable(name="test", start_line=1, end_line=1)
        
        assert is_element_of_type(var, ELEMENT_TYPE_VARIABLE) is True
        assert is_element_of_type(var, ELEMENT_TYPE_FUNCTION) is False
        assert is_element_of_type(var, ELEMENT_TYPE_CLASS) is False

    def test_is_element_of_type_import(self):
        """Test is_element_of_type with Import"""
        imp = Import(name="test", start_line=1, end_line=1)
        
        assert is_element_of_type(imp, ELEMENT_TYPE_IMPORT) is True
        assert is_element_of_type(imp, ELEMENT_TYPE_FUNCTION) is False
        assert is_element_of_type(imp, ELEMENT_TYPE_CLASS) is False

    def test_is_element_of_type_custom_element(self):
        """Test is_element_of_type with custom element"""
        class CustomElement:
            element_type = "custom"
        
        element = CustomElement()
        
        assert is_element_of_type(element, "custom") is True
        assert is_element_of_type(element, ELEMENT_TYPE_FUNCTION) is False

    def test_is_element_of_type_unknown_element(self):
        """Test is_element_of_type with unknown element"""
        class UnknownElement:
            pass
        
        element = UnknownElement()
        
        assert is_element_of_type(element, "unknown") is True
        assert is_element_of_type(element, ELEMENT_TYPE_FUNCTION) is False

    def test_is_element_of_type_none_input(self):
        """Test is_element_of_type with None input"""
        assert is_element_of_type(None, ELEMENT_TYPE_FUNCTION) is False
        assert is_element_of_type(None, "unknown") is True

    def test_is_element_of_type_primitive_input(self):
        """Test is_element_of_type with primitive input"""
        assert is_element_of_type("string", ELEMENT_TYPE_FUNCTION) is False
        assert is_element_of_type(42, ELEMENT_TYPE_VARIABLE) is False
        assert is_element_of_type([], ELEMENT_TYPE_CLASS) is False


class TestConstantsIntegration:
    """Test constants integration with other modules"""

    def test_constants_consistency(self):
        """Test that constants are consistent across mappings"""
        # Verify that all mappings point to the same constants
        for key, value in ELEMENT_TYPE_MAPPING.items():
            assert value in [
                ELEMENT_TYPE_CLASS,
                ELEMENT_TYPE_FUNCTION,
                ELEMENT_TYPE_VARIABLE,
                ELEMENT_TYPE_IMPORT,
                ELEMENT_TYPE_PACKAGE,
                ELEMENT_TYPE_ANNOTATION
            ]
        
        for key, value in LEGACY_CLASS_MAPPING.items():
            assert value in [
                ELEMENT_TYPE_CLASS,
                ELEMENT_TYPE_FUNCTION,
                ELEMENT_TYPE_VARIABLE,
                ELEMENT_TYPE_IMPORT,
                ELEMENT_TYPE_PACKAGE,
                ELEMENT_TYPE_ANNOTATION
            ]

    def test_constants_with_real_models(self):
        """Test constants with real model instances"""
        # Create instances of all model types
        models = [
            Function(name="func", start_line=1, end_line=5),
            Class(name="cls", start_line=1, end_line=10),
            Variable(name="var", start_line=1, end_line=1),
            Import(name="imp", start_line=1, end_line=1)
        ]
        
        expected_types = [
            ELEMENT_TYPE_FUNCTION,
            ELEMENT_TYPE_CLASS,
            ELEMENT_TYPE_VARIABLE,
            ELEMENT_TYPE_IMPORT
        ]
        
        for model, expected_type in zip(models, expected_types):
            actual_type = get_element_type(model)
            assert actual_type == expected_type
            assert is_element_of_type(model, expected_type) is True

    def test_constants_immutability(self):
        """Test that constants are immutable"""
        # Test that constants are strings and can't be easily modified
        assert isinstance(ELEMENT_TYPE_CLASS, str)
        assert isinstance(ELEMENT_TYPE_FUNCTION, str)
        assert isinstance(ELEMENT_TYPE_VARIABLE, str)
        assert isinstance(ELEMENT_TYPE_IMPORT, str)
        assert isinstance(ELEMENT_TYPE_PACKAGE, str)
        assert isinstance(ELEMENT_TYPE_ANNOTATION, str)
        
        # Test that mappings are dictionaries
        assert isinstance(ELEMENT_TYPE_MAPPING, dict)
        assert isinstance(LEGACY_CLASS_MAPPING, dict)

    def test_all_element_types_covered(self):
        """Test that all element types are covered in mappings"""
        all_types = {
            ELEMENT_TYPE_CLASS,
            ELEMENT_TYPE_FUNCTION,
            ELEMENT_TYPE_VARIABLE,
            ELEMENT_TYPE_IMPORT,
            ELEMENT_TYPE_PACKAGE,
            ELEMENT_TYPE_ANNOTATION
        }
        
        mapping_types = set(ELEMENT_TYPE_MAPPING.values())
        legacy_types = set(LEGACY_CLASS_MAPPING.values())
        
        # All types should be represented in mappings
        assert all_types.issubset(mapping_types)
        assert all_types.issubset(legacy_types)