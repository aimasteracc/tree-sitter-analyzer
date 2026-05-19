#!/usr/bin/env python3
"""SearchContentTool execute method tests — all async execution paths."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.search_content_tool import (
    SearchContentTool,
)


@pytest.fixture
def tool():
    return SearchContentTool()


@pytest.fixture
def sample_project_structure(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "README.md").write_text("# Test Project")
    (tmp_path / "src" / "main.py").write_text("def main():\n    print('hello')")
    (tmp_path / "src" / "utils.py").write_text("def helper():\n    return 42")
    (tmp_path / "tests" / "test_main.py").write_text("def test():\n    assert True")
    return tmp_path


class TestExecute:
    """Tests for execute method."""

    @pytest.mark.asyncio
    async def test_execute_rg_not_found(self, tool):
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=False,
        ):
            arguments = {"roots": ["."], "query": "test"}
            result = await tool.execute(arguments)
            assert result["success"] is False
            assert "rg (ripgrep) command not found" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_total_only_mode(self, tool, sample_project_structure):
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b"42", b"")

                with patch(
                    "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_count_output",
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
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b"10\n5\n", b"")

                with patch(
                    "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_count_output",
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

    @pytest.mark.asyncio
    async def test_execute_summary_only_mode(self, tool, sample_project_structure):
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b'{"path": "file1.py"}\n', b"")

                with patch(
                    "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py"}],
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.summarize_search_results",
                        return_value={"top_files": ["file1.py"]},
                    ):
                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "query": "test",
                            "summary_only": True,
                        }

                        result = await tool.execute(arguments)

                        assert result["success"] is True
                        assert "toon_content" in result

    @pytest.mark.asyncio
    async def test_execute_group_by_file_mode(self, tool, sample_project_structure):
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b'{"path": "file1.py"}\n', b"")

                with patch(
                    "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py"}],
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.group_matches_by_file",
                        return_value={
                            "success": True,
                            "count": 1,
                            "files": [{"path": "file1.py"}],
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

    @pytest.mark.asyncio
    async def test_execute_with_file_output(self, tool, sample_project_structure):
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b'{"path": "file1.py"}\n', b"")

                with patch(
                    "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py"}],
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
                        assert "output_file" in result

    @pytest.mark.asyncio
    async def test_execute_with_suppress_output(self, tool, sample_project_structure):
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b'{"path": "file1.py"}\n', b"")

                with patch(
                    "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py"}],
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
                        assert "output_file" in result
                        assert result["agent_summary"]["suppress_output"] is True
                        assert "results" not in result

    @pytest.mark.asyncio
    async def test_execute_with_toon_format(self, tool, sample_project_structure):
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b'{"path": "file1.py"}\n', b"")

                with patch(
                    "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py"}],
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.search_content_tool.apply_toon_format_to_response"
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

    @pytest.mark.asyncio
    async def test_execute_rg_failure(self, tool, sample_project_structure):
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (2, b"", b"ripgrep: error")

                arguments = {
                    "roots": [str(sample_project_structure)],
                    "query": "test",
                }

                result = await tool.execute(arguments)

                assert result["success"] is False
                assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_with_cache_hit(self, tool, sample_project_structure):
        tool.cache = MagicMock()
        tool.cache.get.return_value = {"success": True, "count": 5}
        tool.cache.create_cache_key.return_value = "cache_key"

        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            arguments = {
                "roots": [str(sample_project_structure)],
                "query": "test",
            }

            result = await tool.execute(arguments)

            assert result["cache_hit"] is True

    @pytest.mark.asyncio
    async def test_execute_with_cache_disabled(self, tool, sample_project_structure):
        tool_no_cache = SearchContentTool(enable_cache=False)

        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b"", b"")

                arguments = {
                    "roots": [str(sample_project_structure)],
                    "query": "test",
                }

                await tool_no_cache.execute(arguments)
                assert tool_no_cache.cache is None

    @pytest.mark.asyncio
    async def test_execute_with_parallel_processing(
        self, tool, sample_project_structure
    ):
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.split_roots_for_parallel_processing",
                return_value=[["root1"], ["root2"]],
            ):
                with patch(
                    "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_parallel_rg_searches",
                    new_callable=AsyncMock,
                ) as mock_parallel:
                    mock_parallel.return_value = (
                        (0, b"", b""),
                        (0, b"", b""),
                    )

                    with patch(
                        "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.merge_rg_results",
                        return_value=(0, b"", b""),
                    ):
                        arguments = {
                            "roots": [
                                str(sample_project_structure),
                                str(sample_project_structure / "src"),
                            ],
                            "query": "test",
                            "enable_parallel": True,
                        }

                        await tool.execute(arguments)
                        assert mock_parallel.called

    @pytest.mark.asyncio
    async def test_execute_with_files_parameter(self, tool, sample_project_structure):
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b"", b"")

                arguments = {
                    "files": [str(sample_project_structure / "README.md")],
                    "query": "test",
                }

                result = await tool.execute(arguments)
                assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_with_optimize_paths(self, tool, sample_project_structure):
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (
                    0,
                    b'{"path": "/very/long/path/to/file1.py"}\n',
                    b"",
                )

                with patch(
                    "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "/very/long/path/to/file1.py"}],
                ):
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.optimize_match_paths",
                        return_value=[{"path": "file1.py"}],
                    ):
                        arguments = {
                            "roots": [str(sample_project_structure)],
                            "query": "test",
                            "optimize_paths": True,
                        }

                        result = await tool.execute(arguments)
                        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_file_save_error(self, tool, sample_project_structure):
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b'{"path": "file1.py"}\n', b"")

                with patch(
                    "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.parse_rg_json_lines_to_matches",
                    return_value=[{"path": "file1.py"}],
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

    @pytest.mark.asyncio
    async def test_execute_with_timeout(self, tool, sample_project_structure):
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b"", b"")

                arguments = {
                    "roots": [str(sample_project_structure)],
                    "query": "test",
                    "timeout_ms": 5000,
                }

                result = await tool.execute(arguments)
                assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_with_max_count(self, tool, sample_project_structure):
        with patch(
            "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
            return_value=True,
        ):
            with patch(
                "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = (0, b"", b"")

                arguments = {
                    "roots": [str(sample_project_structure)],
                    "query": "test",
                    "max_count": 100,
                }

                result = await tool.execute(arguments)
                assert result["success"] is True
