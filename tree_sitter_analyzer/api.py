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
from .core.engine import AnalysisEngine
from .utils import log_error

logger = logging.getLogger(__name__)

# Global engine instance (singleton pattern)
_engine: AnalysisEngine | None = None


def get_engine() -> AnalysisEngine:
    """
    Get the global analysis engine instance.

    Returns:
        AnalysisEngine instance
    """
    global _engine
    if _engine is None:
        _engine = AnalysisEngine()
    return _engine


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
        engine = get_engine()

        # Perform the analysis
        analysis_result = engine.analyze_file(file_path, language)

        # Convert AnalysisResult to expected API format (same as analyze_code)
        result = {
            "success": analysis_result.success,
            "file_info": {
                "path": str(file_path),
                "exists": True,
            },
            "language_info": {
                "language": analysis_result.language,
                "detected": language is None,  # True if language was auto-detected
            },
            "ast_info": {
                "node_count": analysis_result.node_count,
                "line_count": analysis_result.line_count,
            },
        }

        # Add elements if requested and available
        if include_elements and hasattr(analysis_result, "elements"):
            result["elements"] = []
            for elem in analysis_result.elements:
                elem_dict = {
                    "name": elem.name,
                    "type": type(elem).__name__.lower(),
                    "start_line": elem.start_line,
                    "end_line": elem.end_line,
                    "raw_text": elem.raw_text,
                    "language": elem.language,
                }

                # Add type-specific fields
                if hasattr(elem, "module_path"):
                    elem_dict["module_path"] = elem.module_path
                if hasattr(elem, "module_name"):
                    elem_dict["module_name"] = elem.module_name
                if hasattr(elem, "imported_names"):
                    elem_dict["imported_names"] = elem.imported_names
                if hasattr(elem, "variable_type"):
                    elem_dict["variable_type"] = elem.variable_type
                if hasattr(elem, "initializer"):
                    elem_dict["initializer"] = elem.initializer
                if hasattr(elem, "is_constant"):
                    elem_dict["is_constant"] = elem.is_constant
                if hasattr(elem, "parameters"):
                    elem_dict["parameters"] = elem.parameters
                if hasattr(elem, "return_type"):
                    elem_dict["return_type"] = elem.return_type
                if hasattr(elem, "is_async"):
                    elem_dict["is_async"] = elem.is_async
                if hasattr(elem, "is_static"):
                    elem_dict["is_static"] = elem.is_static
                if hasattr(elem, "is_constructor"):
                    elem_dict["is_constructor"] = elem.is_constructor
                if hasattr(elem, "is_method"):
                    elem_dict["is_method"] = elem.is_method
                if hasattr(elem, "complexity_score"):
                    elem_dict["complexity_score"] = elem.complexity_score
                if hasattr(elem, "superclass"):
                    elem_dict["superclass"] = elem.superclass
                if hasattr(elem, "class_type"):
                    elem_dict["class_type"] = elem.class_type

                # For methods, try to find the class name from context
                if elem_dict.get("is_method") and elem_dict["type"] == "function":
                    # Look for the class this method belongs to
                    for other_elem in analysis_result.elements:
                        if (
                            hasattr(other_elem, "start_line")
                            and hasattr(other_elem, "end_line")
                            and type(other_elem).__name__.lower() == "class"
                            and other_elem.start_line
                            <= elem.start_line
                            <= other_elem.end_line
                        ):
                            elem_dict["class_name"] = other_elem.name
                            break
                    else:
                        elem_dict["class_name"] = None

                result["elements"].append(elem_dict)

        # Add query results if requested and available
        if include_queries and hasattr(analysis_result, "query_results"):
            result["query_results"] = analysis_result.query_results

        # Add error message if analysis failed
        if not analysis_result.success and analysis_result.error_message:
            result["error"] = analysis_result.error_message

        # Filter results based on options
        if not include_elements and "elements" in result:
            del result["elements"]

        if not include_queries and "query_results" in result:
            del result["query_results"]

        return result

    except FileNotFoundError as e:
        # Re-raise FileNotFoundError for tests that expect it
        raise e
    except Exception as e:
        log_error(f"API analyze_file failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "file_info": {"path": str(file_path), "exists": False},
            "language_info": {"language": language or "unknown", "detected": False},
            "ast_info": {"node_count": 0, "line_count": 0},
        }


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

        # Perform the analysis
        analysis_result = engine.analyze_code(source_code, language)

        # Convert AnalysisResult to expected API format
        result = {
            "success": analysis_result.success,
            "language_info": {
                "language": analysis_result.language,
                "detected": False,  # Language was explicitly provided
            },
            "ast_info": {
                "node_count": analysis_result.node_count,
                "line_count": analysis_result.line_count,
            },
        }

        # Add elements if requested and available
        if include_elements and hasattr(analysis_result, "elements"):
            result["elements"] = []
            for elem in analysis_result.elements:
                elem_dict = {
                    "name": elem.name,
                    "type": type(elem).__name__.lower(),
                    "start_line": elem.start_line,
                    "end_line": elem.end_line,
                    "raw_text": elem.raw_text,
                    "language": elem.language,
                }

                # Add type-specific fields
                if hasattr(elem, "module_path"):
                    elem_dict["module_path"] = elem.module_path
                if hasattr(elem, "module_name"):
                    elem_dict["module_name"] = elem.module_name
                if hasattr(elem, "imported_names"):
                    elem_dict["imported_names"] = elem.imported_names
                if hasattr(elem, "variable_type"):
                    elem_dict["variable_type"] = elem.variable_type
                if hasattr(elem, "initializer"):
                    elem_dict["initializer"] = elem.initializer
                if hasattr(elem, "is_constant"):
                    elem_dict["is_constant"] = elem.is_constant
                if hasattr(elem, "parameters"):
                    elem_dict["parameters"] = elem.parameters
                if hasattr(elem, "return_type"):
                    elem_dict["return_type"] = elem.return_type
                if hasattr(elem, "is_async"):
                    elem_dict["is_async"] = elem.is_async
                if hasattr(elem, "is_static"):
                    elem_dict["is_static"] = elem.is_static
                if hasattr(elem, "is_constructor"):
                    elem_dict["is_constructor"] = elem.is_constructor
                if hasattr(elem, "is_method"):
                    elem_dict["is_method"] = elem.is_method
                if hasattr(elem, "complexity_score"):
                    elem_dict["complexity_score"] = elem.complexity_score
                if hasattr(elem, "superclass"):
                    elem_dict["superclass"] = elem.superclass
                if hasattr(elem, "class_type"):
                    elem_dict["class_type"] = elem.class_type

                # For methods, try to find the class name from context
                if elem_dict.get("is_method") and elem_dict["type"] == "function":
                    # Look for the class this method belongs to
                    for other_elem in analysis_result.elements:
                        if (
                            hasattr(other_elem, "start_line")
                            and hasattr(other_elem, "end_line")
                            and type(other_elem).__name__.lower() == "class"
                            and other_elem.start_line
                            <= elem.start_line
                            <= other_elem.end_line
                        ):
                            elem_dict["class_name"] = other_elem.name
                            break
                    else:
                        elem_dict["class_name"] = None

                result["elements"].append(elem_dict)

        # Add query results if requested and available
        if include_queries and hasattr(analysis_result, "query_results"):
            result["query_results"] = analysis_result.query_results

        # Add error message if analysis failed
        if not analysis_result.success and analysis_result.error_message:
            result["error"] = analysis_result.error_message

        # Filter results based on options
        if not include_elements and "elements" in result:
            del result["elements"]

        if not include_queries and "query_results" in result:
            del result["query_results"]

        return result

    except Exception as e:
        log_error(f"API analyze_code failed: {e}")
        return {"success": False, "error": str(e)}


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
        # Try to get plugin and its supported queries
        plugin = engine._get_language_plugin(language)
        if plugin and hasattr(plugin, "get_supported_queries"):
            result = plugin.get_supported_queries()
            return list(result) if result else []
        else:
            # Return default queries
            return ["class", "method", "field"]
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

        return result
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

    result: dict[str, Any] = {
        "valid": False,
        "exists": file_path.exists(),
        "readable": False,
        "language": None,
        "supported": False,
        "size": 0,
        "errors": [],
    }

    try:
        # Check if file exists
        if not file_path.exists():
            result["errors"].append("File does not exist")
            return result

        # Check if file is readable
        try:
            with open(file_path, encoding="utf-8") as f:
                f.read(100)  # Read first 100 chars to test
            result["readable"] = True
            result["size"] = file_path.stat().st_size
        except Exception as e:
            result["errors"].append(f"File is not readable: {e}")
            return result

        # Detect language
        language = detect_language(file_path)
        result["language"] = language

        if language:
            result["supported"] = is_language_supported(language)
            if not result["supported"]:
                result["errors"].append(f"Language '{language}' is not supported")
        else:
            result["errors"].append("Could not detect programming language")

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

        return {
            "name": "tree-sitter-analyzer",
            "version": __version__,
            "supported_languages": engine.get_supported_languages(),
            "total_languages": len(engine.get_supported_languages()),
            "plugin_info": {
                "manager_available": engine.plugin_manager is not None,
                "loaded_plugins": (
                    len(engine.plugin_manager.get_supported_languages())
                    if engine.plugin_manager
                    else 0
                ),
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

        if result["success"] and "query_results" in result:
            query_results = result["query_results"].get(query_name, [])
            return {
                "success": True,
                "query_name": query_name,
                "results": query_results,
                "count": len(query_results),
                "language": result.get("language_info", {}).get("language"),
                "file_path": str(file_path),
            }
        else:
            return {
                "success": False,
                "query_name": query_name,
                "error": result.get("error", "Unknown error"),
                "file_path": str(file_path),
            }

    except Exception as e:
        log_error(f"Query execution failed: {e}")
        return {
            "success": False,
            "query_name": query_name,
            "error": str(e),
            "file_path": str(file_path),
        }


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
            elements = result["elements"]

            # Filter by element types if specified
            if element_types:
                filtered_elements = []
                for element in elements:
                    if any(
                        etype.lower() in element.get("type", "").lower()
                        for etype in element_types
                    ):
                        filtered_elements.append(element)
                elements = filtered_elements

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
