#!/usr/bin/env python3
"""
統一解析エンジン - CLI・MCP共通解析システム（修正版）

このモジュールは、すべての解析処理の中心となる統一エンジンを提供します。
CLI、MCP、その他のインターフェースから共通して使用されます。

Roo Code規約準拠:
- 型ヒント: 全関数に型ヒント必須
- MCPログ: 各ステップでログ出力
- docstring: Google Style docstring
- パフォーマンス重視: シングルトンパターンとキャッシュ共有
"""

import hashlib
import threading
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from ..models import AnalysisResult
from ..utils import log_debug, log_error, log_info, log_performance
from .cache_service import CacheService


class UnsupportedLanguageError(Exception):
    """サポートされていない言語エラー"""

    pass


class PluginRegistry(Protocol):
    """プラグイン登録管理のプロトコル"""

    def get_plugin(self, language: str) -> Optional["LanguagePlugin"]:
        """言語プラグインを取得"""
        ...


class LanguagePlugin(Protocol):
    """言語プラグインのプロトコル"""

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> AnalysisResult:
        """ファイル解析"""
        ...


class PerformanceMonitor:
    """パフォーマンス監視（簡易版）"""

    def __init__(self) -> None:
        self._last_duration: float = 0.0
        self._monitoring_active: bool = False
        self._operation_stats: dict[str, Any] = {}
        self._total_operations: int = 0

    def measure_operation(self, operation_name: str) -> "PerformanceContext":
        """操作の測定コンテキストを返す"""
        return PerformanceContext(operation_name, self)

    def get_last_duration(self) -> float:
        """最後の操作時間を取得"""
        return self._last_duration

    def _set_duration(self, duration: float) -> None:
        """操作時間を設定（内部用）"""
        self._last_duration = duration

    def start_monitoring(self) -> None:
        """パフォーマンス監視を開始"""
        self._monitoring_active = True
        log_info("Performance monitoring started")

    def stop_monitoring(self) -> None:
        """パフォーマンス監視を停止"""
        self._monitoring_active = False
        log_info("Performance monitoring stopped")

    def get_operation_stats(self) -> dict[str, Any]:
        """操作統計を取得"""
        return self._operation_stats.copy()

    def get_performance_summary(self) -> dict[str, Any]:
        """パフォーマンス要約を取得"""
        return {
            "total_operations": self._total_operations,
            "monitoring_active": self._monitoring_active,
            "last_duration": self._last_duration,
            "operation_count": len(self._operation_stats),
        }

    def record_operation(self, operation_name: str, duration: float) -> None:
        """操作を記録"""
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
        """メトリクスをクリア"""
        self._operation_stats.clear()
        self._total_operations = 0
        self._last_duration = 0.0
        log_info("Performance metrics cleared")


class PerformanceContext:
    """パフォーマンス測定コンテキスト"""

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
    解析リクエスト

    Attributes:
        file_path: 解析対象ファイルパス
        language: プログラミング言語（Noneの場合は自動検出）
        include_complexity: 複雑度計算を含むか
        include_details: 詳細情報を含むか
        format_type: 出力フォーマット
    """

    file_path: str
    language: str | None = None
    include_complexity: bool = True
    include_details: bool = False
    format_type: str = "json"

    @classmethod
    def from_mcp_arguments(cls, arguments: dict[str, Any]) -> "AnalysisRequest":
        """
        MCP引数から解析リクエストを作成

        Args:
            arguments: MCP引数辞書

        Returns:
            解析リクエスト
        """
        return cls(
            file_path=arguments.get("file_path", ""),
            language=arguments.get("language"),
            include_complexity=arguments.get("include_complexity", True),
            include_details=arguments.get("include_details", False),
            format_type=arguments.get("format_type", "json"),
        )


class SimplePluginRegistry:
    """簡易プラグイン登録管理"""

    def __init__(self) -> None:
        self._plugins: dict[str, LanguagePlugin] = {}

    def register_plugin(self, language: str, plugin: LanguagePlugin) -> None:
        """プラグインを登録"""
        self._plugins[language] = plugin
        log_info(f"Plugin registered for language: {language}")

    def get_plugin(self, language: str) -> LanguagePlugin | None:
        """プラグインを取得"""
        return self._plugins.get(language)

    def get_supported_languages(self) -> list[str]:
        """サポートされている言語一覧を取得"""
        return list(self._plugins.keys())


class UnifiedAnalysisEngine:
    """
    統一解析エンジン（修正版）

    CLI・MCP・その他のインターフェースから共通して使用される
    中央集権的な解析エンジン。シングルトンパターンで実装し、
    リソースの効率的な利用とキャッシュの共有を実現。

    修正点：
    - デストラクタでの非同期処理問題を解決
    - 明示的なクリーンアップメソッドを提供

    Attributes:
        _cache_service: キャッシュサービス
        _plugin_registry: プラグイン登録管理
        _performance_monitor: パフォーマンス監視
    """

    _instance: Optional["UnifiedAnalysisEngine"] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "UnifiedAnalysisEngine":
        """シングルトンパターンでインスタンス共有"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """初期化（一度のみ実行）"""
        if hasattr(self, "_initialized"):
            return

        self._cache_service = CacheService()
        self._plugin_registry = SimplePluginRegistry()
        self._performance_monitor = PerformanceMonitor()

        # プラグインを自動ロード
        self._load_plugins()

        self._initialized = True

        log_info("UnifiedAnalysisEngine initialized")

    def _load_plugins(self) -> None:
        """利用可能なプラグインを自動ロード"""
        log_info("Loading plugins...")

        try:
            # Javaプラグインの登録
            log_debug("Attempting to load Java plugin...")
            from ..languages.java_plugin import JavaPlugin

            java_plugin = JavaPlugin()
            self._plugin_registry.register_plugin("java", java_plugin)
            log_debug("Loaded Java plugin")
        except Exception as e:
            log_error(f"Failed to load Java plugin: {e}")
            import traceback

            log_error(f"Java plugin traceback: {traceback.format_exc()}")

        try:
            # JavaScriptプラグインの登録
            log_debug("Attempting to load JavaScript plugin...")
            from ..plugins.javascript_plugin import JavaScriptPlugin

            js_plugin = JavaScriptPlugin()
            self._plugin_registry.register_plugin("javascript", js_plugin)
            log_debug("Loaded JavaScript plugin")
        except Exception as e:
            log_error(f"Failed to load JavaScript plugin: {e}")
            import traceback

            log_error(f"JavaScript plugin traceback: {traceback.format_exc()}")

        try:
            # Pythonプラグインの登録
            log_debug("Attempting to load Python plugin...")
            from ..languages.python_plugin import PythonPlugin

            python_plugin = PythonPlugin()
            self._plugin_registry.register_plugin("python", python_plugin)
            log_debug("Loaded Python plugin")
        except Exception as e:
            log_error(f"Failed to load Python plugin: {e}")
            import traceback

            log_error(f"Python plugin traceback: {traceback.format_exc()}")

        final_languages = self._plugin_registry.get_supported_languages()
        log_info(
            f"Successfully loaded {len(final_languages)} language plugins: {', '.join(final_languages)}"
        )

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """
        統一解析メソッド

        Args:
            request: 解析リクエスト

        Returns:
            解析結果

        Raises:
            UnsupportedLanguageError: サポートされていない言語
            FileNotFoundError: ファイルが見つからない
        """
        log_info(f"Starting analysis for {request.file_path}")

        # キャッシュチェック（CLI・MCP間で共有）
        cache_key = self._generate_cache_key(request)
        cached_result = await self._cache_service.get(cache_key)
        if cached_result:
            log_info(f"Cache hit for {request.file_path}")
            return cached_result

        # 言語検出
        language = request.language or self._detect_language(request.file_path)
        log_debug(f"Detected language: {language}")

        # デバッグ：登録されているプラグインを確認
        supported_languages = self._plugin_registry.get_supported_languages()
        log_debug(f"Supported languages: {supported_languages}")
        log_debug(f"Looking for plugin for language: {language}")

        # プラグイン取得
        plugin = self._plugin_registry.get_plugin(language)
        if not plugin:
            error_msg = f"Language {language} not supported"
            log_error(error_msg)
            raise UnsupportedLanguageError(error_msg)

        log_debug(f"Found plugin for {language}: {type(plugin)}")

        # 解析実行（パフォーマンス監視付き）
        with self._performance_monitor.measure_operation(f"analyze_{language}"):
            log_debug(f"Calling plugin.analyze_file for {request.file_path}")
            result = await plugin.analyze_file(request.file_path, request)
            log_debug(
                f"Plugin returned result: success={result.success}, elements={len(result.elements) if result.elements else 0}"
            )

        # 言語情報を確実に設定
        if result.language == "unknown" or not result.language:
            result.language = language

        # キャッシュ保存
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
        request = AnalysisRequest(
            file_path=file_path,
            language=None,  # Auto-detect
            include_complexity=True,
            include_details=True,
        )
        return await self.analyze(request)

    def _generate_cache_key(self, request: AnalysisRequest) -> str:
        """
        キャッシュキーを生成

        Args:
            request: 解析リクエスト

        Returns:
            ハッシュ化されたキャッシュキー
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
        言語検出

        Args:
            file_path: ファイルパス

        Returns:
            検出された言語
        """
        # 簡易的な拡張子ベース検出
        import os

        _, ext = os.path.splitext(file_path)

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
        """キャッシュクリア（テスト用）"""
        self._cache_service.clear()
        log_info("Analysis engine cache cleared")

    def register_plugin(self, language: str, plugin: LanguagePlugin) -> None:
        """
        プラグインを登録

        Args:
            language: 言語名
            plugin: 言語プラグイン
        """
        self._plugin_registry.register_plugin(language, plugin)

    def get_supported_languages(self) -> list[str]:
        """
        サポートされている言語一覧を取得

        Returns:
            サポート言語のリスト
        """
        return self._plugin_registry.get_supported_languages()

    def get_cache_stats(self) -> dict[str, Any]:
        """
        キャッシュ統計を取得

        Returns:
            キャッシュ統計情報
        """
        return self._cache_service.get_stats()

    async def invalidate_cache_pattern(self, pattern: str) -> int:
        """
        パターンに一致するキャッシュを無効化

        Args:
            pattern: 無効化するキーのパターン

        Returns:
            無効化されたキー数
        """
        return await self._cache_service.invalidate_pattern(pattern)

    def measure_operation(self, operation_name: str) -> "PerformanceContext":
        """
        パフォーマンス計測のためのコンテキストマネージャ

        Args:
            operation_name: 操作名

        Returns:
            パフォーマンス測定コンテキスト
        """
        return self._performance_monitor.measure_operation(operation_name)

    def start_monitoring(self) -> None:
        """パフォーマンス監視を開始"""
        self._performance_monitor.start_monitoring()

    def stop_monitoring(self) -> None:
        """パフォーマンス監視を停止"""
        self._performance_monitor.stop_monitoring()

    def get_operation_stats(self) -> dict[str, Any]:
        """操作統計を取得"""
        return self._performance_monitor.get_operation_stats()

    def get_performance_summary(self) -> dict[str, Any]:
        """パフォーマンス要約を取得"""
        return self._performance_monitor.get_performance_summary()

    def clear_metrics(self) -> None:
        """
        収集したパフォーマンスメトリクスをクリア

        パフォーマンス監視で収集されたメトリクスをリセットします。
        テストやデバッグ時に使用されます。
        """
        # 新しいパフォーマンスモニターインスタンスを作成してリセット
        self._performance_monitor = PerformanceMonitor()
        log_info("Performance metrics cleared")

    def cleanup(self) -> None:
        """
        明示的なリソースクリーンアップ

        テスト終了時などに明示的に呼び出してリソースをクリーンアップします。
        デストラクタでの非同期処理問題を避けるため、明示的な呼び出しが必要です。
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
        デストラクタ - 非同期コンテキストでの問題を避けるため最小限の処理

        デストラクタでは何もしません。これは非同期コンテキストでの
        ガベージコレクション時に発生する問題を避けるためです。
        明示的なクリーンアップはcleanup()メソッドを使用してください。
        """
        # デストラクタでは何もしない（非同期コンテキストでの問題を避けるため）
        pass


# 簡易的なプラグイン実装（テスト用）
class MockLanguagePlugin:
    """テスト用のモックプラグイン"""

    def __init__(self, language: str) -> None:
        self.language = language

    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        """モック解析実装"""
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
            imports=[],
            classes=[],
            methods=[],
            fields=[],
            annotations=[],
            analysis_time=0.1,
            success=True,
            error_message=None,
        )


def get_analysis_engine() -> UnifiedAnalysisEngine:
    """
    統一解析エンジンのインスタンスを取得

    Returns:
        統一解析エンジンのシングルトンインスタンス
    """
    return UnifiedAnalysisEngine()
