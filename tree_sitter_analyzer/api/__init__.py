"""TSA public API package — Pulse, Serialization, Semantic.

This package replaces the top-level api.py module. All symbols previously
available from tree_sitter_analyzer.api are re-exported here for backward
compatibility.
"""

import logging
from pathlib import Path
from typing import Any

from .. import __version__
from ..core.analysis_engine import AnalysisRequest, UnifiedAnalysisEngine
from ..internal_api.query_helpers import (
    filter_elements_by_type,
    group_captures_by_main_node,
    query_execution_result,
)
from ..internal_api.result_helpers import (
    code_analysis_error,
    code_analysis_result,
    file_analysis_error,
    file_analysis_result,
)
from ..internal_api.validation_helpers import (
    apply_language_validation,
    mark_validation_readable,
    validation_result_template,
)
from ..utils import log_error

logger = logging.getLogger(__name__)

_engine: UnifiedAnalysisEngine | None = None


def _group_captures_by_main_node(
    captures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return group_captures_by_main_node(captures)


def get_engine() -> UnifiedAnalysisEngine:
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
    include_details: bool = False,
    include_queries: bool = True,
    include_complexity: bool = False,
) -> dict[str, Any]:
    try:
        return _analyze_file_sync(file_path, language, queries, include_elements, include_queries)
    except FileNotFoundError as e:
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
    try:
        engine = get_engine()
        analysis_result = engine.analyze_code_sync(source_code, language, filename="string")
        return code_analysis_result(
            analysis_result, language,
            include_elements=include_elements, include_queries=include_queries,
        )
    except Exception as e:
        log_error(f"API analyze_code failed: {e}")
        return code_analysis_error(language, e)


def get_supported_languages() -> list[str]:
    try:
        return get_engine().get_supported_languages()
    except Exception as e:
        log_error(f"Failed to get supported languages: {e}")
        return []


def get_available_queries(language: str) -> list[str]:
    try:
        return get_engine().get_available_queries(language)
    except Exception as e:
        log_error(f"Failed to get available queries for {language}: {e}")
        return []


def is_language_supported(language: str) -> bool:
    try:
        return language.lower() in [lang.lower() for lang in get_supported_languages()]
    except Exception as e:
        log_error(f"Failed to check language support for {language}: {e}")
        return False


def detect_language(file_path: str | Path) -> str:
    try:
        if not file_path:
            return "unknown"
        engine = get_engine()
        result = engine.language_detector.detect_from_extension(str(file_path))
        return str(result) if result and result.strip() else "unknown"
    except Exception as e:
        log_error(f"Failed to detect language for {file_path}: {e}")
        return "unknown"


def get_file_extensions(language: str) -> list[str]:
    try:
        engine = get_engine()
        if hasattr(engine.language_detector, "get_extensions_for_language"):
            result = engine.language_detector.get_extensions_for_language(language)
            return list(result) if result else []
        extension_map = {
            "java": [".java"], "python": [".py"], "javascript": [".js"],
            "typescript": [".ts"], "c": [".c"], "cpp": [".cpp", ".cxx", ".cc"],
            "go": [".go"], "rust": [".rs"],
        }
        return extension_map.get(language.lower(), [])
    except Exception as e:
        log_error(f"Failed to get extensions for {language}: {e}")
        return []


def validate_file(file_path: str | Path) -> dict[str, Any]:
    file_path = Path(file_path)
    result = validation_result_template(file_path)
    try:
        if not mark_validation_readable(file_path, result):
            return result
        language = detect_language(file_path)
        apply_language_validation(result, language, is_language_supported)
        result["valid"] = len(result["errors"]) == 0
    except Exception as e:
        result["errors"].append(f"Validation failed: {e}")
    return result


def get_framework_info() -> dict[str, Any]:
    try:
        engine = get_engine()
        plugin_manager = engine.plugin_manager
        loaded_plugins = len(plugin_manager.get_supported_languages()) if plugin_manager else 0
        return {
            "name": "tree-sitter-analyzer",
            "version": __version__,
            "supported_languages": engine.get_supported_languages(),
            "total_languages": len(engine.get_supported_languages()),
            "plugin_info": {"manager_available": plugin_manager is not None, "loaded_plugins": loaded_plugins},
            "core_components": ["AnalysisEngine", "Parser", "QueryExecutor", "PluginManager", "LanguageDetector"],
        }
    except Exception as e:
        log_error(f"Failed to get framework info: {e}")
        return {"name": "tree-sitter-analyzer", "version": __version__, "error": str(e)}


def execute_query(
    file_path: str | Path, query_name: str, language: str | None = None
) -> dict[str, Any]:
    try:
        result = analyze_file(file_path, language=language, queries=[query_name],
                               include_elements=False, include_queries=True)
        return query_execution_result(result, query_name, file_path)
    except Exception as e:
        log_error(f"Query execution failed: {e}")
        return {"success": False, "query_name": query_name, "error": str(e), "file_path": str(file_path)}


def extract_elements(
    file_path: str | Path,
    language: str | None = None,
    element_types: list[str] | None = None,
) -> dict[str, Any]:
    try:
        result = analyze_file(file_path, language=language, include_elements=True, include_queries=False)
        if result["success"] and "elements" in result:
            elements = filter_elements_by_type(result["elements"], element_types)
            return {"success": True, "elements": elements, "count": len(elements),
                    "language": result.get("language_info", {}).get("language"), "file_path": str(file_path)}
        return {"success": False, "error": result.get("error", "Unknown error"), "file_path": str(file_path)}
    except Exception as e:
        log_error(f"Element extraction failed: {e}")
        return {"success": False, "error": str(e), "file_path": str(file_path)}


def analyze(file_path: str | Path, **kwargs: Any) -> dict[str, Any]:
    return analyze_file(file_path, **kwargs)


def get_languages() -> list[str]:
    return get_supported_languages()


__all__ = [
    "get_engine", "analyze_file", "analyze_code", "get_supported_languages",
    "get_available_queries", "is_language_supported", "detect_language",
    "get_file_extensions", "validate_file", "get_framework_info",
    "execute_query", "extract_elements", "analyze", "get_languages",
]
