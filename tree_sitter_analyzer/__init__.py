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

__version__ = "1.10.4"
__author__ = "aisheng.yu"
__email__ = "aimasteracc@gmail.com"

# Type checking
from typing import TYPE_CHECKING, Any, Optional, List, Dict, Union, Callable, Type

if TYPE_CHECKING:
    # Core Engine - with type hints
    from .core.analysis_engine import UnifiedAnalysisEngine as UniversalCodeAnalyzer
    from .encoding_utils import (
        EncodingManager,
        detect_encoding,
        extract_text_slice,
        read_file_safe,
        safe_decode,
        safe_encode,
        write_file_safe,
        EncodingManagerType,
        FilePath,
        TextEncoding,
        DecodedText,
    )
    
    # Language detection with type hints
    from .language_detector import LanguageDetector, LanguageInfo, LanguageType
    
    # Language loader with type hints
    from .language_loader import get_loader, LanguageLoader

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
    )

    # Data Models (Java-specific for backward compatibility) with type hints
    from .models import (
        JavaAnnotation,
        JavaClass,
        JavaField,
        JavaImport,
        JavaMethod,
        JavaPackage,
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
    UnifiedAnalysisEngine = Any
    LanguageDetector = Any
    LanguageInfo = Any
    LanguageType = Any
    LanguageLoader = Any
    
    EncodingManager = Any
    EncodingManagerType = Any
    FilePath = Any
    TextEncoding = Any
    DecodedText = Any
    
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
    LoggerConfig = Any

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
    # New Utilities
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


# Convenience functions with type hints
def create_language_detector(project_root: str) -> LanguageDetector:
    """Create language detector instance
    
    Args:
        project_root: Root directory of the project
        
    Returns:
        LanguageDetector instance
        
    Raises:
        ValueError: If project_root is invalid
    """
    if not project_root:
        raise ValueError("project_root cannot be empty")
    
    return LanguageDetector(project_root)


def create_analysis_engine(project_root: str) -> UnifiedAnalysisEngine:
    """Create analysis engine instance
    
    Args:
        project_root: Root directory of the project
        
    Returns:
        UnifiedAnalysisEngine instance
        
    Raises:
        ValueError: If project_root is invalid
    """
    if not project_root:
        raise ValueError("project_root cannot be empty")
    
    return UnifiedAnalysisEngine(project_root)


def analyze_file(file_path: str, language: Optional[str] = None) -> AnalysisResult:
    """Analyze a single file
    
    Args:
        file_path: Path to the file
        language: Optional language (auto-detect if not provided)
        
    Returns:
        AnalysisResult with file analysis
        
    Raises:
        FileNotFoundError: If file does not exist
        ValueError: If file_path is invalid
    """
    detector = create_language_detector(file_path)
    
    if language:
        # Use specified language
        language_info: Optional[LanguageInfo] = detector.get_language_info(language)
        if not language_info:
            raise ValueError(f"Unsupported language: {language}")
    else:
        # Auto-detect language
        language_info = detector.detect(file_path)
        if not language_info:
            raise ValueError("Could not detect language")
        language = language_info.name
    
    # Load language analyzer
    loader: LanguageLoader = get_loader(language)
    if not loader:
        raise ValueError(f"Language loader not found for: {language}")
    
    # Analyze file
    engine: UnifiedAnalysisEngine = create_analysis_engine(file_path)
    result = engine.analyze_file(file_path, language)
    
    return result


def analyze_project(project_root: str, languages: Optional[List[str]] = None) -> List[AnalysisResult]:
    """Analyze an entire project
    
    Args:
        project_root: Root directory of the project
        languages: Optional list of languages (auto-detect if not provided)
        
    Returns:
        List of AnalysisResult for all files in the project
        
    Raises:
        ValueError: If project_root is invalid
    """
    detector = create_language_detector(project_root)
    
    # Detect all files
    files: List[str] = detector.scan_project()
    if not files:
        return []
    
    # Filter by languages if provided
    if languages:
        files = [f for f in files if detector.detect_language(f).name in languages]
    
    # Analyze each file
    results: List[AnalysisResult] = []
    for file_path in files:
        try:
            result = analyze_file(file_path)
            results.append(result)
        except Exception as e:
            log_error(f"Failed to analyze {file_path}: {e}")
            continue
    
    return results


def get_supported_languages() -> List[str]:
    """Get list of supported languages
    
    Returns:
        List of supported language names
    """
    from .language_loader import get_loader
    
    # Get all available loaders
    languages: List[str] = []
    
    # Common programming languages
    common_languages = [
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
    for lang in common_languages:
        try:
            loader = get_loader(lang)
            if loader:
                languages.append(lang)
        except Exception:
            continue
    
    return sorted(languages)


# Public API with type hints
def __getattr__(name: str) -> Any:
    """Fallback for dynamic imports
    
    Args:
        name: Name of the module or class
        
    Returns:
        Imported module or class
        
    Raises:
        ImportError: If module not found
    """
    # Special handling for legacy imports
    if name == "UniversalCodeAnalyzer":
        if TYPE_CHECKING:
            from .core.analysis_engine import UnifiedAnalysisEngine
            return UnifiedAnalysisEngine
        else:
            return UniversalCodeAnalyzer
    
    # Default behavior
    raise ImportError(f"module {name} not found")
