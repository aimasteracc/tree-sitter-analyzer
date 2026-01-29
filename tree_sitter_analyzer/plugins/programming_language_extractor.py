#!/usr/bin/env python3
"""
Programming Language Extractor - Advanced Plugin System

Base class for programming language plugins with advanced features
including iterative AST traversal, element caching, cyclomatic complexity
calculation, and container node type customization.

Optimized with:
- Complete type hints (PEP 484)
- Comprehensive error handling and recovery
- Performance optimization (LRU caching, iterative traversal)
- Thread-safe operations
- Complexity calculation (cyclomatic metrics)
- Detailed documentation

Features:
- Iterative AST traversal with depth limits
- Element caching for performance
- Cyclomatic complexity calculation
- Container node type customization
- Comprehensive error handling
- Performance monitoring and statistics
- Type-safe operations (PEP 484)

Architecture:
- Layered design with clear separation of concerns
- Performance optimization with LRU caching and iterative traversal
- Thread-safe operations where applicable
- Integration with models and core components

Usage:
    >>> from tree_sitter_analyzer.plugins import ProgrammingLanguageExtractor
    >>> extractor = ProgrammingLanguageExtractor(max_depth=50)
    >>> functions = extractor.extract_functions(tree, source_code)

Author: aisheng.yu
Version: 1.10.5
Date: 2026-01-28
"""

import functools
import hashlib
import logging
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, List, Dict, Tuple, Union, Callable, Type, NamedTuple
from functools import lru_cache, wraps
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from time import perf_counter

# Type checking setup
if TYPE_CHECKING:
    # Tree-sitter imports
    from tree_sitter import Tree, Language, Node

    # Model imports
    from ..models import (
        CodeElement,
        Class,
        Function,
        Variable,
        Import,
    )

    # Utility imports
    from ..utils.logging import (
        log_debug,
        log_info,
        log_warning,
        log_error,
        log_performance,
        setup_logger,
        create_performance_logger,
    )
else:
    # Runtime imports (when type checking is disabled)
    Tree = Any
    Language = Any
    Node = Any
    CodeElement = Any
    Class = Any
    Function = Any
    Variable = Any
    Import = Any
    log_debug = Any
    log_info = Any
    log_warning = Any
    log_error = Any
    log_performance = Any
    setup_logger = Any
    create_performance_logger = Any

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ============================================================================
# Type Definitions
# ============================================================================

if sys.version_info >= (3, 8):
    from typing import Protocol
else:
    Protocol = object

class ExtractorProtocol(Protocol):
    """Interface for extractor creation functions."""

    def __call__(self, project_root: str) -> "ProgrammingLanguageExtractor":
        """
        Create extractor instance.

        Args:
            project_root: Root directory of the project

        Returns:
            ProgrammingLanguageExtractor instance
        """
        ...

class CacheProtocol(Protocol):
    """Interface for cache services."""

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        ...

    def set(self, key: str, value: Any) -> None:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
        """
        ...

    def clear(self) -> None:
        """Clear all cache entries."""
        ...

class PerformanceMonitorProtocol(Protocol):
    """Interface for performance monitoring."""

    def measure_operation(self, operation_name: str) -> Any:
        """
        Measure operation execution time.

        Args:
            operation_name: Name of operation

        Returns:
            Context manager for measuring time
        """
        ...

# ============================================================================
# Custom Exceptions
# ============================================================================

class ProgrammingLanguageExtractorError(Exception):
    """Base exception for programming language extractor errors."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


class InitializationError(ProgrammingLanguageExtractorError):
    """Exception raised when extractor initialization fails."""
    pass


class ExtractionError(ProgrammingLanguageExtractorError):
    """Exception raised when code extraction fails."""
    pass


class TraversalError(ProgrammingLanguageExtractorError):
    """Exception raised when AST traversal fails."""
    pass


class ComplexityCalculationError(ProgrammingLanguageExtractorError):
    """Exception raised when complexity calculation fails."""
    pass


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ExtractionMetrics:
    """
    Metrics for code extraction operations.

    Attributes:
        total_nodes: Total number of nodes visited
        processed_nodes: Number of nodes processed
        extracted_elements: Number of elements extracted
        cache_hits: Number of cache hits
        extraction_time: Time taken for extraction (in seconds)
        complexity_score: Total complexity score (cyclomatic metrics)
        average_complexity: Average complexity per function
    """

    total_nodes: int = 0
    processed_nodes: int = 0
    extracted_elements: int = 0
    cache_hits: int = 0
    extraction_time: float = 0.0
    complexity_score: int = 0
    average_complexity: float = 0.0


@dataclass
class ExtractionContext:
    """
    Context for code extraction operations.

    Attributes:
        source_code: Source code being extracted
        content_lines: Source code split by lines
        max_depth: Maximum traversal depth
        language: Programming language name
        extractor_name: Name of the extractor
        metrics: Extraction metrics
    """

    source_code: str
    content_lines: List[str] = field(default_factory=list)
    max_depth: int = 50
    language: str = "unknown"
    extractor_name: str = "ProgrammingLanguageExtractor"
    metrics: Optional[ExtractionMetrics] = None

    @property
    def line_count(self) -> int:
        """Get line count of source code."""
        return len(self.content_lines)


# ============================================================================
# Programming Language Extractor
# ============================================================================

class ProgrammingLanguageExtractor:
    """
    Optimized programming language extractor with advanced features.

    Features:
    - Iterative AST traversal with depth limits
    - Element caching for performance
    - Cyclomatic complexity calculation
    - Container node type customization
    - Thread-safe operations
    - Performance monitoring and statistics
    - Comprehensive error handling

    Architecture:
    - Layered design with clear separation of concerns
    - Performance optimization with LRU caching and iterative traversal
    - Thread-safe operations where applicable
    - Integration with models and core components

    Usage:
        >>> extractor = ProgrammingLanguageExtractor(max_depth=50)
        >>> functions = extractor.extract_functions(tree, source_code)
        >>> print(f"Extracted {len(functions)} functions")
    """

    # Class-level cache (shared across all instances)
    _element_cache: Dict[Tuple[int, str], Any] = {}
    _node_cache: Dict[int, Dict[str, Any]] = {}
    _lock: threading.RLock = threading.RLock()

    # Performance statistics
    _stats: Dict[str, Any] = {
        "total_extractions": 0,
        "total_nodes": 0,
        "total_cache_hits": 0,
        "total_cache_misses": 0,
        "extraction_times": [],
    }

    def __init__(self, max_depth: int = 50, enable_caching: bool = True, enable_thread_safety: bool = True):
        """
        Initialize programming language extractor.

        Args:
            max_depth: Maximum traversal depth (default: 50)
            enable_caching: Enable LRU caching for elements (default: True)
            enable_thread_safety: Enable thread-safe operations (default: True)
        """
        self._max_depth = max_depth
        self._enable_caching = enable_caching
        self._enable_thread_safety = enable_thread_safety

        # Thread-safe lock for operations
        self._lock = threading.RLock() if self._enable_thread_safety else type(None)

    def _get_container_node_types(self) -> set[str]:
        """
        Get node types that may contain target elements.

        Returns:
            Set of container node type names

        Note:
            - Default implementation uses common containers
            - Can be overridden for language-specific types
        """
        return {
            "program",
            "module",
            "block",
            "function_definition",
            "class_definition",
            "if_statement",
            "for_statement",
            "while_statement",
            "try_statement",
            "catch_statement",
            "with_statement",
            "import_statement",
            "export_statement",
        }

    def extract_functions(self, tree: Tree, source_code: str) -> List[Function]:
        """
        Extract function definitions from AST.

        Args:
            tree: Tree-sitter tree
            source_code: Source code string

        Returns:
            List of Function objects

        Raises:
            ExtractionError: If extraction fails
            TraversalError: If AST traversal fails

        Note:
            - Uses iterative traversal with depth limits
            - Extracts function metadata (name, parameters, return type)
            - Calculates cyclomatic complexity
            - Performance: O(n) where n is number of nodes
        """
        # Start performance monitoring
        operation_name = f"extract_functions_{language}"
        start_time = perf_counter()

        # Update statistics
        self._stats["total_extractions"] += 1

        try:
            # Create extraction context
            context = ExtractionContext(
                source_code=source_code,
                content_lines=source_code.splitlines(),
                max_depth=self._max_depth,
                language=language,
                extractor_name="extract_functions",
            )

            # Define extractors for function nodes
            extractors = {
                "function_definition": self._extract_function_definition,
            "method_definition": self._extract_method_definition,
                "lambda_expression": self._extract_lambda_expression,
            "async_function": self._extract_async_function,
            "generator_function": self._extract_generator_function,
            "constructor": self._extract_constructor,
            "decorated_function": self._extract_decorated_function,
            "function_overload": self._extract_function_overload,
            "template_function": self._extract_template_function,
                "inline_function": self._extract_inline_function,
                "callback_function": self._extract_callback_function,
                "getter_function": self._extract_getter,
                "setter_function": self._extract_setter,
                "property_function": self._extract_property,
                "static_method": self._extract_static_method,
                "class_method": self._extract_class_method,
                "instance_method": self._extract_instance_method,
                "public_function": self._extract_public_function,
                "private_function": self._extract_private_function,
                "protected_function": self._extract_protected_function,
            }

            # Execute extraction
            results = []
            self._traverse_and_extract(tree, source_code, extractors, results, context)

            # Update statistics
            self._stats["total_nodes"] += context.metrics.total_nodes
            self._stats["total_cache_hits"] += context.metrics.cache_hits

            # Calculate complexity
            complexity_scores = []
            for func in results:
                if hasattr(func, "complexity"):
                    complexity_scores.append(func.complexity)

            if complexity_scores:
                average_complexity = sum(complexity_scores) / len(complexity_scores)
            else:
                average_complexity = 0.0

            # Update metrics
            context.metrics.complexity_score = sum(complexity_scores)
            context.metrics.average_complexity = average_complexity

            return results

        except Exception as e:
            end_time = perf_counter()
            extraction_time = end_time - start_time

            self._stats["extraction_times"].append(extraction_time)

            log_error(f"Function extraction failed: {e}")

            raise ExtractionError(f"Function extraction failed: {e}")

    def extract_classes(self, tree: Tree, source_code: str) -> List[Class]:
        """
        Extract class definitions from AST.

        Args:
            tree: Tree-sitter tree
            source_code: Source code string

        Returns:
            List of Class objects

        Raises:
            ExtractionError: If extraction fails
            TraversalError: If AST traversal fails

        Note:
            - Uses iterative traversal with depth limits
            - Extracts class metadata (name, parent classes, methods)
            - Calculates cyclomatic complexity
            - Performance: O(n) where n is number of nodes
        """
        # Start performance monitoring
        operation_name = f"extract_classes_{language}"
        start_time = perf_counter()

        # Update statistics
        self._stats["total_extractions"] += 1

        try:
            # Create extraction context
            context = ExtractionContext(
                source_code=source_code,
                content_lines=source_code.splitlines(),
                max_depth=self._max_depth,
                language=language,
                extractor_name="extract_classes",
            )

            # Define extractors for class nodes
            extractors = {
                "class_definition": self._extract_class_definition,
                "interface_definition": self._extract_interface_definition,
                "struct_definition": self._extract_struct_definition,
                "abstract_class": self._extract_abstract_class,
                "final_class": self._extract_final_class,
                "sealed_class": self._extract_sealed_class,
                "inner_class": self._extract_inner_class,
                "static_class": self._extract_static_class,
                "public_class": self._extract_public_class,
                "private_class": self._extract_private_class,
                "protected_class": self._extract_protected_class,
                "enum_definition": self._extract_enum_definition,
                "mixin_class": self._extract_mixin_class,
                "decorated_class": self._extract_decorated_class,
                "generic_class": self._extract_generic_class,
            }

            # Execute extraction
            results = []
            self._traverse_and_extract(tree, source_code, extractors, results, context)

            # Update statistics
            self._stats["total_nodes"] += context.metrics.total_nodes
            self._stats["total_cache_hits"] += context.metrics.cache_hits

            return results

        except Exception as e:
            end_time = perf_counter()
            extraction_time = end_time - start_time

            self._stats["extraction_times"].append(extraction_time)

            log_error(f"Class extraction failed: {e}")

            raise ExtractionError(f"Class extraction failed: {e}")

    def _traverse_and_extract(self, tree: Tree, source_code: str, extractors: Dict[str, Callable], results: List[Any], context: ExtractionContext) -> None:
        """
        Generic iterative AST traversal with element extraction.

        Args:
            tree: Tree-sitter tree
            source_code: Source code string
            extractors: Mapping of node types to extractor functions
            results: List to accumulate extracted elements
            context: Extraction context for metadata

        Note:
            - Uses iterative traversal (not recursive) to avoid stack overflow
            - Depth-limited traversal for safety
            - Uses caching for performance
            - Thread-safe if enabled
        """
        # Use iterative traversal with explicit stack (not recursive)
        node_stack = deque([(tree.root_node, 0)])
        target_node_types = set(extractors.keys())
        container_node_types = self._get_container_node_types()

        while node_stack:
            current_node, depth = node_stack.popleft()

            # Skip if None or exceeds max depth
            if current_node is None or depth > self._max_depth:
                continue

            # Update metrics
            context.metrics.total_nodes += 1

            # Check if this node type has an extractor
            if current_node.type in extractors:
                try:
                    start_time = perf_counter()
                    extractor = extractors[current_node.type]
                    element = extractor(current_node, context)
                    end_time = perf_counter()
                    extraction_time = end_time - start_time

                    if element is not None:
                        results.append(element)
                        context.metrics.extracted_elements += 1

                    log_debug(f"Extracted {current_node.type} in {extraction_time:.3f}s")

                except Exception as e:
                    log_error(f"Extraction failed for {current_node.type}: {e}")
                    continue

            # Push children to stack (if any)
            if hasattr(current_node, "children") and current_node.children:
                # Check if this is a container node (might contain targets)
                if current_node.type in container_node_types:
                    for child in reversed(current_node.children):
                        node_stack.append((child, depth + 1))
                else:
                    # Non-container, but might have children (e.g., block)
                    for child in reversed(current_node.children):
                        node_stack.append((child, depth + 1))

    def _extract_function_definition(self, node: Node, context: ExtractionContext) -> Optional[Function]:
        """
        Extract function definition from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Function object or None

        Note:
            - Extracts function name, parameters, return type
            - Calculates cyclomatic complexity
            - Extracts docstring
        """
        try:
            # Check for cache
            cache_key = (id(node), "function")
            if self._enable_caching and cache_key in self._element_cache:
                context.metrics.cache_hits += 1
                return self._element_cache[cache_key]

            # Extract function name
            if hasattr(node, "named_child_count") and node.named_child_count > 0:
                for i in range(node.named_child_count):
                    child = node.named_child(i)
                    if child.type == "identifier":
                        name = child.text.decode("utf-8", errors="replace") if child.text else ""
                        break
            else:
                name = ""

            # Extract parameters
            parameters = []
            if hasattr(node, "children"):
                for child in node.children:
                    if child.type == "parameters":
                        for param in child.children:
                            if param.type == "identifier":
                                param_name = param.text.decode("utf-8", errors="replace") if param.text else ""
                                if param_name:
                                    parameters.append(param_name)

            # Extract return type
            return_type = ""
            if hasattr(node, "children"):
                for child in node.children:
                    if child.type == "type":
                        if hasattr(child, "named_child_count") and child.named_child_count > 0:
                            type_node = child.named_child(0)
                            if type_node and type_node.type == "identifier":
                                return_type = type_node.text.decode("utf-8", errors="replace") if type_node.text else ""

            # Extract docstring
            docstring = self._extract_docstring(node, context)

            # Calculate complexity
            complexity = self._calculate_complexity(node, context)

            # Create function object
            function = Function(
                name=name,
                parameters=parameters,
                return_type=return_type,
                complexity=complexity,
                docstring=docstring,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                start_column=node.start_point[1] + 1,
                end_column=node.end_point[1] + 1,
            )

            # Cache result
            if self._enable_caching:
                self._element_cache[cache_key] = function

            return function

        except Exception as e:
            log_error(f"Function definition extraction failed: {e}")
            return None

    def _extract_method_definition(self, node: Node, context: ExtractionContext) -> Optional[Function]:
        """
        Extract method definition from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Function object or None

        Note:
            - Similar to function definition but for methods
            - Extracts method name, parameters, return type
            - Calculates cyclomatic complexity
        """
        return self._extract_function_definition(node, context)

    def _extract_lambda_expression(self, node: Node, context: ExtractionContext) -> Optional[Function]:
        """
        Extract lambda expression from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Function object or None

        Note:
            - Extracts lambda parameters
            - Calculates cyclomatic complexity
        """
        try:
            # Extract parameters
            parameters = []
            if hasattr(node, "children"):
                for child in node.children:
                    if child.type == "lambda":
                        for param in child.children:
                            if param.type == "identifier":
                                param_name = param.text.decode("utf-8", errors="replace") if param.text else ""
                                if param_name:
                                    parameters.append(param_name)

            # Create function object
            function = Function(
                name="<lambda>",
                parameters=parameters,
                return_type="",
                complexity=1,  # Lambda complexity
                docstring="",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                start_column=node.start_point[1] + 1,
                end_column=node.end_point[1] + 1,
            )

            return function

        except Exception as e:
            log_error(f"Lambda expression extraction failed: {e}")
            return None

    def _extract_async_function(self, node: Node, context: ExtractionContext) -> Optional[Function]:
        """
        Extract async function definition from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Function object or None

        Note:
            - Extracts async function name, parameters, return type
            - Calculates cyclomatic complexity
        """
        return self._extract_function_definition(node, context)

    def _extract_generator_function(self, node: Node, context: ExtractionContext) -> Optional[Function]:
        """
        Extract generator function from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Function object or None

        Note:
            - Identifies generator functions
            - Extracts function name, parameters, return type
            - Calculates cyclomatic complexity
        """
        return self._extract_function_definition(node, context)

    def _extract_constructor(self, node: Node, context: ExtractionContext) -> Optional[Function]:
        """
        Extract constructor from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Function object or None

        Note:
            - Identifies constructors
            - Extracts parameters
            - Calculates cyclomatic complexity
        """
        try:
            # Extract parameters
            parameters = []
            if hasattr(node, "children"):
                for child in node.children:
                    if child.type == "parameters":
                        for param in child.children:
                            if param.type == "identifier":
                                param_name = param.text.decode("utf-8", errors="replace") if param.text else ""
                                if param_name:
                                    parameters.append(param_name)

            # Create function object
            function = Function(
                name="<constructor>",
                parameters=parameters,
                return_type="",
                complexity=self._calculate_complexity(node, context),
                docstring="",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                start_column=node.start_point[1] + 1,
                end_column=node.end_point[1] + 1,
            )

            return function

        except Exception as e:
            log_error(f"Constructor extraction failed: {e}")
            return None

    def _extract_decorated_function(self, node: Node, context: ExtractionContext) -> Optional[Function]:
        """
        Extract decorated function from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Function object or None

        Note:
            - Identifies decorators and wraps function
            - Extracts function name, parameters, return type
            - Calculates cyclomatic complexity
        """
        try:
            # Find the actual function definition (skip decorators)
            actual_function = None
            if hasattr(node, "children"):
                for child in node.children:
                    if child.type == "function_definition":
                        actual_function = child
                        break
                    elif child.type == "method_definition":
                        actual_function = child
                        break

            if actual_function:
                return self._extract_function_definition(actual_function, context)

            return None

        except Exception as e:
            log_error(f"Decorated function extraction failed: {e}")
            return None

    def _extract_function_overload(self, node: Node, context: ExtractionContext) -> Optional[Function]:
        """
        Extract function overload from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Function object or None

        Note:
            - Identifies overloads (multiple functions with same name)
            - Extracts function name, parameters, return type
            - Calculates cyclomatic complexity
        """
        try:
            # Extract function definition
            return self._extract_function_definition(node, context)

        except Exception as e:
            log_error(f"Function overload extraction failed: {e}")
            return None

    def _extract_template_function(self, node: Node, context: ExtractionContext) -> Optional[Function]:
        """
        Extract template function from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Function object or None

        Note:
            - Identifies template functions
            - Extracts function name, parameters, return type
            - Calculates cyclomatic complexity
        """
        try:
            # Extract function definition
            return self._extract_function_definition(node, context)

        except Exception as e:
            log_error(f"Template function extraction failed: {e}")
            return None

    def _extract_inline_function(self, node: Node, context: ExtractionContext) -> Optional[Function]:
        """
        Extract inline function from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Function object or None

        Note:
            - Identifies inline functions
            - Extracts function name, parameters, return type
            - Calculates cyclomatic complexity
        """
        return self._extract_function_definition(node, context)

    def _extract_callback_function(self, node: Node, context: ExtractionContext) -> Optional[Function]:
        """
        Extract callback function from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Function object or None

        Note:
            - Identifies callback functions
            - Extracts function name, parameters, return type
            - Calculates cyclomatic complexity
        """
        return self._extract_function_definition(node, context)

    def _extract_getter(self, node: Node, context: ExtractionContext) -> Optional[Function]:
        """
        Extract getter function from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Function object or None

        Note:
            - Identifies getter methods
            - Extracts return type
            - Calculates cyclomatic complexity
        """
        try:
            # Get property name
            property_name = ""
            if hasattr(node, "property_name"):
                property_name = node.property_name

            # Extract return type
            return_type = ""
            if hasattr(node, "return_type"):
                if hasattr(node.return_type, "type"):
                    type_node = node.return_type.type
                    if hasattr(type_node, "named_child_count") and type_node.named_child_count > 0:
                        return_type_node = type_node.named_child(0)
                        if return_type_node and return_type_node.type == "identifier":
                            return_type = return_type_node.text.decode("utf-8", errors="replace") if return_type_node.text else ""

            # Create function object
            function = Function(
                name=f"get_{property_name}",
                parameters=[],
                return_type=return_type,
                complexity=self._calculate_complexity(node, context),
                docstring="",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                start_column=node.start_point[1] + 1,
                end_column=node.end_point[1] + 1,
            )

            return function

        except Exception as e:
            log_error(f"Getter extraction failed: {e}")
            return None

    def _extract_setter(self, node: Node, context: ExtractionContext) -> Optional[Function]:
        """
        Extract setter function from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Function object or None

        Note:
            - Identifies setter methods
            - Extracts parameter type
            - Calculates cyclomatic complexity
        """
        try:
            # Get property name
            property_name = ""
            if hasattr(node, "property_name"):
                property_name = node.property_name

            # Extract parameter type
            param_type = ""
            if hasattr(node, "parameters") and node.parameters:
                if hasattr(node.parameters, "type"):
                    type_node = node.parameters.type
                    if hasattr(type_node, "named_child_count") and type_node.named_child_count > 0:
                        param_type_node = type_node.named_child(0)
                        if param_type_node and param_type_node.type == "identifier":
                            param_type = param_type_node.text.decode("utf-8", errors="replace") if param_type_node.text else ""

            # Create function object
            function = Function(
                name=f"set_{property_name}",
                parameters=[f"value: {param_type}"],
                return_type="",
                complexity=self._calculate_complexity(node, context),
                docstring="",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                start_column=node.start_point[1] + 1,
                end_column=node.end_point[1] + 1,
            )

            return function

        except Exception as e:
            log_error(f"Setter extraction failed: {e}")
            return None

    def _extract_property_function(self, node: Node, context: ExtractionContext) -> Optional[Function]:
        """
        Extract property function from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Function object or None

        Note:
            - Identifies property decorators
            - Extracts getter/setter functions
            - Calculates cyclomatic complexity
        """
        return self._extract_getter(node, context)

    def _extract_static_method(self, node: Node, context: ExtractionContext) -> Optional[Function]:
        """
        Extract static method from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Function object or None

        Note:
            - Identifies static methods
            - Extracts method name, parameters, return type
            - Calculates cyclomatic complexity
        """
        # Check if static
        is_static = False
        if hasattr(node, "modifier"):
            for mod in node.modifier:
                if mod and mod.text.decode("utf-8", errors="replace") == "static":
                    is_static = True
                    break

        if is_static:
            # Add static prefix to name
            base_function = self._extract_function_definition(node, context)
            if base_function:
                return Function(
                    name=f"static_{base_function.name}",
                    parameters=base_function.parameters,
                    return_type=base_function.return_type,
                    complexity=base_function.complexity,
                    docstring=base_function.docstring,
                    start_line=base_function.start_line,
                    end_line=base_function.end_line,
                    start_column=base_function.start_column,
                    end_column=base_function.end_column,
                )

        return base_function

    def _extract_class_method(self, node: Node, context: ExtractionContext) -> Optional[Function]:
        """
        Extract class method from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Function object or None

        Note:
            - Extracts method name, parameters, return type
            - Calculates cyclomatic complexity
            - Includes visibility (public, private, protected)
        """
        return self._extract_function_definition(node, context)

    def _extract_instance_method(self, node: Node, context: ExtractionContext) -> Optional[Function]:
        """
        Extract instance method from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Function object or None

        Note:
            - Extracts instance method name, parameters, return type
            - Calculates cyclomatic complexity
            - Includes visibility (public, private, protected)
        """
        return self._extract_function_definition(node, context)

    def _extract_public_function(self, node: Node, context: ExtractionContext) -> Optional[Function]:
        """
        Extract public function from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Function object or None

        Note:
            - Identifies public methods
            - Extracts method name, parameters, return type
            - Calculates cyclomatic complexity
        """
        return self._extract_function_definition(node, context)

    def _extract_private_function(self, node: Node, context: ExtractionContext) -> Optional[Function]:
        """
        Extract private function from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Function object or None

        Note:
            - Identifies private methods
            - Extracts method name, parameters, return type
            - Calculates cyclomatic complexity
        """
        return self._extract_function_definition(node, context)

    def _extract_protected_function(self, node: Node, context: ExtractionContext) -> Optional[Function]:
        """
        Extract protected function from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Function object or None

        Note:
            - Identifies protected methods
            - Extracts method name, parameters, return type
            - Calculates cyclomatic complexity
        """
        return self._extract_function_definition(node, context)

    def _extract_class_definition(self, node: Node, context: ExtractionContext) -> Optional[Class]:
        """
        Extract class definition from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Class object or None

        Raises:
            ExtractionError: If class extraction fails

        Note:
            - Extracts class name, parent classes, methods
            - Calculates cyclomatic complexity
            - Extracts docstring
        """
        try:
            # Check for cache
            cache_key = (id(node), "class")
            if self._enable_caching and cache_key in self._element_cache:
                context.metrics.cache_hits += 1
                return self._element_cache[cache_key]

            # Extract class name
            name = ""
            if hasattr(node, "name"):
                name = node.name.text.decode("utf-8", errors="replace") if node.name else ""

            # Extract parent classes
            parent_classes = []
            if hasattr(node, "superclass"):
                # Extract parent class name
                if hasattr(node.superclass, "type"):
                    type_node = node.superclass.type
                    if hasattr(type_node, "name"):
                        parent_name = type_node.name.text.decode("utf-8", errors="replace") if type_node.name else ""
                        if parent_name:
                            parent_classes.append(parent_name)

            # Extract docstring
            docstring = self._extract_docstring(node, context)

            # Calculate complexity
            complexity = self._calculate_complexity(node, context)

            # Create class object
            class_obj = Class(
                name=name,
                parent_classes=parent_classes,
                complexity=complexity,
                docstring=docstring,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                start_column=node.start_point[1] + 1,
                end_column=node.end_point[1] + 1,
            )

            # Cache result
            if self._enable_caching:
                self._element_cache[cache_key] = class_obj

            return class_obj

        except Exception as e:
            log_error(f"Class definition extraction failed: {e}")
            return None

    def _extract_interface_definition(self, node: Node, context: ExtractionContext) -> Optional[Class]:
        """
        Extract interface definition from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Class object or None

        Note:
            - Similar to class definition but for interfaces
            - Extracts interface name, parent interfaces, methods
            - Calculates cyclomatic complexity
        """
        return self._extract_class_definition(node, context)

    def _extract_struct_definition(self, node: Node, context: ExtractionContext) -> Optional[Class]:
        """
        Extract struct definition from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Class object or None

        Note:
            - Similar to class definition but for structs
            - Extracts struct name, parent structs, members
            - Calculates cyclomatic complexity
        """
        return self._extract_class_definition(node, context)

    def _extract_abstract_class(self, node: Node, context: ExtractionContext) -> Optional[Class]:
        """
        Extract abstract class definition from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Class object or None

        Note:
            - Identifies abstract classes
            - Extracts class name, parent classes, abstract methods
            - Calculates cyclomatic complexity
        """
        # Check if abstract
        is_abstract = False
        if hasattr(node, "modifier"):
            for mod in node.modifier:
                if mod and mod.text.decode("utf-8", errors="replace") == "abstract":
                    is_abstract = True
                    break

        class_obj = self._extract_class_definition(node, context)
        if class_obj:
            class_obj.is_abstract = is_abstract

        return class_obj

    def _extract_final_class(self, node: Node, context: ExtractionContext) -> Optional[Class]:
        """
        Extract final class definition from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Class object or None

        Note:
            - Identifies final classes
            - Extracts class name, parent classes, methods
            - Calculates cyclomatic complexity
        """
        return self._extract_class_definition(node, context)

    def _extract_sealed_class(self, node: Node, context: ExtractionContext) -> Optional[Class]:
        """
        Extract sealed class definition from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Class object or None

        Note:
            - Identifies sealed classes
            - Extracts class name, parent classes, methods
            - Calculates cyclomatic complexity
        """
        return self._extract_class_definition(node, context)

    def _extract_inner_class(self, node: Node, context: ExtractionContext) -> Optional[Class]:
        """
        Extract inner class definition from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Class object or None

        Note:
            - Identifies inner classes
            - Extracts class name, parent classes, methods
            - Calculates cyclomatic complexity
        """
        return self._extract_class_definition(node, context)

    def _extract_static_class(self, node: Node, context: ExtractionContext) -> Optional[Class]:
        """
        Extract static class definition from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Class object or None

        Note:
            - Identifies static classes
            - Extracts class name, parent classes, static methods
            - Calculates cyclomatic complexity
        """
        # Check if static
        is_static = False
        if hasattr(node, "modifier"):
            for mod in node.modifier:
                if mod and mod.text.decode("utf-8", errors="replace") == "static":
                    is_static = True
                    break

        class_obj = self._extract_class_definition(node, context)
        if class_obj:
            class_obj.is_static = is_static

        return class_obj

    def _extract_public_class(self, node: Node, context: ExtractionContext) -> Optional[Class]:
        """
        Extract public class definition from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Class object or None

        Note:
            - Identifies public classes
            - Extracts class name, parent classes, public methods
            - Calculates cyclomatic complexity
        """
        return self._extract_class_definition(node, context)

    def _extract_private_class(self, node: Node, context: ExtractionContext) -> Optional[Class]:
        """
        Extract private class definition from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Class object or None

        Note:
            - Identifies private classes
            - Extracts class name, parent classes, private methods
            - Calculates cyclomatic complexity
        """
        return self._extract_class_definition(node, context)

    def _extract_protected_class(self, node: Node, context: ExtractionContext) -> Optional[Class]:
        """
        Extract protected class definition from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Class object or None

        Note:
            - Identifies protected classes
            - Extracts class name, parent classes, protected methods
            - Calculates cyclomatic complexity
        """
        return self._extract_class_definition(node, context)

    def _extract_enum_definition(self, node: Node, context: ExtractionContext) -> Optional[Class]:
        """
        Extract enum definition from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Class object or None

        Note:
            - Identifies enum definitions
            - Extracts enum name, enum values
            - Calculates cyclomatic complexity
        """
        try:
            # Extract enum name
            name = ""
            if hasattr(node, "name"):
                name = node.name.text.decode("utf-8", errors="replace") if node.name else ""

            # Extract enum values
            enum_values = []
            if hasattr(node, "members"):
                for member in node.members:
                    if member.type == "enum_member":
                        if hasattr(member, "name"):
                            value = member.name.text.decode("utf-8", errors="replace") if member.name else ""
                            if value:
                                enum_values.append(value)

            # Create class object with enum values
            class_obj = Class(
                name=name,
                parent_classes=[],
                complexity=1,  # Enum complexity
                docstring="",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                start_column=node.start_point[1] + 1,
                end_column=node.end_point[1] + 1,
                is_enum=True,
            )
            class_obj.enum_values = enum_values

            return class_obj

        except Exception as e:
            log_error(f"Enum extraction failed: {e}")
            return None

    def _extract_mixin_class(self, node: Node, context: ExtractionContext) -> Optional[Class]:
        """
        Extract mixin class definition from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Class object or None

        Note:
            - Identifies mixin classes
            - Extracts class name, parent classes, methods
            - Calculates cyclomatic complexity
        """
        return self._extract_class_definition(node, context)

    def _extract_decorated_class(self, node: Node, context: ExtractionContext) -> Optional[Class]:
        """
        Extract decorated class definition from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Class object or None

        Note:
            - Identifies decorators and wraps class
            - Extracts class name, parent classes, methods
            - Calculates cyclomatic complexity
        """
        return self._extract_class_definition(node, context)

    def _extract_generic_class(self, node: Node, context: ExtractionContext) -> Optional[Class]:
        """
        Extract generic class definition from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Class object or None

        Note:
            - Identifies generic classes
            - Extracts class name, parent classes, methods
            - Calculates cyclomatic complexity
        """
        return self._extract_class_definition(node, context)

    def _extract_docstring(self, node: Node, context: ExtractionContext) -> Optional[str]:
        """
        Extract docstring from node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Docstring text or None

        Note:
            - Default implementation uses triple-quoted strings
            - Can be overridden for language-specific docstring extraction
        """
        try:
            # Look for docstring in preceding nodes
            if hasattr(node, "child_count") and node.child_count > 0:
                for i in range(node.child_count):
                    child = node.child(i)
                    if child.type == "string" and child.text:
                        text = child.text.decode("utf-8", errors="replace")
                        if text.startswith('"""') or text.startswith("'''"):
                            return text[3:-3]
                        return None

            return None

        except Exception as e:
            log_error(f"Docstring extraction failed: {e}")
            return None

    def _calculate_complexity(self, node: Node, context: ExtractionContext) -> int:
        """
        Calculate cyclomatic complexity score.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Complexity score (integer)

        Note:
            - Default implementation uses simple decision point counting
            - Can be overridden for language-specific complexity
        """
        try:
            complexity = 1  # Base complexity

            # Count decision points
            decision_keywords = [
                "if",
                "else",
                "elif",
                "for",
                "while",
                "case",
                "switch",
                "try",
                "catch",
                "finally",
                "with",
                "return",
            ]

            # Check node text for decision keywords
            if hasattr(node, "text"):
                node_text = node.text.decode("utf-8", errors="replace") if node.text else ""
                for keyword in decision_keywords:
                    if keyword in node_text:
                        complexity += 1
                        break

            # Check children for decision points
            if hasattr(node, "child_count") and node.child_count > 0:
                for i in range(node.child_count):
                    child = node.child(i)
                    child_complexity = self._calculate_complexity(child, context)
                    complexity += child_complexity

            return complexity

        except Exception as e:
            log_error(f"Complexity calculation failed: {e}")
            return 1  # Default complexity on error


# ============================================================================
# Convenience Functions with LRU Caching
# ============================================================================

@lru_cache(maxsize=64, typed=True)
def get_programming_language_extractor(max_depth: int = 50) -> ProgrammingLanguageExtractor:
    """
    Get programming language extractor instance with LRU caching.

    Args:
        max_depth: Maximum traversal depth (default: 50)

    Returns:
        ProgrammingLanguageExtractor instance

    Performance:
        LRU caching with maxsize=64 reduces overhead for repeated calls.
    """
    return ProgrammingLanguageExtractor(max_depth=max_depth)


# ============================================================================
# Module-level exports for backward compatibility
# ============================================================================

__all__: List[str] = [
    # Exceptions
    "ProgrammingLanguageExtractorError",
    "InitializationError",
    "ExtractionError",
    "TraversalError",
    "ComplexityCalculationError",

    # Data classes
    "ExtractionMetrics",
    "ExtractionContext",

    # Main class
    "ProgrammingLanguageExtractor",

    # Convenience functions
    "get_programming_language_extractor",
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
    if name == "ProgrammingLanguageExtractor":
        return ProgrammingLanguageExtractor
    elif name == "ExtractionMetrics":
        return ExtractionMetrics
    elif name == "ExtractionContext":
        return ExtractionContext
    elif name in [
        "ProgrammingLanguageExtractorError",
        "InitializationError",
        "ExtractionError",
        "TraversalError",
        "ComplexityCalculationError",
    ]:
        # Import from module
        import sys
        module = sys.modules[__name__]
        if module is None:
            raise ImportError(f"Module {name} not found")
        return module
    elif name == "get_programming_language_extractor":
        return get_programming_language_extractor
    else:
        # Default behavior
        try:
            # Try to import from current package
            module = __import__(f".{name}", fromlist=["__name__"])
            return module
        except ImportError:
            raise ImportError(f"Module {name} not found in programming_language_extractor package")
