#!/usr/bin/env python3
"""
キャッシュ管理ユーティリティ

tree-sitter-analyzerの各種キャッシュを管理し、
テスト実行前にクリアする機能を提供します。
"""

import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)


class CacheManager:
    """
    tree-sitter-analyzerのキャッシュを統合管理するクラス
    """

    def __init__(self, project_root: str | None = None):
        """
        初期化

        Args:
            project_root: プロジェクトルートパス
        """
        self.project_root = project_root
        self.cache_stats = {}

    def clear_all_caches(self) -> dict[str, Any]:
        """
        全てのキャッシュをクリア

        Returns:
            クリア結果の詳細
        """
        results = {
            "cleared_caches": [],
            "failed_caches": [],
            "total_cleared": 0,
            "errors": [],
        }

        # 1. UnifiedAnalysisEngine のキャッシュをクリア
        try:
            self._clear_analysis_engine_cache()
            results["cleared_caches"].append("UnifiedAnalysisEngine")
            results["total_cleared"] += 1
            logger.info("✅ UnifiedAnalysisEngine キャッシュをクリアしました")
        except Exception as e:
            results["failed_caches"].append("UnifiedAnalysisEngine")
            results["errors"].append(f"UnifiedAnalysisEngine: {str(e)}")
            logger.error(f"❌ UnifiedAnalysisEngine キャッシュクリア失敗: {e}")

        # 2. SearchContentTool は廃止済み - キャッシュクリア不要

        # 3. その他のMCPツールキャッシュをクリア
        try:
            self._clear_other_mcp_caches()
            results["cleared_caches"].append("OtherMCPTools")
            results["total_cleared"] += 1
            logger.info("✅ その他のMCPツール キャッシュをクリアしました")
        except Exception as e:
            results["failed_caches"].append("OtherMCPTools")
            results["errors"].append(f"OtherMCPTools: {str(e)}")
            logger.error(f"❌ その他のMCPツール キャッシュクリア失敗: {e}")

        return results

    def _clear_analysis_engine_cache(self) -> None:
        """UnifiedAnalysisEngine のキャッシュをクリア"""
        try:
            # UnifiedAnalysisEngineのインスタンスを取得してキャッシュクリア
            from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine

            # 既存のインスタンスがあればクリア
            engine = get_analysis_engine(self.project_root)
            if hasattr(engine, "clear_cache"):
                engine.clear_cache()

            # シングルトンインスタンスもクリア
            from tree_sitter_analyzer.core.analysis_engine import UnifiedAnalysisEngine

            if hasattr(UnifiedAnalysisEngine, "_instances"):
                for instance in UnifiedAnalysisEngine._instances.values():
                    if hasattr(instance, "clear_cache"):
                        instance.clear_cache()

        except ImportError as e:
            logger.warning(f"UnifiedAnalysisEngine インポート失敗: {e}")
        except Exception as e:
            logger.error(f"UnifiedAnalysisEngine キャッシュクリア中にエラー: {e}")
            raise

    def _clear_other_mcp_caches(self) -> None:
        """その他のMCPツールのキャッシュをクリア"""
        try:
            # 他のツールにキャッシュがある場合はここで処理
            # 現在は特に追加のキャッシュは確認されていないため、プレースホルダー
            pass

        except Exception as e:
            logger.error(f"その他のMCPツール キャッシュクリア中にエラー: {e}")
            raise

    def get_cache_stats(self) -> dict[str, Any]:
        """
        各キャッシュの統計情報を取得

        Returns:
            キャッシュ統計情報
        """
        # search_content キャッシュは廃止済み (SearchContentTool 削除)
        stats = {"analysis_engine": {}, "timestamp": None}

        # UnifiedAnalysisEngine の統計
        try:
            from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine

            engine = get_analysis_engine(self.project_root)
            if hasattr(engine, "get_cache_stats"):
                stats["analysis_engine"] = engine.get_cache_stats()
        except Exception as e:
            stats["analysis_engine"]["error"] = str(e)

        # タイムスタンプを追加
        import datetime

        stats["timestamp"] = datetime.datetime.now().isoformat()

        return stats

    def force_disable_caches(self) -> dict[str, Any]:
        """
        キャッシュを強制的に無効化（テスト用）

        Returns:
            無効化結果
        """
        results = {
            "disabled_caches": [],
            "failed_disables": [],
            "total_disabled": 0,
            "errors": [],
        }

        # SearchContentTool は廃止済み - キャッシュ無効化不要

        return results


def clear_all_caches(project_root: str | None = None) -> dict[str, Any]:
    """
    便利関数：全キャッシュをクリア

    Args:
        project_root: プロジェクトルートパス

    Returns:
        クリア結果
    """
    manager = CacheManager(project_root)
    return manager.clear_all_caches()


def get_cache_status(project_root: str | None = None) -> dict[str, Any]:
    """
    便利関数：キャッシュ状態を取得

    Args:
        project_root: プロジェクトルートパス

    Returns:
        キャッシュ統計情報
    """
    manager = CacheManager(project_root)
    return manager.get_cache_stats()


if __name__ == "__main__":
    # コマンドライン実行時のテスト
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) > 1 and sys.argv[1] == "clear":
        print("🧹 全キャッシュをクリア中...")
        result = clear_all_caches()
        print(f"✅ {result['total_cleared']} 個のキャッシュをクリアしました")
        if result["errors"]:
            print(f"❌ エラー: {result['errors']}")
    else:
        print("📊 キャッシュ状態を確認中...")
        stats = get_cache_status()
        print(f"キャッシュ統計: {stats}")
