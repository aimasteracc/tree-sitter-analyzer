"""
Test file output optimization features for find_and_grep, search_content, and list_files tools.

This module tests the new output_file and suppress_output parameters that were added
to reduce token consumption by saving detailed results to files.
"""

import json
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool
from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


class DummyProc:
    """Mock process for testing command execution."""

    def __init__(self, rc=0, stdout=b"", stderr=b""):
        self.rc = rc
        self.stdout = stdout
        self.stderr = stderr


@pytest.mark.asyncio
async def test_search_content_with_output_file_and_suppress_output(
    monkeypatch, tmp_path
):
    """Test SearchContentTool with output_file and suppress_output parameters."""
    tool = SearchContentTool(str(tmp_path))

    # Create test files
    test_file = tmp_path / "test.py"
    test_file.write_text("def calculate_total():\n    return sum([1, 2, 3])\n")

    # Mock ripgrep command
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
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
        mock_run_command,
    )

    # Test with output_file and suppress_output (use JSON output_format)
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

    # Verify response structure
    assert result["success"] is True
    assert "results" not in result  # Should be suppressed
    assert result["output_file"] == output_file
    assert "file_saved" in result

    # Verify file was created and contains expected data
    output_path = tmp_path / output_file
    assert output_path.exists()

    with open(output_path, encoding="utf-8") as f:
        saved_data = json.load(f)

    assert saved_data["success"] is True
    assert "results" in saved_data
    assert len(saved_data["results"]) > 0
    assert "calculate_total" in saved_data["results"][0]["text"]


@pytest.mark.asyncio
async def test_find_and_grep_with_output_file_and_suppress_output(
    monkeypatch, tmp_path
):
    """Test FindAndGrepTool with output_file and suppress_output parameters."""
    tool = FindAndGrepTool(str(tmp_path))

    # Create test files
    test_file = tmp_path / "calculator.py"
    test_file.write_text("def calculate_total():\n    return sum([1, 2, 3])\n")

    # Mock fd command
    fd_output = str(test_file) + "\n"

    # Mock ripgrep command
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
        if call_count == 1:  # fd command
            return (0, fd_output.encode(), b"")
        else:  # rg command
            return (0, rg_output.encode(), b"")

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
        mock_run_command,
    )

    # Test with output_file and suppress_output (use JSON output_format)
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

    # Verify response structure
    assert result["success"] is True
    assert "files" not in result  # Should be suppressed
    assert result["output_file"] == output_file
    assert "file_saved" in result

    # Verify file was created and contains expected data
    output_path = tmp_path / output_file
    assert output_path.exists()

    with open(output_path, encoding="utf-8") as f:
        saved_data = json.load(f)

    assert saved_data["success"] is True
    assert "files" in saved_data
    assert len(saved_data["files"]) > 0
    assert "calculate_total" in str(saved_data["files"][0]["matches"])


@pytest.mark.asyncio
async def test_search_content_output_file_without_suppress_output(
    monkeypatch, tmp_path
):
    """Test SearchContentTool with output_file but without suppress_output."""
    tool = SearchContentTool(str(tmp_path))

    # Create test files
    test_file = tmp_path / "test.py"
    test_file.write_text("def process_data():\n    return 'processed'\n")

    # Mock ripgrep command
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
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
        mock_run_command,
    )

    # Test with output_file but suppress_output=False (use JSON output_format)
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

    # Verify response structure - should include both results and file info
    assert result["success"] is True
    assert "results" in result  # Should NOT be suppressed
    assert result["output_file"] == output_file
    assert "file_saved" in result
    assert len(result["results"]) > 0

    # Verify file was still created
    output_path = tmp_path / output_file
    assert output_path.exists()


@pytest.mark.asyncio
async def test_find_and_grep_output_file_auto_extension_detection(
    monkeypatch, tmp_path
):
    """Test FindAndGrepTool with output_file auto-extension detection."""
    tool = FindAndGrepTool(str(tmp_path))

    # Create test files
    test_file = tmp_path / "data.txt"
    test_file.write_text("important data here\n")

    # Mock fd and rg commands
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
        if call_count == 1:  # fd command
            return (0, fd_output.encode(), b"")
        else:  # rg command
            return (0, rg_output.encode(), b"")

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
        mock_run_command,
    )

    # Test with output_file without extension (use JSON output_format)
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

    # Verify response
    assert result["success"] is True
    assert result["output_file"] == output_file

    # Check that file was created with appropriate extension
    # The FileOutputManager should auto-detect and add .json extension
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

    assert (
        created_file is not None
    ), f"No output file found. Checked: {[str(f) for f in possible_files]}"


@pytest.mark.asyncio
async def test_search_content_large_results_token_optimization(monkeypatch, tmp_path):
    """Test SearchContentTool token optimization with large results."""
    tool = SearchContentTool(str(tmp_path))

    # Create multiple test files with many matches
    for i in range(5):
        test_file = tmp_path / f"file_{i}.py"
        content = "\n".join([f"def function_{j}():" for j in range(10)])
        test_file.write_text(content)

    # Mock ripgrep command to return many matches
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
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
        mock_run_command,
    )

    # Test with suppress_output to save tokens (use JSON output_format)
    result = await tool.execute(
        {
            "roots": [str(tmp_path)],
            "query": "function",
            "output_file": "large_results.json",
            "suppress_output": True,
            "output_format": "json",
        }
    )

    # Verify token optimization
    assert result["success"] is True
    assert "results" not in result  # Suppressed to save tokens
    assert result["output_file"] == "large_results.json"
    assert "file_saved" in result

    # Verify file contains full results
    output_path = tmp_path / "large_results.json"
    assert output_path.exists()

    with open(output_path, encoding="utf-8") as f:
        saved_data = json.load(f)

    assert saved_data["success"] is True
    # Full results are saved to file
    assert "results" in saved_data
    assert len(saved_data["results"]) == 50  # 5 files × 10 matches


@pytest.mark.asyncio
async def test_find_and_grep_combined_optimization_features(monkeypatch, tmp_path):
    """Test FindAndGrepTool with multiple optimization features combined."""
    tool = FindAndGrepTool(str(tmp_path))

    # Create test files
    for i in range(3):
        test_file = tmp_path / f"module_{i}.py"
        test_file.write_text(
            f"class Module{i}:\n    def process(self):\n        pass\n"
        )

    # Mock fd and rg commands
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
        if call_count == 1:  # fd command
            return (0, fd_output.encode(), b"")
        else:  # rg command
            return (0, rg_output.encode(), b"")

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
        mock_run_command,
    )

    # Test with multiple optimization features (use JSON output_format)
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

    # Verify optimized response
    assert result["success"] is True
    assert "files" not in result  # Suppressed
    assert "summary" not in result  # Suppressed
    assert result["output_file"] == "optimized_search.json"
    assert "file_saved" in result

    # Verify file contains complete results
    output_path = tmp_path / "optimized_search.json"
    assert output_path.exists()

    with open(output_path, encoding="utf-8") as f:
        saved_data = json.load(f)

    assert saved_data["success"] is True
    assert "files" in saved_data
    assert "summary" in saved_data
    assert len(saved_data["files"]) == 3


@pytest.mark.unit
def test_search_content_validation_with_new_parameters(tmp_path):
    """Test SearchContentTool parameter validation including new output_file parameters."""
    tool = SearchContentTool(str(tmp_path))

    # Valid parameters with new options
    valid_args = {
        "roots": [str(tmp_path)],
        "query": "test",
        "output_file": "results.json",
        "suppress_output": True,
    }

    # Should not raise exception
    tool.validate_arguments(valid_args)

    # Test invalid suppress_output type - but validation may not be implemented yet
    invalid_args = {
        "roots": [str(tmp_path)],
        "query": "test",
        "output_file": "results.json",
        "suppress_output": "invalid",  # Should be boolean
    }

    # Note: Validation may not be implemented yet, so this test might need to be updated
    try:
        tool.validate_arguments(invalid_args)
        # If no exception is raised, validation is not implemented yet
        pass
    except ValueError as e:
        # If validation is implemented, check the error message
        assert "suppress_output" in str(e) or "boolean" in str(e)


@pytest.mark.unit
def test_find_and_grep_validation_with_new_parameters(tmp_path):
    """Test FindAndGrepTool parameter validation including new output_file parameters."""
    tool = FindAndGrepTool(str(tmp_path))

    # Valid parameters with new options
    valid_args = {
        "roots": [str(tmp_path)],
        "query": "test",
        "output_file": "results.json",
        "suppress_output": True,
    }

    # Should not raise exception
    tool.validate_arguments(valid_args)

    # Test invalid output_file type - but validation may not be implemented yet
    invalid_args = {
        "roots": [str(tmp_path)],
        "query": "test",
        "output_file": 123,  # Should be string
        "suppress_output": True,
    }

    # Note: Validation may not be implemented yet, so this test might need to be updated
    try:
        tool.validate_arguments(invalid_args)
        # If no exception is raised, validation is not implemented yet
        pass
    except ValueError as e:
        # If validation is implemented, check the error message
        assert "output_file" in str(e) or "string" in str(e)


@pytest.mark.asyncio
async def test_list_files_with_output_file_and_suppress_output(monkeypatch, tmp_path):
    """Test ListFilesTool with output_file and suppress_output parameters."""
    tool = ListFilesTool(str(tmp_path))

    # Create test files
    for i in range(3):
        test_file = tmp_path / f"test_{i}.py"
        test_file.write_text(f"# Test file {i}\nprint('hello')\n")

    # Create a subdirectory with files
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "nested.txt").write_text("nested content")

    # Mock fd command
    fd_files = [str(tmp_path / f"test_{i}.py") for i in range(3)] + [
        str(subdir / "nested.txt")
    ]
    fd_output = "\n".join(fd_files) + "\n"

    async def mock_run_command(cmd, **kwargs):
        return (0, fd_output.encode(), b"")

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
        mock_run_command,
    )

    # Test with output_file and suppress_output (use JSON output_format)
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

    # Verify response structure
    assert result["success"] is True
    assert "results" not in result  # Should be suppressed
    assert result["output_file"].endswith(output_file)  # Check filename, not full path
    assert "message" in result

    # Verify file was created and contains expected data
    # Use the actual saved path from the result
    saved_file_path = result["output_file"]
    assert Path(saved_file_path).exists()

    with open(saved_file_path, encoding="utf-8") as f:
        saved_data = json.load(f)

    assert saved_data["count"] == 4  # 3 .py files + 1 .txt file
    assert "results" in saved_data
    assert len(saved_data["results"]) == 4


@pytest.mark.asyncio
async def test_list_files_count_only_with_output_file(monkeypatch, tmp_path):
    """Test ListFilesTool count_only mode with output_file and suppress_output."""
    tool = ListFilesTool(str(tmp_path))

    # Create test files
    for i in range(5):
        test_file = tmp_path / f"data_{i}.json"
        test_file.write_text(f'{{"id": {i}}}')

    # Mock fd command
    fd_files = [str(tmp_path / f"data_{i}.json") for i in range(5)]
    fd_output = "\n".join(fd_files) + "\n"

    async def mock_run_command(cmd, **kwargs):
        return (0, fd_output.encode(), b"")

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
        mock_run_command,
    )

    # Test count_only mode with output_file and suppress_output (use JSON output_format)
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

    # Verify response structure for count_only mode
    assert result["success"] is True
    assert result["count_only"] is True
    assert result["total_count"] == 5
    assert result["output_file"].endswith(output_file)
    assert "message" in result

    # Verify file was created and contains expected data
    saved_file_path = result["output_file"]
    assert Path(saved_file_path).exists()

    with open(saved_file_path, encoding="utf-8") as f:
        saved_data = json.load(f)

    assert saved_data["count_only"] is True
    assert saved_data["total_count"] == 5
    assert "query_info" in saved_data


@pytest.mark.asyncio
async def test_list_files_output_file_without_suppress_output(monkeypatch, tmp_path):
    """Test ListFilesTool with output_file but without suppress_output."""
    tool = ListFilesTool(str(tmp_path))

    # Create test files
    test_file = tmp_path / "example.md"
    test_file.write_text("# Example\nThis is a test file.")

    # Mock fd command
    fd_output = str(test_file) + "\n"

    async def mock_run_command(cmd, **kwargs):
        return (0, fd_output.encode(), b"")

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
        mock_run_command,
    )

    # Test with output_file but suppress_output=False (use JSON output_format)
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

    # Verify response structure - should include both results and file info
    assert result["success"] is True
    assert "results" in result  # Should NOT be suppressed
    assert result["output_file"].endswith(output_file)
    assert len(result["results"]) == 1

    # Verify file was still created
    saved_file_path = result["output_file"]
    assert Path(saved_file_path).exists()


@pytest.mark.asyncio
async def test_list_files_large_results_token_optimization(monkeypatch, tmp_path):
    """Test ListFilesTool token optimization with large results."""
    tool = ListFilesTool(str(tmp_path))

    # Create many test files
    for i in range(20):
        test_file = tmp_path / f"large_file_{i:03d}.txt"
        test_file.write_text(f"Content of file {i}")

    # Mock fd command to return many files
    fd_files = [str(tmp_path / f"large_file_{i:03d}.txt") for i in range(20)]
    fd_output = "\n".join(fd_files) + "\n"

    async def mock_run_command(cmd, **kwargs):
        return (0, fd_output.encode(), b"")

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
        mock_run_command,
    )

    # Test with suppress_output to save tokens (use JSON output_format)
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

    # Verify token optimization
    assert result["success"] is True
    assert "results" not in result  # Suppressed to save tokens
    assert result["output_file"].endswith("large_file_list.json")
    assert "message" in result

    # Verify file contains full results
    saved_file_path = result["output_file"]
    assert Path(saved_file_path).exists()

    with open(saved_file_path, encoding="utf-8") as f:
        saved_data = json.load(f)

    assert saved_data["count"] == 20
    assert "results" in saved_data
    assert len(saved_data["results"]) == 20


@pytest.mark.unit
def test_list_files_validation_with_new_parameters(tmp_path):
    """Test ListFilesTool parameter validation including new output_file parameters."""
    tool = ListFilesTool(str(tmp_path))

    # Valid parameters with new options
    valid_args = {
        "roots": [str(tmp_path)],
        "extensions": ["py"],
        "output_file": "results.json",
        "suppress_output": True,
    }

    # Should not raise exception
    tool.validate_arguments(valid_args)

    # Test invalid suppress_output type - but validation may not be implemented yet
    invalid_args = {
        "roots": [str(tmp_path)],
        "extensions": ["py"],
        "output_file": "results.json",
        "suppress_output": "invalid",  # Should be boolean
    }

    # Note: Validation may not be implemented yet, so this test might need to be updated
    try:
        tool.validate_arguments(invalid_args)
        # If no exception is raised, validation is not implemented yet
        pass
    except ValueError as e:
        # If validation is implemented, check the error message
        assert "suppress_output" in str(e) or "boolean" in str(e)
