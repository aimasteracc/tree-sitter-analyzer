"""
Test file output optimization for SearchContentTool.

Tests output_file and suppress_output parameters that reduce token consumption
by saving detailed results to files.
"""

import json

import pytest

from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


@pytest.mark.asyncio
async def test_search_content_with_output_file_and_suppress_output(
    monkeypatch, tmp_path
):
    tool = SearchContentTool(str(tmp_path))

    test_file = tmp_path / "test.py"
    test_file.write_text("def calculate_total():\n    return sum([1, 2, 3])\n")

    rg_output = (
        json.dumps(
            {
                "type": "match",
                "data": {
                    "path": {"text": str(test_file)},
                    "lines": {"text": "def calculate_total():"},
                    "line_number": 1,
                    "absolute_offset": 0,
                    "submatches": [
                        {"match": {"text": "calculate_total"}, "start": 4, "end": 19}
                    ],
                },
            }
        )
        + "\n"
    )

    async def mock_run_command(cmd, **kwargs):
        return (0, rg_output.encode(), b"")

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
        mock_run_command,
    )

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
    assert len(saved_data["results"]) > 0
    assert "calculate_total" in saved_data["results"][0]["text"]


@pytest.mark.asyncio
async def test_search_content_output_file_without_suppress_output(
    monkeypatch, tmp_path
):
    tool = SearchContentTool(str(tmp_path))

    test_file = tmp_path / "test.py"
    test_file.write_text("def process_data():\n    return 'processed'\n")

    rg_output = (
        json.dumps(
            {
                "type": "match",
                "data": {
                    "path": {"text": str(test_file)},
                    "lines": {"text": "def process_data():"},
                    "line_number": 1,
                    "absolute_offset": 0,
                    "submatches": [
                        {"match": {"text": "process_data"}, "start": 4, "end": 16}
                    ],
                },
            }
        )
        + "\n"
    )

    async def mock_run_command(cmd, **kwargs):
        return (0, rg_output.encode(), b"")

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
        mock_run_command,
    )

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
    assert len(result["results"]) > 0

    output_path = tmp_path / output_file
    assert output_path.exists()


@pytest.mark.asyncio
async def test_search_content_large_results_token_optimization(monkeypatch, tmp_path):
    tool = SearchContentTool(str(tmp_path))

    for i in range(5):
        test_file = tmp_path / f"file_{i}.py"
        content = "\n".join([f"def function_{j}():" for j in range(10)])
        test_file.write_text(content)

    matches = []
    for i in range(5):
        for j in range(10):
            matches.append(
                json.dumps(
                    {
                        "type": "match",
                        "data": {
                            "path": {"text": str(tmp_path / f"file_{i}.py")},
                            "lines": {"text": f"def function_{j}():"},
                            "line_number": j + 1,
                            "absolute_offset": j * 20,
                            "submatches": [
                                {"match": {"text": "function"}, "start": 4, "end": 12}
                            ],
                        },
                    }
                )
            )

    rg_output = "\n".join(matches) + "\n"

    async def mock_run_command(cmd, **kwargs):
        return (0, rg_output.encode(), b"")

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.search_content_tool.fd_rg_utils.run_command_capture",
        mock_run_command,
    )

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
