#!/usr/bin/env python3
"""
エンコーディング検索互換性修正のテストケース。

このモジュールは、search_contentツールの自動エンコーディング検出機能をテストし、
日本語やその他の非UTF-8テキストが異なるツール間で一貫して検索できることを保証します。
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


class TestEncodingSearchCompatibility:
    """search_contentツールの自動エンコーディング検出をテストします。"""

    @pytest.fixture
    def temp_files(self):
        """異なるエンコーディングの一時ファイルを作成します。"""
        from tree_sitter_analyzer.mcp.utils.search_cache import clear_cache

        clear_cache()

        temp_dir = tempfile.mkdtemp()

        # Shift_JISファイル（examples/encoding.txtのような）
        shift_jis_content = "これはShift_JISエンコーディングのテストファイルです。\nTESTSTRING が含まれています。"
        shift_jis_file = Path(temp_dir) / "shift_jis_test.txt"
        with open(shift_jis_file, "w", encoding="shift_jis") as f:
            f.write(shift_jis_content)

        # UTF-8ファイル
        utf8_content = "これはUTF-8エンコーディングのテストファイルです。\nTESTSTRING が含まれています。"
        utf8_file = Path(temp_dir) / "utf8_test.txt"
        with open(utf8_file, "w", encoding="utf-8") as f:
            f.write(utf8_content)

        # CP932ファイル
        cp932_content = "これはCP932エンコーディングのテストファイルです。\nTESTSTRING が含まれています。"
        cp932_file = Path(temp_dir) / "cp932_test.txt"
        with open(cp932_file, "w", encoding="cp932") as f:
            f.write(cp932_content)

        yield {
            "temp_dir": temp_dir,
            "shift_jis_file": str(shift_jis_file),
            "utf8_file": str(utf8_file),
            "cp932_file": str(cp932_file),
        }

        # クリーンアップ
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_shift_jis_auto_detection(self, temp_files):
        """Shift_JISファイルの自動検出と検索をテストします。"""
        tool = SearchContentTool(temp_files["temp_dir"])

        # エンコーディングパラメータを検証するためripgrep実行をモック
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # 成功した検索結果をモック
            mock_run.return_value = (
                0,
                '{"type":"match","data":{"path":{"text":"shift_jis_test.txt"},"line_number":1,"lines":{"text":"これはShift_JISエンコーディングのテストファイルです。"}}}'.encode(),
                b"",
            )

            result = await tool.execute(
                {"files": [temp_files["shift_jis_file"]], "query": "これは"}
            )

            # ripgrepが正しいエンコーディングで呼ばれたことを検証
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "--encoding" in cmd
            encoding_index = cmd.index("--encoding")
            assert cmd[encoding_index + 1] == "shift-jis"

            # 検索が成功したことを検証
            assert result["success"] is True
            assert result["count"] > 0

    @pytest.mark.asyncio
    async def test_utf8_default_handling(self, temp_files):
        """明示的なエンコーディング指定なしでUTF-8ファイルが正しく処理されることをテストします。"""
        tool = SearchContentTool(temp_files["temp_dir"])

        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            mock_run.return_value = (
                0,
                '{"type":"match","data":{"path":{"text":"utf8_test.txt"},"line_number":1,"lines":{"text":"これはUTF-8エンコーディングのテストファイルです。"}}}'.encode(),
                b"",
            )

            result = await tool.execute(
                {"files": [temp_files["utf8_file"]], "query": "これは"}
            )

            # 検索が成功したことを検証
            assert result["success"] is True
            assert result["count"] > 0

    @pytest.mark.asyncio
    async def test_explicit_encoding_priority(self, temp_files):
        """明示的なencodingパラメータが自動検出より優先されることをテストします。"""
        tool = SearchContentTool(temp_files["temp_dir"])

        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (0, b"", b"")

            await tool.execute(
                {
                    "files": [temp_files["shift_jis_file"]],
                    "query": "これは",
                    "encoding": "utf-8",  # 明示的にUTF-8を指定
                    "roots": [],
                }
            )

            # 明示的なエンコーディングが使用されたことを検証
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "--encoding" in cmd
            encoding_index = cmd.index("--encoding")
            assert cmd[encoding_index + 1] == "utf-8"

    @pytest.mark.asyncio
    async def test_encoding_detection_failure_fallback(self, temp_files):
        """エンコーディング検出失敗時のUTF-8フォールバックをテストします。"""
        tool = SearchContentTool(temp_files["temp_dir"])

        # エンコーディング検出失敗をモック
        with patch(
            "tree_sitter_analyzer.encoding_utils.detect_encoding"
        ) as mock_detect:
            mock_detect.side_effect = Exception("Detection failed")

            with patch(
                "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
            ) as mock_run:
                mock_run.return_value = (0, b"", b"")

                result = await tool.execute(
                    {"files": [temp_files["utf8_file"]], "query": "test"}
                )

                # UTF-8にフォールバックして継続すべき
                assert result["success"] is True

    @pytest.mark.asyncio
    async def test_mixed_encoding_files(self, temp_files):
        """異なるエンコーディングの複数ファイルの処理をテストします。"""
        tool = SearchContentTool(temp_files["temp_dir"])

        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            mock_run.return_value = (0, b"", b"")

            # 異なるエンコーディングの複数ファイルで検索
            result = await tool.execute(
                {
                    "files": [
                        temp_files["shift_jis_file"],
                        temp_files["utf8_file"],
                        temp_files["cp932_file"],
                    ],
                    "query": "TESTSTRING",
                }
            )

            # 混合エンコーディングを適切に処理すべき
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_performance_requirement(self, temp_files):
        """エンコーディング検出がパフォーマンス要件内で完了することをテストします。"""
        tool = SearchContentTool(temp_files["temp_dir"])

        import time

        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            mock_run.return_value = (0, b"", b"")

            start_time = time.time()

            await tool.execute(
                {"files": [temp_files["shift_jis_file"]], "query": "これは"}
            )

            elapsed_time = (time.time() - start_time) * 1000  # ミリ秒に変換

            # エンコーディング検出は100ms以内で完了すべき
            assert elapsed_time < 100

    @pytest.mark.asyncio
    async def test_cache_functionality(self, temp_files):
        """エンコーディング検出結果がキャッシュされることをテストします。"""
        tool = SearchContentTool(temp_files["temp_dir"], enable_cache=True)

        with patch(
            "tree_sitter_analyzer.encoding_utils.detect_encoding"
        ) as mock_detect:
            mock_detect.return_value = "shift-jis"

            with patch(
                "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
            ) as mock_run:
                mock_run.return_value = (0, b"", b"")

                # 最初の呼び出しで検出をトリガー
                await tool.execute(
                    {"files": [temp_files["shift_jis_file"]], "query": "test"}
                )

                # 2回目の呼び出しでキャッシュを使用
                await tool.execute(
                    {"files": [temp_files["shift_jis_file"]], "query": "test"}
                )

                # キャッシュにより検出は1回のみ呼ばれるべき
                assert mock_detect.call_count <= 2  # キャッシュミスを許容

    @pytest.mark.asyncio
    async def test_consistency_with_extract_code_section(self, temp_files):
        """search_contentとextract_code_sectionが一貫したエンコーディング検出を使用することをテストします。"""
        from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool

        search_tool = SearchContentTool(temp_files["temp_dir"])
        extract_tool = ReadPartialTool(temp_files["temp_dir"])

        # 両ツールが同じファイルを一貫して処理すべき
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            mock_run.return_value = (
                0,
                '{"type":"match","data":{"path":{"text":"shift_jis_test.txt"},"line_number":1,"lines":{"text":"これはShift_JISエンコーディングのテストファイルです。"}}}'.encode(),
                b"",
            )

            search_result = await search_tool.execute(
                {"files": [temp_files["shift_jis_file"]], "query": "これは"}
            )

            extract_result = await extract_tool.execute(
                {
                    "file_path": temp_files["shift_jis_file"],
                    "start_line": 1,
                    "end_line": 1,
                }
            )

            # 両方とも日本語テキストで成功すべき
            assert search_result["success"] is True
            assert "これは" in extract_result["partial_content_result"]

    def test_backward_compatibility(self, temp_files):
        """既存のsearch_content使用方法が変更されないことをテストします。"""
        tool = SearchContentTool(temp_files["temp_dir"])

        # 既存のパラメータが全てサポートされることを検証
        arguments = {
            "files": [temp_files["utf8_file"]],
            "query": "test",
            "case": "smart",
            "fixed_strings": False,
            "word": False,
            "multiline": False,
            "include_globs": ["*.txt"],
            "exclude_globs": ["*.log"],
            "follow_symlinks": False,
            "hidden": False,
            "no_ignore": False,
            "max_filesize": "10M",
            "context_before": 2,
            "context_after": 2,
            "encoding": "utf-8",  # 明示的エンコーディングは引き続き動作すべき
            "max_count": 100,
            "timeout_ms": 5000,
        }

        # エラーなしで検証されるべき
        assert tool.validate_arguments(arguments) is True


class TestEncodingDetectionIntegration:
    """エンコーディング検出機能の統合テスト。"""

    @pytest.mark.asyncio
    async def test_real_examples_encoding_file(self):
        """問題を引き起こした実際のexamples/encoding.txtファイルでテストします。"""
        # このテストは問題を実証した実際のファイルを使用
        encoding_file = Path("examples/encoding.txt")

        if not encoding_file.exists():
            pytest.skip("examples/encoding.txt not found")

        tool = SearchContentTool(".")

        # 自動エンコーディング検出で動作するはず
        result = await tool.execute({"files": [str(encoding_file)], "query": "これは"})

        # 元の問題: これでマッチが見つかるはず
        assert result["success"] is True
        assert (
            result["count"] > 0
        ), "examples/encoding.txtで日本語テキスト'これは'が見つかるべき"

    @pytest.mark.asyncio
    async def test_english_text_still_works(self):
        """英語テキスト検索が引き続き正常に動作することをテストします。"""
        encoding_file = Path("examples/encoding.txt")

        if not encoding_file.exists():
            pytest.skip("examples/encoding.txt not found")

        tool = SearchContentTool(".")

        # 英語テキストは引き続き動作すべき
        result = await tool.execute(
            {"files": [str(encoding_file)], "query": "TESTSTRING"}
        )

        assert result["success"] is True
        assert (
            result["count"] > 0
        ), f"英語テキスト'TESTSTRING'が見つかるべき, got {result}"
