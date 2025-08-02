#!/usr/bin/env python3
"""
Tests for core.analysis_engine

Roo Code規約準拠:
- TDD: テスト先行実装
- 型ヒント: 全関数に型ヒント必須
- MCPログ: 各ステップでログ出力
- docstring: Google Style docstring
- カバレッジ: 80%以上目標
"""


# Mock functionality now provided by pytest-mock

import pytest

# テスト対象のインポート
from tree_sitter_analyzer.core.analysis_engine import (
    AnalysisRequest,
    MockLanguagePlugin,
    UnifiedAnalysisEngine,
    UnsupportedLanguageError,
)


@pytest.fixture
def engine():
    """統一解析エンジンのフィクスチャ"""
    engine = UnifiedAnalysisEngine()
    # テスト用プラグインを登録
    engine.register_plugin("java", MockLanguagePlugin("java"))
    engine.register_plugin("python", MockLanguagePlugin("python"))
    yield engine
    # クリーンアップ
    engine.clear_cache()


class TestUnifiedAnalysisEngine:
    """統一解析エンジンのテスト"""

    @pytest.mark.unit
    def test_singleton_pattern(self) -> None:
        """シングルトンパターンのテスト"""
        # Arrange & Act
        engine1 = UnifiedAnalysisEngine()
        engine2 = UnifiedAnalysisEngine()

        # Assert
        assert engine1 is engine2  # 同じインスタンス
        assert id(engine1) == id(engine2)

    @pytest.mark.unit
    def test_initialization(self) -> None:
        """初期化テスト"""
        # Arrange & Act
        engine = UnifiedAnalysisEngine()

        # Assert
        assert engine is not None
        assert engine._cache_service is not None
        assert engine._plugin_manager is not None
        assert engine._performance_monitor is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_analyze_with_cache_hit(self, engine) -> None:
        """キャッシュヒット時の解析テスト"""
        # Arrange
        request = AnalysisRequest(file_path="test.java", language="java")

        # 事前にキャッシュに結果を設定
        cache_key = engine._generate_cache_key(request)
        from tree_sitter_analyzer.models import AnalysisResult

        expected_result = AnalysisResult(
            file_path="test.java",
            package=None,
            imports=[],
            classes=[],
            methods=[],
            fields=[],
            annotations=[],
            analysis_time=0.0,
            success=True,
            error_message=None,
        )
        await engine._cache_service.set(cache_key, expected_result)

        # Act
        result = await engine.analyze(request)

        # Assert
        assert result.file_path == expected_result.file_path
        assert result.success == expected_result.success

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_analyze_with_cache_miss(self, engine) -> None:
        """キャッシュミス時の解析テスト"""
        # Arrange
        request = AnalysisRequest(file_path="test.java", language="java")

        # Act
        result = await engine.analyze(request)

        # Assert
        assert result is not None
        assert result.file_path == "test.java"
        assert result.success is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_analyze_unsupported_language(self, engine) -> None:
        """サポートされていない言語のテスト"""
        # Arrange
        request = AnalysisRequest(file_path="test.unknown", language="unknown")

        # Act & Assert
        with pytest.raises(UnsupportedLanguageError) as exc_info:
            await engine.analyze(request)

        assert "Language unknown not supported" in str(exc_info.value)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_language_detection(self, engine) -> None:
        """言語自動検出のテスト"""
        # Arrange
        request = AnalysisRequest(file_path="test.java")  # languageなし

        # Act
        result = await engine.analyze(request)

        # Assert
        assert result.file_path == "test.java"
        assert result.success is True

    @pytest.mark.unit
    def test_generate_cache_key(self, engine) -> None:
        """キャッシュキー生成のテスト"""
        # Arrange
        request1 = AnalysisRequest(
            file_path="test.java", language="java", include_complexity=True
        )
        request2 = AnalysisRequest(
            file_path="test.java", language="java", include_complexity=True
        )
        request3 = AnalysisRequest(
            file_path="test.java", language="java", include_complexity=False
        )

        # Act
        key1 = engine._generate_cache_key(request1)
        key2 = engine._generate_cache_key(request2)
        key3 = engine._generate_cache_key(request3)

        # Assert
        assert key1 == key2  # 同じリクエストなら同じキー
        assert key1 != key3  # 異なるリクエストなら異なるキー
        assert isinstance(key1, str)
        assert len(key1) > 0

    @pytest.mark.unit
    def test_language_detection_by_extension(self, engine) -> None:
        """拡張子による言語検出のテスト"""
        # Act & Assert
        assert engine._detect_language("test.java") == "java"
        assert engine._detect_language("test.py") == "python"
        assert engine._detect_language("test.js") == "javascript"
        assert engine._detect_language("test.ts") == "typescript"
        assert engine._detect_language("test.c") == "c"
        assert engine._detect_language("test.cpp") == "cpp"
        assert engine._detect_language("test.rs") == "rust"
        assert engine._detect_language("test.go") == "go"
        assert engine._detect_language("test.unknown") == "unknown"

    @pytest.mark.unit
    def test_plugin_registration(self, engine) -> None:
        """プラグイン登録のテスト"""
        # Arrange
        plugin = MockLanguagePlugin("test_lang")

        # Act
        engine.register_plugin("test_lang", plugin)

        # Assert
        assert "test_lang" in engine.get_supported_languages()
        retrieved_plugin = engine._plugin_manager.get_plugin("test_lang")
        assert retrieved_plugin == plugin

    @pytest.mark.unit
    def test_cache_stats(self, engine) -> None:
        """キャッシュ統計のテスト"""
        # Act
        stats = engine.get_cache_stats()

        # Assert
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats
        assert isinstance(stats["hits"], int)
        assert isinstance(stats["misses"], int)
        assert isinstance(stats["hit_rate"], float)


class TestAnalysisRequest:
    """AnalysisRequestのテスト"""

    @pytest.mark.unit
    def test_analysis_request_creation(self) -> None:
        """AnalysisRequest作成テスト"""
        # Arrange & Act
        request = AnalysisRequest(
            file_path="test.java",
            language="java",
            include_complexity=True,
            include_details=False,
        )

        # Assert
        assert request.file_path == "test.java"
        assert request.language == "java"
        assert request.include_complexity is True
        assert request.include_details is False

    @pytest.mark.unit
    def test_analysis_request_defaults(self) -> None:
        """AnalysisRequestデフォルト値テスト"""
        # Arrange & Act
        request = AnalysisRequest(file_path="test.java")

        # Assert
        assert request.file_path == "test.java"
        assert request.language is None
        assert request.include_complexity is True
        assert request.include_details is False
        assert request.format_type == "json"

    @pytest.mark.unit
    def test_from_mcp_arguments(self) -> None:
        """MCP引数からの作成テスト"""
        # Arrange
        mcp_args = {
            "file_path": "test.java",
            "language": "java",
            "include_complexity": False,
            "include_details": True,
            "format_type": "table",
        }

        # Act
        request = AnalysisRequest.from_mcp_arguments(mcp_args)

        # Assert
        assert request.file_path == "test.java"
        assert request.language == "java"
        assert request.include_complexity is False
        assert request.include_details is True
        assert request.format_type == "table"


class TestUnifiedAnalysisEngineErrorHandling:
    """統一解析エンジンエラーハンドリングテスト"""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_plugin_analysis_error(self) -> None:
        """プラグイン解析エラーのハンドリング"""
        # Arrange
        engine = UnifiedAnalysisEngine()

        # エラーを発生させるモックプラグインを作成
        class ErrorPlugin:
            def get_language_name(self) -> str:
                return "error_lang"

            def get_file_extensions(self) -> list[str]:
                return [".error"]

            def create_extractor(self):
                return None

            async def analyze_file(self, file_path: str, request: AnalysisRequest):
                raise Exception("Analysis failed")

        engine.register_plugin("error_lang", ErrorPlugin())
        request = AnalysisRequest(file_path="test.error", language="error_lang")

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            await engine.analyze(request)

        assert "Analysis failed" in str(exc_info.value)


class TestMockLanguagePlugin:
    """MockLanguagePluginのテスト"""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_mock_plugin_analysis(self) -> None:
        """モックプラグインの解析テスト"""
        # Arrange
        plugin = MockLanguagePlugin("java")
        request = AnalysisRequest(file_path="test.java", language="java")

        # Act
        result = await plugin.analyze_file("test.java", request)

        # Assert
        assert result.file_path == "test.java"
        assert result.success is True
        assert result.error_message is None
        assert result.analysis_time == 0.1
