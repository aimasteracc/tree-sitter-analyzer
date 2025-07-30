#!/usr/bin/env python3
"""
Global test configuration for tree-sitter-analyzer

テスト実行時の警告とログを制御し、クリーンな出力を確保します。
"""

import logging
import warnings
import pytest
import asyncio
import gc
import os


@pytest.fixture(autouse=True)
def configure_logging():
    """
    テスト用ログ設定の自動適用
    
    全テスト実行前にログレベルを調整し、
    不要なログ出力を抑制します。
    """
    # メインロガーの設定
    root_logger = logging.getLogger()
    original_level = root_logger.level
    root_logger.setLevel(logging.ERROR)
    
    # アプリケーション固有のロガー設定
    app_logger = logging.getLogger("tree_sitter_analyzer")
    app_original_level = app_logger.level
    app_logger.setLevel(logging.ERROR)
    
    # パフォーマンスロガーの設定
    perf_logger = logging.getLogger("tree_sitter_analyzer.performance")
    perf_original_level = perf_logger.level
    perf_logger.setLevel(logging.ERROR)
    
    yield
    
    # テスト後にレベルを復元
    root_logger.setLevel(original_level)
    app_logger.setLevel(app_original_level)
    perf_logger.setLevel(perf_original_level)


@pytest.fixture(autouse=True)
def cleanup_event_loops():
    """
    Event loop ResourceWarning の根本解決
    
    テスト後に未クローズのイベントループを適切にクリーンアップ
    """
    yield
    
    # 明示的なイベントループクリーンアップ
    try:
        # 現在のイベントループを取得してクローズ
        try:
            loop = asyncio.get_running_loop()
            if loop and not loop.is_closed():
                # 実行中のタスクをキャンセル
                pending_tasks = [task for task in asyncio.all_tasks(loop) if not task.done()]
                for task in pending_tasks:
                    task.cancel()
                
                # タスクの完了を待機
                if pending_tasks:
                    loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
        except RuntimeError:
            # イベントループが実行中でない場合は無視
            pass
        
        # すべてのイベントループを取得してクローズ
        try:
            # 既存のループを取得（新規作成しない）
            try:
                # Python 3.12+対応: DeprecationWarningを避けるため警告を抑制
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    try:
                        loop = asyncio.get_event_loop_policy().get_event_loop()
                    except RuntimeError:
                        # イベントループが存在しない場合
                        loop = None
                if loop and not loop.is_closed():
                    # 全ての未完了タスクをキャンセル
                    pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
                    for task in pending:
                        task.cancel()
                    
                    # タスクをクリーンアップ
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    
                    # ループを明示的にクローズ
                    loop.close()
            except (RuntimeError, AttributeError):
                pass
                
            # イベントループポリシーをリセット
            try:
                if hasattr(asyncio, 'WindowsProactorEventLoopPolicy') and os.name == 'nt':
                    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                else:
                    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
                asyncio.set_event_loop(None)
            except Exception:
                pass
            
        except Exception:
            # エラーが発生しても継続
            pass
        
        # ガベージコレクションを強制実行
        gc.collect()
        
    except Exception:
        # クリーンアップエラーは無視（テストの継続を優先）
        pass


# Disabled warning suppression - let's fix the root causes instead
# @pytest.fixture(autouse=True)
# def suppress_warnings():
#     """
#     警告の抑制設定
#     
#     テスト実行中の不要な警告を抑制します。
#     """
#     # 各種警告を抑制
#     warnings.filterwarnings("ignore", category=DeprecationWarning)
#     warnings.filterwarnings("ignore", category=PendingDeprecationWarning)
#     warnings.filterwarnings("ignore", category=FutureWarning)
#     warnings.filterwarnings("ignore", category=UserWarning)
#     warnings.filterwarnings("ignore", category=ResourceWarning)
#     
#     # pytest固有の警告
#     try:
#         import pytest
#         warnings.filterwarnings("ignore", category=pytest.PytestMockWarning)
#         warnings.filterwarnings("ignore", category=pytest.PytestRemovedIn9Warning)
#     except (ImportError, AttributeError):
#         pass
#     
#     # asyncio固有の警告
#     warnings.filterwarnings("ignore", message=".*unclosed event loop.*", category=ResourceWarning)
#     warnings.filterwarnings("ignore", message=".*Enable tracemalloc.*", category=ResourceWarning)
#     
#     yield


# pytest-asyncio設定
pytest_plugins = ["pytest_asyncio"] 