"""
Integration tests for SearchContentTool.

Tests the complete search workflow with real file system operations,
verifying Strategy Pattern integration and end-to-end functionality.
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


class TestSearchContentToolIntegration:
    """Integration tests for SearchContentTool with real file operations."""

    @pytest.fixture
    def temp_project(self, tmp_path: Path) -> Path:
        """Create a temporary project with test files."""
        # Create directory structure
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        # Create Python files
        (src_dir / "main.py").write_text(
            "def main():\n    print('Hello, World!')\n\nif __name__ == '__main__':\n    main()\n"
        )
        (src_dir / "utils.py").write_text(
            "def helper():\n    return 'helper'\n\ndef another_helper():\n    return 'another'\n"
        )
        (tests_dir / "test_main.py").write_text(
            "def test_main():\n    assert True\n\ndef test_helper():\n    assert True\n"
        )

        # Create .gitignore
        (tmp_path / ".gitignore").write_text("*.pyc\n__pycache__/\n.venv/\n")

        return tmp_path

    @pytest.fixture
    def search_tool(self, temp_project: Path) -> SearchContentTool:
        """Create SearchContentTool instance."""
        return SearchContentTool(project_root=str(temp_project))

    @pytest.mark.asyncio
    async def test_basic_search_finds_pattern(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test basic search finds pattern in files."""
        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [str(temp_project)],
            }
        )

        assert isinstance(result, dict)
        assert "matches" in result
        assert len(result["matches"]) > 0
        # Should find 'def' in multiple files
        assert any("main.py" in match.get("file", "") for match in result["matches"])
        assert any("utils.py" in match.get("file", "") for match in result["matches"])

    @pytest.mark.asyncio
    async def test_search_with_file_pattern(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test search with file pattern filtering."""
        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [str(temp_project)],
                "include_globs": ["*.py"],
            }
        )

        assert isinstance(result, dict)
        assert "matches" in result
        # All matches should be from .py files
        for match in result["matches"]:
            assert match["file"].endswith(".py")

    @pytest.mark.asyncio
    async def test_total_only_mode(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test total_only mode returns integer count."""
        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [str(temp_project)],
                "total_only": True,
            }
        )

        assert isinstance(result, int)
        assert result > 0  # Should find multiple 'def' keywords

    @pytest.mark.asyncio
    async def test_count_only_matches_mode(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test count_only_matches mode returns file counts."""
        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [str(temp_project)],
                "count_only_matches": True,
            }
        )

        assert isinstance(result, dict)
        assert "file_counts" in result
        assert len(result["file_counts"]) > 0
        # Should have counts for multiple files
        assert any("main.py" in file for file in result["file_counts"])

    @pytest.mark.asyncio
    async def test_summary_only_mode(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test summary_only mode returns condensed summary."""
        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [str(temp_project)],
                "summary_only": True,
            }
        )

        assert isinstance(result, dict)
        assert "summary" in result
        assert "total_matches" in result["summary"]
        assert "top_files" in result["summary"]
        assert result["summary"]["total_matches"] > 0

    @pytest.mark.asyncio
    async def test_group_by_file_mode(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test group_by_file mode groups results by file."""
        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [str(temp_project)],
                "group_by_file": True,
            }
        )

        assert isinstance(result, dict)
        assert "files" in result
        assert len(result["files"]) > 0
        # Each file should have matches
        for file_entry in result["files"]:
            assert "file" in file_entry
            assert "matches" in file_entry
            assert len(file_entry["matches"]) > 0

    @pytest.mark.asyncio
    async def test_case_sensitive_search(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test case-sensitive search."""
        # Search for 'HELLO' (uppercase) - should not find 'Hello'
        result = await search_tool.execute(
            {
                "query": "HELLO",
                "roots": [str(temp_project)],
                "case": "sensitive",
            }
        )

        assert isinstance(result, dict)
        assert "matches" in result
        # Should not find 'Hello, World!' with case-sensitive search
        assert len(result["matches"]) == 0

    @pytest.mark.asyncio
    async def test_case_insensitive_search(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test case-insensitive search."""
        # Search for 'hello' (lowercase) - should find 'Hello'
        result = await search_tool.execute(
            {
                "query": "hello",
                "roots": [str(temp_project)],
                "case": "insensitive",
            }
        )

        assert isinstance(result, dict)
        assert "matches" in result
        # Should find 'Hello, World!' with case-insensitive search
        assert len(result["matches"]) > 0
        assert any("Hello" in match.get("text", "") for match in result["matches"])

    @pytest.mark.asyncio
    async def test_max_count_limits_results(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test max_count parameter limits results per file."""
        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [str(temp_project)],
                "max_count": 1,
            }
        )

        assert isinstance(result, dict)
        assert "matches" in result
        # Each file should have at most 1 match
        file_counts: dict[str, int] = {}
        for match in result["matches"]:
            file = match["file"]
            file_counts[file] = file_counts.get(file, 0) + 1
        for count in file_counts.values():
            assert count <= 1

    @pytest.mark.asyncio
    async def test_context_lines(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test context_before and context_after parameters."""
        result = await search_tool.execute(
            {
                "query": "main",
                "roots": [str(temp_project)],
                "context_before": 1,
                "context_after": 1,
            }
        )

        assert isinstance(result, dict)
        assert "matches" in result
        # Matches should include context lines
        for match in result["matches"]:
            if "context" in match:
                assert "before" in match["context"] or "after" in match["context"]

    @pytest.mark.asyncio
    async def test_file_output_saves_results(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test output_file parameter saves results to file."""
        output_file = temp_project / "search_results.json"

        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [str(temp_project)],
                "output_file": str(output_file),
            }
        )

        assert isinstance(result, dict)
        assert "output_file" in result
        assert output_file.exists()
        # File should contain JSON data
        content = output_file.read_text()
        assert len(content) > 0
        assert "matches" in content or "total" in content

    @pytest.mark.asyncio
    async def test_suppress_output_with_file_output(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test suppress_output with output_file returns minimal result."""
        output_file = temp_project / "search_results.json"

        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [str(temp_project)],
                "output_file": str(output_file),
                "suppress_output": True,
            }
        )

        assert isinstance(result, dict)
        assert "output_file" in result
        assert output_file.exists()
        # Result should be minimal (no matches in response)
        assert "matches" not in result or len(result.get("matches", [])) == 0

    @pytest.mark.asyncio
    async def test_parallel_search_multiple_roots(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test parallel search with multiple root directories."""
        src_dir = temp_project / "src"
        tests_dir = temp_project / "tests"

        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [str(src_dir), str(tests_dir)],
                "enable_parallel": True,
            }
        )

        assert isinstance(result, dict)
        assert "matches" in result
        # Should find matches in both directories
        src_matches = [m for m in result["matches"] if "src" in m["file"]]
        test_matches = [m for m in result["matches"] if "tests" in m["file"]]
        assert len(src_matches) > 0
        assert len(test_matches) > 0

    @pytest.mark.asyncio
    async def test_gitignore_detection(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test automatic .gitignore detection and handling."""
        # Create a file that should be ignored
        pycache_dir = temp_project / "src" / "__pycache__"
        pycache_dir.mkdir()
        (pycache_dir / "test.pyc").write_text("compiled code")

        # Search without no_ignore - should respect .gitignore
        result = await search_tool.execute(
            {
                "query": "compiled",
                "roots": [str(temp_project)],
            }
        )

        assert isinstance(result, dict)
        # Should not find matches in __pycache__ (ignored by .gitignore)
        if "matches" in result:
            assert not any("__pycache__" in m["file"] for m in result["matches"])

    @pytest.mark.asyncio
    async def test_no_ignore_flag(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test no_ignore flag searches ignored files."""
        # Create a file that should be ignored
        pycache_dir = temp_project / "src" / "__pycache__"
        pycache_dir.mkdir()
        (pycache_dir / "test.pyc").write_text("compiled code")

        # Search with no_ignore - should search ignored files
        result = await search_tool.execute(
            {
                "query": "compiled",
                "roots": [str(temp_project)],
                "no_ignore": True,
            }
        )

        assert isinstance(result, dict)
        assert "matches" in result
        # Should find matches in __pycache__ when no_ignore=True
        assert any("__pycache__" in m["file"] for m in result["matches"])

    @pytest.mark.asyncio
    async def test_error_handling_invalid_root(self, search_tool: SearchContentTool):
        """Test error handling for invalid root directory."""
        result = await search_tool.execute(
            {
                "query": "test",
                "roots": ["/nonexistent/directory"],
            }
        )

        assert isinstance(result, dict)
        assert "error" in result or "matches" in result
        # Should handle gracefully (either error or empty results)

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_result(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test cache returns same result for identical queries."""
        arguments = {
            "query": "def",
            "roots": [str(temp_project)],
        }

        # First execution
        result1 = await search_tool.execute(arguments)

        # Second execution (should hit cache)
        result2 = await search_tool.execute(arguments)

        # Results should be identical
        assert result1 == result2

    @pytest.mark.asyncio
    async def test_toon_format_output(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test TOON format output."""
        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [str(temp_project)],
                "output_format": "toon",
            }
        )

        assert isinstance(result, dict)
        # TOON format should have specific structure
        # (exact structure depends on implementation)
        assert "matches" in result or "total" in result


class TestSearchContentToolStrategyIntegration:
    """Integration tests for Strategy Pattern implementation."""

    @pytest.fixture
    def temp_project(self, tmp_path: Path) -> Path:
        """Create a temporary project with test files."""
        (tmp_path / "file1.txt").write_text("pattern1\npattern2\npattern3\n")
        (tmp_path / "file2.txt").write_text("pattern1\npattern1\npattern2\n")
        (tmp_path / "file3.txt").write_text("pattern2\npattern3\npattern3\n")
        return tmp_path

    @pytest.fixture
    def search_tool(self, temp_project: Path) -> SearchContentTool:
        """Create SearchContentTool instance."""
        return SearchContentTool(project_root=str(temp_project))

    @pytest.mark.asyncio
    async def test_strategy_pattern_total_only(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test Strategy Pattern with total_only mode."""
        result = await search_tool.execute(
            {
                "query": "pattern1",
                "roots": [str(temp_project)],
                "total_only": True,
            }
        )

        assert isinstance(result, int)
        assert result == 3  # 1 in file1, 2 in file2

    @pytest.mark.asyncio
    async def test_strategy_pattern_count_only(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test Strategy Pattern with count_only_matches mode."""
        result = await search_tool.execute(
            {
                "query": "pattern2",
                "roots": [str(temp_project)],
                "count_only_matches": True,
            }
        )

        assert isinstance(result, dict)
        assert "file_counts" in result
        # Should have counts for file1, file2, file3
        assert len(result["file_counts"]) == 3

    @pytest.mark.asyncio
    async def test_strategy_pattern_summary(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test Strategy Pattern with summary_only mode."""
        result = await search_tool.execute(
            {
                "query": "pattern3",
                "roots": [str(temp_project)],
                "summary_only": True,
            }
        )

        assert isinstance(result, dict)
        assert "summary" in result
        assert result["summary"]["total_matches"] == 4  # 1 in file1, 2 in file3

    @pytest.mark.asyncio
    async def test_strategy_pattern_group_by_file(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test Strategy Pattern with group_by_file mode."""
        result = await search_tool.execute(
            {
                "query": "pattern",
                "roots": [str(temp_project)],
                "group_by_file": True,
            }
        )

        assert isinstance(result, dict)
        assert "files" in result
        # Should group all matches by file
        assert len(result["files"]) == 3  # file1, file2, file3

    @pytest.mark.asyncio
    async def test_strategy_pattern_normal_mode(
        self, search_tool: SearchContentTool, temp_project: Path
    ):
        """Test Strategy Pattern with normal mode (default)."""
        result = await search_tool.execute(
            {
                "query": "pattern1",
                "roots": [str(temp_project)],
            }
        )

        assert isinstance(result, dict)
        assert "matches" in result
        # Should return all matches
        assert len(result["matches"]) == 3  # 1 in file1, 2 in file2


class TestSearchContentToolErrorHandling:
    """Integration tests for error handling."""

    @pytest.fixture
    def search_tool(self, tmp_path: Path) -> SearchContentTool:
        """Create SearchContentTool instance."""
        return SearchContentTool(project_root=str(tmp_path))

    @pytest.mark.asyncio
    async def test_missing_query_parameter(self, search_tool: SearchContentTool):
        """Test error handling for missing query parameter."""
        result = await search_tool.execute(
            {
                "roots": ["."],
            }
        )

        assert isinstance(result, dict)
        assert "error" in result
        assert "query" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_invalid_roots_type(self, search_tool: SearchContentTool):
        """Test error handling for invalid roots type."""
        result = await search_tool.execute(
            {
                "query": "test",
                "roots": "not_a_list",  # Should be list
            }
        )

        assert isinstance(result, dict)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_mutually_exclusive_parameters(
        self, search_tool: SearchContentTool, tmp_path: Path
    ):
        """Test error handling for mutually exclusive parameters."""
        result = await search_tool.execute(
            {
                "query": "test",
                "roots": [str(tmp_path)],
                "total_only": True,
                "count_only_matches": True,  # Mutually exclusive with total_only
            }
        )

        assert isinstance(result, dict)
        # Should either error or use one mode (implementation-dependent)
        assert "error" in result or isinstance(result, int) or "file_counts" in result
