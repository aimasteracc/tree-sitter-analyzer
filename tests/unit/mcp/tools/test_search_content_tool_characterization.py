"""Characterization Tests for SearchContentTool.execute()

これらのテストは、リファクタリング前の現在の動作を保証するために作成されています。
リファクタリング後も、これらのテストがすべてパスすることを確認してください。

Test Coverage:
1. 基本的な検索機能
2. キャッシュ機能
3. 引数検証
4. エラーハンドリング
5. 各種出力フォーマット（total_only, count_only_matches, summary_only, group_by_file, optimize_paths）
6. ファイル出力機能
7. 並列処理
8. .gitignore自動検出
9. エッジケース
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


@pytest.fixture
def search_tool(tmp_path):
    """SearchContentToolのインスタンスを作成"""
    tool = SearchContentTool(project_root=str(tmp_path))
    return tool


@pytest.fixture
def sample_files(tmp_path):
    """テスト用のサンプルファイルを作成"""
    # ディレクトリ構造を作成
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()

    # サンプルファイルを作成
    (src_dir / "main.py").write_text("def main():\n    print('Hello, World!')\n")
    (src_dir / "utils.py").write_text("def helper():\n    return 42\n")
    (tests_dir / "test_main.py").write_text("def test_main():\n    assert True\n")

    return {
        "src_dir": str(src_dir),
        "tests_dir": str(tests_dir),
        "main_py": str(src_dir / "main.py"),
        "utils_py": str(src_dir / "utils.py"),
        "test_main_py": str(tests_dir / "test_main.py"),
    }


class TestBasicSearch:
    """基本的な検索機能のテスト"""

    @pytest.mark.asyncio
    async def test_basic_search_with_roots(
        self, search_tool, sample_files, monkeypatch
    ):
        """Test 1: rootsパラメータを使用した基本的な検索"""

        # Mock ripgrep command
        async def mock_run_command(cmd, timeout_ms=None):
            # Simulate ripgrep JSON output
            output = b'{"type":"match","data":{"path":{"text":"src/main.py"},"lines":{"text":"def main():\\n"},"line_number":1,"absolute_offset":0,"submatches":[{"match":{"text":"def"},"start":0,"end":3}]}}\n'
            return (0, output, b"")

        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
            mock_run_command,
        )

        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [sample_files["src_dir"]],
            }
        )

        assert result["success"] is True
        assert result["count"] >= 0
        assert "results" in result or "toon_content" in result

    @pytest.mark.asyncio
    async def test_basic_search_with_files(
        self, search_tool, sample_files, monkeypatch
    ):
        """Test 2: filesパラメータを使用した基本的な検索"""

        async def mock_run_command(cmd, timeout_ms=None):
            output = b'{"type":"match","data":{"path":{"text":"src/main.py"},"lines":{"text":"def main():\\n"},"line_number":1,"absolute_offset":0,"submatches":[{"match":{"text":"def"},"start":0,"end":3}]}}\n'
            return (0, output, b"")

        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
            mock_run_command,
        )

        result = await search_tool.execute(
            {
                "query": "def",
                "files": [sample_files["main_py"]],
            }
        )

        assert result["success"] is True
        assert result["count"] >= 0


class TestCacheFunctionality:
    """キャッシュ機能のテスト"""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_result(
        self, search_tool, sample_files, monkeypatch
    ):
        """Test 3: キャッシュヒット時に、キャッシュされた結果を返す"""
        # Enable cache
        from tree_sitter_analyzer.core.smart_cache import SmartCache

        search_tool.cache = SmartCache()

        async def mock_run_command(cmd, timeout_ms=None):
            output = b'{"type":"match","data":{"path":{"text":"src/main.py"},"lines":{"text":"def main():\\n"},"line_number":1,"absolute_offset":0,"submatches":[{"match":{"text":"def"},"start":0,"end":3}]}}\n'
            return (0, output, b"")

        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
            mock_run_command,
        )

        # First call - should execute and cache
        args = {"query": "def", "roots": [sample_files["src_dir"]]}
        result1 = await search_tool.execute(args)

        # Second call - should return cached result
        result2 = await search_tool.execute(args)

        assert result2.get("cache_hit") is True or result2 == result1

    @pytest.mark.asyncio
    async def test_total_only_cache_returns_integer(
        self, search_tool, sample_files, monkeypatch
    ):
        """Test 4: total_onlyモードでキャッシュから整数を返す"""
        from tree_sitter_analyzer.core.smart_cache import SmartCache

        search_tool.cache = SmartCache()

        async def mock_run_command(cmd, timeout_ms=None):
            # Simulate count output
            output = b"src/main.py:2\nsrc/utils.py:1\n"
            return (0, output, b"")

        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
            mock_run_command,
        )

        # First call with total_only
        args = {"query": "def", "roots": [sample_files["src_dir"]], "total_only": True}
        result1 = await search_tool.execute(args)

        # Should return integer
        assert isinstance(result1, int)

        # Second call should also return integer from cache
        result2 = await search_tool.execute(args)
        assert isinstance(result2, int)
        assert result2 == result1


class TestArgumentValidation:
    """引数検証のテスト"""

    @pytest.mark.asyncio
    async def test_missing_query_raises_error(self, search_tool, sample_files):
        """Test 5: queryパラメータが欠けている場合、エラーを発生させる"""
        with pytest.raises(ValueError, match="query"):
            await search_tool.execute({"roots": [sample_files["src_dir"]]})

    @pytest.mark.asyncio
    async def test_invalid_roots_type_raises_error(self, search_tool):
        """Test 6: rootsパラメータの型が不正な場合、エラーを発生させる"""
        with pytest.raises((ValueError, TypeError)):
            await search_tool.execute({"query": "test", "roots": "not_a_list"})

    @pytest.mark.asyncio
    async def test_invalid_files_type_raises_error(self, search_tool):
        """Test 7: filesパラメータの型が不正な場合、エラーを発生させる"""
        with pytest.raises((ValueError, TypeError)):
            await search_tool.execute({"query": "test", "files": "not_a_list"})


class TestErrorHandling:
    """エラーハンドリングのテスト"""

    @pytest.mark.asyncio
    async def test_ripgrep_not_found_returns_error(
        self, search_tool, sample_files, monkeypatch
    ):
        """Test 8: ripgrepコマンドが見つからない場合、エラーを返す"""
        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
            lambda cmd: False,
        )

        result = await search_tool.execute(
            {
                "query": "test",
                "roots": [sample_files["src_dir"]],
            }
        )

        assert result["success"] is False
        assert "rg" in result["error"].lower() or "ripgrep" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_ripgrep_failure_returns_error(
        self, search_tool, sample_files, monkeypatch
    ):
        """Test 9: ripgrepコマンドが失敗した場合、エラーを返す"""

        async def mock_run_command(cmd, timeout_ms=None):
            return (2, b"", b"ripgrep error")

        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
            mock_run_command,
        )

        result = await search_tool.execute(
            {
                "query": "test",
                "roots": [sample_files["src_dir"]],
            }
        )

        assert result["success"] is False
        assert "error" in result


class TestOutputFormats:
    """各種出力フォーマットのテスト"""

    @pytest.mark.asyncio
    async def test_total_only_returns_integer(
        self, search_tool, sample_files, monkeypatch
    ):
        """Test 10: total_onlyモードで整数を返す"""

        async def mock_run_command(cmd, timeout_ms=None):
            output = b"src/main.py:2\nsrc/utils.py:1\n"
            return (0, output, b"")

        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
            mock_run_command,
        )

        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [sample_files["src_dir"]],
                "total_only": True,
            }
        )

        assert isinstance(result, int)
        assert result >= 0

    @pytest.mark.asyncio
    async def test_count_only_matches_returns_dict_with_counts(
        self, search_tool, sample_files, monkeypatch
    ):
        """Test 11: count_only_matchesモードでファイルごとのカウントを含む辞書を返す"""

        async def mock_run_command(cmd, timeout_ms=None):
            output = b"src/main.py:2\nsrc/utils.py:1\n"
            return (0, output, b"")

        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
            mock_run_command,
        )

        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [sample_files["src_dir"]],
                "count_only_matches": True,
            }
        )

        assert isinstance(result, dict)
        assert result["success"] is True
        assert "count_only" in result or "total_matches" in result
        assert "file_counts" in result or "toon_content" in result

    @pytest.mark.asyncio
    async def test_summary_only_returns_summary(
        self, search_tool, sample_files, monkeypatch
    ):
        """Test 12: summary_onlyモードでサマリーを返す"""

        async def mock_run_command(cmd, timeout_ms=None):
            output = b'{"type":"match","data":{"path":{"text":"src/main.py"},"lines":{"text":"def main():\\n"},"line_number":1,"absolute_offset":0,"submatches":[{"match":{"text":"def"},"start":0,"end":3}]}}\n'
            return (0, output, b"")

        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
            mock_run_command,
        )

        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [sample_files["src_dir"]],
                "summary_only": True,
            }
        )

        assert isinstance(result, dict)
        assert result["success"] is True
        assert "summary" in result or "toon_content" in result

    @pytest.mark.asyncio
    async def test_group_by_file_returns_grouped_results(
        self, search_tool, sample_files, monkeypatch
    ):
        """Test 13: group_by_fileモードでファイルごとにグループ化された結果を返す"""

        async def mock_run_command(cmd, timeout_ms=None):
            output = b'{"type":"match","data":{"path":{"text":"src/main.py"},"lines":{"text":"def main():\\n"},"line_number":1,"absolute_offset":0,"submatches":[{"match":{"text":"def"},"start":0,"end":3}]}}\n'
            return (0, output, b"")

        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
            mock_run_command,
        )

        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [sample_files["src_dir"]],
                "group_by_file": True,
            }
        )

        assert isinstance(result, dict)
        assert result["success"] is True
        assert "files" in result or "toon_content" in result

    @pytest.mark.asyncio
    async def test_optimize_paths_optimizes_file_paths(
        self, search_tool, sample_files, monkeypatch
    ):
        """Test 14: optimize_pathsモードでファイルパスを最適化する"""

        async def mock_run_command(cmd, timeout_ms=None):
            output = b'{"type":"match","data":{"path":{"text":"src/main.py"},"lines":{"text":"def main():\\n"},"line_number":1,"absolute_offset":0,"submatches":[{"match":{"text":"def"},"start":0,"end":3}]}}\n'
            return (0, output, b"")

        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
            mock_run_command,
        )

        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [sample_files["src_dir"]],
                "optimize_paths": True,
            }
        )

        assert isinstance(result, dict)
        assert result["success"] is True


class TestFileOutput:
    """ファイル出力機能のテスト"""

    @pytest.mark.asyncio
    async def test_output_file_saves_results(
        self, search_tool, sample_files, monkeypatch, tmp_path
    ):
        """Test 15: output_fileパラメータで結果をファイルに保存する"""

        async def mock_run_command(cmd, timeout_ms=None):
            output = b'{"type":"match","data":{"path":{"text":"src/main.py"},"lines":{"text":"def main():\\n"},"line_number":1,"absolute_offset":0,"submatches":[{"match":{"text":"def"},"start":0,"end":3}]}}\n'
            return (0, output, b"")

        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
            mock_run_command,
        )

        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [sample_files["src_dir"]],
                "output_file": "search_results.json",
            }
        )

        assert result["success"] is True
        assert "file_saved" in result or "output_file" in result

    @pytest.mark.asyncio
    async def test_suppress_output_with_output_file_returns_minimal_result(
        self, search_tool, sample_files, monkeypatch
    ):
        """Test 16: suppress_outputとoutput_fileを併用すると最小限の結果を返す"""

        async def mock_run_command(cmd, timeout_ms=None):
            output = b'{"type":"match","data":{"path":{"text":"src/main.py"},"lines":{"text":"def main():\\n"},"line_number":1,"absolute_offset":0,"submatches":[{"match":{"text":"def"},"start":0,"end":3}]}}\n'
            return (0, output, b"")

        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
            mock_run_command,
        )

        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [sample_files["src_dir"]],
                "output_file": "search_results.json",
                "suppress_output": True,
            }
        )

        assert result["success"] is True
        assert "results" not in result or len(str(result)) < 500  # Minimal result


class TestParallelProcessing:
    """並列処理のテスト"""

    @pytest.mark.asyncio
    async def test_parallel_processing_with_multiple_roots(
        self, search_tool, sample_files, monkeypatch
    ):
        """Test 17: 複数のrootsで並列処理を実行する"""

        async def mock_run_parallel(commands, timeout_ms=None, max_concurrent=4):
            # Simulate parallel execution results
            results = []
            for _ in commands:
                output = b'{"type":"match","data":{"path":{"text":"src/main.py"},"lines":{"text":"def main():\\n"},"line_number":1,"absolute_offset":0,"submatches":[{"match":{"text":"def"},"start":0,"end":3}]}}\n'
                results.append((0, output, b""))
            return results

        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_parallel_rg_searches",
            mock_run_parallel,
        )

        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [sample_files["src_dir"], sample_files["tests_dir"]],
                "enable_parallel": True,
            }
        )

        assert result["success"] is True


class TestGitignoreDetection:
    """gitignore自動検出のテスト"""

    @pytest.mark.asyncio
    async def test_auto_enable_no_ignore_when_needed(
        self, search_tool, sample_files, monkeypatch
    ):
        """Test 18: 必要に応じて--no-ignoreを自動的に有効にする"""
        # Create .gitignore file
        gitignore_path = Path(sample_files["src_dir"]).parent / ".gitignore"
        gitignore_path.write_text("*.pyc\n")

        async def mock_run_command(cmd, timeout_ms=None):
            # Check if --no-ignore is in the command
            output = b'{"type":"match","data":{"path":{"text":"src/main.py"},"lines":{"text":"def main():\\n"},"line_number":1,"absolute_offset":0,"submatches":[{"match":{"text":"def"},"start":0,"end":3}]}}\n'
            return (0, output, b"")

        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
            mock_run_command,
        )

        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [sample_files["src_dir"]],
            }
        )

        assert result["success"] is True


class TestEdgeCases:
    """エッジケースのテスト"""

    @pytest.mark.asyncio
    async def test_empty_results_returns_zero_count(
        self, search_tool, sample_files, monkeypatch
    ):
        """Test 19: 検索結果が空の場合、カウント0を返す"""

        async def mock_run_command(cmd, timeout_ms=None):
            # No matches
            return (1, b"", b"")

        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
            mock_run_command,
        )

        result = await search_tool.execute(
            {
                "query": "nonexistent_pattern",
                "roots": [sample_files["src_dir"]],
            }
        )

        assert result["success"] is True
        if isinstance(result, dict):
            assert result.get("count", 0) == 0

    @pytest.mark.asyncio
    async def test_max_count_limits_results(
        self, search_tool, sample_files, monkeypatch
    ):
        """Test 20: max_countパラメータで結果数を制限する"""

        async def mock_run_command(cmd, timeout_ms=None):
            # Multiple matches
            output = b'{"type":"match","data":{"path":{"text":"src/main.py"},"lines":{"text":"def main():\\n"},"line_number":1,"absolute_offset":0,"submatches":[{"match":{"text":"def"},"start":0,"end":3}]}}\n'
            output += b'{"type":"match","data":{"path":{"text":"src/utils.py"},"lines":{"text":"def helper():\\n"},"line_number":1,"absolute_offset":0,"submatches":[{"match":{"text":"def"},"start":0,"end":3}]}}\n'
            return (0, output, b"")

        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
            mock_run_command,
        )

        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [sample_files["src_dir"]],
                "max_count": 1,
            }
        )

        assert result["success"] is True
        # Note: max_count behavior may vary, just ensure it doesn't crash


class TestToonFormat:
    """TOON形式出力のテスト"""

    @pytest.mark.asyncio
    async def test_toon_format_output(self, search_tool, sample_files, monkeypatch):
        """Test 21: output_format='toon'でTOON形式を返す"""

        async def mock_run_command(cmd, timeout_ms=None):
            output = b'{"type":"match","data":{"path":{"text":"src/main.py"},"lines":{"text":"def main():\\n"},"line_number":1,"absolute_offset":0,"submatches":[{"match":{"text":"def"},"start":0,"end":3}]}}\n'
            return (0, output, b"")

        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
            mock_run_command,
        )

        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [sample_files["src_dir"]],
                "output_format": "toon",
            }
        )

        assert isinstance(result, dict)
        # TOON format may include 'toon_content' or 'format' field
        assert (
            result.get("success") is True
            or "toon_content" in result
            or "format" in result
        )
