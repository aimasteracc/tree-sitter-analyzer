#!/usr/bin/env python3
"""ListFilesTool execute method tests — all async execution paths."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool


@pytest.fixture
def tool():
    return ListFilesTool()


@pytest.fixture
def sample_project_structure(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / "README.md").write_text("# Test Project")
    (tmp_path / "src" / "main.py").write_text("print('hello')")
    (tmp_path / "src" / "utils.py").write_text("def helper(): pass")
    (tmp_path / "tests" / "test_main.py").write_text("def test(): pass")
    (tmp_path / "docs" / "guide.md").write_text("# Guide")
    (tmp_path / ".env").write_text("KEY=value")
    (tmp_path / ".gitignore").write_text("*.pyc\n__pycache__/")
    return tmp_path


class TestExecute:
    @pytest.mark.asyncio
    async def test_execute_fd_not_found(self, tool):
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=False,
        ):
            arguments = {"roots": ["."]}
            result = await tool.execute(arguments)
            assert result["success"] is False
            assert "fd command not found" in result["error"]
            assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_execute_success(self, tool, sample_project_structure):
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (
                    0,
                    b"/path/to/file1.py\n/path/to/file2.py\n",
                    b"",
                )

                with patch(
                    "tree_sitter_analyzer.mcp.tools.list_files_tool.get_default_detector"
                ):
                    arguments = {
                        "roots": [str(sample_project_structure)],
                        "pattern": "*.py",
                        "output_format": "json",
                    }

                    result = await tool.execute(arguments)

                    assert result["success"] is True
                    assert "agent_summary" in result
                    assert result["agent_summary"]["suggested_tool"] == "smart_context"
                    assert "count" in result
                    assert "elapsed_ms" in result

    @pytest.mark.asyncio
    async def test_execute_count_only_mode(self, tool, sample_project_structure):
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (
                    0,
                    b"/path/to/file1.py\n/path/to/file2.py\n/path/to/file3.py\n",
                    b"",
                )

                with patch(
                    "tree_sitter_analyzer.mcp.tools.list_files_tool.get_default_detector"
                ):
                    arguments = {
                        "roots": [str(sample_project_structure)],
                        "count_only": True,
                    }

                    result = await tool.execute(arguments)

                    assert result["success"] is True
                    assert result["count_only"] is True
                    assert result["agent_summary"]["count_only"] is True
                    assert result["agent_summary"]["suggested_tool"] == "list_files"
                    assert "total_count" in result
                    assert result["total_count"] == 3

    @pytest.mark.asyncio
    async def test_execute_with_file_output(self, tool, sample_project_structure):
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (
                    0,
                    b"/path/to/file1.py\n/path/to/file2.py\n",
                    b"",
                )

                with patch(
                    "tree_sitter_analyzer.mcp.tools.list_files_tool.get_default_detector"
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.list_files_helpers.FileOutputManager"
                    ) as mock_manager_class:
                        mock_manager = MagicMock()
                        mock_manager.save_to_file.return_value = "/output/results.json"
                        mock_manager_class.return_value = mock_manager

                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "output_file": "results.json",
                        }

                        result = await tool.execute(arguments)

                        assert result["success"] is True
                        assert "output_file" in result
                        assert result["output_file"] == "/output/results.json"

    @pytest.mark.asyncio
    async def test_execute_with_suppress_output(self, tool, sample_project_structure):
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (
                    0,
                    b"/path/to/file1.py\n/path/to/file2.py\n",
                    b"",
                )

                with patch(
                    "tree_sitter_analyzer.mcp.tools.list_files_tool.get_default_detector"
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.list_files_helpers.FileOutputManager"
                    ) as mock_manager_class:
                        mock_manager = MagicMock()
                        mock_manager.save_to_file.return_value = "/output/results.json"
                        mock_manager_class.return_value = mock_manager

                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "output_file": "results.json",
                            "suppress_output": True,
                        }

                        result = await tool.execute(arguments)

                        assert result["success"] is True
                        assert "output_file" in result
                        assert "message" in result
                        assert "results" not in result

    @pytest.mark.asyncio
    async def test_execute_with_output_format_toon(
        self, tool, sample_project_structure
    ):
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (
                    0,
                    b"/path/to/file1.py\n/path/to/file2.py\n",
                    b"",
                )

                with patch(
                    "tree_sitter_analyzer.mcp.tools.list_files_tool.get_default_detector"
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.list_files_helpers.apply_toon_format_to_response"
                    ) as mock_toon:
                        mock_toon.return_value = {"toon": "formatted"}

                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "output_format": "toon",
                        }

                        result = await tool.execute(arguments)

                        assert mock_toon.called
                        assert result == {"toon": "formatted"}

    @pytest.mark.asyncio
    async def test_execute_fd_command_failure(self, tool, sample_project_structure):
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (
                    1,
                    b"",
                    b"fd: error: invalid pattern",
                )

                with patch(
                    "tree_sitter_analyzer.mcp.tools.list_files_tool.get_default_detector"
                ):
                    arguments = {
                        "roots": [str(sample_project_structure)],
                        "pattern": "*.py",
                    }

                    result = await tool.execute(arguments)

                    assert result["success"] is False
                    assert "error" in result
                    assert result["returncode"] == 1

    @pytest.mark.asyncio
    async def test_execute_with_extensions_auto_types(
        self, tool, sample_project_structure
    ):
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.build_fd_command"
            ) as mock_build:
                mock_build.return_value = ["fd", "test"]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
                    new_callable=AsyncMock,
                ) as mock_run:
                    mock_run.return_value = (0, b"", b"")

                    with patch(
                        "tree_sitter_analyzer.mcp.tools.list_files_tool.get_default_detector"
                    ):
                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "extensions": ["py", "js"],
                        }

                        await tool.execute(arguments)

                        call_kwargs = mock_build.call_args.kwargs
                        assert call_kwargs["types"] == ["f"]

    @pytest.mark.asyncio
    async def test_execute_with_gitignore_detection(
        self, tool, sample_project_structure
    ):
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.build_fd_command"
            ) as mock_build:
                mock_build.return_value = ["fd", "test"]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
                    new_callable=AsyncMock,
                ) as mock_run:
                    mock_run.return_value = (0, b"", b"")

                    with patch(
                        "tree_sitter_analyzer.mcp.tools.list_files_tool.get_default_detector"
                    ) as mock_detector:
                        mock_detector.return_value.should_use_no_ignore.return_value = (
                            True
                        )
                        mock_detector.return_value.get_detection_info.return_value = {
                            "reason": "test reason"
                        }

                        arguments = {"roots": [str(sample_project_structure)]}

                        await tool.execute(arguments)

                        call_kwargs = mock_build.call_args.kwargs
                        assert call_kwargs["no_ignore"] is True

    @pytest.mark.asyncio
    async def test_execute_limit_clamping(self, tool, sample_project_structure):
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.build_fd_command"
            ) as mock_build:
                mock_build.return_value = ["fd", "test"]

                with patch(
                    "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
                    new_callable=AsyncMock,
                ) as mock_run:
                    mock_run.return_value = (0, b"", b"")

                    with patch(
                        "tree_sitter_analyzer.mcp.tools.list_files_tool.get_default_detector"
                    ):
                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "limit": 50000,
                        }

                        await tool.execute(arguments)

                        call_kwargs = mock_build.call_args.kwargs
                        from tree_sitter_analyzer.mcp.tools import fd_rg_utils

                        assert call_kwargs["limit"] == fd_rg_utils.MAX_RESULTS_HARD_CAP

    # Windows full-matrix under xdist load can exceed the 5s per-test budget
    # (this test fabricates a large file list for truncation; ~13s with reruns).
    # Logic is correct — exempt from the perf budget, not a perf claim.
    @pytest.mark.slow_ok
    @pytest.mark.asyncio
    async def test_execute_truncation_defensive(self, tool, sample_project_structure):
        with patch(
            "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            many_files = "\n".join(
                [f"/path/to/file{i}.py" for i in range(15000)]
            ).encode()

            with patch(
                "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, many_files, b"")

                with patch(
                    "tree_sitter_analyzer.mcp.tools.list_files_tool.get_default_detector"
                ):
                    arguments = {"roots": [str(sample_project_structure)]}

                    result = await tool.execute(arguments)

                    assert result["truncated"] is True
                    assert result["agent_summary"]["risk"] == "high"
                    assert result["agent_summary"]["suggested_tool"] == "list_files"
                    assert "toon_content" in result
