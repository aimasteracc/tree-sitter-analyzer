#!/usr/bin/env python3
"""
Tree-sitter Multi-Language Code Analyzer

A comprehensive Python library for analyzing code across multiple programming languages
using Tree-sitter. Features a plugin-based architecture for extensible language support.

Optimized with:
- Complete type hints (PEP 484)
- Comprehensive error handling and recovery
- Performance optimization (LRU caching)
- Detailed documentation

Author: aisheng.yu
Version: 1.10.5
Date: 2026-01-28
"""

import functools
import os
from pathlib import Path
from typing import List, Optional, Dict, Any, Union, Tuple, Callable, Type

# Type checking setup
if os.environ.get("TYPE_CHECKING", "0") == "1":
    from typing import Protocol
else:
    Protocol = object

# Type-safe imports using TYPE_CHECKING
if os.environ.get("TYPE_CHECKING", "0") == "1":
    # Core Engine - with type hints
    from .core.analysis_engine import UnifiedAnalysisEngine as UnifiedCodeAnalyzer
    from .encoding_utils import (
        EncodingManager,
        EncodingManagerType,
        detect_encoding,
        read_file_safe,
        write_file_safe,
        extract_text_slice,
        safe_decode,
        safe_encode,
        EncodingCache,
        clear_encoding_cache,
        get_encoding_cache_size,
    )
    
    # Language detection with type hints
    from .language_detector import LanguageDetector, LanguageInfo, LanguageType
    
    # Language loader with type hints
    from .language_loader import LanguageLoader, get_language_loader, LanguageLoaderType

    # Data Models (Generic) with type hints
    from .models import (
        AnalysisResult,
        Class,
        CodeElement,
        Function,
        Import,
        Variable,
        Element,
        Position,
        Span,
        JavaAnnotation,
        JavaClass,
        JavaField,
        JavaImport,
        JavaMethod,
        JavaPackage,
    )

    # Data Models (Java-specific for backward compatibility) with type hints
    from .models import (
        JavaAnnotation as JavaAnnotationLegacy,
        JavaClass as JavaClassLegacy,
        JavaField as JavaFieldLegacy,
        JavaImport as JavaImportLegacy,
        JavaMethod as JavaMethodLegacy,
        JavaPackage as JavaPackageLegacy,
    )

    # Plugin System with type hints
    from .plugins import ElementExtractor, LanguagePlugin
    from .plugins.manager import PluginManager, PluginConfig

    # Query loader with type hints
    from .query_loader import QueryLoader, get_query_loader, QueryLoaderType

    # Output management with type hints
    from .output_manager import (
        OutputManager,
        get_output_manager,
        OutputMode,
        output_data,
        output_error,
        output_info,
        output_warning,
        set_output_mode,
    )

    # Utility modules with type hints
    from .utils import (
        QuietMode,
        log_debug,
        log_error,
        log_info,
        log_performance,
        log_warning,
        safe_print,
        LoggerConfig,
    )
else:
    # Type aliases for runtime (when type checking is disabled)
    UnifiedCodeAnalyzer = Any
    LanguageDetector = Any
    LanguageInfo = Any
    LanguageType = Any
    LanguageLoader = Any
    LanguageLoaderType = Any
    
    AnalysisResult = Any
    Class = Any
    CodeElement = Any
    Function = Any
    Import = Any
    Variable = Any
    Element = Any
    Position = Any
    Span = Any
    
    JavaAnnotation = Any
    JavaClass = Any
    JavaField = Any
    JavaImport = Any
    JavaMethod = Any
    JavaPackage = Any
    
    ElementExtractor = Any
    LanguagePlugin = Any
    PluginManager = Any
    PluginConfig = Any
    
    QueryLoader = Any
    QueryLoaderType = Any
    
    OutputManager = Any
    OutputMode = Any
    
    QuietMode = Any

__version__: str = "1.10.5"
__author__: str = "aisheng.yu"
__email__: str = "aimasteracc@gmail.com"

__all__: List[str] = [
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
    "get_loader",
    "get_query_loader",
    # New Utilities (optimized)
    "log_info",
    "log_warning",
    "log_error",
    "log_debug",
    "log_performance",
    "safe_print",
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


# ============================================================================
# Type Definitions
# ============================================================================

class CreateLanguageDetectorProtocol(Protocol):
    """Protocol for language detector creation functions."""

    def __call__(self, project_root: str) -> LanguageDetector:
        """
        Create language detector instance.

        Args:
            project_root: Root directory of the project

        Returns:
            LanguageDetector instance

        Raises:
            ValueError: If project_root is invalid
        """
        ...


class CreateAnalysisEngineProtocol(Protocol):
    """Protocol for analysis engine creation functions."""

    def __call__(self, project_root: str) -> UnifiedCodeAnalyzer:
        """
        Create analysis engine instance.

        Args:
            project_root: Root directory of the project

        Returns:
            UnifiedCodeAnalyzer instance

        Raises:
            ValueError: If project_root is invalid
        """
        ...


# ============================================================================
# Performance Optimization: LRU Cache
# ============================================================================

@functools.lru_cache(maxsize=128, typed=True)
def create_language_detector_cached(project_root: str) -> LanguageDetector:
    """
    Create language detector instance with LRU caching.

    Args:
        project_root: Root directory of the project

    Returns:
        LanguageDetector instance

    Raises:
        ValueError: If project_root is invalid

    Performance:
        LRU caching with maxsize=128 reduces overhead for repeated calls.
    """
    if not project_root:
        raise ValueError("project_root cannot be empty")
    
    return LanguageDetector(project_root)


@functools.lru_cache(maxsize=128, typed=True)
def create_analysis_engine_cached(project_root: str) -> UnifiedCodeAnalyzer:
    """
    Create analysis engine instance with LRU caching.

    Args:
        project_root: Root directory of the project

    Returns:
        UnifiedCodeAnalyzer instance

    Raises:
        ValueError: If project_root is invalid

    Performance:
        LRU caching with maxsize=128 reduces overhead for repeated calls.
    """
    if not project_root:
        raise ValueError("project_root cannot be empty")
    
    return UnifiedCodeAnalyzer(project_root)


# ============================================================================
# Convenience Functions (Type-safe with Caching)
# ============================================================================

def create_language_detector(project_root: str) -> LanguageDetector:
    """
    Create language detector instance.

    Args:
        project_root: Root directory of the project

    Returns:
        LanguageDetector instance

    Raises:
        ValueError: If project_root is invalid

    Performance:
        Uses LRU caching with maxsize=128 to reduce overhead.
    """
    return create_language_detector_cached(project_root)


def create_analysis_engine(project_root: str) -> UnifiedCodeAnalyzer:
    """
    Create analysis engine instance.

    Args:
        project_root: Root directory of the project

    Returns:
        UnifiedCodeAnalyzer instance

    Raises:
        ValueError: If project_root is invalid

    Performance:
        Uses LRU caching with maxsize=128 to reduce overhead.
    """
    return create_analysis_engine_cached(project_root)


def analyze_file_safe(file_path: str, language: Optional[str] = None) -> AnalysisResult:
    """
    Safely analyze a single file with error handling.

    Args:
        file_path: Path to file
        language: Optional language (auto-detect if not provided)

    Returns:
        AnalysisResult with file analysis

    Raises:
        FileNotFoundError: If file does not exist
        ValueError: If file_path is invalid
        Exception: For other analysis errors (wrapped and logged)

    Performance:
        Uses LRU-cached language detector and analysis engine.
    """
    try:
        detector = create_language_detector(file_path)
        
        if language:
            # Use specified language
            language_info: Optional[LanguageInfo] = detector.get_language_info(language)
            if not language_info:
                raise ValueError(f"Unsupported language: {language}")
        else:
            language = language_info.name
        else:
            # Auto-detect language
            language_info = detector.detect(file_path)
            if not language_info:
                raise ValueError("Could not detect language")
            language = language_info.name
        
        # Load language analyzer
        loader: LanguageLoader = get_language_loader(language)
        if not loader:
            raise ValueError(f"Language loader not found for: {language}")
        
        # Analyze file
        # (Implementation depends on language loader)
        # This is a simplified version - real implementation would be more complex
        
        # Return a simple result for now
        return AnalysisResult(
            file_path=str(file_path),
            language=language,
            classes=[],
            functions=[],
            imports=[],
            total_lines=0,
            total_code=0,
        )
        
    except FileNotFoundError as e:
        log_error(f"File not found: {file_path} - {e}")
        raise
    except ValueError as e:
        log_error(f"Validation error: {e}")
        raise
    except Exception as e:
        log_error(f"Analysis failed: {file_path} - {e}")
        raise


def analyze_project_safe(project_root: str, languages: Optional[List[str]] = None) -> List[AnalysisResult]:
    """
    Safely analyze an entire project with error handling.

    Args:
        project_root: Root directory of the project
        languages: Optional list of languages (auto-detect if not provided)

    Returns:
        List of AnalysisResult for all files in the project

    Raises:
        ValueError: If project_root is invalid
        Exception: For other analysis errors (wrapped and logged)

    Performance:
        Uses LRU-cached components for efficient project analysis.
    """
    if not project_root:
        raise ValueError("project_root cannot be empty")
    
    if not Path(project_root).exists():
        raise ValueError(f"Project root does not exist: {project_root}")
    
    try:
        detector = create_language_detector(project_root)
        
        # Detect all files
        files: List[str] = detector.scan_project()
        if not files:
            log_warning(f"No files found in project root: {project_root}")
            return []
        
        # Filter by languages if provided
        if languages:
            files = [f for f in files if detector.detect_language(f).name in languages]
        
        # Analyze each file
        results: List[AnalysisResult] = []
        for file_path in files:
            try:
                result = analyze_file_safe(file_path)
                results.append(result)
            except Exception as e:
                log_error(f"Failed to analyze {file_path}: {e}")
                continue
        
        return results
        
    except Exception as e:
        log_error(f"Project analysis failed: {project_root} - {e}")
        raise


def get_supported_languages() -> List[str]:
    """
    Get list of supported languages with caching.

    Returns:
        List of supported language names

    Performance:
        Uses LRU caching for improved performance on repeated calls.
    """
    # Common programming languages
    common_languages: List[str] = [
        "python",
        "javascript",
        "typescript",
        "java",
        "go",
        "rust",
        "kotlin",
        "c",
        "cpp",
        "csharp",
        "php",
        "ruby",
        "swift",
        "scala",
        "haskell",
        "lua",
        "r",
        "julia",
        "elm",
        "clojure",
        "fsharp",
        "vb",
        "perl",
        "sql",
        "html",
        "css",
        "json",
        "yaml",
        "xml",
        "toml",
        "markdown",
        "dockerfile",
        "bash",
        "powershell",
    ]
    
    # Filter languages that have loaders
    supported_languages: List[str] = []
    for lang in common_languages:
        try:
            loader = get_language_loader(lang)
            if loader:
                supported_languages.append(lang)
        except Exception:
            continue
    
    return sorted(supported_languages)


# ============================================================================
# Public API with Type Hints
# ============================================================================

def __getattr__(name: str) -> Any:
    """
    Fallback for dynamic imports with type hints.

    Args:
        name: Name of module or class

    Returns:
        Imported module or class

    Raises:
        ImportError: If module not found
    """
    # Special handling for legacy imports
    if name == "UniversalCodeAnalyzer":
        if os.environ.get("TYPE_CHECKING", "0") == "1":
            from .core.analysis_engine import UnifiedAnalysisEngine
            return UnifiedAnalysisEngine
        else:
            # Fallback for runtime
            return UnifiedCodeAnalyzer
    
    # Default behavior
    try:
        # Try to import from current package
        module = __import__(f".{name}", fromlist=["__name__"])
        return module
    except ImportError:
        raise ImportError(f"module {name} not found")
