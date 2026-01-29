#!/usr/bin/env python3
"""
Tree-sitter Analyzer - Core Module

This module provides the core components for code analysis, including:
- AnalysisEngine: Main orchestrator for all analysis operations
- Parser: Wrapper around Tree-sitter parsing functionality
- QueryExecutor: Engine for executing complex queries on syntax trees
- ParseResult: Result objects from parsing operations

Architecture:
- Layered architecture with clear separation of concerns
- Performance-optimized with caching and lazy loading
- Type-safe with comprehensive PEP 484 type hints
- Extensible with plugin-based language support

Key Features:
- Unified analysis interface for multiple languages
- Tree-sitter query execution with result caching
- Parse result abstraction and handling
- Performance monitoring and statistics

Usage:
    >>> from tree_sitter_analyzer.core import AnalysisEngine, Parser, QueryExecutor
    >>> engine = AnalysisEngine(project_root=".")
    >>> parser = Parser()
    >>> executor = QueryExecutor()

Author: aisheng.yu
Version: 1.10.5
Date: 2026-01-28
"""

import import os
import sys
from typing import TYPE_CHECKING

# Type-safe imports using TYPE_CHECKING to avoid circular dependencies
if TYPE_CHECKING:
    # Analysis engine components
    from .analysis_engine import (
        AnalysisEngine,
        AnalysisConfig,
        AnalysisResult,
        Analyzer,
        AnalysisError,
    )
    from .parser import (
        Parser,
        ParseResult,
        ParserError,
        ParseConfig,
        Tree,
        Node,
    )
    from .query import (
        QueryExecutor,
        QueryResult,
        QueryError,
        QueryConfig,
        Query,
        Cursor,
    )
    
    # Legacy exports for backward compatibility
    from .analysis_engine import (
        UnifiedAnalysisEngine as AnalysisEngineLegacy,
        AnalysisConfig as AnalysisConfigLegacy,
    )
else:
    # Runtime imports (when type checking is disabled)
    from .analysis_engine import (
        AnalysisEngine,
        AnalysisConfig,
        AnalysisResult,
        Analyzer,
        AnalysisError,
        UnifiedAnalysisEngine as AnalysisEngineLegacy,
        AnalysisConfig as AnalysisConfigLegacy,
    )
    from .parser import (
        Parser,
        ParseResult,
        ParserError,
        ParseConfig,
        Tree,
        Node,
    )
    from .query import (
        QueryExecutor,
        QueryResult,
        QueryError,
        QueryConfig,
        Query,
        Cursor,
    )


# Version information
__version__: str = "1.10.5"
__author__: str = "aisheng.yu"
__email__: str = "aimasteracc@gmail.com"


# Public API exports
__all__: List[str] = [
    # Version information
    "__version__",
    "__author__",
    "__email__",
    
    # Analysis Engine
    "AnalysisEngine",
    "AnalysisConfig",
    "AnalysisResult",
    "Analyzer",
    "AnalysisError",
    
    # Parser
    "Parser",
    "ParseResult",
    "ParserError",
    "ParseConfig",
    "Tree",
    "Node",
    
    # Query Executor
    "QueryExecutor",
    "QueryResult",
    "QueryError",
    "QueryConfig",
    "Query",
    "Cursor",
    
    # Legacy exports (backward compatibility)
    "AnalysisEngineLegacy",
    "AnalysisConfigLegacy",
]


# ============================================================================
# Convenience Functions
# ============================================================================

def create_analysis_engine(project_root: str, config: Optional[AnalysisConfig] = None) -> AnalysisEngine:
    """
    Create and configure an AnalysisEngine instance.

    This function provides a convenient way to create and configure
    the core analysis engine with sensible defaults.

    Args:
        project_root: Root directory of the project to analyze.
        config: Optional analysis configuration (uses defaults if None).

    Returns:
        Configured AnalysisEngine instance.

    Raises:
        ValueError: If project_root is invalid or doesn't exist.

    Example:
        >>> engine = create_analysis_engine(
        ...     project_root="/path/to/project",
        ...     config=AnalysisConfig(
        ...         include_stats=True,
        ...         include_complexity=True
        ...     )
        ... )
    """
    if not project_root:
        raise ValueError("project_root cannot be empty")
    
    project_path = os.path.abspath(project_root)
    if not os.path.exists(project_path):
        raise ValueError(f"Project root does not exist: {project_path}")
    
    # Use provided config or create default
    if config is None:
        config = AnalysisConfig()
    
    # Create and return engine
    return AnalysisEngine(project_root=project_root, config=config)


def create_parser(language: str, project_root: Optional[str] = None) -> Parser:
    """
    Create and configure a Parser instance for a specific language.

    Args:
        language: Programming language to parse (e.g., 'python', 'java').
        project_root: Optional root directory for language-specific queries.

    Returns:
        Configured Parser instance.

    Raises:
        ValueError: If language is invalid.
        Exception: If parser cannot be initialized for the language.

    Example:
        >>> parser = create_parser("python")
        >>> result = parser.parse(source_code, "example.py")
    """
    if not language:
        raise ValueError("language cannot be empty")
    
    # Create parser with optional project root
    if project_root:
        return Parser(language=language, project_root=project_root)
    else:
        return Parser(language=language)


def create_query_executor(project_root: str) -> QueryExecutor:
    """
    Create and configure a QueryExecutor instance.

    Args:
        project_root: Root directory of the project.

    Returns:
        Configured QueryExecutor instance.

    Raises:
        ValueError: If project_root is invalid.

    Example:
        >>> executor = create_query_executor("/path/to/project")
        >>> results = executor.execute(query_code, files=["main.py"])
    """
    if not project_root:
        raise ValueError("project_root cannot be empty")
    
    project_path = os.path.abspath(project_root)
    if not os.path.exists(project_path):
        raise ValueError(f"Project root does not exist: {project_path}")
    
    return QueryExecutor(project_root=project_root)


def parse_file(file_path: str, language: Optional[str] = None) -> ParseResult:
    """
    Parse a single file and return the result.

    This is a convenience function that wraps parser creation and file reading.

    Args:
        file_path: Path to the file to parse.
        language: Optional language to use for parsing (auto-detect if None).

    Returns:
        ParseResult containing the syntax tree.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        Exception: If parsing fails.

    Example:
        >>> result = parse_file("main.py")
        >>> tree = result.tree
        >>> root_node = tree.root_node
    """
    if not file_path:
        raise ValueError("file_path cannot be empty")
    
    # Create parser
    parser = create_parser(language or "python")
    
    # Read file
    from ..encoding_utils import read_file_safe
    
    try:
        code, encoding = read_file_safe(file_path)
    except Exception as e:
        raise FileNotFoundError(f"Failed to read file {file_path}: {e}")
    
    # Parse file
    return parser.parse(code, file_path)


def query_files(
    files: List[str],
    query_code: str,
    project_root: str,
    language: Optional[str] = None
) -> List[QueryResult]:
    """
    Execute a query on multiple files.

    Args:
        files: List of file paths to query.
        query_code: Tree-sitter query code.
        project_root: Root directory of the project.
        language: Optional language to use for parsing (auto-detect if None).

    Returns:
        List of QueryResult objects.

    Raises:
        ValueError: If query_code or files are invalid.

    Example:
        >>> results = query_files(
        ...     ["main.py", "utils.py"],
        ...     "(function_declaration) @name",
        ...     "."
        ... )
    """
    if not files:
        raise ValueError("files list cannot be empty")
    if not query_code:
        raise ValueError("query_code cannot be empty")
    if not project_root:
        raise ValueError("project_root cannot be empty")
    
    # Create query executor
    executor = create_query_executor(project_root)
    
    # Create query
    from .query import Query
    query = Query(query_code)
    
    # Create parser
    parser = create_parser(language or "python")
    
    # Execute query on all files
    results = []
    for file_path in files:
        try:
            # Parse file
            code, _ = read_file_safe(file_path)
            tree = parser.parse(code, file_path)
            
            # Execute query
            result = executor.execute(query, tree, file_path)
            results.append(result)
        except Exception as e:
            from ..utils import log_error
            log_error(f"Failed to query {file_path}: {e}")
            continue
    
    return results


# Module-level exports for backward compatibility
def __getattr__(name: str) -> Any:
    """
    Fallback for dynamic imports and backward compatibility.

    Args:
        name: Name of the component to import.

    Returns:
        Imported component.

    Raises:
        ImportError: If component not found.
    """
    # Handle legacy imports
    if name in [
        "UnifiedAnalysisEngine",
        "UnifiedAnalysisConfig",
    ]:
        from .analysis_engine import (
            UnifiedAnalysisEngine,
            UnifiedAnalysisConfig as AnalysisConfigLegacy,
        )
        if name == "UnifiedAnalysisEngine":
            return UnifiedAnalysisEngine
        elif name == "UnifiedAnalysisConfig":
            return AnalysisConfigLegacy
    
    # Default behavior
    raise ImportError(f"Module {name} not found in core package")
