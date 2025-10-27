#!/usr/bin/env python3
"""
ログ重複修正のテストケース

LoggerManagerの動作とログ重複防止機能を検証します。
"""

import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.logging_manager import LoggerManager, get_logger_manager
from tree_sitter_analyzer.utils import setup_logger


class TestLoggerManager:
    """LoggerManagerクラスのテスト"""
    
    def setup_method(self):
        """各テストの前に実行される設定"""
        # テスト用にLoggerManagerをリセット
        LoggerManager._instance = None
        LoggerManager._loggers = {}
        LoggerManager._handler_registry = {}
        LoggerManager._initialized = False
        # 環境変数をクリア（他のテストからの漏れを防ぐ）
        os.environ.pop('LOG_LEVEL', None)
    
    def test_singleton_pattern(self):
        """シングルトンパターンの動作テスト"""
        manager1 = LoggerManager()
        manager2 = LoggerManager()
        
        # 同一インスタンスが返されることを確認
        assert manager1 is manager2
        
    def test_thread_safe_singleton(self):
        """スレッドセーフなシングルトン実装のテスト"""
        instances = []
        
        def create_manager():
            instances.append(LoggerManager())
        
        # 複数スレッドでLoggerManagerを作成
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=create_manager)
            threads.append(thread)
            thread.start()
        
        # 全スレッドの完了を待機
        for thread in threads:
            thread.join()
        
        # 全て同一インスタンスであることを確認
        first_instance = instances[0]
        for instance in instances:
            assert instance is first_instance
    
    def test_get_logger_basic(self):
        """基本的なロガー取得のテスト"""
        manager = LoggerManager()
        
        # 基本的なロガー取得
        logger1 = manager.get_logger("test_logger1")
        assert isinstance(logger1, logging.Logger)
        assert logger1.name == "test_logger1"
        
        # 同じ名前での再取得
        logger2 = manager.get_logger("test_logger1")
        assert logger1 is logger2
    
    def test_get_logger_with_level(self):
        """ログレベル指定でのロガー取得テスト"""
        manager = LoggerManager()
        
        # DEBUG レベルでロガー作成
        debug_logger = manager.get_logger("debug_test", "DEBUG")
        assert debug_logger.level == logging.DEBUG
        
        # INFO レベルでロガー作成
        info_logger = manager.get_logger("info_test", logging.INFO)
        assert info_logger.level == logging.INFO
    
    def test_duplicate_handler_prevention(self):
        """重複ハンドラー防止のテスト"""
        manager = LoggerManager()
        
        # 最初のロガー作成
        logger1 = manager.get_logger("test_dup")
        initial_handler_count = len(logger1.handlers)
        
        # 同じ名前でロガー再取得
        logger2 = manager.get_logger("test_dup")
        
        # ハンドラー数が増加していないことを確認
        assert len(logger2.handlers) == initial_handler_count
        assert logger1 is logger2
    
    @patch.dict('os.environ', {
        'TREE_SITTER_ANALYZER_ENABLE_FILE_LOG': 'true',
        'TREE_SITTER_ANALYZER_LOG_DIR': ''
    })
    def test_file_logging_enabled(self):
        """ファイルログ有効化のテスト"""
        manager = LoggerManager()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('tempfile.gettempdir') as mock_tempdir:
                mock_tempdir.return_value = temp_dir
                logger = manager.get_logger("file_test")
                
                # FileHandlerが追加されていることを確認
                file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
                assert len(file_handlers) > 0
                
                # テスト後にファイルハンドラーをクローズしてファイルロックを解除
                for handler in file_handlers:
                    handler.close()
                    logger.removeHandler(handler)
    
    def test_reset_for_testing(self):
        """テスト用リセット機能のテスト"""
        manager = LoggerManager()
        
        # ロガーを作成
        logger1 = manager.get_logger("test_reset1")
        logger2 = manager.get_logger("test_reset2")
        
        # リセット前の状態確認
        assert len(manager._loggers) >= 2
        assert len(manager._handler_registry) >= 2
        
        # リセット実行
        manager.reset_for_testing()
        
        # リセット後の状態確認
        assert len(manager._loggers) == 0
        assert len(manager._handler_registry) == 0


class TestSetupLoggerIntegration:
    """setup_logger関数とLoggerManagerの統合テスト"""
    
    def setup_method(self):
        """各テストの前に実行される設定"""
        # テスト用にLoggerManagerをリセット
        if hasattr(LoggerManager, '_instance') and LoggerManager._instance:
            LoggerManager._instance.reset_for_testing()
        LoggerManager._instance = None
        # 環境変数をクリア（他のテストからの漏れを防ぐ）
        os.environ.pop('LOG_LEVEL', None)
    
    def test_setup_logger_uses_manager(self):
        """setup_logger がLoggerManagerを使用することのテスト"""
        logger1 = setup_logger("integration_test1")
        logger2 = setup_logger("integration_test1")
        
        # 同一インスタンスが返されることを確認
        assert logger1 is logger2
    
    def test_setup_logger_backward_compatibility(self):
        """setup_logger の後方互換性テスト"""
        # 文字列レベル指定
        logger1 = setup_logger("compat_test1", "DEBUG")
        assert logger1.level == logging.DEBUG
        
        # 数値レベル指定
        logger2 = setup_logger("compat_test2", logging.INFO)
        assert logger2.level == logging.INFO
        
        # デフォルト引数
        logger3 = setup_logger()
        assert logger3.name == "tree_sitter_analyzer"
    
    @patch.dict('os.environ', {'LOG_LEVEL': 'DEBUG'})
    def test_environment_variable_precedence(self):
        """環境変数LOG_LEVELの優先順位テスト"""
        logger = setup_logger("env_test", "INFO")
        
        # 環境変数が優先されることを確認
        assert logger.level == logging.DEBUG


class TestLoggerDuplicationPrevention:
    """ログ重複防止の統合テスト"""
    
    def setup_method(self):
        """各テストの前に実行される設定"""
        # テスト用にLoggerManagerをリセット
        if hasattr(LoggerManager, '_instance') and LoggerManager._instance:
            LoggerManager._instance.reset_for_testing()
        LoggerManager._instance = None
        # 環境変数をクリア（他のテストからの漏れを防ぐ）
        os.environ.pop('LOG_LEVEL', None)
    
    def test_no_duplicate_logs_multiple_modules(self):
        """複数モジュールでのログ重複がないことのテスト"""
        # 複数のモジュール名でロガーを作成（実際の使用パターンをシミュレート）
        start_logger = setup_logger("start_mcp_server")
        server_logger = setup_logger("tree_sitter_analyzer.mcp.server")
        tools_logger = setup_logger("tree_sitter_analyzer.mcp.tools.query_tool")
        
        # 全て異なるロガーインスタンスであることを確認
        assert start_logger is not server_logger
        assert server_logger is not tools_logger
        assert start_logger is not tools_logger
        
        # しかし、同じ名前なら同じインスタンス
        start_logger2 = setup_logger("start_mcp_server")
        assert start_logger is start_logger2
    
    def test_handler_count_consistency(self):
        """ハンドラー数の一貫性テスト"""
        logger1 = setup_logger("handler_test")
        initial_count = len(logger1.handlers)
        
        # 複数回同じロガーを取得
        for _ in range(5):
            logger_dup = setup_logger("handler_test")
            assert len(logger_dup.handlers) == initial_count
    
    def test_performance_logger_unification(self):
        """パフォーマンスロガーの統一テスト"""
        from tree_sitter_analyzer.utils import create_performance_logger, setup_performance_logger
        
        # 両方の関数で同じ名前のロガーを作成
        perf1 = create_performance_logger("perf_test")
        perf2 = setup_performance_logger()
        
        # 異なる名前なので異なるインスタンス
        assert perf1 is not perf2
        
        # しかし、LoggerManagerが管理していることを確認
        manager = get_logger_manager()
        assert "perf_test.performance" in manager._loggers


class TestSafeStreamHandler:
    """SafeStreamHandlerのテスト"""
    
    def test_safe_emit_with_closed_stream(self):
        """クローズされたストリームでの安全な出力テスト"""
        from tree_sitter_analyzer.logging_manager import SafeStreamHandler
        
        # モックストリームを作成
        mock_stream = Mock()
        mock_stream.closed = True
        
        handler = SafeStreamHandler(mock_stream)
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="test message", args=(), exc_info=None
        )
        
        # 例外が発生しないことを確認
        try:
            handler.emit(record)
        except Exception as e:
            pytest.fail(f"SafeStreamHandler should not raise exception: {e}")
    
    def test_safe_emit_with_invalid_stream(self):
        """無効なストリームでの安全な出力テスト"""
        from tree_sitter_analyzer.logging_manager import SafeStreamHandler
        
        # writeメソッドがないモックストリーム
        mock_stream = Mock()
        del mock_stream.write
        
        handler = SafeStreamHandler(mock_stream)
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="test message", args=(), exc_info=None
        )
        
        # 例外が発生しないことを確認
        try:
            handler.emit(record)
        except Exception as e:
            pytest.fail(f"SafeStreamHandler should not raise exception: {e}")


class TestPerformanceImpact:
    """性能影響のテスト"""
    
    def setup_method(self):
        """各テストの前に実行される設定"""
        # テスト用にLoggerManagerをリセット
        if hasattr(LoggerManager, '_instance') and LoggerManager._instance:
            LoggerManager._instance.reset_for_testing()
        LoggerManager._instance = None
        # 環境変数をクリア（他のテストからの漏れを防ぐ）
        os.environ.pop('LOG_LEVEL', None)
    
    def test_logger_creation_performance(self):
        """ロガー作成の性能テスト"""
        import time
        
        start_time = time.time()
        
        # 大量のロガーを作成
        loggers = []
        for i in range(100):
            logger = setup_logger(f"perf_test_{i}")
            loggers.append(logger)
        
        creation_time = time.time() - start_time
        
        # 作成時間が合理的な範囲内であることを確認（1秒以内）
        assert creation_time < 1.0
        
        # 全てのロガーが適切に作成されていることを確認
        assert len(loggers) == 100
        assert all(isinstance(logger, logging.Logger) for logger in loggers)
    
    def test_logger_retrieval_performance(self):
        """ロガー取得の性能テスト"""
        import time
        
        # 事前にロガーを作成
        logger_name = "retrieval_test"
        setup_logger(logger_name)
        
        start_time = time.time()
        
        # 同じロガーを大量に取得
        for _ in range(1000):
            logger = setup_logger(logger_name)
        
        retrieval_time = time.time() - start_time
        
        # 取得時間が合理的な範囲内であることを確認（0.1秒以内）
        assert retrieval_time < 0.1


if __name__ == "__main__":
    # テスト実行
    pytest.main([__file__, "-v"])