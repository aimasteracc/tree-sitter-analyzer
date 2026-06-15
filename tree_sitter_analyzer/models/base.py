#!/usr/bin/env python3
"""
Base / language-agnostic code element models.

Contains: CodeElement, Function, Class, Variable, Import, Package,
          Lambda, Comprehension, Expression
"""

from abc import ABC
from dataclasses import dataclass, field
from typing import Any

from ..constants import (
    ELEMENT_TYPE_ANNOTATION,
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_PACKAGE,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)


# Use dataclass with slots for Python 3.10+
def dataclass_with_slots(*args: Any, **kwargs: Any) -> Any:
    return dataclass(*args, slots=True, **kwargs)


# ========================================
# Base Generic Models (Language Agnostic)
# ========================================


@dataclass(frozen=False)
class CodeElement(ABC):
    """Base class for all code elements"""

    name: str
    start_line: int
    end_line: int
    raw_text: str = ""
    language: str = "unknown"
    docstring: str | None = None  # JavaDoc/docstring for this element
    element_type: str = "unknown"
    node_type: str | None = None  # Tree-sitter node type for grammar coverage tracking

    @property
    def line_count(self) -> int:
        """Number of source lines spanned: end_line - start_line + 1.

        Computed on-the-fly so callers using ``getattr(elem, "line_count", 0)``
        get the real value instead of the fallback 0. (#769)
        """
        return self.end_line - self.start_line + 1

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-style attribute access so formatters can use e.get('element_type')
        interchangeably on both CodeElement objects and plain dicts."""
        return getattr(self, key, default)

    def to_summary_item(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.element_type,
            "lines": {"start": self.start_line, "end": self.end_line},
        }


@dataclass(frozen=False)
class Function(CodeElement):
    """Generic function/method representation"""

    parameters: list[str] = field(default_factory=list)
    parameter_defaults: dict[str, str] = field(
        default_factory=dict
    )  # param name -> default value
    return_type: str | None = None
    modifiers: list[str] = field(default_factory=list)
    is_async: bool = False
    is_static: bool = False
    is_private: bool = False
    is_public: bool = True
    is_constant: bool = False
    visibility: str = "public"
    is_suspend: bool | None = None  # Kotlin
    receiver: str | None = None  # Go
    receiver_type: str | None = None  # Go
    is_constructor: bool | None = None  # Java
    element_type: str = "function"
    # Java-specific fields for detailed analysis
    annotations: list[dict[str, Any]] = field(default_factory=list)
    throws: list[str] = field(default_factory=list)
    complexity_score: int = 1
    is_abstract: bool = False
    is_final: bool = False
    # JavaScript-specific fields
    is_generator: bool = False
    is_arrow: bool = False
    is_method: bool = False
    parent_class: str | None = None  # owning class for prototype-assigned methods
    framework_type: str | None = None
    # Python-specific fields
    is_property: bool = False
    is_classmethod: bool = False
    is_staticmethod: bool = False
    # When decorated, the line of the first decorator (outer node start).
    # start_line remains the `def` line for go-to-definition compatibility.
    decorator_start_line: int | None = None


@dataclass(frozen=False)
class Class(CodeElement):
    """Generic class representation"""

    class_type: str = "class"
    full_qualified_name: str | None = None
    package_name: str | None = None
    superclass: str | None = None
    interfaces: list[str] = field(default_factory=list)
    modifiers: list[str] = field(default_factory=list)
    visibility: str = "public"
    element_type: str = "class"
    methods: list[Function] = field(default_factory=list)
    # Java-specific fields for detailed analysis
    annotations: list[dict[str, Any]] = field(default_factory=list)
    is_nested: bool = False
    parent_class: str | None = None
    extends_class: str | None = None  # Alias for superclass
    implements_interfaces: list[str] = field(
        default_factory=list
    )  # Alias for interfaces
    # JavaScript-specific fields
    is_react_component: bool = False
    framework_type: str | None = None
    is_exported: bool = False
    # Python-specific fields
    is_dataclass: bool = False
    is_abstract: bool = False
    is_exception: bool = False
    # When decorated, the line of the first decorator (outer node start).
    # start_line remains the `class` line for go-to-definition compatibility.
    decorator_start_line: int | None = None


@dataclass(frozen=False)
class Variable(CodeElement):
    """Generic variable representation"""

    variable_type: str | None = None
    modifiers: list[str] = field(default_factory=list)
    is_constant: bool = False
    is_static: bool = False
    visibility: str = "private"
    element_type: str = "variable"
    is_val: bool | None = None  # Kotlin
    is_var: bool | None = None  # Kotlin
    initializer: str | None = None
    # Java-specific fields for detailed analysis
    annotations: list[dict[str, Any]] = field(default_factory=list)
    is_final: bool = False
    is_readonly: bool = False  # PHP 8.1+ readonly property
    field_type: str | None = None  # Alias for variable_type
    # Owning struct/class for class-level fields (#794) — mirrors
    # Function.receiver_type; names stay bare, the owner travels here.
    receiver_type: str | None = None  # Go struct field owner


@dataclass(frozen=False)
class Import(CodeElement):
    """Generic import statement representation"""

    module_name: str = ""
    module_path: str = ""  # Add module_path for compatibility with plugins
    imported_names: list[str] = field(default_factory=list)
    is_wildcard: bool = False
    is_static: bool = False
    element_type: str = "import"
    alias: str | None = None
    # Java-specific fields for detailed analysis
    imported_name: str = ""  # Alias for name
    import_statement: str = ""  # Full import statement
    line_number: int = 0  # Line number for compatibility


@dataclass(frozen=False)
class Package(CodeElement):
    """Generic package declaration representation"""

    element_type: str = "package"


@dataclass(frozen=False)
class Lambda(CodeElement):
    """Lambda expression representation

    Represents anonymous functions (lambda expressions) in Python.

    Example:
        lambda x: x + 1
        lambda x, y=10: x + y
    """

    parameters: list[str] = field(default_factory=list)
    body_preview: str = ""  # First 50 chars of lambda body
    element_type: str = "lambda"


@dataclass(frozen=False)
class Comprehension(CodeElement):
    """List/set/dict comprehension or generator expression

    Represents all forms of comprehensions in Python.

    Examples:
        [x**2 for x in range(10)]  # list
        {x**2 for x in range(10)}  # set
        {x: x**2 for x in range(10)}  # dict
        (x**2 for x in range(10))  # generator
        [x for x in range(100) if x % 2 == 0]  # with condition
    """

    comprehension_type: str = ""  # "list", "set", "dict", or "generator"
    target_variable: str = ""  # "x" in "x for x in ..."
    iterable_preview: str = ""  # Preview of iterable expression
    has_condition: bool = False
    element_type: str = "comprehension"


@dataclass(frozen=False)
class Expression(CodeElement):
    """Generic expression (conditional, subscript, list literals)

    Represents various expression-level constructs in Python.

    Examples:
        value if condition else fallback  # conditional
        my_list[0]  # subscript
        my_dict['key']  # subscript
        [1, 2, 3]  # list literal
    """

    expression_kind: str = ""  # "conditional", "subscript", or "list"
    preview: str = ""  # First 50 chars of expression
    element_type: str = "expression"


__all__ = [
    "dataclass_with_slots",
    "CodeElement",
    "Function",
    "Class",
    "Variable",
    "Import",
    "Package",
    "Lambda",
    "Comprehension",
    "Expression",
    # re-exported constants used by result.py helpers
    "ELEMENT_TYPE_ANNOTATION",
    "ELEMENT_TYPE_CLASS",
    "ELEMENT_TYPE_FUNCTION",
    "ELEMENT_TYPE_IMPORT",
    "ELEMENT_TYPE_PACKAGE",
    "ELEMENT_TYPE_VARIABLE",
    "is_element_of_type",
]
