#!/usr/bin/env python3
"""
Unified Analysis Engine - Core Component for CLI and MCP

This module provides a unified analysis engine with dependency injection,
singleton pattern support, and comprehensive error handling.

Optimized with:
- Complete type hints (PEP 484)
- Comprehensive error handling and recovery
- Performance optimization (LRU caching, timing)
- Thread-safe operations
- Detailed documentation

Architecture:
- Dependency Injection: Recommended for new code
- Singleton Pattern: For backward compatibility
- Lazy Initialization: For performance optimization
- Type Safety: Full type hints (PEP 484)
- Error Handling: Comprehensive error handling and recovery

Author: aisheng.yu
Version: 1.10.5
Date: 2026-01-28
"""

import asyncio
import hashlib
import os
import threading
import time
from typing import TYPE_CHECKING, Any, Optional, List, Dict, Union, Tuple, Callable, Type
from functools import lru_cache
from pathlib import Path

# Type checking setup
if TYPE_CHECKING:
    # Models
    from ..models import AnalysisResult, Element, Function, Import, Class

    # Core imports
    from ..performance import PerformanceContext, PerformanceMonitor

    # Request/Response
    from .request import AnalysisRequest

    # Utility imports
    from ..utils import (
        log_debug,
        log_info,
        log_error,
        log_warning,
        log_performance,
    )

    # Dependency imports
    from ..language_detector import LanguageDetector, LanguageInfo, LanguageType
    from ..plugins.manager import PluginManager, PluginConfig
    from ..security import SecurityValidator
    from ..cache_service import CacheService, CacheConfig
    from ..parser import Parser
    from ..query import QueryExecutor, QueryConfig

else:
    # Runtime imports (when type checking is disabled)
    AnalysisResult = Any
    Element = Any
    Function = Any
    Import = Any
    Class = Any

    # Core imports
    PerformanceContext = Any
    PerformanceMonitor = Any
    AnalysisRequest = Any

    # Utility imports
    from ..utils import (
        log_debug,
        log_info,
        log_error,
        log_warning,
        log_performance,
    )

    # Dependency imports
    LanguageDetector = Any
    LanguageInfo = Any
    LanguageType = Any
    PluginManager = Any
    PluginConfig = Any
    SecurityValidator = Any
    CacheService = Any
    CacheConfig = Any
    Parser = Any
    QueryExecutor = Any
    QueryConfig = Any


# ============================================================================
# Type Definitions
# ============================================================================

if sys.version_info >= (3, 8):
    from typing import Protocol
else:
    Protocol = object

class AnalysisEngineProtocol(Protocol):
    """Interface for analysis engine creation functions."""

    def __call__(self, project_root: str) -> "AnalysisEngine":
        """
        Create analysis engine instance.

        Args:
            project_root: Root directory of the project

        Returns:
            AnalysisEngine instance
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


class ParserProtocol(Protocol):
    """Interface for parser services."""

    def parse_file(self, file_path: str, language: str) -> Any:
        """
        Parse file with specified language.

        Args:
            file_path: Path to file
            language: Programming language

        Returns:
            Parse result
        """
        ...


class PluginProtocol(Protocol):
    """Interface for language plugins."""

    def analyze_file(self, file_path: str, language: str) -> Any:
        """
        Analyze file with specified language.

        Args:
            file_path: Path to file
            language: Programming language

        Returns:
            Analysis result
        """
        ...


class SecurityValidatorProtocol(Protocol):
    """Interface for security validation services."""

    def validate_file_path(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Validate file path for security.

        Args:
            file_path: Path to file

        Returns:
            Tuple of (is_valid, error_message)
        """
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

class AnalysisEngineError(Exception):
    """Base exception for analysis engine errors."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


class InitializationError(AnalysisEngineError):
    """Exception raised when engine initialization fails."""

    pass


class ConfigurationError(AnalysisEngineError):
    """Exception raised when configuration is invalid."""

    pass


class AnalysisExecutionError(AnalysisEngineError):
    """Exception raised when file analysis fails."""

    pass


class LanguageNotSupportedError(AnalysisEngineError):
    """Exception raised when a language is not supported."""

    pass


class CachingError(AnalysisEngineError):
    """Exception raised when caching fails."""

    pass


class SecurityValidationError(AnalysisEngineError):
    """Exception raised when security validation fails."""

    pass


# ============================================================================
# Analysis Engine Configuration
# ============================================================================

class AnalysisEngineConfig:
    """Configuration for analysis engine."""

    def __init__(
        self,
        project_root: str = ".",
        enable_caching: bool = True,
        cache_max_size: int = 256,
        cache_ttl_seconds: int = 3600,
        enable_performance_monitoring: bool = True,
        enable_lazy_loading: bool = True,
        enable_security_validation: bool = True,
        enable_thread_safety: bool = True,
    ):
        """
        Initialize analysis engine configuration.

        Args:
            project_root: Root directory of the project
            enable_caching: Enable LRU caching for analysis results
            cache_max_size: Maximum size of LRU cache
            cache_ttl_seconds: Time-to-live for cache entries in seconds
            enable_performance_monitoring: Enable performance monitoring
            enable_lazy_loading: Enable lazy loading for dependencies
            enable_security_validation: Enable security validation
            enable_thread_safety: Enable thread-safe operations
        """
        self.project_root = project_root
        self.enable_caching = enable_caching
        self.cache_max_size = cache_max_size
        self.cache_ttl_seconds = cache_ttl_seconds
        self.enable_performance_monitoring = enable_performance_monitoring
        self.enable_lazy_loading = enable_lazy_loading
        self.enable_security_validation = enable_security_validation
        self.enable_thread_safety = enable_thread_safety


# ============================================================================
# Analysis Engine
# ============================================================================

class AnalysisEngine:
    """
    Optimized analysis engine with dependency injection, singleton support, and caching.

    Features:
    - Type-safe operations (PEP 484)
    - Comprehensive error handling
    - Performance monitoring
    - Caching for optimization
    - Lazy loading for dependencies
    - Thread-safe operations
    - Security validation

    Architecture:
    - Layered design with clear separation of concerns
    - Dependency injection for flexibility
    - Singleton pattern for backward compatibility
    - Lazy initialization for performance
    - Comprehensive caching with TTL support

    Usage:
        >>> from tree_sitter_analyzer.core.analysis_engine import create_analysis_engine
        >>> engine = create_analysis_engine(project_root=".")
        >>> result = await engine.analyze_file("main.py")
    """

    # Singleton instances (thread-safe)
    _instances: Dict[str, "AnalysisEngine"] = {}
    _lock: threading.RLock = threading.RLock()

    def __init__(
        self,
        project_root: str = ".",
        config: Optional[AnalysisEngineConfig] = None,
        parser: Optional[ParserProtocol] = None,
        language_detector: Optional[Any] = None,
        plugin_manager: Optional[PluginManager] = None,
        cache_service: Optional[CacheProtocol] = None,
        security_validator: Optional[SecurityValidatorProtocol] = None,
        performance_monitor: Optional[PerformanceMonitorProtocol] = None,
        **kwargs: Any,
    ):
        """
        Initialize analysis engine with optional dependency injection.

        Args:
            project_root: Root directory of the project
            config: Optional engine configuration
            parser: Parser instance (dependency injection)
            language_detector: Language detector instance (dependency injection)
            plugin_manager: Plugin manager instance (dependency injection)
            cache_service: Cache service instance (dependency injection)
            security_validator: Security validator instance (dependency injection)
            performance_monitor: Performance monitor instance (dependency injection)
            **kwargs: Additional configuration
        """
        self._config = config or AnalysisEngineConfig(project_root=project_root)
        self._project_root = project_root

        # Dependency injection or lazy loading
        self._parser = parser
        self._language_detector = language_detector
        self._plugin_manager = plugin_manager
        self._cache_service = cache_service
        self._security_validator = security_validator
        self._performance_monitor = performance_monitor

        # Thread-safe lock for operations
        self._lock = threading.RLock() if self._config.enable_thread_safety else type(None)

        # Performance statistics
        self._stats: Dict[str, Any] = {
            "total_analyses": 0,
            "successful_analyses": 0,
            "failed_analyses": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "execution_times": [],
        }

    def _ensure_dependencies(self) -> None:
        """
        Ensure all dependencies are initialized (lazy loading).
        """
        with self._lock:
            # Initialize parser
            if self._parser is None:
                if TYPE_CHECKING:
                    from ..parser import Parser
                else:
                    from ..parser import Parser
                self._parser = Parser()

            # Initialize language detector
            if self._language_detector is None:
                if TYPE_CHECKING:
                    from ..language_detector import LanguageDetector
                else:
                    from ..language_detector import LanguageDetector
                self._language_detector = LanguageDetector(self._project_root)

            # Initialize plugin manager
            if self._plugin_manager is None:
                if TYPE_CHECKING:
                    from ..plugins.manager import PluginManager
                else:
                    from ..plugins.manager import PluginManager
                self._plugin_manager = PluginManager()

            # Initialize cache service
            if self._cache_service is None:
                if TYPE_CHECKING:
                    from ..cache_service import CacheService
                else:
                    from ..cache_service import CacheService
                cache_config = CacheConfig(
                    max_size=self._config.cache_max_size,
                    ttl_seconds=self._config.cache_ttl_seconds,
                )
                self._cache_service = CacheService(config=cache_config)

            # Initialize security validator
            if self._security_validator is None:
                if TYPE_CHECKING:
                    from ..security import SecurityValidator
                else:
                    from ..security import SecurityValidator
                self._security_validator = SecurityValidator(self._project_root)

            # Initialize performance monitor
            if self._performance_monitor is None:
                if TYPE_CHECKING:
                    from ..performance import PerformanceMonitor
                else:
                    from ..performance import PerformanceMonitor
                self._performance_monitor = PerformanceMonitor()

            # Load plugins
            if self._plugin_manager:
                self._plugin_manager.load_plugins()

    def _generate_cache_key(
        self,
        file_path: str,
        language: str,
        options: Dict[str, Any],
    ) -> str:
        """
        Generate deterministic cache key from parameters.

        Args:
            file_path: Path to file
            language: Programming language
            options: Analysis options

        Returns:
            SHA-256 hash string
        """
        key_components = [
            file_path,
            language,
            str(options.get("include_complexity", False)),
            str(options.get("include_details", False)),
            str(options.get("include_elements", True)),
            str(options.get("include_queries", True)),
        ]

        # Add file metadata for cache invalidation
        try:
            if os.path.exists(file_path) and os.path.isfile(file_path):
                stat = os.stat(file_path)
                key_components.extend([
                    str(int(stat.st_mtime)),  # Modification time
                    str(stat.st_size),      # File size
                ])
        except (OSError, FileNotFoundError):
            pass

        # Generate SHA-256 hash
        key_str = ":".join(key_components)
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()

    async def analyze_file(
        self,
        file_path: str,
        language: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> AnalysisResult:
        """
        Analyze a single file with caching and performance monitoring.

        Args:
            file_path: Path to file
            language: Optional programming language (auto-detect if not provided)
            options: Analysis options

        Returns:
            Analysis result with file analysis

        Raises:
            FileNotFoundError: If file does not exist
            SecurityValidationError: If security validation fails
            AnalysisExecutionError: If analysis fails
            LanguageNotSupportedError: If language is not supported

        Performance:
            Monitors analysis execution time and cache performance.
        """
        # Ensure dependencies are initialized
        self._ensure_dependencies()

        # Update statistics
        self._stats["total_analyses"] += 1

        # Validate file path
        if self._security_validator:
            is_valid, error_message = self._security_validator.validate_file_path(file_path)
            if not is_valid:
                self._stats["failed_analyses"] += 1
                raise SecurityValidationError(f"Security validation failed: {error_message}")

        # Detect language if not provided
        if language is None:
            if self._language_detector:
                language_info = self._language_detector.detect_from_extension(file_path)
                language = language_info.name
            else:
                language = "unknown"

        # Validate language support
        if self._plugin_manager and language != "unknown":
            plugin = self._plugin_manager.get_plugin(language)
            if not plugin:
                self._stats["failed_analyses"] += 1
                raise LanguageNotSupportedError(f"Language not supported: {language}")

        # Check cache
        if self._cache_service:
            cache_key = self._generate_cache_key(file_path, language, options or {})
            cached_result = await self._cache_service.get(cache_key)
            if cached_result:
                self._stats["cache_hits"] += 1
                log_debug(f"Cache hit for {file_path}")
                return cached_result

            self._stats["cache_misses"] += 1
            log_debug(f"Cache miss for {file_path}")

        # Parse file
        if self._parser:
            try:
                parse_result = self._parser.parse_file(file_path, language)
                if not parse_result:
                    self._stats["failed_analyses"] += 1
                    return AnalysisResult(
                        file_path=file_path,
                        language=language,
                        success=False,
                        error_message="Failed to parse file",
                        elements=[],
                        analysis_time=0.0,
                    )

                tree = parse_result.tree
            except Exception as e:
                self._stats["failed_analyses"] += 1
                log_error(f"Failed to parse file {file_path}: {e}")
                return AnalysisResult(
                    file_path=file_path,
                    language=language,
                    success=False,
                    error_message=str(e),
                    elements=[],
                    analysis_time=0.0,
                )
        else:
            self._stats["failed_analyses"] += 1
            return AnalysisResult(
                file_path=file_path,
                language=language,
                success=False,
                error_message="Parser not initialized",
                elements=[],
                analysis_time=0.0,
            )

        # Analyze with plugin
        if self._plugin_manager and language != "unknown":
            try:
                plugin = self._plugin_manager.get_plugin(language)
                if not plugin:
                    self._stats["failed_analyses"] += 1
                    return AnalysisResult(
                        file_path=file_path,
                        language=language,
                        success=False,
                        error_message="Plugin not found",
                        elements=[],
                        analysis_time=0.0,
                    )

                result = plugin.analyze_file(file_path, language)
                self._stats["successful_analyses"] += 1

                # Update cache
                if self._cache_service:
                    cache_key = self._generate_cache_key(file_path, language, options or {})
                    await self._cache_service.set(cache_key, result)

                return result
            except Exception as e:
                self._stats["failed_analyses"] += 1
                log_error(f"Failed to analyze file {file_path}: {e}")
                return AnalysisResult(
                    file_path=file_path,
                    language=language,
                    success=False,
                    error_message=str(e),
                    elements=[],
                    analysis_time=0.0,
                )
        else:
            self._stats["failed_analyses"] += 1
            return AnalysisResult(
                file_path=file_path,
                language=language,
                success=False,
                error_message="Plugin manager not initialized",
                elements=[],
                analysis_time=0.0,
            )

    async def analyze_project(
        self,
        project_root: str,
        file_patterns: Optional[List[str]] = None,
        language: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> List[AnalysisResult]:
        """
        Analyze multiple files in a project.

        Args:
            project_root: Root directory of the project
            file_patterns: Optional list of file patterns to analyze
            language: Optional programming language (auto-detect if not provided)
            options: Analysis options

        Returns:
            List of analysis results

        Raises:
            FileNotFoundError: If project root does not exist
            AnalysisExecutionError: If analysis fails

        Performance:
            Monitors project analysis execution time.
        """
        # Ensure dependencies are initialized
        self._ensure_dependencies()

        # Update statistics
        self._stats["total_analyses"] += 1

        # Validate project root
        if not os.path.exists(project_root):
            self._stats["failed_analyses"] += 1
            raise FileNotFoundError(f"Project root does not exist: {project_root}")

        # Collect files to analyze
        files_to_analyze = []
        project_path = Path(project_root)

        if file_patterns:
            # Use provided file patterns
            for pattern in file_patterns:
                files_to_analyze.extend(project_path.glob(pattern))
        else:
            # Analyze all Python files
            files_to_analyze.extend(project_path.glob("**/*.py"))

        # Analyze each file
        results = []
        for file_path in files_to_analyze:
            try:
                result = await self.analyze_file(str(file_path), language, options)
                results.append(result)
            except Exception as e:
                log_error(f"Failed to analyze {file_path}: {e}")
                results.append(AnalysisResult(
                    file_path=str(file_path),
                    language=language or "unknown",
                    success=False,
                    error_message=str(e),
                    elements=[],
                    analysis_time=0.0,
                ))

        return results

    def get_stats(self) -> Dict[str, Any]:
        """
        Get analysis engine statistics.

        Returns:
            Dictionary with engine statistics
        """
        with self._lock:
            return {
                "total_analyses": self._stats["total_analyses"],
                "successful_analyses": self._stats["successful_analyses"],
                "failed_analyses": self._stats["failed_analyses"],
                "cache_hits": self._stats["cache_hits"],
                "cache_misses": self._stats["cache_misses"],
                "execution_times": self._stats["execution_times"],
                "average_execution_time": (
                    sum(self._stats["execution_times"])
                    / len(self._stats["execution_times"])
                    if self._stats["execution_times"]
                    else 0
                ),
                "config": {
                    "project_root": self._project_root,
                    "enable_caching": self._config.enable_caching,
                    "cache_max_size": self._config.cache_max_size,
                    "cache_ttl_seconds": self._config.cache_ttl_seconds,
                    "enable_performance_monitoring": self._config.enable_performance_monitoring,
                    "enable_lazy_loading": self._config.enable_lazy_loading,
                    "enable_security_validation": self._config.enable_security_validation,
                    "enable_thread_safety": self._config.enable_thread_safety,
                },
            }

    def clear_cache(self) -> None:
        """Clear all caches."""
        with self._lock:
            if self._cache_service:
                self._cache_service.clear()
            self._stats["cache_hits"] = 0
            self._stats["cache_misses"] = 0

    def cleanup(self) -> None:
        """Clean up resources."""
        with self._lock:
            if self._cache_service:
                self._cache_service.clear()
            self._stats.clear()


# ============================================================================
# Factory Functions with LRU Caching
# ============================================================================

@lru_cache(maxsize=64, typed=True)
def get_analysis_engine(
    project_root: str = ".",
    config: Optional[AnalysisEngineConfig] = None,
) -> AnalysisEngine:
    """
    Get analysis engine instance with LRU caching.

    Args:
        project_root: Root directory of the project
        config: Optional engine configuration (uses defaults if None)

    Returns:
        AnalysisEngine instance

    Performance:
        LRU caching with maxsize=64 reduces overhead for repeated calls.
    """
    engine_config = config or AnalysisEngineConfig(project_root=project_root)
    return AnalysisEngine(project_root=project_root, config=engine_config)


# ============================================================================
# Module-level exports for backward compatibility
# ============================================================================

__all__: List[str] = [
    # Type definitions
    "AnalysisEngineProtocol",
    "CacheProtocol",
    "ParserProtocol",
    "PluginProtocol",
    "SecurityValidatorProtocol",
    "PerformanceMonitorProtocol",

    # Configuration
    "AnalysisEngineConfig",

    # Exceptions
    "AnalysisEngineError",
    "InitializationError",
    "ConfigurationError",
    "AnalysisExecutionError",
    "LanguageNotSupportedError",
    "CachingError",
    "SecurityValidationError",

    # Main class
    "AnalysisEngine",

    # Factory functions
    "get_analysis_engine",
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
        ImportError: If the requested component is not found
    """
    # Handle specific imports
    if name == "AnalysisEngine":
        return AnalysisEngine
    elif name == "AnalysisEngineConfig":
        return AnalysisEngineConfig
    elif name == "create_analysis_engine":
        return get_analysis_engine
    elif name in [
        "AnalysisEngineError",
        "InitializationError",
        "ConfigurationError",
        "AnalysisExecutionError",
        "LanguageNotSupportedError",
        "CachingError",
        "SecurityValidationError",
    ]:
        # Import from module
        import sys
        module = sys.modules[__name__]
        if module is None:
            raise ImportError(f"Module {name} not found")
        return module
    else:
        # Default behavior
        try:
            # Try to import from current package
            module = __import__(f".{name}", fromlist=["__name__"])
            return module
        except ImportError:
            raise ImportError(f"Module {name} not found")
