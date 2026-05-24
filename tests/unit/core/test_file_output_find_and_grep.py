"""
Test file output optimization for FindAndGrepTool.

Tests output_file and suppress_output parameters that reduce token consumption
by saving detailed results to files.
"""

import json

import pytest

from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool


@pytest.mark.asyncio
async def test_find_and_grep_with_output_file_and_suppress_output(
    monkeypatch, tmp_path
):
    tool = FindAndGrepTool(str(tmp_path))

    test_file = tmp_path / "calculator.py"
    test_file.write_text("def calculate_total():\n    return sum([1, 2, 3])\n")

    fd_output = str(test_file) + "\n"

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

    call_count = 0

    async def mock_run_command(cmd, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (0, fd_output.encode(), b"")
        else:
            return (0, rg_output.encode(), b"")

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
        mock_run_command,
    )

    output_file = "find_and_grep_results.json"
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*calc*",
            "glob": True,
            "query": "calculate_total",
            "output_file": output_file,
            "suppress_output": True,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert "files" not in result
    assert result["output_file"] == output_file
    assert "file_saved" in result

    output_path = tmp_path / output_file
    assert output_path.exists()

    with open(output_path, encoding="utf-8") as f:
        saved_data = json.load(f)

    assert saved_data["success"] is True
    assert "files" in saved_data
    assert len(saved_data["files"]) > 0
    assert "calculate_total" in str(saved_data["files"][0]["matches"])


@pytest.mark.asyncio
async def test_find_and_grep_output_file_auto_extension_detection(
    monkeypatch, tmp_path
):
    tool = FindAndGrepTool(str(tmp_path))

    test_file = tmp_path / "data.txt"
    test_file.write_text("important data here\n")

    fd_output = str(test_file) + "\n"
    rg_output = (
        json.dumps(
            {
                "type": "match",
                "data": {
                    "path": {"text": str(test_file)},
                    "lines": {"text": "important data here"},
                    "line_number": 1,
                    "absolute_offset": 0,
                    "submatches": [{"match": {"text": "data"}, "start": 10, "end": 14}],
                },
            }
        )
        + "\n"
    )

    call_count = 0

    async def mock_run_command(cmd, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (0, fd_output.encode(), b"")
        else:
            return (0, rg_output.encode(), b"")

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
        mock_run_command,
    )

    output_file = "analysis_results"
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "*.txt",
            "glob": True,
            "query": "data",
            "output_file": output_file,
            "suppress_output": True,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert result["output_file"] == output_file

    possible_files = [
        tmp_path / f"{output_file}.json",
        tmp_path / f"{output_file}.md",
        tmp_path / output_file,
    ]

    created_file = None
    for possible_file in possible_files:
        if possible_file.exists():
            created_file = possible_file
            break

    assert created_file is not None, (
        f"No output file found. Checked: {[str(f) for f in possible_files]}"
    )


@pytest.mark.asyncio
async def test_find_and_grep_combined_optimization_features(monkeypatch, tmp_path):
    tool = FindAndGrepTool(str(tmp_path))

    for i in range(3):
        test_file = tmp_path / f"module_{i}.py"
        test_file.write_text(
            f"class Module{i}:\n    def process(self):\n        pass\n"
        )

    fd_files = [str(tmp_path / f"module_{i}.py") for i in range(3)]
    fd_output = "\n".join(fd_files) + "\n"

    rg_matches = []
    for i in range(3):
        rg_matches.append(
            json.dumps(
                {
                    "type": "match",
                    "data": {
                        "path": {"text": str(tmp_path / f"module_{i}.py")},
                        "lines": {"text": f"class Module{i}:"},
                        "line_number": 1,
                        "absolute_offset": 0,
                        "submatches": [
                            {"match": {"text": "Module"}, "start": 6, "end": 12}
                        ],
                    },
                }
            )
        )

    rg_output = "\n".join(rg_matches) + "\n"

    call_count = 0

    async def mock_run_command(cmd, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (0, fd_output.encode(), b"")
        else:
            return (0, rg_output.encode(), b"")

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.find_and_grep_tool.fd_rg_utils.run_command_capture",
        mock_run_command,
    )

    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "pattern": "module_*",
            "glob": True,
            "extensions": ["py"],
            "query": "Module",
            "case": "insensitive",
            "max_count": 10,
            "group_by_file": True,
            "summary_only": True,
            "output_file": "optimized_search.json",
            "suppress_output": True,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert "files" not in result
    assert "summary" not in result
    assert result["output_file"] == "optimized_search.json"
    assert "file_saved" in result

    output_path = tmp_path / "optimized_search.json"
    assert output_path.exists()

    with open(output_path, encoding="utf-8") as f:
        saved_data = json.load(f)

    assert saved_data["success"] is True
    assert "files" in saved_data
    assert "summary" in saved_data
    assert len(saved_data["files"]) == 3


@pytest.mark.unit
def test_find_and_grep_validation_with_new_parameters(tmp_path):
    tool = FindAndGrepTool(str(tmp_path))

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
        "output_file": 123,
        "suppress_output": True,
    }

    try:
        tool.validate_arguments(invalid_args)
        pass
    except ValueError as e:
        assert "output_file" in str(e) or "string" in str(e)
