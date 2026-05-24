"""
Test file output optimization for ListFilesTool.

Tests output_file and suppress_output parameters that reduce token consumption
by saving detailed results to files.
"""

import json
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool


@pytest.mark.asyncio
async def test_list_files_with_output_file_and_suppress_output(monkeypatch, tmp_path):
    tool = ListFilesTool(str(tmp_path))

    for i in range(3):
        test_file = tmp_path / f"test_{i}.py"
        test_file.write_text(f"# Test file {i}\nprint('hello')\n")

    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "nested.txt").write_text("nested content")

    fd_files = [str(tmp_path / f"test_{i}.py") for i in range(3)] + [
        str(subdir / "nested.txt")
    ]
    fd_output = "\n".join(fd_files) + "\n"

    async def mock_run_command(cmd, **kwargs):
        return (0, fd_output.encode(), b"")

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
        mock_run_command,
    )

    output_file = "file_list_results.json"
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "extensions": ["py", "txt"],
            "output_file": output_file,
            "suppress_output": True,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert "results" not in result
    assert result["output_file"].endswith(output_file)
    assert "message" in result

    saved_file_path = result["output_file"]
    assert Path(saved_file_path).exists()

    with open(saved_file_path, encoding="utf-8") as f:
        saved_data = json.load(f)

    assert saved_data["count"] == 4
    assert "results" in saved_data
    assert len(saved_data["results"]) == 4


@pytest.mark.asyncio
async def test_list_files_count_only_with_output_file(monkeypatch, tmp_path):
    tool = ListFilesTool(str(tmp_path))

    for i in range(5):
        test_file = tmp_path / f"data_{i}.json"
        test_file.write_text(f'{{"id": {i}}}')

    fd_files = [str(tmp_path / f"data_{i}.json") for i in range(5)]
    fd_output = "\n".join(fd_files) + "\n"

    async def mock_run_command(cmd, **kwargs):
        return (0, fd_output.encode(), b"")

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
        mock_run_command,
    )

    output_file = "count_results.json"
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "extensions": ["json"],
            "count_only": True,
            "output_file": output_file,
            "suppress_output": True,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert result["count_only"] is True
    assert result["total_count"] == 5
    assert result["output_file"].endswith(output_file)
    assert "message" in result

    saved_file_path = result["output_file"]
    assert Path(saved_file_path).exists()

    with open(saved_file_path, encoding="utf-8") as f:
        saved_data = json.load(f)

    assert saved_data["count_only"] is True
    assert saved_data["total_count"] == 5
    assert "query_info" in saved_data


@pytest.mark.asyncio
async def test_list_files_output_file_without_suppress_output(monkeypatch, tmp_path):
    tool = ListFilesTool(str(tmp_path))

    test_file = tmp_path / "example.md"
    test_file.write_text("# Example\nThis is a test file.")

    fd_output = str(test_file) + "\n"

    async def mock_run_command(cmd, **kwargs):
        return (0, fd_output.encode(), b"")

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
        mock_run_command,
    )

    output_file = "list_results_full.json"
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "extensions": ["md"],
            "output_file": output_file,
            "suppress_output": False,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert "results" in result
    assert result["output_file"].endswith(output_file)
    assert len(result["results"]) == 1

    saved_file_path = result["output_file"]
    assert Path(saved_file_path).exists()


@pytest.mark.asyncio
async def test_list_files_large_results_token_optimization(monkeypatch, tmp_path):
    tool = ListFilesTool(str(tmp_path))

    for i in range(20):
        test_file = tmp_path / f"large_file_{i:03d}.txt"
        test_file.write_text(f"Content of file {i}")

    fd_files = [str(tmp_path / f"large_file_{i:03d}.txt") for i in range(20)]
    fd_output = "\n".join(fd_files) + "\n"

    async def mock_run_command(cmd, **kwargs):
        return (0, fd_output.encode(), b"")

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.list_files_tool.fd_rg_utils.run_command_capture",
        mock_run_command,
    )

    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "large_file_*",
            "glob": True,
            "extensions": ["txt"],
            "output_file": "large_file_list.json",
            "suppress_output": True,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert "results" not in result
    assert result["output_file"].endswith("large_file_list.json")
    assert "message" in result

    saved_file_path = result["output_file"]
    assert Path(saved_file_path).exists()

    with open(saved_file_path, encoding="utf-8") as f:
        saved_data = json.load(f)

    assert saved_data["count"] == 20
    assert "results" in saved_data
    assert len(saved_data["results"]) == 20


@pytest.mark.unit
def test_list_files_validation_with_new_parameters(tmp_path):
    tool = ListFilesTool(str(tmp_path))

    valid_args = {
        "roots": [str(tmp_path)],
        "extensions": ["py"],
        "output_file": "results.json",
        "suppress_output": True,
    }

    tool.validate_arguments(valid_args)

    invalid_args = {
        "roots": [str(tmp_path)],
        "extensions": ["py"],
        "output_file": "results.json",
        "suppress_output": "invalid",
    }

    try:
        tool.validate_arguments(invalid_args)
        pass
    except ValueError as e:
        assert "suppress_output" in str(e) or "boolean" in str(e)
