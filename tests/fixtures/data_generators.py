#!/usr/bin/env python3
"""
Test data generators for comprehensive testing.

This module provides generators and factories for creating realistic
test data across different programming languages and scenarios.
"""

from __future__ import annotations

import random
import string
from typing import Any


def generate_python_function(
    name: str = "test_function",
    params: list[str] | None = None,
    body: str = "pass",
    decorators: list[str] | None = None,
    docstring: str | None = None,
) -> str:
    """
    Generate Python function code.

    Args:
        name: Function name
        params: List of parameter names
        body: Function body
        decorators: List of decorators
        docstring: Function docstring

    Returns:
        Python function code as string

    Example:
        >>> code = generate_python_function("foo", ["x", "y"], "return x + y")
        >>> print(code)
        def foo(x, y):
            return x + y
    """
    if params is None:
        params = []

    lines = []

    # Add decorators
    if decorators:
        for decorator in decorators:
            lines.append(f"@{decorator}")

    # Function signature
    param_str = ", ".join(params)
    lines.append(f"def {name}({param_str}):")

    # Add docstring
    if docstring:
        lines.append(f'    """{docstring}"""')

    # Add body
    for line in body.split("\n"):
        lines.append(f"    {line}")

    return "\n".join(lines)


def generate_python_class(
    name: str = "TestClass",
    bases: list[str] | None = None,
    methods: list[dict[str, Any]] | None = None,
    attributes: list[str] | None = None,
    docstring: str | None = None,
) -> str:
    """
    Generate Python class code.

    Args:
        name: Class name
        bases: List of base class names
        methods: List of method definitions
        attributes: List of class attributes
        docstring: Class docstring

    Returns:
        Python class code as string

    Example:
        >>> code = generate_python_class("MyClass", methods=[
        ...     {"name": "__init__", "params": ["self"], "body": "pass"}
        ... ])
    """
    if bases is None:
        bases = []
    if methods is None:
        methods = []
    if attributes is None:
        attributes = []

    lines = []

    # Class declaration
    if bases:
        base_str = ", ".join(bases)
        lines.append(f"class {name}({base_str}):")
    else:
        lines.append(f"class {name}:")

    # Docstring
    if docstring:
        lines.append(f'    """{docstring}"""')

    # Attributes
    for attr in attributes:
        lines.append(f"    {attr}")

    # Methods
    if not methods and not attributes:
        lines.append("    pass")
    else:
        for method in methods:
            method_code = generate_python_function(
                name=method.get("name", "method"),
                params=method.get("params", ["self"]),
                body=method.get("body", "pass"),
                docstring=method.get("docstring"),
            )
            # Indent method code
            for line in method_code.split("\n"):
                lines.append(f"    {line}")
            lines.append("")  # Blank line between methods

    return "\n".join(lines)


def generate_javascript_function(
    name: str = "testFunction",
    params: list[str] | None = None,
    body: str = "return null;",
    is_async: bool = False,
    is_arrow: bool = False,
) -> str:
    """
    Generate JavaScript function code.

    Args:
        name: Function name
        params: List of parameters
        body: Function body
        is_async: Whether function is async
        is_arrow: Whether to use arrow function syntax

    Returns:
        JavaScript function code as string
    """
    if params is None:
        params = []

    param_str = ", ".join(params)
    async_prefix = "async " if is_async else ""

    if is_arrow:
        if "\n" in body:
            return f"{async_prefix}const {name} = ({param_str}) => {{\n  {body}\n}};"
        else:
            return f"{async_prefix}const {name} = ({param_str}) => {body};"
    else:
        return f"{async_prefix}function {name}({param_str}) {{\n  {body}\n}}"


def generate_typescript_interface(
    name: str = "TestInterface",
    properties: dict[str, str] | None = None,
    methods: dict[str, str] | None = None,
) -> str:
    """
    Generate TypeScript interface code.

    Args:
        name: Interface name
        properties: Dictionary of property name to type
        methods: Dictionary of method name to signature

    Returns:
        TypeScript interface code as string
    """
    if properties is None:
        properties = {}
    if methods is None:
        methods = {}

    lines = [f"interface {name} {{"]

    for prop, type_str in properties.items():
        lines.append(f"  {prop}: {type_str};")

    for method, signature in methods.items():
        lines.append(f"  {method}{signature};")

    lines.append("}")

    return "\n".join(lines)


def generate_java_class(
    name: str = "TestClass",
    package: str | None = None,
    modifiers: list[str] | None = None,
    extends: str | None = None,
    implements: list[str] | None = None,
    fields: list[dict[str, str]] | None = None,
    methods: list[dict[str, Any]] | None = None,
) -> str:
    """
    Generate Java class code.

    Args:
        name: Class name
        package: Package declaration
        modifiers: Class modifiers (public, abstract, etc.)
        extends: Parent class name
        implements: List of implemented interfaces
        fields: List of field definitions
        methods: List of method definitions

    Returns:
        Java class code as string
    """
    if modifiers is None:
        modifiers = ["public"]
    if implements is None:
        implements = []
    if fields is None:
        fields = []
    if methods is None:
        methods = []

    lines = []

    # Package declaration
    if package:
        lines.append(f"package {package};")
        lines.append("")

    # Class declaration
    modifiers_str = " ".join(modifiers)
    class_line = f"{modifiers_str} class {name}"

    if extends:
        class_line += f" extends {extends}"

    if implements:
        class_line += f" implements {', '.join(implements)}"

    lines.append(f"{class_line} {{")

    # Fields
    for field in fields:
        field_line = f"    {field['modifiers']} {field['type']} {field['name']};"
        lines.append(field_line)

    if fields:
        lines.append("")

    # Methods
    for method in methods:
        method_modifiers = method.get("modifiers", "public")
        method_return = method.get("return_type", "void")
        method_name = method.get("name", "method")
        method_params = method.get("params", "")
        method_body = method.get("body", "")

        lines.append(
            f"    {method_modifiers} {method_return} {method_name}({method_params}) {{"
        )
        if method_body:
            for line in method_body.split("\n"):
                lines.append(f"        {line}")
        lines.append("    }")
        lines.append("")

    lines.append("}")

    return "\n".join(lines)


def generate_html_page(
    title: str = "Test Page",
    body_content: str = "<p>Hello, World!</p>",
    head_elements: list[str] | None = None,
) -> str:
    """
    Generate HTML page code.

    Args:
        title: Page title
        body_content: HTML body content
        head_elements: Additional head elements

    Returns:
        Complete HTML document as string
    """
    if head_elements is None:
        head_elements = []

    lines = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        f"  <title>{title}</title>",
    ]

    for element in head_elements:
        lines.append(f"  {element}")

    lines.extend(
        [
            "</head>",
            "<body>",
            f"  {body_content}",
            "</body>",
            "</html>",
        ]
    )

    return "\n".join(lines)


def generate_css_rules(
    selectors: dict[str, dict[str, str]],
) -> str:
    """
    Generate CSS rules.

    Args:
        selectors: Dictionary of selector to properties

    Returns:
        CSS rules as string

    Example:
        >>> css = generate_css_rules({
        ...     "body": {"margin": "0", "padding": "0"},
        ...     ".container": {"max-width": "1200px"}
        ... })
    """
    lines = []

    for selector, properties in selectors.items():
        lines.append(f"{selector} {{")
        for prop, value in properties.items():
            lines.append(f"  {prop}: {value};")
        lines.append("}")
        lines.append("")

    return "\n".join(lines)


def generate_random_identifier(
    length: int = 8,
    prefix: str = "test_",
) -> str:
    """
    Generate a random identifier.

    Args:
        length: Length of random part
        prefix: Prefix for identifier

    Returns:
        Random identifier string
    """
    random_part = "".join(random.choices(string.ascii_lowercase, k=length))
    return f"{prefix}{random_part}"


def generate_large_file_content(
    language: str = "python",
    num_functions: int = 100,
    num_classes: int = 20,
) -> str:
    """
    Generate large file content for performance testing.

    Args:
        language: Programming language
        num_functions: Number of functions to generate
        num_classes: Number of classes to generate

    Returns:
        Large code file content
    """
    lines = []

    if language == "python":
        # Generate imports
        lines.append("import os")
        lines.append("import sys")
        lines.append("from typing import Any, Dict, List")
        lines.append("")

        # Generate functions
        for i in range(num_functions):
            func_code = generate_python_function(
                name=f"function_{i}",
                params=["x", "y"],
                body=f"return x + y + {i}",
            )
            lines.append(func_code)
            lines.append("")

        # Generate classes
        for i in range(num_classes):
            class_code = generate_python_class(
                name=f"Class{i}",
                methods=[
                    {"name": "__init__", "params": ["self"], "body": "pass"},
                    {
                        "name": f"method_{i}",
                        "params": ["self", "x"],
                        "body": "return x * 2",
                    },
                ],
            )
            lines.append(class_code)
            lines.append("")

    return "\n".join(lines)


# Export all generators
__all__ = [
    "generate_python_function",
    "generate_python_class",
    "generate_javascript_function",
    "generate_typescript_interface",
    "generate_java_class",
    "generate_html_page",
    "generate_css_rules",
    "generate_random_identifier",
    "generate_large_file_content",
]
