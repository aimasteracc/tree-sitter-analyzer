#!/usr/bin/env python3
"""
Constants for tree-sitter-analyzer

This module defines constants used throughout the project to ensure consistency.
"""

# Element types for unified element management system
ELEMENT_TYPE_CLASS = "class"
ELEMENT_TYPE_FUNCTION = "function"
ELEMENT_TYPE_VARIABLE = "variable"
ELEMENT_TYPE_IMPORT = "import"
ELEMENT_TYPE_PACKAGE = "package"
ELEMENT_TYPE_ANNOTATION = "annotation"

# Element type mapping for backward compatibility
ELEMENT_TYPE_MAPPING = {
    "Class": ELEMENT_TYPE_CLASS,
    "Function": ELEMENT_TYPE_FUNCTION,
    "Variable": ELEMENT_TYPE_VARIABLE,
    "Import": ELEMENT_TYPE_IMPORT,
    "Package": ELEMENT_TYPE_PACKAGE,
    "Annotation": ELEMENT_TYPE_ANNOTATION,
}

# Legacy class name to element type mapping
LEGACY_CLASS_MAPPING = {
    "Class": ELEMENT_TYPE_CLASS,
    "Function": ELEMENT_TYPE_FUNCTION,
    "Variable": ELEMENT_TYPE_VARIABLE,
    "Import": ELEMENT_TYPE_IMPORT,
    "Package": ELEMENT_TYPE_PACKAGE,
    "Annotation": ELEMENT_TYPE_ANNOTATION,
}


def get_element_type(element) -> str:
    """
    Get the element type from an element object.

    Args:
        element: Element object with element_type attribute or __class__.__name__

    Returns:
        Standardized element type string
    """
    if hasattr(element, "element_type"):
        return element.element_type

    if hasattr(element, "__class__") and hasattr(element.__class__, "__name__"):
        class_name = element.__class__.__name__
        return LEGACY_CLASS_MAPPING.get(class_name, "unknown")

    return "unknown"


def is_element_of_type(element, element_type: str) -> bool:
    """
    Check if an element is of a specific type.

    Args:
        element: Element object to check
        element_type: Expected element type

    Returns:
        True if element is of the specified type
    """
    return get_element_type(element) == element_type
