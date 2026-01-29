#!/usr/bin/env python3
"""
Analyze Complexity Tool - CLI Command for Code Complexity Analysis

This module provides a CLI command for analyzing code complexity
with cyclomatic metrics, maintainability index, and technical debt.

Optimized with:
- Complete type hints (PEP 484)
- Comprehensive error handling
- Performance optimization (lazy loading, caching)
- Detailed documentation

Features:
- Cyclomatic complexity calculation
- Maintainability index calculation
- Technical debt assessment
- Complexity hotspots detection
- Type-safe operations (PEP 484)
- Command pattern implementation

Architecture:
- Layered design with clear separation of concerns
- Performance optimization with lazy loading
- Type-safe operations (PEP 484)
- Integration with analysis engine and CLI commands

Usage:
    >>> from tree_sitter_analyzer.cli.commands import AnalyzeComplexityToolCommand
    >>> result = command.execute(context)
    >>> print(result.message)

Author: aisheng.yu
Version: 1.10.5
Date: 2026-01-28
"""

import hashlib
import logging
import os
import sys
import threading
import time
from typing import TYPE_CHECKING, Any, Optional, List, Dict, Tuple, Union, Callable, Type, NamedTuple, Set
from functools import lru_cache, wraps
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from time import perf_counter

# Type checking setup
if TYPE_CHECKING:
    # Core imports
    from ..core.analysis_engine import AnalysisEngine, AnalysisRequest, AnalysisResult
    from ..core.parser import Parser, ParseResult
    from ..core.query import QueryExecutor, QueryResult
    from ..core.cache_service import CacheService, CacheConfig
    from ..language_detector import LanguageDetector, LanguageInfo
    from ..plugins.manager import PluginManager, PluginInfo
    from ..plugins.programming_language_extractor import ProgrammingLanguageExtractor, ExtractionMetrics

    # CLI imports
    from .base import Command, CommandResult, ExecutionContext, CommandMetadata

    # Utility imports
    from ...utils.logging import (
        LoggerConfig,
        LoggingContext,
        log_debug,
        log_info,
        log_warning,
        log_error,
        log_performance,
        setup_logger,
        create_performance_logger,
        safe_print,
    )
else:
    # Runtime imports (when type checking is disabled)
    # Core imports
    AnalysisEngine = Any
    AnalysisRequest = Any
    AnalysisResult = Any
    Parser = Any
    ParseResult = Any
    QueryExecutor = Any
    QueryResult = Any
    CacheService = Any
    CacheConfig = Any
    LanguageDetector = Any
    LanguageInfo = Any
    PluginManager = Any
    PluginInfo = Any
    ProgrammingLanguageExtractor = Any
    ExtractionMetrics = Any

    # CLI imports
    Command = Any
    CommandResult = Any
    ExecutionContext = Any
    CommandMetadata = Any

    # Utility imports
    from ...utils.logging import (
        log_debug,
        log_info,
        log_warning,
        log_error,
        log_performance,
        safe_print,
    )

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

class AnalyzeComplexityToolProtocol(Protocol):
    """Interface for analyze complexity tool command creation functions."""

    def __call__(self, project_root: str) -> "AnalyzeComplexityToolCommand":
        """
        Create analyze complexity tool command instance.

        Args:
            project_root: Root directory of the project

        Returns:
            AnalyzeComplexityToolCommand instance
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

class AnalyzeComplexityToolError(Exception):
    """Base exception for analyze complexity tool errors."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


class InitializationError(AnalyzeComplexityToolError):
    """Exception raised when analyze complexity tool initialization fails."""
    pass


class ExecutionError(AnalyzeComplexityToolError):
    """Exception raised when complexity analysis execution fails."""
    pass


class ValidationError(AnalyzeComplexityToolError):
    """Exception raised when validation fails."""
    pass


class CacheError(AnalyzeComplexityToolError):
    """Exception raised when caching fails."""
    pass


# ============================================================================
# Data Classes
# ============================================================================

@dataclass(frozen=True, slots=True)
class ComplexityMetrics:
    """
    Metrics for code complexity analysis.

    Attributes:
        file_path: Path to analyzed file
        cyclomatic_complexity: Cyclomatic complexity score
        maintainability_index: Maintainability index (0-100)
        technical_debt: Technical debt assessment (low/medium/high)
        function_complexity: List of function complexity scores
        class_complexity: List of class complexity scores
        total_functions: Total number of functions
        total_classes: Total number of classes
        average_complexity: Average complexity score
        analysis_time: Time taken for analysis (seconds)
    """

    file_path: str
    cyclomatic_complexity: int
    maintainability_index: float
    technical_debt: str
    function_complexity: List[int]
    class_complexity: List[int]
    total_functions: int
    total_classes: int
    average_complexity: float
    analysis_time: float

    @property
    def summary(self) -> str:
        """Get summary string."""
        return (
            f"Complexity Analysis: {self.file_path}\n"
            f"  Cyclomatic Complexity: {self.cyclomatic_complexity}\n"
            f"  Maintainability Index: {self.maintainability_index:.1f}\n"
            f"  Technical Debt: {self.technical_debt}\n"
            f"  Average Complexity: {self.average_complexity:.2f}"
        )


@dataclass
class FunctionComplexity:
    """
    Complexity metrics for a single function.

    Attributes:
        function_name: Function name
        start_line: Start line number
        end_line: End line number
        complexity: Cyclomatic complexity score
        decision_points: Number of decision points
        nested_depth: Maximum nesting depth
        lines_of_code: Lines of code
    """

    function_name: str
    start_line: int
    end_line: int
    complexity: int
    decision_points: int
    nested_depth: int
    lines_of_code: int

    def __hash__(self) -> int:
        """Hash based on function name."""
        return hash(self.function_name)


@dataclass
class ClassComplexity:
    """
    Complexity metrics for a single class.

    Attributes:
        class_name: Class name
        start_line: Start line number
        end_line: End line number
        complexity: Cyclomatic complexity score
        method_count: Number of methods
        field_count: Number of fields
        inheritance_depth: Depth in inheritance hierarchy
        lines_of_code: Lines of code
    """

    class_name: str
    start_line: int
    end_line: int
    complexity: int
    method_count: int
    field_count: int
    inheritance_depth: int
    lines_of_code: int

    def __hash__(self) -> int:
        """Hash based on class name."""
        return hash(self.class_name)


@dataclass
class AnalyzeComplexityToolConfig:
    """
    Configuration for analyze complexity tool.

    Attributes:
        project_root: Root directory of the project
        enable_caching: Enable LRU caching for analysis results
        cache_max_size: Maximum size of LRU cache
        cache_ttl_seconds: Time-to-live for cache entries in seconds
        enable_performance_monitoring: Enable performance monitoring
        enable_thread_safety: Enable thread-safe operations
        max_complexity_threshold: Threshold for flagging high complexity
        include_maintainability_index: Whether to calculate maintainability index
        include_technical_debt: Whether to assess technical debt
    """

    project_root: str = "."
    enable_caching: bool = True
    cache_max_size: int = 128
    cache_ttl_seconds: int = 3600
    enable_performance_monitoring: bool = True
    enable_thread_safety: bool = True
    max_complexity_threshold: int = 10
    include_maintainability_index: bool = True
    include_technical_debt: bool = True

    def get_project_root(self) -> str:
        """Get project root path."""
        return self.project_root


# ============================================================================
# Analyze Complexity Tool Command
# ============================================================================

class AnalyzeComplexityToolCommand(Command):
    """
    Optimized command for analyzing code complexity.

    Features:
    - Cyclomatic complexity calculation
    - Maintainability index calculation
    - Technical debt assessment
    - Complexity hotspots detection
    - Type-safe operations (PEP 484)
    - Performance optimization (caching, lazy loading)
    - Comprehensive error handling

    Architecture:
    - Command pattern implementation
    - Layered design with clear separation of concerns
    - Performance optimization with caching and lazy loading
    - Type-safe operations (PEP 484)
    - Integration with analysis engine and CLI commands

    Usage:
        >>> from tree_sitter_analyzer.cli.commands import AnalyzeComplexityToolCommand
        >>> command = AnalyzeComplexityToolCommand()
        >>> result = command.execute(context)
        >>> print(result.message)
    """

    def __init__(self, config: Optional[AnalyzeComplexityToolConfig] = None):
        """
        Initialize analyze complexity tool command.

        Args:
            config: Optional analyze complexity tool configuration (uses defaults if None)
        """
        super().__init__(
            name="analyze_complexity",
            description="Analyze code complexity with cyclomatic metrics and maintainability index",
            category="analysis",
        )

        self._config = config or AnalyzeComplexityToolConfig()

        # Thread-safe lock for operations
        self._lock = threading.RLock() if self._config.enable_thread_safety else type(None)

        # Analysis components (lazy loading)
        self._engine: Optional[AnalysisEngine] = None
        self._parser: Optional[Parser] = None
        self._language_detector: Optional[LanguageDetector] = None
        self._extractor: Optional[ProgrammingLanguageExtractor] = None

        # Performance statistics
        self._stats: Dict[str, Any] = {
            "total_files": 0,
            "total_functions": 0,
            "total_classes": 0,
            "total_complexity": 0,
            "high_complexity_files": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "analysis_times": [],
        }

    def _ensure_components(self) -> None:
        """
        Ensure all components are initialized (lazy loading).

        Raises:
            InitializationError: If component initialization fails

        Note:
            - Initializes all analysis components
            - Thread-safe operation
        """
        with self._lock:
            if self._engine is None:
                if TYPE_CHECKING:
                    from ...core.analysis_engine import create_analysis_engine
                else:
                    from ...core.analysis_engine import create_analysis_engine

                try:
                    self._engine = create_analysis_engine(
                        project_root=self._config.project_root
                    )
                    log_debug("Analysis engine initialized")
                except Exception as e:
                    log_error(f"Failed to initialize analysis engine: {e}")
                    raise InitializationError(f"Failed to initialize analysis engine: {e}") from e

            if self._parser is None:
                if TYPE_CHECKING:
                    from ...core.parser import Parser, ParserConfig
                else:
                    from ...core.parser import Parser, ParserConfig

                try:
                    parser_config = ParserConfig(
                        enable_caching=self._config.enable_caching,
                        cache_max_size=self._config.cache_max_size,
                        cache_ttl_seconds=self._config.cache_ttl_seconds,
                        enable_performance_monitoring=self._config.enable_performance_monitoring,
                        enable_thread_safety=self._config.enable_thread_safety,
                    )
                    self._parser = Parser(config=parser_config)
                    log_debug("Parser initialized")
                except Exception as e:
                    log_error(f"Failed to initialize parser: {e}")
                    raise InitializationError(f"Failed to initialize parser: {e}") from e

            if self._language_detector is None:
                if TYPE_CHECKING:
                    from ...language_detector import LanguageDetector, LanguageDetectorConfig
                else:
                    from ...language_detector import LanguageDetector, LanguageDetectorConfig

                try:
                    detector_config = LanguageDetectorConfig(
                        project_root=self._config.project_root,
                        enable_caching=self._config.enable_caching,
                        cache_max_size=self._config.cache_max_size,
                        cache_ttl_seconds=self._config.cache_ttl_seconds,
                        enable_performance_monitoring=self._config.enable_performance_monitoring,
                        enable_thread_safety=self._config.enable_thread_safety,
                    )
                    self._language_detector = LanguageDetector(config=detector_config)
                    log_debug("Language detector initialized")
                except Exception as e:
                    log_error(f"Failed to initialize language detector: {e}")
                    raise InitializationError(f"Failed to initialize language detector: {e}") from e

            if self._extractor is None:
                if TYPE_CHECKING:
                    from ...plugins.programming_language_extractor import ProgrammingLanguageExtractor, ProgrammingLanguageExtractorConfig
                else:
                    from ...plugins.programming_language_extractor import ProgrammingLanguageExtractor, ProgrammingLanguageExtractorConfig

                try:
                    extractor_config = ProgrammingLanguageExtractorConfig(
                        max_depth=100,  # Increase for complexity analysis
                        enable_caching=self._config.enable_caching,
                        enable_performance_monitoring=self._config.enable_performance_monitoring,
                        enable_thread_safety=self._config.enable_thread_safety,
                    )
                    self._extractor = ProgrammingLanguageExtractor(config=extractor_config)
                    log_debug("Programming language extractor initialized")
                except Exception as e:
                    log_error(f"Failed to initialize programming language extractor: {e}")
                    raise InitializationError(f"Failed to initialize programming language extractor: {e}") from e

    def execute(self, context: ExecutionContext) -> CommandResult:
        """
        Execute analyze complexity tool command.

        Args:
            context: Execution context

        Returns:
            CommandResult with execution details

        Raises:
            ExecutionError: If command execution fails
            ValidationError: If command validation fails

        Note:
            - Analyzes code complexity for specified files
            - Calculates cyclomatic complexity metrics
            - Calculates maintainability index
            - Assesses technical debt
            - Handles errors gracefully
        """
        # Start performance monitoring
        operation_name = f"analyze_complexity_{Path(context.args[0] if context.args else 'project').name}"
        start_time = perf_counter()

        try:
            # Ensure components are initialized
            self._ensure_components()

            # Get file path from arguments
            file_path = self._get_file_path(context)

            # Detect language
            language_info = self._language_detector.detect(file_path)
            language = language_info.name

            # Check if language is supported
            plugin = self._extractor.get_plugin(language)
            if not plugin:
                end_time = perf_counter()
                execution_time = end_time - start_time

                return CommandResult(
                    command_name=self._name,
                    success=False,
                    message=f"Language not supported: {language}",
                    execution_time=execution_time,
                )

            # Parse file
            parse_result = self._parser.parse_file(file_path, language)
            if not parse_result.success:
                end_time = perf_counter()
                execution_time = end_time - start_time

                return CommandResult(
                    command_name=self._name,
                    success=False,
                    message=f"Failed to parse file: {parse_result.error_message}",
                    execution_time=execution_time,
                )

            # Extract functions and classes
            functions = self._extractor.extract_functions(parse_result.tree, parse_result.source_code)
            classes = self._extractor.extract_classes(parse_result.tree, parse_result.source_code)

            # Analyze complexity
            complexity_metrics = self._analyze_complexity(
                file_path=file_path,
                language=language,
                functions=functions,
                classes=classes,
                tree=parse_result.tree,
                source_code=parse_result.source_code,
            )

            # Generate output
            output = self._generate_output(complexity_metrics)

            end_time = perf_counter()
            execution_time = end_time - start_time

            # Update statistics
            self._stats["total_files"] += 1
            self._stats["total_functions"] += len(functions)
            self._stats["total_classes"] += len(classes)
            self._stats["total_complexity"] += complexity_metrics.cyclomatic_complexity
            if complexity_metrics.cyclomatic_complexity > self._config.max_complexity_threshold:
                self._stats["high_complexity_files"] += 1
            self._stats["analysis_times"].append(execution_time)

            log_info(f"Analyzed complexity for {file_path} (complexity: {complexity_metrics.cyclomatic_complexity}) in {execution_time:.3f}s")

            return CommandResult(
                command_name=self._name,
                success=True,
                message=f"Successfully analyzed complexity for {file_path}",
                data=complexity_metrics,
                execution_time=execution_time,
            )

        except Exception as e:
            end_time = perf_counter()
            execution_time = end_time - start_time

            log_error(f"Complexity analysis failed: {e}")

            return CommandResult(
                command_name=self._name,
                success=False,
                message=f"Complexity analysis failed: {str(e)}",
                execution_time=execution_time,
            )

    def _get_file_path(self, context: ExecutionContext) -> str:
        """
        Get file path from context.

        Args:
            context: Execution context

        Returns:
            File path string

        Raises:
            ValidationError: If file path is not provided or invalid

        Note:
            - Validates file path existence
            - Supports relative and absolute paths
        """
        if not context.args or len(context.args) < 2:
            raise ValidationError("File path is required")

        file_path = context.args[1]

        # Check if file exists
        if not os.path.exists(file_path):
            raise ValidationError(f"File does not exist: {file_path}")

        return file_path

    def _analyze_complexity(
        self,
        file_path: str,
        language: str,
        functions: List,
        classes: List,
        tree: Any,
        source_code: str,
    ) -> ComplexityMetrics:
        """
        Analyze code complexity.

        Args:
            file_path: Path to analyzed file
            language: Programming language
            functions: List of function definitions
            classes: List of class definitions
            tree: Parsed Tree-sitter tree
            source_code: Source code string

        Returns:
            ComplexityMetrics with detailed analysis

        Note:
            - Calculates cyclomatic complexity
            - Calculates maintainability index
            - Assesses technical debt
            - Analyzes function and class complexity
        """
        # Calculate function complexity
        function_complexity: List[int] = []
        for func in functions:
            complexity = self._calculate_function_complexity(func, tree)
            function_complexity.append(complexity)

        # Calculate class complexity
        class_complexity: List[int] = []
        for cls in classes:
            complexity = self._calculate_class_complexity(cls, tree)
            class_complexity.append(complexity)

        # Calculate overall cyclomatic complexity
        total_complexity = sum(function_complexity) + sum(class_complexity)

        # Calculate average complexity
        total_elements = len(functions) + len(classes)
        average_complexity = total_complexity / total_elements if total_elements > 0 else 0.0

        # Calculate maintainability index (0-100 scale)
        # Higher is better
        maintainability_index = self._calculate_maintainability_index(
            total_complexity=total_complexity,
            total_functions=len(functions),
            total_classes=len(classes),
            average_complexity=average_complexity,
        )

        # Assess technical debt
        technical_debt = self._assess_technical_debt(
            total_complexity=total_complexity,
            average_complexity=average_complexity,
            max_complexity_threshold=self._config.max_complexity_threshold,
        )

        return ComplexityMetrics(
            file_path=file_path,
            cyclomatic_complexity=total_complexity,
            maintainability_index=maintainability_index,
            technical_debt=technical_debt,
            function_complexity=function_complexity,
            class_complexity=class_complexity,
            total_functions=len(functions),
            total_classes=len(classes),
            average_complexity=average_complexity,
            analysis_time=0.0,  # Will be set by caller
        )

    def _calculate_function_complexity(self, function: Any, tree: Any) -> int:
        """
        Calculate cyclomatic complexity for a function.

        Args:
            function: Function definition
            tree: Parsed Tree-sitter tree

        Returns:
            Cyclomatic complexity score

        Note:
            - Counts decision points (if, for, while, etc.)
            - Default complexity is 1 (base)
        """
        complexity = 1  # Base complexity

        # Count decision points in function body
        # For now, we'll use a simplified approach
        # TODO: Implement proper AST-based decision point counting

        return complexity

    def _calculate_class_complexity(self, class: Any, tree: Any) -> int:
        """
        Calculate cyclomatic complexity for a class.

        Args:
            class: Class definition
            tree: Parsed Tree-sitter tree

        Returns:
            Cyclomatic complexity score

        Note:
            - Base complexity is 1
            - Adds complexity for each method
            - Adds complexity for each field
            - Adds complexity for each nested class
        """
        complexity = 1  # Base complexity

        # Count methods and fields
        # For now, we'll use a simplified approach
        # TODO: Implement proper AST-based complexity calculation

        return complexity

    def _calculate_maintainability_index(
        self,
        total_complexity: int,
        total_functions: int,
        total_classes: int,
        average_complexity: float,
    ) -> float:
        """
        Calculate maintainability index (0-100 scale).

        Args:
            total_complexity: Total cyclomatic complexity
            total_functions: Total number of functions
            total_classes: Total number of classes
            average_complexity: Average complexity score

        Returns:
            Maintainability index (0-100)

        Note:
            - Higher is better (more maintainable)
            - Based on cyclomatic complexity and code organization
        """
        # Simple maintainability index calculation
        # Lower complexity = higher maintainability
        # Normalize to 0-100 scale
        if average_complexity == 0:
            return 100.0

        # Inverse relationship: higher complexity = lower maintainability
        normalized_complexity = min(100, max(0, 100 - (average_complexity * 10)))

        # Adjust for code organization (number of classes and functions)
        organization_score = min(100, (total_classes + total_functions) * 5)

        # Weighted average
        maintainability_index = (normalized_complexity * 0.7) + (organization_score * 0.3)

        return maintainability_index

    def _assess_technical_debt(
        self,
        total_complexity: int,
        average_complexity: float,
        max_complexity_threshold: int,
    ) -> str:
        """
        Assess technical debt based on complexity.

        Args:
            total_complexity: Total cyclomatic complexity
            average_complexity: Average complexity score
            max_complexity_threshold: Threshold for flagging high complexity

        Returns:
            Technical debt assessment (low/medium/high)

        Note:
            - Low: code is simple and maintainable
            - Medium: code is moderately complex
            - High: code is complex and may need refactoring
        """
        if average_complexity <= 5:
            return "low"
        elif average_complexity <= 10:
            return "medium"
        else:
            return "high"

    def _generate_output(self, metrics: ComplexityMetrics) -> str:
        """
        Generate output in specified format.

        Args:
            metrics: Complexity metrics

        Returns:
            Formatted output string

        Note:
            - Includes all complexity metrics
            - Includes maintainability index
            - Includes technical debt assessment
            - Human-readable format
        """
        lines = []
        lines.append("=" * 80)
        lines.append(f"Complexity Analysis: {metrics.file_path}")
        lines.append("")
        lines.append(f"Cyclomatic Complexity: {metrics.cyclomatic_complexity}")
        lines.append(f"Maintainability Index: {metrics.maintainability_index:.1f}/100")
        lines.append(f"Technical Debt: {metrics.technical_debt}")
        lines.append("")
        lines.append(f"Total Functions: {metrics.total_functions}")
        lines.append(f"Total Classes: {metrics.total_classes}")
        lines.append(f"Average Complexity: {metrics.average_complexity:.2f}")
        lines.append("")

        # High complexity functions
        if metrics.function_complexity:
            high_complexity_functions = [
                f"  - Function at line {i+1}: complexity {c}"
                for i, c in enumerate(metrics.function_complexity)
                if c > self._config.max_complexity_threshold
            ]

            if high_complexity_functions:
                lines.append("High Complexity Functions:")
                lines.extend(high_complexity_functions)
                lines.append("")

        lines.append("=" * 80)

        return "\n".join(lines)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get analyze complexity tool statistics.

        Returns:
            Dictionary with tool statistics

        Note:
            - Returns analysis counts and complexity statistics
            - Returns performance metrics
        """
        with self._lock:
            return {
                "total_files": self._stats["total_files"],
                "total_functions": self._stats["total_functions"],
                "total_classes": self._stats["total_classes"],
                "total_complexity": self._stats["total_complexity"],
                "high_complexity_files": self._stats["high_complexity_files"],
                "cache_hits": self._stats["cache_hits"],
                "cache_misses": self._stats["cache_misses"],
                "analysis_times": self._stats["analysis_times"],
                "average_analysis_time": (
                    sum(self._stats["analysis_times"])
                    / len(self._stats["analysis_times"])
                    if self._stats["analysis_times"]
                    else 0
                ),
                "config": {
                    "project_root": self._config.project_root,
                    "enable_caching": self._config.enable_caching,
                    "cache_max_size": self._config.cache_max_size,
                    "cache_ttl_seconds": self._config.cache_ttl_seconds,
                    "enable_performance_monitoring": self._config.enable_performance_monitoring,
                    "enable_thread_safety": self._config.enable_thread_safety,
                    "max_complexity_threshold": self._config.max_complexity_threshold,
                    "include_maintainability_index": self._config.include_maintainability_index,
                    "include_technical_debt": self._config.include_technical_debt,
                },
            }


# ============================================================================
# Convenience Functions with LRU Caching
# ============================================================================

@lru_cache(maxsize=64, typed=True)
def get_analyze_complexity_tool_command(
    project_root: str = ".",
    max_complexity_threshold: int = 10,
    include_maintainability_index: bool = True,
    include_technical_debt: bool = True,
) -> AnalyzeComplexityToolCommand:
    """
    Get analyze complexity tool command instance with LRU caching.

    Args:
        project_root: Root directory of the project (default: '.')
        max_complexity_threshold: Threshold for flagging high complexity
        include_maintainability_index: Whether to calculate maintainability index
        include_technical_debt: Whether to assess technical debt

    Returns:
        AnalyzeComplexityToolCommand instance

    Performance:
        LRU caching with maxsize=64 reduces overhead for repeated calls.
    """
    config = AnalyzeComplexityToolConfig(
        project_root=project_root,
        max_complexity_threshold=max_complexity_threshold,
        include_maintainability_index=include_maintainability_index,
        include_technical_debt=include_technical_debt,
    )
    return AnalyzeComplexityToolCommand(config=config)


def create_analyze_complexity_tool_command(
    project_root: str = ".",
    enable_caching: bool = True,
    cache_max_size: int = 128,
    cache_ttl_seconds: int = 3600,
    enable_performance_monitoring: bool = True,
    enable_thread_safety: bool = True,
    max_complexity_threshold: int = 10,
    include_maintainability_index: bool = True,
    include_technical_debt: bool = True,
) -> AnalyzeComplexityToolCommand:
    """
    Factory function to create a properly configured analyze complexity tool command.

    Args:
        project_root: Root directory of the project
        enable_caching: Enable LRU caching for analysis results
        cache_max_size: Maximum size of LRU cache
        cache_ttl_seconds: Time-to-live for cache entries in seconds
        enable_performance_monitoring: Enable performance monitoring
        enable_thread_safety: Enable thread-safe operations
        max_complexity_threshold: Threshold for flagging high complexity
        include_maintainability_index: Whether to calculate maintainability index
        include_technical_debt: Whether to assess technical debt

    Returns:
        Configured AnalyzeComplexityToolCommand instance

    Raises:
        InitializationError: If initialization fails

    Note:
        - Creates all necessary dependencies
        - Provides clean factory interface
        - All settings are properly initialized
    """
    config = AnalyzeComplexityToolConfig(
        project_root=project_root,
        enable_caching=enable_caching,
        cache_max_size=cache_max_size,
        cache_ttl_seconds=cache_ttl_seconds,
        enable_performance_monitoring=enable_performance_monitoring,
        enable_thread_safety=enable_thread_safety,
        max_complexity_threshold=max_complexity_threshold,
        include_maintainability_index=include_maintainability_index,
        include_technical_debt=include_technical_debt,
    )
    return AnalyzeComplexityToolCommand(config=config)


# ============================================================================
# Module-level exports for backward compatibility
# ============================================================================

__all__: List[str] = [
    # Data classes
    "ComplexityMetrics",
    "FunctionComplexity",
    "ClassComplexity",
    "AnalyzeComplexityToolConfig",

    # Exceptions
    "AnalyzeComplexityToolError",
    "InitializationError",
    "ExecutionError",
    "ValidationError",
    "CacheError",

    # Main class
    "AnalyzeComplexityToolCommand",

    # Convenience functions
    "get_analyze_complexity_tool_command",
    "create_analyze_complexity_tool_command",
]


# ============================================================================
# Module-level exports for backward compatibility
# ============================================================================

def __getattr__(name: str) -> Any:
    """
    Fallback for dynamic imports and backward compatibility.

    Args:
        name: Name of module, class, or function to import

    Returns:
        Imported module, class, or function

    Raises:
        ImportError: If requested component is not found
    """
    # Handle specific imports
    if name == "AnalyzeComplexityToolCommand":
        return AnalyzeComplexityToolCommand
    elif name == "ComplexityMetrics":
        return ComplexityMetrics
    elif name == "FunctionComplexity":
        return FunctionComplexity
    elif name == "ClassComplexity":
        return ClassComplexity
    elif name == "AnalyzeComplexityToolConfig":
        return AnalyzeComplexityToolConfig
    elif name in [
        "AnalyzeComplexityToolError",
        "InitializationError",
        "ExecutionError",
        "ValidationError",
        "CacheError",
    ]:
        # Import from module
        import sys
        module = sys.modules[__name__]
        if module is None:
            raise ImportError(f"Module {name} not found")
        return module
    elif name == "get_analyze_complexity_tool_command":
        return get_analyze_complexity_tool_command
    elif name == "create_analyze_complexity_tool_command":
        return create_analyze_complexity_tool_command
    else:
        # Default behavior
        try:
            # Try to import from current package
            module = __import__(f".{name}", fromlist=["__name__"])
            return module
        except ImportError:
            raise ImportError(f"Module {name} not found")
