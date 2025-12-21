#!/usr/bin/env python3
"""
Tests for search_content tool parallel processing functionality.
"""

from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.tools import fd_rg_utils
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


class TestSearchContentParallel:
    """Test parallel processing functionality in search_content tool."""

    @pytest.fixture
    def tool(self):
        """Create a SearchContentTool instance for testing."""
        return SearchContentTool(project_root="/test/project", enable_cache=False)

    @pytest.mark.asyncio
    async def test_parallel_processing_enabled_by_default(self, tool):
        """Test that parallel processing is enabled by default for multiple roots."""
        arguments = {
            "query": "test",
            "roots": ["/test/dir1", "/test/dir2", "/test/dir3"],
        }

        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
                return_value=True,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_parallel_rg_searches"
            ) as mock_parallel,
            patch.object(tool, "_validate_roots", return_value=arguments["roots"]),
        ):
            # Mock parallel search results
            mock_parallel.return_value = [
                (0, b'{"type":"match","data":{"path":{"text":"test.py"}}}', b"")
            ]

            result = await tool.execute(arguments)

            # Verify parallel processing was called
            mock_parallel.assert_called_once()
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_parallel_processing_disabled_option(self, tool):
        """Test that parallel processing can be disabled via option."""
        arguments = {
            "query": "test",
            "roots": ["/test/dir1", "/test/dir2"],
            "enable_parallel": False,
        }

        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
                return_value=True,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
            ) as mock_single,
            patch(
                "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_parallel_rg_searches"
            ) as mock_parallel,
            patch.object(tool, "_validate_roots", return_value=arguments["roots"]),
        ):
            # Mock single command results
            mock_single.return_value = (
                0,
                b'{"type":"match","data":{"path":{"text":"test.py"}}}',
                b"",
            )

            result = await tool.execute(arguments)

            # Verify single command was used, not parallel
            mock_single.assert_called_once()
            mock_parallel.assert_not_called()
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_single_root_uses_single_command(self, tool):
        """Test that single root directory uses single command execution."""
        arguments = {
            "query": "test",
            "roots": ["/test/dir1"],
        }

        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
                return_value=True,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
            ) as mock_single,
            patch(
                "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_parallel_rg_searches"
            ) as mock_parallel,
            patch.object(tool, "_validate_roots", return_value=arguments["roots"]),
        ):
            # Mock single command results
            mock_single.return_value = (
                0,
                b'{"type":"match","data":{"path":{"text":"test.py"}}}',
                b"",
            )

            result = await tool.execute(arguments)

            # Verify single command was used for single root
            mock_single.assert_called_once()
            mock_parallel.assert_not_called()
            assert result["success"] is True

    def test_split_roots_for_parallel_processing(self):
        """Test root splitting logic for parallel processing."""
        # Test with fewer roots than max chunks
        roots = ["/dir1", "/dir2"]
        chunks = fd_rg_utils.split_roots_for_parallel_processing(roots, max_chunks=4)
        assert len(chunks) == 2
        assert chunks == [["/dir1"], ["/dir2"]]

        # Test with more roots than max chunks
        roots = ["/dir1", "/dir2", "/dir3", "/dir4", "/dir5", "/dir6"]
        chunks = fd_rg_utils.split_roots_for_parallel_processing(roots, max_chunks=3)
        assert len(chunks) == 3
        # Should distribute evenly: 2, 2, 2
        assert len(chunks[0]) == 2
        assert len(chunks[1]) == 2
        assert len(chunks[2]) == 2

        # Test with empty roots
        chunks = fd_rg_utils.split_roots_for_parallel_processing([], max_chunks=4)
        assert chunks == []

    @pytest.mark.asyncio
    async def test_parallel_rg_searches_execution(self):
        """Test parallel ripgrep search execution."""
        commands = [
            ["rg", "--json", "test", "/dir1"],
            ["rg", "--json", "test", "/dir2"],
        ]

        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock different results for each command
            mock_run.side_effect = [
                (0, b'{"type":"match","data":{"path":{"text":"file1.py"}}}', b""),
                (0, b'{"type":"match","data":{"path":{"text":"file2.py"}}}', b""),
            ]

            results = await fd_rg_utils.run_parallel_rg_searches(
                commands, max_concurrent=2
            )

            assert len(results) == 2
            assert all(rc == 0 for rc, _, _ in results)
            assert mock_run.call_count == 2

    def test_merge_json_results(self):
        """Test merging of JSON results from parallel searches."""
        results = [
            (0, b'{"type":"match","data":{"path":{"text":"file1.py"}}}\n', b""),
            (0, b'{"type":"match","data":{"path":{"text":"file2.py"}}}\n', b""),
            (1, b"", b""),  # No matches
        ]

        rc, stdout, stderr = fd_rg_utils.merge_rg_results(
            results, count_only_mode=False
        )

        assert rc == 0  # Should be 0 since we have matches
        assert b"file1.py" in stdout
        assert b"file2.py" in stdout

    def test_merge_count_results(self):
        """Test merging of count results from parallel searches."""
        results = [
            (0, b"file1.py:3\nfile2.py:2\n", b""),
            (0, b"file3.py:1\n", b""),
            (1, b"", b""),  # No matches
        ]

        rc, stdout, stderr = fd_rg_utils.merge_rg_results(results, count_only_mode=True)

        assert rc == 0  # Should be 0 since we have matches
        stdout_str = stdout.decode("utf-8")
        assert "file1.py:3" in stdout_str
        assert "file2.py:2" in stdout_str
        assert "file3.py:1" in stdout_str

    @pytest.mark.asyncio
    async def test_parallel_processing_with_count_only(self, tool):
        """Test parallel processing works with count-only mode."""
        arguments = {
            "query": "test",
            "roots": ["/test/dir1", "/test/dir2"],
            "count_only_matches": True,
        }

        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
                return_value=True,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_parallel_rg_searches"
            ) as mock_parallel,
            patch.object(tool, "_validate_roots", return_value=arguments["roots"]),
        ):
            # Mock parallel count results
            mock_parallel.return_value = [
                (0, b"file1.py:3\nfile2.py:2\n", b""),
                (0, b"file3.py:1\n", b""),
            ]

            result = await tool.execute(arguments)

            # Verify parallel processing was called
            mock_parallel.assert_called_once()
            assert result["success"] is True
            assert result["count_only"] is True
            assert result["total_matches"] == 6  # 3 + 2 + 1

    @pytest.mark.asyncio
    async def test_parallel_processing_error_handling(self, tool):
        """Test error handling in parallel processing."""
        arguments = {
            "query": "test",
            "roots": ["/test/dir1", "/test/dir2"],
        }

        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
                return_value=True,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_parallel_rg_searches"
            ) as mock_parallel,
            patch.object(tool, "_validate_roots", return_value=arguments["roots"]),
        ):
            # Mock one successful and one failed result
            mock_parallel.return_value = [
                (0, b'{"type":"match","data":{"path":{"text":"file1.py"}}}', b""),
                (2, b"", b"Error occurred"),  # Error result
            ]

            result = await tool.execute(arguments)

            # Should still succeed with partial results
            assert result["success"] is True

    def test_validate_enable_parallel_argument(self, tool):
        """Test validation of enable_parallel argument."""
        with patch.object(tool, "_validate_roots", return_value=["test"]):
            # Valid boolean values should pass
            arguments = {"query": "test", "roots": ["test"], "enable_parallel": True}
            assert tool.validate_arguments(arguments) is True

            arguments = {"query": "test", "roots": ["test"], "enable_parallel": False}
            assert tool.validate_arguments(arguments) is True

            # Invalid type should raise ValueError
            arguments = {
                "query": "test",
                "roots": ["test"],
                "enable_parallel": "invalid",
            }
            with pytest.raises(ValueError, match="enable_parallel must be a boolean"):
                tool.validate_arguments(arguments)
