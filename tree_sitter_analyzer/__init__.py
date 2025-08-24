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

__version__ = "1.1.0"
__author__ = "aisheng.yu"
__email__ = "aimasteracc@gmail.com"

# Legacy imports for backward compatibility

# Core Engine - temporary direct import
from .core.analysis_engine import UnifiedAnalysisEngine as UniversalCodeAnalyzer
from .encoding_utils import (
    EncodingManager,
    detect_encoding,
    extract_text_slice,
    read_file_safe,
    safe_decode,
    safe_encode,
    write_file_safe,
)

# from .java_advanced_analyzer import AdvancedAnalyzer  # Removed - migrated to plugin system
from .language_detector import LanguageDetector
from .language_loader import get_loader

# Data Models (Java-specific for backward compatibility)
# Data Models (Generic)
from .models import (
    AnalysisResult,
    Class,
    CodeElement,
    Function,
    Import,
    JavaAnnotation,
    JavaClass,
    JavaField,
    JavaImport,
    JavaMethod,
    JavaPackage,
    Variable,
)
from .output_manager import (
    OutputManager,
    get_output_manager,
    output_data,
    output_error,
    output_info,
    output_warning,
    set_output_mode,
)

# Plugin System
from .plugins import ElementExtractor, LanguagePlugin
from .plugins.manager import PluginManager
from .query_loader import QueryLoader, get_query_loader

# Import new utility modules
from .utils import (
    QuietMode,
    log_debug,
    log_error,
    log_info,
    log_performance,
    log_warning,
    safe_print,
)

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
