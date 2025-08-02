#!/usr/bin/env python3
"""
CLI Adapter for tree-sitter-analyzer

既存のCLI APIとの互換性を保ちながら、新しい統一解析エンジンを使用するアダプター。

Roo Code規約準拠:
- 型ヒント: 全関数に型ヒント必須
- MCPログ: 各ステップでログ出力
- docstring: Google Style docstring
- エラーハンドリング: 適切な例外処理
- パフォーマンス: 統一エンジンによる最適化
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from ..core.analysis_engine import AnalysisRequest, UnifiedAnalysisEngine
from ..models import AnalysisResult

logger = logging.getLogger(__name__)


class CLIAdapter:
    """
    CLI用アダプター

    既存のCLI APIとの互換性を保ちながら、新しい統一解析エンジンを使用します。
    同期APIを提供し、内部的に非同期エンジンを呼び出します。

    Features:
        - 既存API互換性の維持
        - 統一解析エンジンの活用
        - 同期/非同期変換
        - パフォーマンス監視
        - エラーハンドリング

    Example:
        >>> adapter = CLIAdapter()
        >>> result = adapter.analyze_file("example.java")
        >>> print(result.classes)
    """

    def __init__(self) -> None:
        """
        CLIアダプターを初期化

        Raises:
            Exception: 統一解析エンジンの初期化に失敗した場合
        """
        try:
            self._engine = UnifiedAnalysisEngine()
            logger.info("CLIAdapter initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize CLIAdapter: {e}")
            raise

    def analyze_file(self, file_path: str, **kwargs: Any) -> AnalysisResult:
        """
        ファイルを解析（同期版）

        既存のCLI APIとの互換性を保つため、同期インターフェースを提供します。
        内部的には統一解析エンジンの非同期メソッドを呼び出します。

        Args:
            file_path: 解析対象ファイルのパス
            **kwargs: 解析オプション
                - language: 言語指定（自動検出も可能）
                - include_complexity: 複雑度計算を含める
                - include_details: 詳細情報を含める
                - format_type: 出力形式（"standard", "structure", "summary"）

        Returns:
            AnalysisResult: 解析結果

        Raises:
            ValueError: 無効なファイルパスの場合
            FileNotFoundError: ファイルが存在しない場合
            UnsupportedLanguageError: サポートされていない言語の場合

        Example:
            >>> adapter = CLIAdapter()
            >>> result = adapter.analyze_file("example.java", include_complexity=True)
            >>> print(f"Classes: {len(result.classes)}")
        """
        start_time = time.time()

        # 入力検証
        if not file_path or not file_path.strip():
            raise ValueError("File path cannot be empty")

        # ファイル存在チェック
        if not Path(file_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            # AnalysisRequestを作成
            request = AnalysisRequest(
                file_path=file_path,
                language=kwargs.get("language"),
                include_complexity=kwargs.get("include_complexity", False),
                include_details=kwargs.get("include_details", True),
                format_type=kwargs.get("format_type", "standard"),
            )

            # 非同期エンジンを同期的に実行
            result = asyncio.run(self._engine.analyze(request))

            # パフォーマンスログ
            elapsed_time = time.time() - start_time
            logger.info(f"CLI analysis completed: {file_path} in {elapsed_time:.3f}s")

            return result

        except Exception as e:
            logger.error(f"CLI analysis failed for {file_path}: {e}")
            raise

    def analyze_structure(self, file_path: str, **kwargs: Any) -> dict[str, Any]:
        """
        構造解析（既存API互換）

        既存のCLI APIとの互換性を保つため、構造情報を辞書形式で返します。

        Args:
            file_path: 解析対象ファイルのパス
            **kwargs: 解析オプション

        Returns:
            Dict[str, Any]: 構造情報の辞書
                - file_path: ファイルパス
                - classes: クラス情報のリスト
                - methods: メソッド情報のリスト
                - fields: フィールド情報のリスト
                - imports: インポート情報のリスト

        Example:
            >>> adapter = CLIAdapter()
            >>> structure = adapter.analyze_structure("example.java")
            >>> print(structure["classes"])
        """
        # 詳細情報を含めて解析
        kwargs["include_details"] = True
        kwargs["format_type"] = "structure"

        result = self.analyze_file(file_path, **kwargs)

        # 構造情報を辞書形式に変換
        return {
            "file_path": result.file_path,
            "language": result.language,
            "package": result.package,
            "imports": [
                {"name": imp.name, "type": str(type(imp).__name__)}
                for imp in result.imports
            ],
            "classes": [
                {"name": cls.name, "type": str(type(cls).__name__)}
                for cls in result.classes
            ],
            "methods": [
                {"name": method.name, "type": str(type(method).__name__)}
                for method in result.methods
            ],
            "fields": [
                {"name": field.name, "type": str(type(field).__name__)}
                for field in result.fields
            ],
            "annotations": [
                {
                    "name": getattr(ann, "name", str(ann)),
                    "type": str(type(ann).__name__),
                }
                for ann in getattr(result, "annotations", [])
            ],
            "analysis_time": result.analysis_time,
            "elements": [
                {"name": elem.name, "type": str(type(elem).__name__)}
                for elem in result.elements
            ],
            "success": result.success,
        }

    def analyze_batch(
        self, file_paths: list[str], **kwargs: Any
    ) -> list[AnalysisResult]:
        """
        複数ファイルの一括解析

        Args:
            file_paths: 解析対象ファイルパスのリスト
            **kwargs: 解析オプション

        Returns:
            list[AnalysisResult]: 解析結果のリスト

        Example:
            >>> adapter = CLIAdapter()
            >>> results = adapter.analyze_batch(["file1.java", "file2.java"])
            >>> print(f"Analyzed {len(results)} files")
        """
        results = []

        for file_path in file_paths:
            try:
                result = self.analyze_file(file_path, **kwargs)
                results.append(result)
            except Exception as e:
                logger.warning(f"Failed to analyze {file_path}: {e}")
                # エラーの場合も結果に含める（失敗情報付き）
                error_result = AnalysisResult(
                    file_path=file_path,
                    package=None,
                    imports=[],
                    classes=[],
                    methods=[],
                    fields=[],
                    annotations=[],
                    analysis_time=0.0,
                    success=False,
                    error_message=str(e),
                )
                results.append(error_result)

        return results

    def get_supported_languages(self) -> list[str]:
        """
        サポートされている言語のリストを取得

        Returns:
            list[str]: サポート言語のリスト

        Example:
            >>> adapter = CLIAdapter()
            >>> languages = adapter.get_supported_languages()
            >>> print(languages)
        """
        return self._engine.get_supported_languages()

    def clear_cache(self) -> None:
        """
        キャッシュをクリア

        Example:
            >>> adapter = CLIAdapter()
            >>> adapter.clear_cache()
        """
        self._engine.clear_cache()
        logger.info("CLI adapter cache cleared")

    def get_cache_stats(self) -> dict[str, Any]:
        """
        キャッシュ統計情報を取得

        Returns:
            Dict[str, Any]: キャッシュ統計情報

        Example:
            >>> adapter = CLIAdapter()
            >>> stats = adapter.get_cache_stats()
            >>> print(f"Cache hit rate: {stats['hit_rate']:.2%}")
        """
        return self._engine.get_cache_stats()

    def validate_file(self, file_path: str) -> bool:
        """
        ファイルが解析可能かどうかを検証

        Args:
            file_path: 検証対象ファイルのパス

        Returns:
            bool: 解析可能な場合True

        Example:
            >>> adapter = CLIAdapter()
            >>> if adapter.validate_file("example.java"):
            ...     result = adapter.analyze_file("example.java")
        """
        try:
            # ファイル存在チェック
            if not Path(file_path).exists():
                return False

            # 言語サポートチェック
            supported_languages = self.get_supported_languages()
            file_extension = Path(file_path).suffix.lower()

            # 拡張子から言語を推定
            extension_map = {
                ".java": "java",
                ".py": "python",
                ".js": "javascript",
                ".ts": "typescript",
                ".cpp": "cpp",
                ".c": "c",
                ".cs": "csharp",
                ".go": "go",
                ".rs": "rust",
                ".php": "php",
                ".rb": "ruby",
            }

            language = extension_map.get(file_extension)
            return language in supported_languages if language else False

        except Exception as e:
            logger.warning(f"File validation failed for {file_path}: {e}")
            return False

    def get_engine_info(self) -> dict[str, Any]:
        """
        エンジン情報を取得

        Returns:
            Dict[str, Any]: エンジン情報

        Example:
            >>> adapter = CLIAdapter()
            >>> info = adapter.get_engine_info()
            >>> print(f"Engine version: {info['version']}")
        """
        return {
            "adapter_type": "CLI",
            "engine_type": "UnifiedAnalysisEngine",
            "supported_languages": self.get_supported_languages(),
            "cache_enabled": True,
            "async_support": True,
        }


# Legacy AdvancedAnalyzerAdapter removed - use UnifiedAnalysisEngine directly


def get_analysis_engine() -> "UnifiedAnalysisEngine":
    """Get analysis engine instance for testing compatibility."""
    from ..core.analysis_engine import UnifiedAnalysisEngine

    return UnifiedAnalysisEngine()
