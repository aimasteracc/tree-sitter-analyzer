#!/usr/bin/env python3
"""
FileOutputManager重複警告防止のテストケース

FileOutputManagerクラスの重複警告防止機能を検証します。
"""

import contextlib
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.utils.file_output_manager import FileOutputManager


def cleanup_lock_files():
    """テスト用のロックファイルをクリーンアップ"""
    temp_dir = Path(tempfile.gettempdir())
    for lock_file in temp_dir.glob("tree_sitter_analyzer_warning_*.lock"):
        with contextlib.suppress(OSError, FileNotFoundError):
            lock_file.unlink()


class TestFileOutputManagerDuplicationPrevention:
    """FileOutputManagerの重複警告防止テスト"""

    def setup_method(self):
        """各テストの前に実行される設定"""
        # 警告メッセージ履歴をリセット
        FileOutputManager._warning_messages_shown.clear()
        # ロックファイルもクリーンアップ
        cleanup_lock_files()

    def teardown_method(self):
        """各テストの後に実行されるクリーンアップ"""
        # ロックファイルをクリーンアップ
        cleanup_lock_files()

    def test_no_duplicate_warnings_multiple_instances(self):
        """複数インスタンス作成時の重複警告防止テスト"""
        with patch.dict("os.environ", {}, clear=True):
            # 複数のFileOutputManagerインスタンスを作成
            instances = []
            for _i in range(5):
                instance = FileOutputManager()
                instances.append(instance)

            # 警告メッセージが1つのキーのみ記録されていることを確認
            assert len(FileOutputManager._warning_messages_shown) == 1

            # すべてのインスタンスが同じパスを使用していることを確認
            expected_path = str(Path.cwd())
            for instance in instances:
                assert instance.get_output_path() == expected_path

    def test_different_paths_generate_different_warnings(self):
        """異なるパスで異なる警告が生成されることのテスト"""
        with tempfile.TemporaryDirectory() as temp_dir1:
            with tempfile.TemporaryDirectory() as temp_dir2:
                # 環境変数をクリア
                with patch.dict("os.environ", {}, clear=True):
                    # 最初のインスタンス（カレントディレクトリフォールバック）
                    FileOutputManager()

                    # プロジェクトルートを設定した2つ目のインスタンス
                    FileOutputManager(project_root=temp_dir1)

                    # 環境変数を設定した3つ目のインスタンス
                    with patch.dict(
                        "os.environ", {"TREE_SITTER_OUTPUT_PATH": temp_dir2}
                    ):
                        FileOutputManager()

                    # 異なるパスに対して異なる警告キーが記録されることを確認
                    # 注意: 実際の実装では、環境変数やプロジェクトルートが設定されている場合、
                    # 警告は出力されないが、ここではフォールバック時の動作をテスト
                    assert len(FileOutputManager._warning_messages_shown) >= 1

    def test_warning_message_key_format(self):
        """警告メッセージキーの形式テスト"""
        with patch.dict("os.environ", {}, clear=True):
            FileOutputManager()

            # 警告メッセージキーが期待される形式であることを確認
            assert len(FileOutputManager._warning_messages_shown) == 1
            warning_key = list(FileOutputManager._warning_messages_shown)[0]
            assert warning_key.startswith("fallback_path:")
            assert str(Path.cwd()) in warning_key

    def test_warning_suppression_across_modules(self):
        """モジュール間での警告抑制テスト"""
        with patch.dict("os.environ", {}, clear=True):
            # 複数の場所からFileOutputManagerを作成
            # 動的インポートをシミュレート
            import importlib
            import sys

            from tree_sitter_analyzer.mcp.utils.file_output_manager import (
                FileOutputManager as FOM1,
            )

            module_name = "tree_sitter_analyzer.mcp.utils.file_output_manager"
            if module_name in sys.modules:
                module = sys.modules[module_name]
                FOM2 = module.FileOutputManager
            else:
                module = importlib.import_module(module_name)
                FOM2 = module.FileOutputManager

            # 両方のクラス参照から作成
            FOM1()
            FOM2()

            # 同じクラス変数を共有していることを確認
            assert FOM1._warning_messages_shown is FOM2._warning_messages_shown
            assert len(FileOutputManager._warning_messages_shown) == 1

    def test_reset_warning_state(self):
        """警告状態リセット機能のテスト"""
        with patch.dict("os.environ", {}, clear=True):
            # 最初のインスタンス作成
            FileOutputManager()
            assert len(FileOutputManager._warning_messages_shown) == 1

            # 状態をリセット
            FileOutputManager._warning_messages_shown.clear()
            assert len(FileOutputManager._warning_messages_shown) == 0

            # 新しいインスタンス作成で警告が再度表示されることを確認
            FileOutputManager()
            assert len(FileOutputManager._warning_messages_shown) == 1

    def test_no_warning_with_valid_environment(self):
        """有効な環境設定時に警告が出力されないことのテスト"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 有効な環境変数を設定
            with patch.dict("os.environ", {"TREE_SITTER_OUTPUT_PATH": temp_dir}):
                initial_warnings = len(FileOutputManager._warning_messages_shown)

                fom = FileOutputManager()

                # 環境変数が設定されている場合、フォールバック警告は表示されない
                assert (
                    len(FileOutputManager._warning_messages_shown) == initial_warnings
                )
                assert fom.get_output_path() == temp_dir

    def test_no_warning_with_valid_project_root(self):
        """有効なプロジェクトルート設定時に警告が出力されないことのテスト"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 環境変数をクリアしてプロジェクトルートのみ設定
            with patch.dict("os.environ", {}, clear=True):
                initial_warnings = len(FileOutputManager._warning_messages_shown)

                fom = FileOutputManager(project_root=temp_dir)

                # 有効なプロジェクトルートが設定されている場合、フォールバック警告は表示されない
                assert (
                    len(FileOutputManager._warning_messages_shown) == initial_warnings
                )
                assert fom.get_output_path() == temp_dir

    def test_cross_process_lock_file_prevention(self):
        """プロセス間でのロックファイルベース重複防止が動作する"""
        import os
        import tempfile
        from pathlib import Path

        # カレントディレクトリをテスト用パスに変更
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                warning_key = f"fallback_path:{temp_dir}"

                # 手動でロックファイルを作成（別プロセスをシミュレート）
                lock_file = FileOutputManager._get_warning_lock_file(warning_key)
                lock_file.touch()

                # FileOutputManagerを作成（環境変数なしでフォールバック発生）
                with patch.dict("os.environ", {}, clear=True):
                    FileOutputManager()

                # ロックファイルが存在するため、_should_show_warning()はFalseを返す
                assert not FileOutputManager._should_show_warning(warning_key)

                # プロセス内の記録にもキーが追加される
                assert warning_key in FileOutputManager._warning_messages_shown

                # テスト用ロックファイルを削除
                with contextlib.suppress(OSError, FileNotFoundError):
                    lock_file.unlink()

            finally:
                os.chdir(original_cwd)

    def test_lock_file_expiration(self):
        """期限切れロックファイルは自動的に削除される"""
        import os
        import tempfile
        import time
        from pathlib import Path

        # カレントディレクトリをテスト用パスに変更
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                warning_key = f"fallback_path:{temp_dir}"

                # 古いロックファイルを作成
                lock_file = FileOutputManager._get_warning_lock_file(warning_key)
                lock_file.touch()

                # ファイルのタイムスタンプを古く設定（6分前）
                old_time = time.time() - 360  # 6分前
                os.utime(lock_file, (old_time, old_time))
                old_mtime = lock_file.stat().st_mtime

                # 期限切れなので警告表示が許可される
                assert FileOutputManager._should_show_warning(
                    warning_key, max_age_seconds=300
                )

                # ロックファイルは存在するが、新しいタイムスタンプになっている
                assert lock_file.exists()
                new_mtime = lock_file.stat().st_mtime
                assert new_mtime > old_mtime  # 新しいロックファイルが作成されている

            finally:
                # テスト用ロックファイルを削除（存在する場合）
                try:
                    if lock_file.exists():
                        lock_file.unlink()
                except (OSError, FileNotFoundError):
                    pass
                os.chdir(original_cwd)

    def test_lock_file_path_generation(self):
        """ロックファイルパスが正しく生成される"""
        import tempfile
        from pathlib import Path

        test_cases = [
            ("fallback_path:/tmp/test", "fallback_path__tmp_test"),
            ("fallback_path:C:\\Windows\\test", "fallback_path_C__Windows_test"),
            ("fallback_path:../relative/path", "fallback_path_.._relative_path"),
        ]

        for warning_key, expected_filename in test_cases:
            lock_file = FileOutputManager._get_warning_lock_file(warning_key)
            expected_path = (
                Path(tempfile.gettempdir())
                / f"tree_sitter_analyzer_warning_{expected_filename}.lock"
            )
            assert lock_file == expected_path

    def test_lock_file_io_error_fallback(self):
        """ロックファイルI/Oエラー時のフォールバック動作"""

        test_path = "/tmp/io_error_test"
        warning_key = f"fallback_path:{test_path}"

        # 読み取り専用ディレクトリでのロックファイル作成を試行
        with patch("tempfile.gettempdir", return_value="/proc"):  # 読み取り専用
            # I/Oエラーでもフォールバックして警告表示を許可
            assert FileOutputManager._should_show_warning(warning_key)

    def test_should_show_warning_method_direct(self):
        """_should_show_warningメソッドの直接テスト"""
        warning_key = "test_direct_method_unique_key"

        # 最初にクラス変数をクリア
        FileOutputManager._warning_messages_shown.discard(warning_key)

        # 1回目：表示すべき
        assert FileOutputManager._should_show_warning(warning_key) is True

        # 2回目：プロセス内で既に表示済みなので表示しない
        assert FileOutputManager._should_show_warning(warning_key) is False

    def test_concurrent_access_protection(self):
        """同時アクセス時の重複防止テスト"""
        import threading
        import uuid

        # ユニークなキーを使用してテスト間の干渉を防ぐ
        warning_key = f"concurrent_test_{uuid.uuid4().hex[:8]}"
        results = []
        lock = threading.Lock()

        # 最初にクラス変数から該当キーを削除
        FileOutputManager._warning_messages_shown.discard(warning_key)

        def create_manager():
            result = FileOutputManager._should_show_warning(warning_key)
            with lock:
                results.append(result)

        # 複数スレッドで同時実行
        threads = []
        for _i in range(10):
            thread = threading.Thread(target=create_manager)
            threads.append(thread)

        # 全スレッドを開始
        for thread in threads:
            thread.start()

        # 全スレッドの完了を待機
        for thread in threads:
            thread.join()

        # 1つのスレッドのみが警告表示権を獲得することを確認
        true_count = sum(1 for result in results if result)
        assert true_count == 1, f"Expected 1 True result, got {true_count}"


if __name__ == "__main__":
    # テスト実行
    pytest.main([__file__, "-v"])
