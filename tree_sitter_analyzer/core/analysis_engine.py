#!/usr/bin/env python3
"""
Unified Analysis Engine - Common Analysis System for CLI and MCP (Fixed Version)

This module provides a unified engine that serves as the center of all analysis processing.
It is commonly used by CLI, MCP, and other interfaces.

Roo Code compliance:
- Type hints: Required for all functions
- MCP logging: Log output at each step
- docstring: Google Style docstring
- Performance-focused: Singleton pattern and cache sharing
"""

import hashlib
import threading
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from ..models import AnalysisResult
from ..plugins.base import LanguagePlugin as BaseLanguagePlugin
from ..plugins.manager import PluginManager
from ..security import SecurityValidator
from ..utils import log_debug, log_error, log_info, log_performance
from .cache_service import CacheService


class UnsupportedLanguageError(Exception):
    """Unsupported language error"""

    pass


class PluginRegistry(Protocol):
    """Protocol for plugin registration management"""

    def get_plugin(self, language: str) -> Optional["LanguagePlugin"]:
        """Get language plugin"""
        ...


class LanguagePlugin(Protocol):
    """Language plugin protocol"""

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> AnalysisResult:
        """File analysis"""
        ...


class PerformanceMonitor:
    """Performance monitoring (simplified version)"""

    def __init__(self) -> None:
        self._last_duration: float = 0.0
        self._monitoring_active: bool = False
        self._operation_stats: dict[str, Any] = {}
        self._total_operations: int = 0

    def measure_operation(self, operation_name: str) -> "PerformanceContext":
        """Return measurement context for operation"""
        return PerformanceContext(operation_name, self)

    def get_last_duration(self) -> float:
        """Get last operation time"""
        return self._last_duration

    def _set_duration(self, duration: float) -> None:
        """Set operation time (internal use)"""
        self._last_duration = duration

    def start_monitoring(self) -> None:
        """Start performance monitoring"""
        self._monitoring_active = True
        log_info("Performance monitoring started")

    def stop_monitoring(self) -> None:
        """Stop performance monitoring"""
        self._monitoring_active = False
        log_info("Performance monitoring stopped")

    def get_operation_stats(self) -> dict[str, Any]:
        """Get operation statistics"""
        return self._operation_stats.copy()

    def get_performance_summary(self) -> dict[str, Any]:
        """Get performance summary"""
        return {
            "total_operations": self._total_operations,
            "monitoring_active": self._monitoring_active,
            "last_duration": self._last_duration,
            "operation_count": len(self._operation_stats),
        }

    def record_operation(self, operation_name: str, duration: float) -> None:
        """Record operation"""
        if self._monitoring_active:
            if operation_name not in self._operation_stats:
                self._operation_stats[operation_name] = {
                    "count": 0,
                    "total_time": 0.0,
                    "avg_time": 0.0,
                    "min_time": float("inf"),
                    "max_time": 0.0,
                }

            stats = self._operation_stats[operation_name]
            stats["count"] += 1
            stats["total_time"] += duration
            stats["avg_time"] = stats["total_time"] / stats["count"]
            stats["min_time"] = min(stats["min_time"], duration)
            stats["max_time"] = max(stats["max_time"], duration)

            self._total_operations += 1

    def clear_metrics(self) -> None:
        """Clear collected metrics"""
        self._operation_stats.clear()
        self._total_operations = 0
        self._last_duration = 0.0
        log_info("Performance metrics cleared")


class PerformanceContext:
    """Performance measurement context"""

    def __init__(self, operation_name: str, monitor: PerformanceMonitor) -> None:
        self.operation_name = operation_name
        self.monitor = monitor
        self.start_time: float = 0.0

    def __enter__(self) -> "PerformanceContext":
        import time

        self.start_time = time.time()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        import time

        duration = time.time() - self.start_time
        self.monitor._set_duration(duration)
        self.monitor.record_operation(self.operation_name, duration)
        log_performance(self.operation_name, duration, "Operation completed")


@dataclass(frozen=True)
class AnalysisRequest:
    """
    Analysis request

    Attributes:
        file_path: Path to target file to analyze
        language: Programming language (auto-detected if None)
        include_complexity: Whether to include complexity metrics
        include_details: Whether to include detailed structure info
        format_type: Output format
    """

    file_path: str
    language: str | None = None
    include_complexity: bool = True
    include_details: bool = False
    format_type: str = "json"

    @classmethod
    def from_mcp_arguments(cls, arguments: dict[str, Any]) -> "AnalysisRequest":
        """
        Create analysis request from MCP tool arguments

        Args:
            arguments: MCP argument dictionary

        Returns:
            AnalysisRequest
        """
        return cls(
            file_path=arguments.get("file_path", ""),
            language=arguments.get("language"),
            include_complexity=arguments.get("include_complexity", True),
            include_details=arguments.get("include_details", False),
            format_type=arguments.get("format_type", "json"),
        )


# SimplePluginRegistry removed - now using PluginManager


class UnifiedAnalysisEngine:
    """
    Unified analysis engine (revised)

    Central engine shared by CLI, MCP and other interfaces, implemented as a
    singleton to enable efficient resource usage and cache sharing.

    Improvements:
    - Fix async issues in destructor
    - Provide explicit cleanup() method

    Attributes:
        _cache_service: Cache service
        _plugin_manager: Plugin manager
        _performance_monitor: Performance monitor
    """

    _instances: dict[str, "UnifiedAnalysisEngine"] = {}
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, project_root: str | None = None) -> "UnifiedAnalysisEngine":
        """Singleton instance sharing (project_root aware)"""
        # Create a key based on project_root for different instances
        instance_key = project_root or "default"

        if instance_key not in cls._instances:
            with cls._lock:
                if instance_key not in cls._instances:
                    instance = super().__new__(cls)
                    cls._instances[instance_key] = instance
                    # Mark as not initialized for this instance
                    instance._initialized: bool = False

        return cls._instances[instance_key]

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize (executed only once per instance)"""
        if hasattr(self, "_initialized") and getattr(self, "_initialized", False):
            return

        self._cache_service = CacheService()
        self._plugin_manager = PluginManager()
        self._performance_monitor = PerformanceMonitor()
        self._security_validator = SecurityValidator(project_root)
        self._project_root = project_root

        # Auto-load plugins
        self._load_plugins()

        self._initialized = True

        log_debug(
            f"UnifiedAnalysisEngine initialized with project root: {project_root}"
        )

    def _load_plugins(self) -> None:
        """Auto-load available plugins"""
        log_debug("Loading plugins using PluginManager...")

        try:
            # PluginManagerの自動ロード機能を使用
            loaded_plugins = self._plugin_manager.load_plugins()

            final_languages = [plugin.get_language_name() for plugin in loaded_plugins]
            log_debug(
                f"Successfully loaded {len(final_languages)} language plugins: {', '.join(final_languages)}"
            )
        except Exception as e:
            log_error(f"Failed to load plugins: {e}")
            import traceback

            log_error(f"Plugin loading traceback: {traceback.format_exc()}")

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """
        Unified analysis method

        Args:
            request: Analysis request

        Returns:
            Analysis result

        Raises:
            UnsupportedLanguageError: When language is not supported
            FileNotFoundError: When file is not found
        """
        log_debug(f"Starting analysis for {request.file_path}")

        # Security validation
        is_valid, error_msg = self._security_validator.validate_file_path(
            request.file_path
        )
        if not is_valid:
            log_error(
                f"Security validation failed for file path: {request.file_path} - {error_msg}"
            )
            raise ValueError(f"Invalid file path: {error_msg}")

        # Cache check (shared across CLI/MCP)
        cache_key = self._generate_cache_key(request)
        cached_result = await self._cache_service.get(cache_key)
        if cached_result:
            log_info(f"Cache hit for {request.file_path}")
            return cached_result  # type: ignore

        # Language detection
        language = request.language or self._detect_language(request.file_path)
        log_debug(f"Detected language: {language}")

        # Debug: inspect registered plugins
        supported_languages = self._plugin_manager.get_supported_languages()
        log_debug(f"Supported languages: {supported_languages}")
        log_debug(f"Looking for plugin for language: {language}")

        # Get plugin
        plugin = self._plugin_manager.get_plugin(language)
        if not plugin:
            error_msg = f"Language {language} not supported"
            log_error(error_msg)
            raise UnsupportedLanguageError(error_msg)

        log_debug(f"Found plugin for {language}: {type(plugin)}")

        # Run analysis (with performance monitoring)
        with self._performance_monitor.measure_operation(f"analyze_{language}"):
            log_debug(f"Calling plugin.analyze_file for {request.file_path}")
            result = await plugin.analyze_file(request.file_path, request)
            log_debug(
                f"Plugin returned result: success={result.success}, elements={len(result.elements) if result.elements else 0}"
            )

        # Ensure language field is set
        if result.language == "unknown" or not result.language:
            result.language = language

        # Save to cache
        await self._cache_service.set(cache_key, result)

        log_performance(
            "unified_analysis",
            self._performance_monitor.get_last_duration(),
            f"Analyzed {request.file_path} ({language})",
        )

        return result

    async def analyze_file(self, file_path: str) -> AnalysisResult:
        """
        Backward compatibility method for analyze_file.

        Args:
            file_path: Path to the file to analyze

        Returns:
            Analysis result
        """
        # Security validation
        is_valid, error_msg = self._security_validator.validate_file_path(file_path)
        if not is_valid:
            log_error(
                f"Security validation failed for file path: {file_path} - {error_msg}"
            )
            raise ValueError(f"Invalid file path: {error_msg}")

        request = AnalysisRequest(
            file_path=file_path,
            language=None,  # Auto-detect
            include_complexity=True,
            include_details=True,
        )
        return await self.analyze(request)

    def _generate_cache_key(self, request: AnalysisRequest) -> str:
        """
        Generate cache key

        Args:
            request: Analysis request

        Returns:
            Hashed cache key
        """
        # 一意なキーを生成するための文字列を構築
        key_components = [
            request.file_path,
            str(request.language),
            str(request.include_complexity),
            str(request.include_details),
            request.format_type,
        ]

        key_string = ":".join(key_components)

        # SHA256でハッシュ化
        return hashlib.sha256(key_string.encode("utf-8")).hexdigest()

    def _detect_language(self, file_path: str) -> str:
        """
        Detect language from file extension

        Args:
            file_path: File path

        Returns:
            Detected language name
        """
        # 簡易的な拡張子ベース検出
        from pathlib import Path

        ext = Path(file_path).suffix

        language_map = {
            ".java": "java",
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".c": "c",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".rs": "rust",
            ".go": "go",
        }

        detected = language_map.get(ext.lower(), "unknown")
        log_debug(f"Language detection: {file_path} -> {detected}")
        return detected

    def clear_cache(self) -> None:
        """Clear cache (for tests)"""
        self._cache_service.clear()
        log_info("Analysis engine cache cleared")

    def register_plugin(self, language: str, plugin: BaseLanguagePlugin) -> None:
        """
        Register plugin

        Args:
            language: Language name (kept for compatibility, not used)
            plugin: Language plugin instance
        """
        self._plugin_manager.register_plugin(plugin)

    def get_supported_languages(self) -> list[str]:
        """
        Get list of supported languages

        Returns:
            List of language names
        """
        return self._plugin_manager.get_supported_languages()

    def get_cache_stats(self) -> dict[str, Any]:
        """
        Get cache statistics

        Returns:
            Cache statistics dictionary
        """
        return self._cache_service.get_stats()

    async def invalidate_cache_pattern(self, pattern: str) -> int:
        """
        Invalidate cached entries matching a pattern

        Args:
            pattern: Pattern to match keys

        Returns:
            Number of invalidated keys
        """
        return await self._cache_service.invalidate_pattern(pattern)

    def measure_operation(self, operation_name: str) -> "PerformanceContext":
        """
        Context manager for performance measurement

        Args:
            operation_name: Operation name

        Returns:
            PerformanceContext
        """
        return self._performance_monitor.measure_operation(operation_name)

    def start_monitoring(self) -> None:
        """Start performance monitoring"""
        self._performance_monitor.start_monitoring()

    def stop_monitoring(self) -> None:
        """Stop performance monitoring"""
        self._performance_monitor.stop_monitoring()

    def get_operation_stats(self) -> dict[str, Any]:
        """Get operation statistics"""
        return self._performance_monitor.get_operation_stats()

    def get_performance_summary(self) -> dict[str, Any]:
        """Get performance summary"""
        return self._performance_monitor.get_performance_summary()

    def clear_metrics(self) -> None:
        """
        Clear collected performance metrics

        Resets metrics collected by performance monitoring. Used in tests/debugging.
        """
        # 新しいパフォーマンスモニターインスタンスを作成してリセット
        self._performance_monitor = PerformanceMonitor()
        log_info("Performance metrics cleared")

    def cleanup(self) -> None:
        """
        Explicit resource cleanup

        Call explicitly (e.g., at end of tests) to clean up resources and avoid
        async issues in destructors.
        """
        try:
            if hasattr(self, "_cache_service"):
                self._cache_service.clear()
            if hasattr(self, "_performance_monitor"):
                self._performance_monitor.clear_metrics()
            log_debug("UnifiedAnalysisEngine cleaned up")
        except Exception as e:
            log_error(f"Error during UnifiedAnalysisEngine cleanup: {e}")

    def __del__(self) -> None:
        """
        Destructor - keep minimal to avoid issues in async contexts

        Performs no cleanup; use cleanup() explicitly when needed.
        """
        # デストラクタでは何もしない（非同期コンテキストでの問題を避けるため）
        pass


# 簡易的なプラグイン実装（テスト用）
class MockLanguagePlugin:
    """Mock plugin for testing"""

    def __init__(self, language: str) -> None:
        self.language = language

    def get_language_name(self) -> str:
        """Get language name"""
        return self.language

    def get_file_extensions(self) -> list[str]:
        """Get supported file extensions"""
        return [f".{self.language}"]

    def create_extractor(self) -> None:
        """Create extractor (mock)"""
        return None

    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        """Mock analysis implementation"""
        log_info(f"Mock analysis for {file_path} ({self.language})")

        # 簡易的な解析結果を返す
        return AnalysisResult(
            file_path=file_path,
            line_count=10,  # 新しいアーキテクチャ用
            elements=[],  # 新しいアーキテクチャ用
            node_count=5,  # 新しいアーキテクチャ用
            query_results={},  # 新しいアーキテクチャ用
            source_code="// Mock source code",  # 新しいアーキテクチャ用
            language=self.language,  # 言語を設定
            package=None,
            analysis_time=0.1,
            success=True,
            error_message=None,
        )


def get_analysis_engine(project_root: str | None = None) -> UnifiedAnalysisEngine:
    """
    Get unified analysis engine instance

    Args:
        project_root: Project root directory for security validation

    Returns:
        Singleton instance of UnifiedAnalysisEngine
    """
    return UnifiedAnalysisEngine(project_root)
