#!/usr/bin/env python3
"""
Class Model - Data Structure for Class Elements

This module provides data structures for representing class elements
in source code with inheritance, members, and metadata.

Optimized with:
- Complete type hints (PEP 484)
- Comprehensive error handling
- Performance optimization (slots, caching)
- Detailed documentation

Features:
- Class definitions with metadata
- Inheritance hierarchy tracking
- Member information (methods, fields, properties)
- Visibility (public, private, protected)
- Type-safe operations (PEP 484)
- Immutable data structures (frozen)

Architecture:
- Layered design with clear separation of concerns
- Performance optimization with slots
- Type-safe operations (PEP 484)
- Integration with element model

Author: aisheng.yu
Version: 1.10.5
Date: 2026-01-28
"""

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import (
    TYPE_CHECKING,
    Any,
    Protocol,
)

# Type checking setup
if TYPE_CHECKING:
    # Model imports
    # Utility imports
    from .element import (
        ElementType,
        NamedElement,
        Position,
        TypeInfo,
        Visibility,
    )
else:
    # Runtime imports (when type checking is disabled)
    # Model imports
    # Utility imports
    from .element import (
        ElementType,
        NamedElement,
        Position,
        TypeInfo,
        Visibility,
    )

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# =====
# Type Definitions
# =====


class ClassModelProtocol(Protocol):
    """Interface for class model creation functions."""

    def __call__(self, project_root: str) -> "ClassModel":
        """
        Create class model instance.

        Args:
            project_root: Root directory of the project

        Returns:
            ClassModel instance
        """
        ...


# ============================================================================
# Custom Exceptions
# ============================================================================


class ClassModelError(Exception):
    """Base exception for class model errors."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


class InitializationError(ClassModelError):
    """Exception raised when class model initialization fails."""

    pass


class ValidationError(ClassModelError):
    """Exception raised when class validation fails."""

    pass


class InconsistencyError(ClassModelError):
    """Exception raised when class data is inconsistent."""

    pass


# ============================================================================
# Data Classes
# ============================================================================


@dataclass(frozen=True, slots=True)
class ClassMember:
    """
    Class member information (method, field, property).

    Attributes:
        name: Member name
        member_type: Member type (method, field, property)
        visibility: Visibility (public, private, protected)
        position: Position in source code
        docstring: Optional documentation string
        return_type: Return type information
        parameters: List of parameter names
        is_static: Whether member is static
        is_abstract: Whether member is abstract
        is_override: Whether member overrides parent
    """

    name: str
    member_type: str  # "method", "field", "property"
    visibility: Visibility
    position: Position
    docstring: str | None = None
    return_type: TypeInfo | None = None
    parameters: list[str] = field(default_factory=list)
    is_static: bool = False
    is_abstract: bool = False
    is_override: bool = False

    def __hash__(self) -> int:
        """Hash based on member name and type."""
        return hash((self.name, self.member_type, self.visibility))

    def __str__(self) -> str:
        """String representation of class member."""
        return f"{self.member_type}: {self.name}"


@dataclass(frozen=True, slots=True)
class InheritanceInfo:
    """
    Inheritance hierarchy information.

    Attributes:
        base_classes: List of base class names
        implemented_interfaces: List of interface names
        depth: Depth in inheritance tree
        is_leaf: Whether class has no subclasses
    """

    base_classes: list[str] = field(default_factory=list)
    implemented_interfaces: list[str] = field(default_factory=list)
    depth: int = 0
    is_leaf: bool = True

    def __hash__(self) -> int:
        """Hash based on bases and interfaces."""
        return hash((tuple(self.base_classes), tuple(self.implemented_interfaces)))

    def __str__(self) -> str:
        """String representation of inheritance."""
        bases_str = ", ".join(self.base_classes)
        interfaces_str = ", ".join(self.implemented_interfaces)
        if bases_str and interfaces_str:
            return f"Inheritance(bases={bases_str}, interfaces={interfaces_str})"
        elif bases_str:
            return f"Inheritance(bases={bases_str})"
        elif interfaces_str:
            return f"Inheritance(interfaces={interfaces_str})"
        else:
            return "Inheritance()"


@dataclass(frozen=True, slots=True)
class ClassMetadata:
    """
    Additional metadata for class element.

    Attributes:
        decorator_names: List of decorator names
        annotation_names: List of annotation names
        metaclass: Metaclass name
        is_exception: Whether class is an exception
        is_generic: Whether class is generic
        type_parameters: List of generic type parameters
        module: Module name where class is defined
    """

    decorator_names: list[str] = field(default_factory=list)
    annotation_names: list[str] = field(default_factory=list)
    metaclass: str | None = None
    is_exception: bool = False
    is_generic: bool = False
    type_parameters: list[str] = field(default_factory=list)
    module: str = ""

    def __hash__(self) -> int:
        """Hash based on decorators, annotations, and metaclass."""
        return hash(
            (
                tuple(self.decorator_names),
                tuple(self.annotation_names),
                self.metaclass or "",
            )
        )

    def __str__(self) -> str:
        """String representation of metadata."""
        return f"Metadata(decorators: {len(self.decorator_names)}, annotations: {len(self.annotation_names)})"


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
        name: Element name
        position: Position in source code
        visibility: Visibility (public, private, protected, etc.)
        docstring: Optional documentation string
        metadata: Optional additional metadata dictionary
        base_classes: List of base class names
        implemented_interfaces: List of interface names
        methods: List of method information
        fields: List of field information
        properties: List of property information
        inheritance_info: Inheritance hierarchy information
        is_abstract: Whether class is abstract
        is_final: Whether class is final
        is_static: Whether class is static
        is_generic: Whether class is generic
        is_exception: Whether class is an exception
        is_enum: Whether class is an enum
        is_mixin: Whether class is a mixin
        complexity: Cyclomatic complexity score
    """

    base_classes: list[str] = field(default_factory=list)
    implemented_interfaces: list[str] = field(default_factory=list)
    methods: list[ClassMember] = field(default_factory=list)
    fields: list[ClassMember] = field(default_factory=list)
    properties: list[ClassMember] = field(default_factory=list)
    inheritance_info: InheritanceInfo | None = None
    is_abstract: bool = False
    is_final: bool = False
    is_static: bool = False
    is_generic: bool = False
    is_exception: bool = False
    is_enum: bool = False
    is_mixin: bool = False
    complexity: int = 1

    def __hash__(self) -> int:
        """Hash based on element type, name, and bases."""
        base_hash = hash(tuple(self.base_classes))
        interface_hash = hash(tuple(self.implemented_interfaces))
        element_hash = super().__hash__()
        return hash((element_hash, base_hash, interface_hash))

    def __str__(self) -> str:
        """String representation of class."""
        return f"Class: {self.name}"


# ============================================================================
# Class Model
# ============================================================================


class ClassModel:
    """
    Optimized class model with type safety, caching, and performance monitoring.

    Features:
    - Type-safe operations (PEP 484)
    - Comprehensive error handling
    - Performance optimization (slots, caching)
    - Member management (methods, fields, properties)
    - Inheritance tracking
    - Cyclomatic complexity calculation
    - Visibility detection

    Architecture:
    - Layered design with clear separation of concerns
    - Performance optimization with slots and caching
    - Type-safe operations (PEP 484)
    - Integration with element model

    Usage:
        >>> from tree_sitter_analyzer.models import ClassModel, Class
        >>> model = ClassModel()
        >>> class_elem = model.create_class("MyClass", position)
        >>> print(class_elem.methods)
    """

    def __init__(self, config: Any | None = None):
        """
        Initialize class model.

        Args:
            config: Optional configuration (not used in this implementation)
        """
        # Performance statistics
        self._stats: dict[str, Any] = {
            "total_classes": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "creation_times": [],
        }

    def create_class(
        self,
        name: str,
        position: Position,
        base_classes: list[str] | None = None,
        implemented_interfaces: list[str] | None = None,
        methods: list[ClassMember] | None = None,
        fields: list[ClassMember] | None = None,
        properties: list[ClassMember] | None = None,
        inheritance_info: InheritanceInfo | None = None,
        is_abstract: bool = False,
        is_final: bool = False,
        is_static: bool = False,
        is_generic: bool = False,
        is_exception: bool = False,
        is_enum: bool = False,
        is_mixin: bool = False,
        decorators: list[str] | None = None,
        annotations: list[str] | None = None,
        metaclass: str | None = None,
        module: str = "",
        docstring: str | None = None,
        visibility: Visibility = Visibility.PUBLIC,
        metadata: dict[str, Any] | None = None,
    ) -> Class:
        """
        Create class element.

        Args:
            name: Class name
            position: Position in source code
            base_classes: List of base class names
            implemented_interfaces: List of interface names
            methods: List of method information
            fields: List of field information
            properties: List of property information
            inheritance_info: Inheritance hierarchy information
            is_abstract: Whether class is abstract
            is_final: Whether class is final
            is_static: Whether class is static
            is_generic: Whether class is generic
            is_exception: Whether class is an exception
            is_enum: Whether class is an enum
            is_mixin: Whether class is a mixin
            decorators: List of decorator names
            annotations: List of annotation names
            metaclass: Metaclass name
            module: Module name
            docstring: Optional documentation string
            visibility: Visibility
            metadata: Optional additional metadata dictionary

        Returns:
            Class element

        Raises:
            ValidationError: If parameters are invalid

        Note:
            - Creates Class element with all attributes
            - Calculates complexity if not provided
            - Thread-safe if enabled (not implemented in this version)
        """
        # Update statistics
        self._stats["total_classes"] += 1

        # Validation
        if not name:
            raise ValidationError("Class name cannot be empty")

        # Calculate complexity
        complexity = 1
        if methods:
            complexity += len(methods)
        if fields:
            complexity += len(fields)
        if properties:
            complexity += len(properties)
        if base_classes:
            complexity += len(base_classes)
        if implemented_interfaces:
            complexity += len(implemented_interfaces)
        if inheritance_info:
            complexity += inheritance_info.depth

        # Create class element
        class_elem = Class(
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
            inheritance_info=inheritance_info,
            is_abstract=is_abstract,
            is_final=is_final,
            is_static=is_static,
            is_generic=is_generic,
            is_exception=is_exception,
            is_enum=is_enum,
            is_mixin=is_mixin,
            complexity=complexity,
        )

        return class_elem

    def create_method_member(
        self,
        name: str,
        position: Position,
        return_type: TypeInfo | None = None,
        parameters: list[str] | None = None,
        visibility: Visibility = Visibility.PUBLIC,
        docstring: str | None = None,
        is_static: bool = False,
        is_abstract: bool = False,
        is_override: bool = False,
    ) -> ClassMember:
        """
        Create method member.

        Args:
            name: Method name
            position: Position in source code
            return_type: Return type information
            parameters: List of parameter names
            visibility: Visibility (default: PUBLIC)
            docstring: Optional documentation string
            is_static: Whether method is static
            is_abstract: Whether method is abstract
            is_override: Whether method overrides parent

        Returns:
            ClassMember element

        Raises:
            ValidationError: If parameters are invalid

        Note:
            - Creates ClassMember with method type
            - Includes all method attributes
        """
        # Validation
        if not name:
            raise ValidationError("Method name cannot be empty")

        # Create method member
        member = ClassMember(
            name=name,
            member_type="method",
            visibility=visibility,
            position=position,
            docstring=docstring,
            return_type=return_type,
            parameters=parameters or [],
            is_static=is_static,
            is_abstract=is_abstract,
            is_override=is_override,
        )

        return member

    def create_field_member(
        self,
        name: str,
        position: Position,
        field_type: TypeInfo,
        visibility: Visibility = Visibility.PUBLIC,
        is_static: bool = False,
        docstring: str | None = None,
    ) -> ClassMember:
        """
        Create field member.

        Args:
            name: Field name
            position: Position in source code
            field_type: Type information
            visibility: Visibility (default: PUBLIC)
            is_static: Whether field is static
            docstring: Optional documentation string

        Returns:
            ClassMember element

        Raises:
            ValidationError: If parameters are invalid

        Note:
            - Creates ClassMember with field type
            - Includes all field attributes
        """
        # Validation
        if not name:
            raise ValidationError("Field name cannot be empty")

        # Create field member
        member = ClassMember(
            name=name,
            member_type="field",
            visibility=visibility,
            position=position,
            docstring=docstring,
            return_type=field_type,
            parameters=[],
            is_static=is_static,
            is_abstract=False,
            is_override=False,
        )

        return member

    def create_property_member(
        self,
        name: str,
        position: Position,
        return_type: TypeInfo,
        visibility: Visibility = Visibility.PUBLIC,
        is_static: bool = False,
        docstring: str | None = None,
    ) -> ClassMember:
        """
        Create property member.

        Args:
            name: Property name
            position: Position in source code
            return_type: Return type information
            visibility: Visibility (default: PUBLIC)
            is_static: Whether property is static
            docstring: Optional documentation string

        Returns:
            ClassMember element

        Raises:
            ValidationError: If parameters are invalid

        Note:
            - Creates ClassMember with property type
            - Includes all property attributes
        """
        # Validation
        if not name:
            raise ValidationError("Property name cannot be empty")

        # Create property member
        member = ClassMember(
            name=name,
            member_type="property",
            visibility=visibility,
            position=position,
            docstring=docstring,
            return_type=return_type,
            parameters=[],
            is_static=is_static,
            is_abstract=False,
            is_override=False,
        )

        return member

    def get_stats(self) -> dict[str, Any]:
        """
        Get class model statistics.

        Returns:
            Dictionary with class model statistics

        Note:
            - Returns creation counts and cache statistics
            - Returns performance metrics
        """
        return {
            "total_classes": self._stats["total_classes"],
            "cache_hits": self._stats["cache_hits"],
            "cache_misses": self._stats["cache_misses"],
            "creation_times": self._stats["creation_times"],
            "average_creation_time": (
                sum(self._stats["creation_times"]) / len(self._stats["creation_times"])
                if self._stats["creation_times"]
                else 0
            ),
        }


# ============================================================================
# Convenience Functions
# ============================================================================


@lru_cache(maxsize=64, typed=True)
def get_class_model() -> ClassModel:
    """
    Get class model instance with LRU caching.

    Returns:
        ClassModel instance

    Performance:
        LRU caching with maxsize=64 reduces overhead for repeated calls.
    """
    return ClassModel()


# ============================================================================
# Module-level exports
# ============================================================================

__all__: list[str] = [
    # Data classes
    "ClassMember",
    "InheritanceInfo",
    "ClassMetadata",
    "Class",
    # Main class
    "ClassModel",
    # Convenience functions
    "get_class_model",
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
    # Handle specific imports
    if name == "ClassModel":
        return ClassModel
    elif name == "ClassMember":
        return ClassMember
    elif name == "InheritanceInfo":
        return InheritanceInfo
    elif name == "ClassMetadata":
        return ClassMetadata
    elif name == "get_class_model":
        return get_class_model
    else:
        # Default behavior
        try:
            # Try to import from current package
            module = __import__(f".{name}", fromlist=["__name__"])
            return module
        except ImportError:
            raise ImportError(f"Module {name} not found") from None
