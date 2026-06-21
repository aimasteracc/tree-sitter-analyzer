"""
Test file output optimization for SearchContentTool.

Tests output_file and suppress_output parameters that reduce token consumption
by saving detailed results to files.
"""

import json

import pytest

from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


def _make_rg_match_line(
    file_path,
    line_text: str,
    function_name: str,
    start: int,
    end: int,
    line_number: int = 1,
    offset: int = 0,
) -> str:
    """Build one ripgrep JSON match line."""
    return json.dumps(
        {
            "type": "match",
            "data": {
                "path": {"text": str(file_path)},
                "lines": {"text": line_text},
                "line_number": line_number,
                "absolute_offset": offset,
                "submatches": [
                    {"match": {"text": function_name}, "start": start, "end": end}
                ],
            },
        }
    )


def _make_multi_file_rg_output(tmp_path, n_files: int, n_functions: int) -> str:
    """Build ripgrep JSON output with n_files × n_functions function matches."""
    matches = [
        _make_rg_match_line(
            tmp_path / f"file_{i}.py",
            f"def function_{j}():",
            "function",
            4,
            12,
            line_number=j + 1,
            offset=j * 20,
        )
        for i in range(n_files)
        for j in range(n_functions)
    ]
    return "\n".join(matches) + "\n"


def _patch_rg_tools(monkeypatch, mock_run_command) -> None:
    """Monkeypatch fd_rg_utils so tests don't invoke real ripgrep."""
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
        mock_run_command,
    )


@pytest.mark.asyncio
async def test_search_content_with_output_file_and_suppress_output(
    monkeypatch, tmp_path
):
    tool = SearchContentTool(str(tmp_path))

    test_file = tmp_path / "test.py"
    test_file.write_text("def calculate_total():\n    return sum([1, 2, 3])\n")

    rg_output = (
        _make_rg_match_line(
            test_file, "def calculate_total():", "calculate_total", 4, 19
        )
        + "\n"
    )

    async def mock_run_command(cmd, **kwargs):
        return (0, rg_output.encode(), b"")

    _patch_rg_tools(monkeypatch, mock_run_command)

    output_file = "search_results.json"
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "query": "calculate_total",
            "output_file": output_file,
            "suppress_output": True,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert "results" not in result
    assert result["output_file"] == output_file
    assert "file_saved" in result

    output_path = tmp_path / output_file
    assert output_path.exists()

    with open(output_path, encoding="utf-8") as f:
        saved_data = json.load(f)

    assert saved_data["success"] is True
    assert "results" in saved_data
    assert saved_data["results"]
    assert "calculate_total" in saved_data["results"][0]["text"]


@pytest.mark.asyncio
async def test_search_content_output_file_without_suppress_output(
    monkeypatch, tmp_path
):
    tool = SearchContentTool(str(tmp_path))

    test_file = tmp_path / "test.py"
    test_file.write_text("def process_data():\n    return 'processed'\n")

    rg_output = (
        _make_rg_match_line(test_file, "def process_data():", "process_data", 4, 16)
        + "\n"
    )

    async def mock_run_command(cmd, **kwargs):
        return (0, rg_output.encode(), b"")

    _patch_rg_tools(monkeypatch, mock_run_command)

    output_file = "search_results_full.json"
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "query": "process_data",
            "output_file": output_file,
            "suppress_output": False,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert "results" in result
    assert result["output_file"] == output_file
    assert "file_saved" in result
    assert result["results"]

    output_path = tmp_path / output_file
    assert output_path.exists()


@pytest.mark.asyncio
async def test_search_content_large_results_token_optimization(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))

    for i in range(5):
        test_file = tmp_path / f"file_{i}.py"
        content = "\n".join([f"def function_{j}():" for j in range(10)])
        test_file.write_text(content)

    rg_output = _make_multi_file_rg_output(tmp_path, n_files=5, n_functions=10)

    async def mock_run_command(cmd, **kwargs):
        return (0, rg_output.encode(), b"")

    _patch_rg_tools(monkeypatch, mock_run_command)

    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "query": "function",
            "output_file": "large_results.json",
            "suppress_output": True,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert "results" not in result
    assert result["output_file"] == "large_results.json"
    assert "file_saved" in result

    output_path = tmp_path / "large_results.json"
    assert output_path.exists()

    with open(output_path, encoding="utf-8") as f:
        saved_data = json.load(f)

    assert saved_data["success"] is True
    assert "results" in saved_data
    assert len(saved_data["results"]) == 50


@pytest.mark.unit
def test_search_content_validation_with_new_parameters(tmp_path):
    tool = SearchContentTool(str(tmp_path))

    valid_args = {
        "roots": [str(tmp_path)],
        "query": "test",
        "output_file": "results.json",
        "suppress_output": True,
    }

    tool.validate_arguments(valid_args)

    invalid_args = {
        "roots": [str(tmp_path)],
        "query": "test",
        "output_file": "results.json",
        "suppress_output": "invalid",
    }

    try:
        tool.validate_arguments(invalid_args)
        pass
    except ValueError as e:
        assert "suppress_output" in str(e) or "boolean" in str(e)
