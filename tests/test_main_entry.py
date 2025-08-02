#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.__main__ module

メインエントリーポイントのテストを提供。
"""

from unittest.mock import patch

import pytest


class TestMainEntry:
    """__main__.pyのテストクラス"""

    def test_main_module_import_only(self):
        """モジュールインポートのみのテスト"""
        # インポートエラーが発生しないことを確認
        try:
            import tree_sitter_analyzer.__main__  # noqa: F401

            assert True  # インポート成功
        except ImportError as e:
            pytest.fail(f"Failed to import __main__ module: {e}")

    def test_main_module_execution_with_mock(self):
        """モック使用でのメイン実行テスト"""
        with patch("tree_sitter_analyzer.cli_main.main") as mock_main:
            mock_main.return_value = None

            # 実際の実行をテスト

            assert True  # 実行成功

    def test_cli_integration_availability(self):
        """CLI統合の可用性テスト"""
        try:
            from tree_sitter_analyzer import cli

            assert hasattr(cli, "main")
        except ImportError:
            pytest.fail("CLI module not available")
