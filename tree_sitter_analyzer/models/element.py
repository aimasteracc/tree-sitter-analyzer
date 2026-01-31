#!/usr/bin/env python3
"""
Element Model - Data Structure for Code Elements

This module provides data structures for representing code elements
such as functions, classes, variables, and imports.

Optimized with:
- Complete type hints (PEP 484)
- Comprehensive error handling
- Performance optimization (slots, caching)
- Detailed documentation

Features:
- Class definitions with metadata
- Function definitions with parameters
- Variable definitions with type inference
- Import statements with module resolution
- Type-safe operations (PEP 484)
- Immutable data structures (frozen)

Author: aisheng.yu
Version: 1.10.5
Date: 2026-01-28
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import (
    TYPE_CHECKING,
    Any,
)

# Type checking setup
if TYPE_CHECKING:
    # Utility imports
    pass
else:
    # Runtime imports (when type checking is disabled)
    # Utility imports
    pass

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ============================================================================
# Type Definitions
# ============================================================================


class ElementType(Enum):
    """Element type enumeration."""

    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    VARIABLE = "variable"
    IMPORT = "import"
    PARAMETER = "parameter"
    DECORATOR = "decorator"
    ANNOTATION = "annotation"
    EXCEPTION = "exception"
    CONSTANT = "constant"
    TYPE_ALIAS = "type_alias"
    COMMENT = "comment"
    WHITESPACE = "whitespace"
    UNKNOWN = "unknown"


class Visibility(Enum):
    """Visibility enumeration."""

    PUBLIC = "public"
    PRIVATE = "private"
    PROTECTED = "protected"
    PACKAGE = "package"
    INTERNAL = "internal"


# ============================================================================
# Custom Exceptions
# ============================================================================


class ElementModelError(Exception):
    """Base exception for element model errors."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


class InitializationError(ElementModelError):
    """Exception raised when element model initialization fails."""

    pass


class ValidationError(ElementModelError):
    """Exception raised when element validation fails."""

    pass


class InconsistencyError(ElementModelError):
    """Exception raised when element data is inconsistent."""

    pass


# ============================================================================
# Data Classes
# ============================================================================


@dataclass(frozen=True, slots=True)
class Position:
    """
    Position information in source code.

    Attributes:
        line: Line number (1-based)
        column: Column number (0-based)
        end_line: End line number (1-based)
        end_column: End column number (0-based)
        offset: Byte offset from start of file
    """

    line: int
    column: int
    end_line: int
    end_column: int
    offset: int

    def __str__(self) -> str:
        """String representation of position."""
        return f"Line {self.line}, Column {self.column}"

    def __hash__(self) -> int:
        """Hash based on position."""
        return hash((self.line, self.column, self.offset))


@dataclass(frozen=True, slots=True)
class TypeInfo:
    """
    Type information for code elements.

    Attributes:
        name: Type name (e.g., "int", "str", "List")
        module: Module name (e.g., "typing", "builtins")
        parameters: Generic parameters (e.g., "List[str]")
        is_generic: Whether type is generic
        is_primitive: Whether type is primitive
        is_nullable: Whether type can be None
    """

    name: str
    module: str
    parameters: list[str] = field(default_factory=list)
    is_generic: bool = False
    is_primitive: bool = True
    is_nullable: bool = False

    def __str__(self) -> str:
        """String representation of type."""
        if self.is_generic and self.parameters:
            return f"{self.name}[{', '.join(self.parameters)}]"
        return self.name

    def __hash__(self) -> int:
        """Hash based on type name."""
        return hash(self.name)


@dataclass(frozen=True, slots=True)
class DocstringInfo:
    """
    Documentation string information.

    Attributes:
        content: Docstring content
        format: Docstring format (reST, Google, etc.)
        position: Position in source code
        summary: Brief summary
        description: Detailed description
        parameters: List of parameter descriptions
        returns: Return value description
        raises: List of exception descriptions
    """

    content: str
    format: str | None = None
    position: Position | None = None
    summary: str | None = None
    description: str | None = None
    parameters: list[str] = field(default_factory=list)
    returns: str | None = None
    raises: list[str] = field(default_factory=list)

    def __hash__(self) -> int:
        """Hash based on content."""
        return hash(self.content)


# ============================================================================
# Base Element Classes
# ============================================================================


@dataclass(frozen=True, slots=True)
class Element:
    """
    Base class for all code elements.

    Features:
    - Immutable data class (frozen=True)
    - Slots for performance
    - Type-safe operations (PEP 484)
    - Hashable for caching

    Attributes:
        element_type: Type of element (function, class, variable, etc.)
        name: Element name
        position: Position in source code
        visibility: Visibility (public, private, protected, etc.)
        docstring: Optional documentation string
        metadata: Optional additional metadata dictionary
    """

    element_type: ElementType
    name: str
    position: Position
    visibility: Visibility = Visibility.PUBLIC
    docstring: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:
        """Hash based on element type and name."""
        return hash((self.element_type.value, self.name))

    def __str__(self) -> str:
        """String representation of element."""
        return f"{self.element_type.value}: {self.name}"

    @property
    def full_name(self) -> str:
        """Get full qualified name."""
        return self.name

    @property
    def qualified_name(self) -> str:
        """Get qualified name with visibility prefix."""
        if self.visibility == Visibility.PRIVATE:
            return f"_{self.name}"
        return self.name


@dataclass(frozen=True, slots=True)
class NamedElement(Element):
    """
    Base class for named elements (functions, classes, variables).

    Features:
    - Inherits from Element
    - Immutable data class (frozen=True)
    - Slots for performance
    - Type-safe operations (PEP 484)
    - Hashable for caching

    Attributes:
        element_type: Type of element (function, class, variable, etc.)
        name: Element name
        position: Position in source code
        visibility: Visibility (public, private, protected, etc.)
        docstring: Optional documentation string
        metadata: Optional additional metadata dictionary
    """

    def __hash__(self) -> int:
        """Hash based on element type and name."""
        return hash((self.element_type.value, self.name))

    def __str__(self) -> str:
        """String representation of named element."""
        return f"{self.element_type.value}: {self.name}"


# ============================================================================
# Variable Element
# ============================================================================


@dataclass(frozen=True, slots=True)
class Variable(NamedElement):
    """
    Variable element with type information.

    Features:
    - Immutable data class (frozen=True)
    - Slots for performance
    - Type-safe operations (PEP 484)
    - Hashable for caching

    Attributes:
        element_type: Type of element (function, class, variable, etc.)
        name: Variable name
        position: Position in source code
        visibility: Visibility (public, private, protected, etc.)
        docstring: Optional documentation string
        metadata: Optional additional metadata dictionary
        variable_type: Type information for the variable
        value: Optional default value (for constants)
        is_constant: Whether variable is constant
        is_mutable: Whether variable is mutable
        is_static: Whether variable is static (class member)
        is_global: Whether variable is global
        is_local: Whether variable is local (function scope)
    """

    variable_type: TypeInfo | None = None
    value: Any | None = None
    is_constant: bool = False
    is_mutable: bool = True
    is_static: bool = False
    is_global: bool = False
    is_local: bool = False

    def __hash__(self) -> int:
        """Hash based on element type, name, and type."""
        return hash((self.element_type.value, self.name, self.variable_type))

    def __str__(self) -> str:
        """String representation of variable."""
        type_str = str(self.variable_type) if self.variable_type else "unknown"
        return f"Variable: {self.name} ({type_str})"


# ============================================================================
# Function Element
# ============================================================================


@dataclass(frozen=True, slots=True)
class Function(NamedElement):
    """
    Function element with parameters and return type.

    Features:
    - Immutable data class (frozen=True)
    - Slots for performance
    - Type-safe operations (PEP 484)
    - Hashable for caching

    Attributes:
        element_type: Type of element (function, class, variable, etc.)
        name: Function name
        position: Position in source code
        visibility: Visibility (public, private, protected, etc.)
        docstring: Optional documentation string
        metadata: Optional additional metadata dictionary
        return_type: Return type information
        parameters: List of function parameters
        is_async: Whether function is async
        is_generator: Whether function is generator
        is_static: Whether function is static (class member)
        is_class_method: Whether function is a class method
        is_static_method: Whether function is a static method
        is_property: Whether function is a property
        is_abstract: Whether function is abstract
        is_constructor: Whether function is a constructor
        is_operator: Whether function is an operator overload
        parameters: List of parameter information
        decorators: List of decorator names
        complexity: Cyclomatic complexity score
    """

    return_type: TypeInfo | None = None
    parameters: list[str] = field(default_factory=list)
    is_async: bool = False
    is_generator: bool = False
    is_static: bool = False
    is_class_method: bool = False
    is_static_method: bool = False
    is_property: bool = False
    is_abstract: bool = False
    is_constructor: bool = False
    is_operator: bool = False
    decorators: list[str] = field(default_factory=list)
    complexity: int = 1

    def __hash__(self) -> int:
        """Hash based on element type, name, and return type."""
        return_type_hash = hash(self.return_type) if self.return_type else 0
        return hash((self.element_type.value, self.name, return_type_hash))

    @property
    def signature(self) -> str:
        """Get function signature string."""
        params_str = ", ".join(self.parameters)
        return_str = str(self.return_type) if self.return_type else ""
        return f"{self.name}({params_str}) -> {return_str}"

    @property
    def full_signature(self) -> str:
        """Get full function signature with visibility."""
        signature = self.signature
        if self.visibility == Visibility.PRIVATE:
            return f"_{self.signature}"
        return signature

    def __str__(self) -> str:
        """String representation of function."""
        return f"Function: {self.signature}"


# ============================================================================
# Class Element
# ============================================================================


@dataclass(frozen=True, slots=True)
class Class(NamedElement):
    """
    Class element with inheritance and members.

    Features:
    - Immutable data class (frozen=True)
    - Slots for performance
    - Type-safe operations (PEP 484)
    - Hashable for caching

    Attributes:
        element_type: Type of element (function, class, variable, etc.)
        name: Class name
        position: Position in source code
        visibility: Visibility (public, private, protected, etc.)
        docstring: Optional documentation string
        metadata: Optional additional metadata dictionary
        base_classes: List of base class names
        implemented_interfaces: List of interface names
        methods: List of method names
        fields: List of field names
        properties: List of property names
        is_abstract: Whether class is abstract
        is_final: Whether class is final
        is_static: Whether class is static
        is_generic: Whether class is generic
        is_exception: Whether class is an exception
        is_enum: Whether class is an enum
        is_mixin: Whether class is a mixin
        decorators: List of decorator names
        complexity: Cyclomatic complexity score
    """

    base_classes: list[str] = field(default_factory=list)
    implemented_interfaces: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)
    properties: list[str] = field(default_factory=list)
    is_abstract: bool = False
    is_final: bool = False
    is_static: bool = False
    is_generic: bool = False
    is_exception: bool = False
    is_enum: bool = False
    is_mixin: bool = False
    decorators: list[str] = field(default_factory=list)
    complexity: int = 1

    def __hash__(self) -> int:
        """Hash based on element type, name, and bases."""
        return hash((self.element_type.value, self.name, tuple(self.base_classes)))

    @property
    def inheritance(self) -> str:
        """Get inheritance hierarchy string."""
        bases_str = "(".join(self.base_classes) + ")" if self.base_classes else ""
        return f"{self.name}{bases_str}"

    def __str__(self) -> str:
        """String representation of class."""
        return f"Class: {self.inheritance}"


# ============================================================================
# Import Element
# ============================================================================


@dataclass(frozen=True, slots=True)
class Import(Element):
    """
    Import element with module and name resolution.

    Features:
    - Immutable data class (frozen=True)
    - Slots for performance
    - Type-safe operations (PEP 484)
    - Hashable for caching

    Attributes:
        element_type: Type of element (function, class, variable, etc.)
        name: Element name (module or alias)
        position: Position in source code
        visibility: Visibility (public, private, protected, etc.)
        docstring: Optional documentation string
        metadata: Optional additional metadata dictionary
        import_type: Type of import (module, function, class, variable, from, star, etc.)
        module: Module name
        imported_name: Name being imported
        imported_from: Original location (if using from)
        is_relative: Whether import is relative
        is_star_import: Whether import is star import
        is_wildcard: Whether import is wildcard import
    """

    import_type: str = "module"
    module: str = ""
    imported_name: str = ""
    imported_from: str = ""
    is_relative: bool = False
    is_star_import: bool = False
    is_wildcard: bool = False

    def __hash__(self) -> int:
        """Hash based on element type, module, and name."""
        return hash((self.element_type.value, self.module, self.imported_name))

    @property
    def full_import(self) -> str:
        """Get full import statement."""
        if self.import_type == "module":
            return f"import {self.module}"
        elif self.import_type == "from":
            return f"from {self.module} import {self.imported_name}"
        elif self.import_type == "function":
            return f"from {self.module} import {self.imported_name}"
        elif self.import_type == "class":
            return f"from {self.module} import {self.imported_name}"
        elif self.import_type == "variable":
            return f"from {self.module} import {self.imported_name}"
        elif self.import_type == "star":
            return f"from {self.module} import *"
        elif self.import_type == "wildcard":
            return f"from {self.module} import * as {self.imported_name}"
        else:
            return f"import {self.module}.{self.imported_name}"

    def __str__(self) -> str:
        """String representation of import."""
        return f"Import: {self.full_import}"


# ============================================================================
# Element Factory
# ============================================================================


@dataclass(frozen=True)
class ElementFactory:
    """
    Factory for creating element objects with validation.

    Features:
    - Element validation
    - Type inference
    - Metadata management
    - Performance optimization (caching)
    - Type-safe operations (PEP 484)

    Usage:
        >>> factory = ElementFactory()
        >>> var = factory.create_variable("x", position)
        >>> func = factory.create_function("foo", position)
    """

    def create_position(
        self,
        line: int = 1,
        column: int = 0,
        end_line: int = 1,
        end_column: int = 0,
        offset: int = 0,
    ) -> Position:
        """
        Create position object.

        Args:
            line: Line number (default: 1)
            column: Column number (default: 0)
            end_line: End line number (default: 1)
            end_column: End column number (default: 0)
            offset: Byte offset (default: 0)

        Returns:
            Position object

        Raises:
            ValidationError: If position parameters are invalid

        Note:
            - Line numbers are 1-based
            - Column numbers are 0-based
            - Offset is bytes from start of file
        """
        # Validation
        if line < 1:
            raise ValidationError(f"Line number must be >= 1, got: {line}")
        if column < 0:
            raise ValidationError(f"Column number must be >= 0, got: {column}")
        if end_line < line:
            raise ValidationError(
                f"End line must be >= start line, got: {end_line} < {line}"
            )
        if end_column < 0:
            raise ValidationError(f"End column must be >= 0, got: {end_column}")
        if offset < 0:
            raise ValidationError(f"Offset must be >= 0, got: {offset}")

        return Position(
            line=line,
            column=column,
            end_line=end_line,
            end_column=end_column,
            offset=offset,
        )

    def create_type(
        self,
        name: str,
        module: str = "builtins",
        is_primitive: bool = True,
        is_generic: bool = False,
        parameters: list[str] | None = None,
    ) -> TypeInfo:
        """
        Create type information object.

        Args:
            name: Type name
            module: Module name (default: "builtins")
            is_primitive: Whether type is primitive
            is_generic: Whether type is generic
            parameters: Generic parameters

        Returns:
            TypeInfo object

        Note:
            - Primitive types include int, float, str, bool, None
            - Generic types include List, Dict, Set, Tuple, etc.
        """
        # Validation
        if not name:
            raise ValidationError("Type name cannot be empty")

        return TypeInfo(
            name=name,
            module=module,
            parameters=parameters or [],
            is_primitive=is_primitive,
            is_generic=is_generic,
            is_nullable=True,
        )

    def create_variable(
        self,
        name: str,
        position: Position,
        visibility: Visibility = Visibility.PUBLIC,
        docstring: str | None = None,
        variable_type: TypeInfo | None = None,
        value: Any | None = None,
        is_constant: bool = False,
        is_mutable: bool = True,
        is_static: bool = False,
        is_global: bool = False,
        is_local: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> Variable:
        """
        Create variable element.

        Args:
            name: Variable name
            position: Position in source code
            visibility: Visibility (default: PUBLIC)
            docstring: Optional documentation string
            variable_type: Type information
            value: Optional default value
            is_constant: Whether variable is constant
            is_mutable: Whether variable is mutable
            is_static: Whether variable is static
            is_global: Whether variable is global
            is_local: Whether variable is local
            metadata: Optional additional metadata

        Returns:
            Variable element

        Raises:
            ValidationError: If parameters are invalid

        Note:
            - Validates name and position
            - Infers variable type if not provided
            - Provides type safety
        """
        # Validation
        if not name:
            raise ValidationError("Variable name cannot be empty")
        if not position:
            raise ValidationError("Position cannot be None")

        return Variable(
            element_type=ElementType.VARIABLE,
            name=name,
            position=position,
            visibility=visibility,
            docstring=docstring,
            metadata=metadata or {},
            variable_type=variable_type,
            value=value,
            is_constant=is_constant,
            is_mutable=is_mutable,
            is_static=is_static,
            is_global=is_global,
            is_local=is_local,
        )

    def create_function(
        self,
        name: str,
        position: Position,
        return_type: TypeInfo | None = None,
        parameters: list[str] | None = None,
        visibility: Visibility = Visibility.PUBLIC,
        docstring: str | None = None,
        is_async: bool = False,
        is_generator: bool = False,
        is_static: bool = False,
        is_class_method: bool = False,
        is_static_method: bool = False,
        is_property: bool = False,
        is_abstract: bool = False,
        is_constructor: bool = False,
        complexity: int = 1,
        decorators: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Function:
        """
        Create function element.

        Args:
            name: Function name
            position: Position in source code
            return_type: Return type
            parameters: Function parameters
            visibility: Visibility
            docstring: Optional documentation string
            is_async: Whether function is async
            is_generator: Whether function is generator
            is_static: Whether function is static
            is_class_method: Whether function is a class method
            is_static_method: Whether function is a static method
            is_property: Whether function is a property
            is_abstract: Whether function is abstract
            is_constructor: Whether function is a constructor
            complexity: Cyclomatic complexity score
            decorators: List of decorator names
            metadata: Optional additional metadata

        Returns:
            Function element

        Raises:
            ValidationError: If parameters are invalid

        Note:
            - Validates name and position
            - Provides type safety
            - Calculates complexity (default: 1)
            - Supports async and generator functions
        """
        # Validation
        if not name:
            raise ValidationError("Function name cannot be empty")
        if not position:
            raise ValidationError("Position cannot be None")

        return Function(
            element_type=ElementType.FUNCTION,
            name=name,
            position=position,
            visibility=visibility,
            docstring=docstring,
            metadata=metadata or {},
            return_type=return_type,
            parameters=parameters or [],
            is_async=is_async,
            is_generator=is_generator,
            is_static=is_static,
            is_class_method=is_class_method,
            is_static_method=is_static_method,
            is_property=is_property,
            is_abstract=is_abstract,
            is_constructor=is_constructor,
            complexity=complexity,
            decorators=decorators or [],
        )

    def create_class(
        self,
        name: str,
        position: Position,
        base_classes: list[str] | None = None,
        implemented_interfaces: list[str] | None = None,
        methods: list[str] | None = None,
        fields: list[str] | None = None,
        properties: list[str] | None = None,
        visibility: Visibility = Visibility.PUBLIC,
        docstring: str | None = None,
        is_abstract: bool = False,
        is_final: bool = False,
        is_static: bool = False,
        is_generic: bool = False,
        is_exception: bool = False,
        is_enum: bool = False,
        is_mixin: bool = False,
        decorators: list[str] | None = None,
        complexity: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> Class:
        """
        Create class element.

        Args:
            name: Class name
            position: Position in source code
            base_classes: List of base class names
            implemented_interfaces: List of interface names
            methods: List of method names
            fields: List of field names
            properties: List of property names
            visibility: Visibility
            docstring: Optional documentation string
            is_abstract: Whether class is abstract
            is_final: Whether class is final
            is_static: Whether class is static
            is_generic: Whether class is generic
            is_exception: Whether class is an exception
            is_enum: Whether class is an enum
            is_mixin: Whether class is a mixin
            decorators: List of decorator names
            complexity: Cyclomatic complexity score
            metadata: Optional additional metadata

        Returns:
            Class element

        Raises:
            ValidationError: If parameters are invalid

        Note:
            - Validates name and position
            - Provides type safety
            - Calculates complexity (default: 1)
            - Supports inheritance and interfaces
        """
        # Validation
        if not name:
            raise ValidationError("Class name cannot be empty")
        if not position:
            raise ValidationError("Position cannot be None")

        return Class(
            element_type=ElementType.CLASS,
            name=name,
            position=position,
            visibility=visibility,
            docstring=docstring,
            metadata=metadata or {},
            base_classes=base_classes or [],
            implemented_interfaces=implemented_interfaces or [],
            methods=methods or [],
            fields=fields or [],
            properties=properties or [],
            is_abstract=is_abstract,
            is_final=is_final,
            is_static=is_static,
            is_generic=is_generic,
            is_exception=is_exception,
            is_enum=is_enum,
            is_mixin=is_mixin,
            decorators=decorators or [],
            complexity=complexity,
        )

    def create_import(
        self,
        module: str,
        position: Position,
        import_type: str = "module",
        imported_name: str = "",
        imported_from: str = "",
        is_relative: bool = False,
        is_star_import: bool = False,
        is_wildcard: bool = False,
        docstring: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Import:
        """
        Create import element.

        Args:
            module: Module name
            position: Position in source code
            import_type: Type of import (module, function, class, variable, from, star, wildcard)
            imported_name: Name being imported
            imported_from: Original location (if using from)
            is_relative: Whether import is relative
            is_star_import: Whether import is star import
            is_wildcard: Whether import is wildcard import
            docstring: Optional documentation string
            metadata: Optional additional metadata

        Returns:
            Import element

        Raises:
            ValidationError: If parameters are invalid

        Note:
            - Validates module name and position
            - Provides type safety
            - Supports all import types (module, function, class, variable, from, star, wildcard)
        """
        # Validation
        if not module:
            raise ValidationError("Module name cannot be empty")
        if not position:
            raise ValidationError("Position cannot be None")

        return Import(
            element_type=ElementType.IMPORT,
            name=f"import_{module}",
            position=position,
            visibility=Visibility.PUBLIC,
            docstring=docstring,
            metadata=metadata or {},
            import_type=import_type,
            module=module,
            imported_name=imported_name,
            imported_from=imported_from,
            is_relative=is_relative,
            is_star_import=is_star_import,
            is_wildcard=is_wildcard,
        )


# ============================================================================
# Convenience Functions
# ============================================================================


@lru_cache(maxsize=128, typed=True)
def get_element_factory() -> ElementFactory:
    """
    Get element factory instance with LRU caching.

    Returns:
        ElementFactory instance

    Performance:
        LRU caching with maxsize=128 reduces overhead for repeated calls.
    """
    return ElementFactory()


# ============================================================================
# Module-level exports
# ============================================================================

__all__: list[str] = [
    # Enums
    "ElementType",
    "Visibility",
    # Exceptions
    "ElementModelError",
    "InitializationError",
    "ValidationError",
    "InconsistencyError",
    # Data classes
    "Position",
    "TypeInfo",
    "DocstringInfo",
    "Element",
    "NamedElement",
    "Variable",
    "Function",
    "Class",
    "Import",
    "ElementFactory",
]

# ============================================================================
# Module-level exports for backward compatibility
# ============================================================================


def __getattr__(name: str) -> Any:
    """
    Fallback for dynamic imports and backward compatibility.

    Args:
        name: Name of the module, class, or function to import

    Returns:
        Imported module, class, or function

    Raises:
        ImportError: If requested component is not found
    """
    # Skip Python internal attributes
    if name.startswith("_"):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    # Handle specific imports
    if name == "ElementFactory":
        return ElementFactory
    elif name == "Position":
        return Position
    elif name == "TypeInfo":
        return TypeInfo
    elif name == "DocstringInfo":
        return DocstringInfo
    elif name == "Element":
        return Element
    elif name == "NamedElement":
        return NamedElement
    elif name == "Variable":
        return Variable
    elif name == "Function":
        return Function
    elif name == "Class":
        return Class
    elif name == "Import":
        return Import
    elif name in [
        "ElementModelError",
        "InitializationError",
        "ValidationError",
        "InconsistencyError",
    ]:
        # Import from module
        import sys

        module = sys.modules[__name__]
        if module is None:
            raise ImportError(f"Module {name} not found")
        return module
    elif name == "get_element_factory":
        return get_element_factory
    else:
        # Default behavior
        try:
            # Try to import from current package
            module = __import__(f".{name}", fromlist=["__name__"])
            return module
        except ImportError:
            raise ImportError(f"Module {name} not found in element package") from None
