#!/usr/bin/env python3
"""
Tree-sitter Multi-Language Code Analyzer

A comprehensive Python library for analyzing code across multiple programming languages
using Tree-sitter. Features a plugin-based architecture for extensible language support.

Architecture:
- Core Engine: UniversalCodeAnalyzer, LanguageDetector, QueryLoader
- Plugin System: Extensible language-specific analyzers and extractors
- Data Models: Generic and language-specific code element representations
"""

__version__ = "1.22.0"
__author__ = "aisheng.yu"
__email__ = "aimasteracc@gmail.com"

import importlib as _importlib
from typing import Any as _Any

# Legacy public names remain import-compatible, but loading them eagerly makes
# the MCP stdio server pay for analysis_engine/models/output_manager before the
# client even receives initialize. PEP 562 keeps import tree_sitter_analyzer
# cheap while preserving from tree_sitter_analyzer import Function.
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "UniversalCodeAnalyzer": (
        "tree_sitter_analyzer.core.analysis_engine",
        "UnifiedAnalysisEngine",
    ),
    "EncodingManager": ("tree_sitter_analyzer.encoding_utils", "EncodingManager"),
    "detect_encoding": ("tree_sitter_analyzer.encoding_utils", "detect_encoding"),
    "extract_text_slice": ("tree_sitter_analyzer.encoding_utils", "extract_text_slice"),
    "read_file_safe": ("tree_sitter_analyzer.encoding_utils", "read_file_safe"),
    "safe_decode": ("tree_sitter_analyzer.encoding_utils", "safe_decode"),
    "safe_encode": ("tree_sitter_analyzer.encoding_utils", "safe_encode"),
    "write_file_safe": ("tree_sitter_analyzer.encoding_utils", "write_file_safe"),
    "LanguageDetector": ("tree_sitter_analyzer.language_detector", "LanguageDetector"),
    "get_loader": ("tree_sitter_analyzer.language_loader", "get_loader"),
    "AnalysisResult": ("tree_sitter_analyzer.models", "AnalysisResult"),
    "Class": ("tree_sitter_analyzer.models", "Class"),
    "CodeElement": ("tree_sitter_analyzer.models", "CodeElement"),
    "Function": ("tree_sitter_analyzer.models", "Function"),
    "Import": ("tree_sitter_analyzer.models", "Import"),
    "JavaAnnotation": ("tree_sitter_analyzer.models", "JavaAnnotation"),
    "JavaClass": ("tree_sitter_analyzer.models", "JavaClass"),
    "JavaField": ("tree_sitter_analyzer.models", "JavaField"),
    "JavaImport": ("tree_sitter_analyzer.models", "JavaImport"),
    "JavaMethod": ("tree_sitter_analyzer.models", "JavaMethod"),
    "JavaPackage": ("tree_sitter_analyzer.models", "JavaPackage"),
    "Variable": ("tree_sitter_analyzer.models", "Variable"),
    "OutputManager": ("tree_sitter_analyzer.output_manager", "OutputManager"),
    "get_output_manager": ("tree_sitter_analyzer.output_manager", "get_output_manager"),
    "output_data": ("tree_sitter_analyzer.output_manager", "output_data"),
    "output_error": ("tree_sitter_analyzer.output_manager", "output_error"),
    "output_info": ("tree_sitter_analyzer.output_manager", "output_info"),
    "output_warning": ("tree_sitter_analyzer.output_manager", "output_warning"),
    "set_output_mode": ("tree_sitter_analyzer.output_manager", "set_output_mode"),
    "ElementExtractor": ("tree_sitter_analyzer.plugins", "ElementExtractor"),
    "LanguagePlugin": ("tree_sitter_analyzer.plugins", "LanguagePlugin"),
    "PluginManager": ("tree_sitter_analyzer.plugins.manager", "PluginManager"),
    "QueryLoader": ("tree_sitter_analyzer.query_loader", "QueryLoader"),
    "get_query_loader": ("tree_sitter_analyzer.query_loader", "get_query_loader"),
    "QuietMode": ("tree_sitter_analyzer.utils", "QuietMode"),
    "log_debug": ("tree_sitter_analyzer.utils", "log_debug"),
    "log_error": ("tree_sitter_analyzer.utils", "log_error"),
    "log_info": ("tree_sitter_analyzer.utils", "log_info"),
    "log_performance": ("tree_sitter_analyzer.utils", "log_performance"),
    "log_warning": ("tree_sitter_analyzer.utils", "log_warning"),
    "safe_print": ("tree_sitter_analyzer.utils", "safe_print"),
}


def __getattr__(name: str) -> _Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'tree_sitter_analyzer' has no attribute {name!r}")
    module_path, attr_name = _LAZY_EXPORTS[name]
    value = getattr(_importlib.import_module(module_path), attr_name)
    globals()[name] = value
    return value


__all__ = [
    # Core Models (optimized)
    "JavaAnnotation",
    "JavaClass",
    "JavaImport",
    "JavaMethod",
    "JavaField",
    "JavaPackage",
    "AnalysisResult",
    # Model classes
    "Class",
    "CodeElement",
    "Function",
    "Import",
    "Variable",
    # Plugin system
    "ElementExtractor",
    "LanguagePlugin",
    "PluginManager",
    "QueryLoader",
    # Language detection
    "LanguageDetector",
    # Core Components (optimized)
    # "AdvancedAnalyzer",  # Removed - migrated to plugin system
    "get_loader",
    "get_query_loader",
    # New Utilities
    "log_info",
    "log_warning",
    "log_error",
    "log_debug",
    "QuietMode",
    "safe_print",
    "log_performance",
    # Output Management
    "OutputManager",
    "set_output_mode",
    "get_output_manager",
    "output_info",
    "output_warning",
    "output_error",
    "output_data",
    # Legacy Components (backward compatibility)
    "UniversalCodeAnalyzer",
    # Version
    "__version__",
    # Encoding utilities
    "EncodingManager",
    "safe_encode",
    "safe_decode",
    "detect_encoding",
    "read_file_safe",
    "write_file_safe",
    "extract_text_slice",
]
