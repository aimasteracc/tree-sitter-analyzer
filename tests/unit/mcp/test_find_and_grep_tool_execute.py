#!/usr/bin/env python3
"""
Tests for FindAndGrepTool.execute method — the two-stage fd+rg search pipeline.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import (
    FindAndGrepTool,
)


@pytest.fixture
def tool():
    """Create a fresh tool instance for each test."""
    return FindAndGrepTool()


@pytest.fixture
def sample_project_structure(tmp_path: Path):
    """Create a sample project structure for testing."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()

    (tmp_path / "README.md").write_text("# Test Project")
    (tmp_path / "src" / "main.py").write_text("def main():\n    print('hello')")
    (tmp_path / "src" / "utils.py").write_text("def helper():\n    return 42")
    (tmp_path / "tests" / "test_main.py").write_text("def test():\n    assert True")
    (tmp_path / "docs" / "guide.md").write_text("# Guide")

    return tmp_path


class TestExecuteErrorPaths:
    """Tests for execute method error and edge-case paths."""

    @pytest.mark.asyncio
    async def test_execute_missing_commands(self, tool):
        """Test execute fails when fd or rg commands are not found."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=["fd", "rg"],
        ):
            arguments = {"roots": ["."], "query": "test"}
            result = await tool.execute(arguments)
            assert result["success"] is False
            assert "Required commands not found" in result["error"]
            assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_execute_fd_failure(self, tool, sample_project_structure):
        """Test execute when fd command fails."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (1, b"", b"fd: error")

                arguments = {
                    "roots": [str(sample_project_structure)],
                    "query": "test",
                }

                result = await tool.execute(arguments)

                assert result["success"] is False
                assert "error" in result
                assert result["returncode"] == 1

    @pytest.mark.asyncio
    async def test_execute_no_files_found(self, tool, sample_project_structure):
        """Test execute when no files are found."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b"", b"")

                arguments = {
                    "roots": [str(sample_project_structure)],
                    "query": "test",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["count"] == 0
                assert result["results"] == []
                assert result["agent_summary"]["mode"] == "empty"
                assert result["agent_summary"]["next_step"]

    @pytest.mark.asyncio
    async def test_execute_rg_failure(self, tool, sample_project_structure):
        """Test execute when ripgrep command fails."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n", b""),
                    (2, b"", b"ripgrep: error"),
                ]

                arguments = {
                    "roots": [str(sample_project_structure)],
                    "query": "test",
                }

                result = await tool.execute(arguments)

                assert result["success"] is False
                assert "error" in result
                assert result["returncode"] == 2

    @pytest.mark.asyncio
    async def test_execute_file_save_error(self, tool, sample_project_structure):
        """Test execute when file save fails."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n", b""),
                    (0, b'{"path": "file1.py"}\n', b""),
                ]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py", "line": 1}],
                ):
                    with patch.object(
                        tool.file_output_manager, "save_to_file"
                    ) as mock_save:
                        mock_save.side_effect = Exception("Save failed")

                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "query": "test",
                            "output_file": "results.json",
                        }

                        result = await tool.execute(arguments)

                        assert result["success"] is True
                        assert "file_save_error" in result
                        assert result["file_saved"] is False


class TestExecuteOutputModes:
    """Tests for execute method output mode variants."""

    @pytest.mark.asyncio
    async def test_execute_total_only_mode(self, tool, sample_project_structure):
        """Test execute in total_only mode."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n/path/to/file2.py\n", b""),
                    (0, b"42", b""),
                ]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.parse_rg_count_output",
                    return_value={"__total__": 42},
                ):
                    arguments = {
                        "roots": [str(sample_project_structure)],
                        "query": "test",
                        "total_only": True,
                    }

                    result = await tool.execute(arguments)

                    assert result == 42

    @pytest.mark.asyncio
    async def test_execute_count_only_matches_mode(
        self, tool, sample_project_structure
    ):
        """Test execute in count_only_matches mode."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n/path/to/file2.py\n", b""),
                    (0, b"10\n5\n", b""),
                ]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.parse_rg_count_output",
                    return_value={"__total__": 15, "file1.py": 10, "file2.py": 5},
                ):
                    arguments = {
                        "roots": [str(sample_project_structure)],
                        "query": "test",
                        "count_only_matches": True,
                    }

                    result = await tool.execute(arguments)

                    assert result["success"] is True
                    assert result["count_only"] is True
                    assert result["total_matches"] == 15
                    assert "file_counts" in result
                    assert result["agent_summary"]["mode"] == "count_only"
                    assert result["agent_summary"]["file_count"] == 2

    @pytest.mark.asyncio
    async def test_execute_group_by_file_mode(self, tool, sample_project_structure):
        """Test execute in group_by_file mode."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n/path/to/file2.py\n", b""),
                    (0, b'{"path": "file1.py"}\n{"path": "file2.py"}\n', b""),
                ]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[
                        {"path": "file1.py", "line": 1, "content": "test"},
                        {"path": "file2.py", "line": 2, "content": "test"},
                    ],
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.group_matches_by_file",
                        return_value={
                            "success": True,
                            "count": 2,
                            "files": [
                                {"path": "file1.py", "matches": 1},
                                {"path": "file2.py", "matches": 1},
                            ],
                        },
                    ):
                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "query": "test",
                            "group_by_file": True,
                        }

                        result = await tool.execute(arguments)

                        assert result["success"] is True
                        assert "files" in result
                        assert result["agent_summary"]["mode"] == "group_by_file"
                        assert result["agent_summary"]["file_count"] == 2

    @pytest.mark.asyncio
    async def test_execute_summary_only_mode(self, tool, sample_project_structure):
        """Test execute in summary_only mode."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n", b""),
                    (0, b'{"path": "file1.py"}\n', b""),
                ]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py", "line": 1}],
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.summarize_search_results",
                        return_value={"top_files": ["file1.py"], "total_count": 1},
                    ):
                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "query": "test",
                            "summary_only": True,
                        }

                        result = await tool.execute(arguments)

                        assert result["success"] is True
                        assert result["summary_only"] is True
                        assert "summary" in result
                        assert result["agent_summary"]["mode"] == "summary"
                        assert result["agent_summary"]["file_count"] == 1

    @pytest.mark.asyncio
    async def test_execute_with_toon_format(self, tool, sample_project_structure):
        """Test execute with toon output format."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n", b""),
                    (0, b'{"path": "file1.py"}\n', b""),
                ]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py", "line": 1}],
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.find_and_grep_response.apply_toon_format_to_response"
                    ) as mock_toon:
                        mock_toon.return_value = {"toon": "formatted"}

                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "query": "test",
                            "output_format": "toon",
                        }

                        result = await tool.execute(arguments)

                        assert mock_toon.called
                        assert result == {"toon": "formatted"}


class TestExecuteOptionsAndFeatures:
    """Tests for execute method with various option flags."""

    @pytest.mark.asyncio
    async def test_execute_with_file_output(self, tool, sample_project_structure):
        """Test execute with file output."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n", b""),
                    (0, b'{"path": "file1.py"}\n', b""),
                ]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py", "line": 1}],
                ):
                    with patch.object(
                        tool.file_output_manager, "save_to_file"
                    ) as mock_save:
                        mock_save.return_value = "/output/results.json"

                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "query": "test",
                            "output_file": "results.json",
                        }

                        result = await tool.execute(arguments)

                        assert result["success"] is True
                        assert "toon_content" in result

    @pytest.mark.asyncio
    async def test_execute_with_suppress_output(self, tool, sample_project_structure):
        """Test execute with suppress_output."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n", b""),
                    (0, b'{"path": "file1.py"}\n', b""),
                ]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py", "line": 1}],
                ):
                    with patch.object(
                        tool.file_output_manager, "save_to_file"
                    ) as mock_save:
                        mock_save.return_value = "/output/results.json"

                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "query": "test",
                            "output_file": "results.json",
                            "suppress_output": True,
                        }

                        result = await tool.execute(arguments)

                        assert result["success"] is True
                        assert "toon_content" in result

    @pytest.mark.asyncio
    async def test_execute_with_optimize_paths(self, tool, sample_project_structure):
        """Test execute with optimize_paths."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n", b""),
                    (0, b'{"path": "/path/to/file1.py"}\n', b""),
                ]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "/path/to/file1.py", "line": 1}],
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.optimize_match_paths",
                        return_value=[{"path": "file1.py", "line": 1}],
                    ):
                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "query": "test",
                            "optimize_paths": True,
                        }

                        result = await tool.execute(arguments)

                        assert result["success"] is True
                        assert "toon_content" in result

    @pytest.mark.asyncio
    async def test_execute_with_gitignore_detection(
        self, tool, sample_project_structure
    ):
        """Test that .gitignore detection works."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.build_fd_command"
            ) as mock_build:
                mock_build.return_value = ["fd", "test"]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                    new_callable=AsyncMock,
                ) as mock_run:
                    mock_run.side_effect = [
                        (0, b"", b""),
                        (0, b"", b""),
                    ]

                    with patch(
                        "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.get_default_detector"
                    ) as mock_detector:
                        mock_detector.return_value.should_use_no_ignore.return_value = (
                            True
                        )
                        mock_detector.return_value.get_detection_info.return_value = {
                            "reason": "test reason"
                        }

                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "query": "test",
                        }

                        await tool.execute(arguments)

                        call_kwargs = mock_build.call_args.kwargs
                        assert call_kwargs["no_ignore"] is True

    @pytest.mark.asyncio
    async def test_execute_with_sort_path(self, tool, sample_project_structure):
        """Test execute with sort by path."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/z.py\n/path/a.py\n", b""),
                    (0, b"", b""),
                ]

                arguments = {
                    "roots": [str(sample_project_structure)],
                    "query": "test",
                    "sort": "path",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_file_limit_clamping(self, tool, sample_project_structure):
        """Test that file_limit is properly clamped."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.build_fd_command"
            ) as mock_build:
                mock_build.return_value = ["fd", "test"]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                    new_callable=AsyncMock,
                ) as mock_run:
                    mock_run.side_effect = [
                        (0, b"", b""),
                        (0, b"", b""),
                    ]

                    arguments = {
                        "roots": [str(sample_project_structure)],
                        "query": "test",
                        "file_limit": 50000,
                    }

                    await tool.execute(arguments)

                    call_kwargs = mock_build.call_args.kwargs
                    from tree_sitter_analyzer.mcp.tools import fd_rg_utils

                    assert call_kwargs["limit"] == fd_rg_utils.MAX_RESULTS_HARD_CAP

    @pytest.mark.asyncio
    async def test_execute_with_max_count(self, tool, sample_project_structure):
        """Test execute with max_count parameter."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"/path/to/file1.py\n", b""),
                    (
                        0,
                        b'{"path": "file1.py", "line": 1}\n{"path": "file1.py", "line": 2}\n',
                        b"",
                    ),
                ]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[
                        {"path": "file1.py", "line": 1},
                        {"path": "file1.py", "line": 2},
                    ],
                ):
                    arguments = {
                        "roots": [str(sample_project_structure)],
                        "query": "test",
                        "max_count": 1,
                    }

                    result = await tool.execute(arguments)

                    assert result["success"] is True
                    assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_execute_with_timeout(self, tool, sample_project_structure):
        """Test execute with timeout parameter."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.get_missing_commands",
            return_value=[],
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.side_effect = [
                    (0, b"", b""),
                    (0, b"", b""),
                ]

                arguments = {
                    "roots": [str(sample_project_structure)],
                    "query": "test",
                    "timeout_ms": 5000,
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
