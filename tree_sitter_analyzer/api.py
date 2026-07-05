#!/usr/bin/env python3
"""
Tree-sitter Analyzer API

Public API facade that provides a stable, high-level interface to the
tree-sitter analyzer framework. This is the main entry point for both
CLI and MCP interfaces.
"""

import logging
from pathlib import Path
from typing import Any

from . import __version__
from .core.analysis_engine import AnalysisRequest, UnifiedAnalysisEngine
from .internal_api.query_helpers import (
    filter_elements_by_type,
    group_captures_by_main_node,
    query_execution_result,
)
from .internal_api.result_helpers import (
    code_analysis_error,
    code_analysis_result,
    file_analysis_error,
    file_analysis_result,
)
from .internal_api.validation_helpers import (
    apply_language_validation,
    mark_validation_readable,
    validation_result_template,
)
from .utils import log_error

logger = logging.getLogger(__name__)

# Global engine instance (singleton pattern)
_engine: UnifiedAnalysisEngine | None = None


def _group_captures_by_main_node(
    captures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Backward-compatible private alias used by legacy tests and callers."""
    return group_captures_by_main_node(captures)


def get_engine() -> UnifiedAnalysisEngine:
    """
    Get the global analysis engine instance.

    Returns:
        UnifiedAnalysisEngine instance
    """
    global _engine
    if _engine is None:
        _engine = UnifiedAnalysisEngine()
    return _engine


def _analyze_file_sync(
    file_path: str | Path,
    language: str | None,
    queries: list[str] | None,
    include_elements: bool,
    include_queries: bool,
) -> dict[str, Any]:
    engine = get_engine()
    request = AnalysisRequest(
        file_path=str(file_path),
        language=language,
        queries=queries,
        include_elements=include_elements,
        include_queries=include_queries,
    )
    analysis_result = engine.analyze_sync(request)
    return file_analysis_result(
        analysis_result,
        file_path,
        language,
        include_elements=include_elements,
        include_queries=include_queries,
    )


def analyze_file(
    file_path: str | Path,
    language: str | None = None,
    queries: list[str] | None = None,
    include_elements: bool = True,
    include_details: bool = False,  # Add for backward compatibility
    include_queries: bool = True,
    include_complexity: bool = False,  # Add for backward compatibility
) -> dict[str, Any]:
    """
    Analyze a source code file.

    This is the main high-level function for file analysis. It handles
    language detection, parsing, query execution, and element extraction.

    Args:
        file_path: Path to the source file to analyze
        language: Programming language (auto-detected if not specified)
        queries: List of query names to execute (all available if not specified)
        include_elements: Whether to extract code elements
        include_queries: Whether to execute queries
        include_complexity: Whether to include complexity metrics (backward compatibility)

    Returns:
        Analysis results dictionary
    """
    try:
        return _analyze_file_sync(
            file_path,
            language,
            queries,
            include_elements,
            include_queries,
        )

    except FileNotFoundError as e:
        # Re-raise FileNotFoundError for tests that expect it
        raise e
    except Exception as e:
        log_error(f"API analyze_file failed: {e}")
        return file_analysis_error(file_path, language, e)


def analyze_code(
    source_code: str,
    language: str,
    queries: list[str] | None = None,
    include_elements: bool = True,
    include_queries: bool = True,
) -> dict[str, Any]:
    """
    Analyze source code directly (without file).

    Args:
        source_code: Source code string to analyze
        language: Programming language
        queries: List of query names to execute (all available if not specified)
        include_elements: Whether to extract code elements
        include_queries: Whether to execute queries

    Returns:
        Analysis results dictionary
    """
    try:
        engine = get_engine()

        # Perform the analysis using sync method
        analysis_result = engine.analyze_code_sync(
            source_code, language, filename="string"
        )

        return code_analysis_result(
            analysis_result,
            language,
            include_elements=include_elements,
            include_queries=include_queries,
        )

    except Exception as e:
        log_error(f"API analyze_code failed: {e}")
        return code_analysis_error(language, e)


def get_supported_languages() -> list[str]:
    """
    Get list of all supported programming languages.

    Returns:
        List of supported language names
    """
    try:
        engine = get_engine()
        return engine.get_supported_languages()
    except Exception as e:
        log_error(f"Failed to get supported languages: {e}")
        return []


def get_available_queries(language: str) -> list[str]:
    """
    Get available queries for a specific language.

    Args:
        language: Programming language name

    Returns:
        List of available query names
    """
    try:
        engine = get_engine()
        return engine.get_available_queries(language)
    except Exception as e:
        log_error(f"Failed to get available queries for {language}: {e}")
        return []


def is_language_supported(language: str) -> bool:
    """
    Check if a programming language is supported.

    Args:
        language: Programming language name

    Returns:
        True if the language is supported
    """
    try:
        supported_languages = get_supported_languages()
        return language.lower() in [lang.lower() for lang in supported_languages]
    except Exception as e:
        log_error(f"Failed to check language support for {language}: {e}")
        return False


# Detect patterns in source code: detect_language
def detect_language(file_path: str | Path) -> str:
    """
    Detect programming language from file path.

    Args:
        file_path: Path to the file

    Returns:
        Detected language name - 常に有効な文字列を返す
    """
    try:
        # Handle invalid input
        if not file_path:
            return "unknown"

        engine = get_engine()
        # Use language_detector instead of language_registry
        result = engine.language_detector.detect_from_extension(str(file_path))

        # Ensure result is valid
        if not result or result.strip() == "":
            return "unknown"

        return str(result)
    except Exception as e:
        log_error(f"Failed to detect language for {file_path}: {e}")
        return "unknown"


def get_file_extensions(language: str) -> list[str]:
    """
    Get file extensions for a specific language.

    Args:
        language: Programming language name

    Returns:
        List of file extensions
    """
    try:
        engine = get_engine()
        # Use language_detector to get extensions
        if hasattr(engine.language_detector, "get_extensions_for_language"):
            result = engine.language_detector.get_extensions_for_language(language)
            return list(result) if result else []
        else:
            # Fallback: return common extensions
            extension_map = {
                "java": [".java"],
                "python": [".py"],
                "javascript": [".js"],
                "typescript": [".ts"],
                "c": [".c"],
                "cpp": [".cpp", ".cxx", ".cc"],
                "go": [".go"],
                "rust": [".rs"],
            }
            return extension_map.get(language.lower(), [])
    except Exception as e:
        log_error(f"Failed to get extensions for {language}: {e}")
        return []


def validate_file(file_path: str | Path) -> dict[str, Any]:
    """
    Validate a source code file without full analysis.

    Args:
        file_path: Path to the file to validate

    Returns:
        Validation results dictionary
    """
    file_path = Path(file_path)
    result = validation_result_template(file_path)

    try:
        if not mark_validation_readable(file_path, result):
            return result

        language = detect_language(file_path)
        apply_language_validation(result, language, is_language_supported)

        # If we got this far with no errors, the file is valid
        result["valid"] = len(result["errors"]) == 0

    except Exception as e:
        result["errors"].append(f"Validation failed: {e}")

    return result


def get_framework_info() -> dict[str, Any]:
    """
    Get information about the framework and its capabilities.

    Returns:
        Framework information dictionary
    """
    try:
        engine = get_engine()
        plugin_manager = engine.plugin_manager
        loaded_plugins = (
            len(plugin_manager.get_supported_languages()) if plugin_manager else 0
        )

        return {
            "name": "tree-sitter-analyzer",
            "version": __version__,
            "supported_languages": engine.get_supported_languages(),
            "total_languages": len(engine.get_supported_languages()),
            "plugin_info": {
                "manager_available": plugin_manager is not None,
                "loaded_plugins": loaded_plugins,
            },
            "core_components": [
                "AnalysisEngine",
                "Parser",
                "QueryExecutor",
                "PluginManager",
                "LanguageDetector",
            ],
        }
    except Exception as e:
        log_error(f"Failed to get framework info: {e}")
        return {"name": "tree-sitter-analyzer", "version": __version__, "error": str(e)}


# Main entry point - dispatches to handler: execute_query
def execute_query(
    file_path: str | Path, query_name: str, language: str | None = None
) -> dict[str, Any]:
    """
    Execute a specific query against a file.

    Args:
        file_path: Path to the source file
        query_name: Name of the query to execute
        language: Programming language (auto-detected if not specified)

    Returns:
        Query execution results
    """
    try:
        # Analyze with only the specified query
        result = analyze_file(
            file_path,
            language=language,
            queries=[query_name],
            include_elements=False,
            include_queries=True,
        )
        return query_execution_result(result, query_name, file_path)

    except Exception as e:
        log_error(f"Query execution failed: {e}")
        return {
            "success": False,
            "query_name": query_name,
            "error": str(e),
            "file_path": str(file_path),
        }


# Extract elements from AST: extract_elements
def extract_elements(
    file_path: str | Path,
    language: str | None = None,
    element_types: list[str] | None = None,
) -> dict[str, Any]:
    """
    Extract code elements from a file.

    Args:
        file_path: Path to the source file
        language: Programming language (auto-detected if not specified)
        element_types: Types of elements to extract (all if not specified)

    Returns:
        Element extraction results
    """
    try:
        # Analyze with only element extraction
        result = analyze_file(
            file_path, language=language, include_elements=True, include_queries=False
        )

        if result["success"] and "elements" in result:
            elements = filter_elements_by_type(result["elements"], element_types)

            return {
                "success": True,
                "elements": elements,
                "count": len(elements),
                "language": result.get("language_info", {}).get("language"),
                "file_path": str(file_path),
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "file_path": str(file_path),
            }

    except Exception as e:
        log_error(f"Element extraction failed: {e}")
        return {"success": False, "error": str(e), "file_path": str(file_path)}


# Convenience functions for backward compatibility
def analyze(file_path: str | Path, **kwargs: Any) -> dict[str, Any]:
    """Convenience function that aliases to analyze_file."""
    return analyze_file(file_path, **kwargs)


def get_languages() -> list[str]:
    """Convenience function that aliases to get_supported_languages."""
    return get_supported_languages()
