#!/usr/bin/env python3
"""
Test find_and_grep_tool file output functionality

Tests the enhanced file output and suppress_output features
for the find_and_grep MCP tool.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool


class TestFindAndGrepToolFileOutput:
    """Test file output functionality for FindAndGrepTool"""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with test files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create test files with different extensions
            (project_path / "test1.py").write_text("""
def hello_world():
    print("Hello, World!")
    return "success"

class TestClass:
    def __init__(self):
        self.value = 42
""")

            (project_path / "test2.js").write_text("""
function helloWorld() {
    console.log("Hello, World!");
    return "success";
}

class TestClass {
    constructor() {
        this.value = 42;
    }
}
""")

            (project_path / "README.md").write_text("""
# Test Project

This is a test project for hello world examples.
""")

            # Create subdirectory
            subdir = project_path / "subdir"
            subdir.mkdir()
            (subdir / "nested.py").write_text("""
def nested_hello():
    print("Nested hello!")
""")

            yield str(project_path)

    @pytest.fixture
    def find_and_grep_tool(self, temp_project_dir):
        """Create FindAndGrepTool instance"""
        return FindAndGrepTool(project_root=temp_project_dir)

    @pytest.mark.asyncio
    async def test_basic_file_output(self, find_and_grep_tool, temp_project_dir):
        """Test basic file output functionality"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock fd output (file discovery)
            fd_output = f"{temp_project_dir}/test1.py\n{temp_project_dir}/test2.js\n"
            # Mock ripgrep output (content search)
            rg_output = b"""{"type":"match","data":{"path":{"text":"test1.py"},"lines":{"text":"def hello_world():"},"line_number":2,"absolute_offset":1,"submatches":[{"match":{"text":"hello"},"start":4,"end":9}]}}
{"type":"match","data":{"path":{"text":"test2.js"},"lines":{"text":"function helloWorld() {"},"line_number":1,"absolute_offset":0,"submatches":[{"match":{"text":"hello"},"start":9,"end":14}]}}
"""

            # First call for fd, second call for rg
            mock_run.side_effect = [
                (0, fd_output.encode(), b""),  # fd result
                (0, rg_output, b""),  # rg result
            ]

            arguments = {
                "roots": [temp_project_dir],
                "query": "hello",
                "extensions": ["py", "js"],
                "output_file": "find_grep_basic",
                "suppress_output": False,
            }

            result = await find_and_grep_tool.execute(arguments)

            # Check basic result structure
            assert result["success"] is True
            assert "count" in result
            assert "results" in result
            assert "meta" in result

            # Check file output
            assert "output_file" in result
            assert "file_saved" in result
            assert "Results saved to" in result["file_saved"]

            # Extract and verify file path
            file_path = result["file_saved"].split("Results saved to ")[1]
            output_file = Path(file_path)
            assert output_file.exists()

            # Verify file content
            with open(output_file, encoding="utf-8") as f:
                saved_content = json.loads(f.read())

            assert "success" in saved_content
            assert "results" in saved_content
            assert "count" in saved_content
            assert "files" in saved_content
            assert "summary" in saved_content
            assert "meta" in saved_content

    @pytest.mark.asyncio
    async def test_suppress_output_functionality(
        self, find_and_grep_tool, temp_project_dir
    ):
        """Test suppress_output functionality"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock outputs
            fd_output = f"{temp_project_dir}/test1.py\n"
            rg_output = b'{"type":"match","data":{"path":{"text":"test1.py"},"lines":{"text":"def hello_world():"},"line_number":2,"absolute_offset":1,"submatches":[{"match":{"text":"hello"},"start":4,"end":9}]}}\n'

            mock_run.side_effect = [(0, fd_output.encode(), b""), (0, rg_output, b"")]

            arguments = {
                "roots": [temp_project_dir],
                "query": "hello",
                "output_file": "find_grep_suppressed",
                "suppress_output": True,
            }

            result = await find_and_grep_tool.execute(arguments)

            # Check that detailed results are suppressed
            assert "results" not in result
            assert "success" in result
            assert "count" in result
            assert "output_file" in result
            assert "file_saved" in result

            # Verify file was still created with full content
            file_path = result["file_saved"].split("Results saved to ")[1]
            output_file = Path(file_path)
            assert output_file.exists()

            with open(output_file, encoding="utf-8") as f:
                saved_content = json.loads(f.read())

            # File should contain full results even when output is suppressed
            assert "results" in saved_content
            assert "files" in saved_content

    @pytest.mark.asyncio
    async def test_group_by_file_with_output(
        self, find_and_grep_tool, temp_project_dir
    ):
        """Test group_by_file mode with file output"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock outputs with multiple matches in same file
            fd_output = f"{temp_project_dir}/test1.py\n"
            rg_output = b"""{"type":"match","data":{"path":{"text":"test1.py"},"lines":{"text":"def hello_world():"},"line_number":2,"absolute_offset":1,"submatches":[{"match":{"text":"hello"},"start":4,"end":9}]}}
{"type":"match","data":{"path":{"text":"test1.py"},"lines":{"text":"    print(\\"Hello, World!\\")"},"line_number":3,"absolute_offset":20,"submatches":[{"match":{"text":"Hello"},"start":11,"end":16}]}}
"""

            mock_run.side_effect = [(0, fd_output.encode(), b""), (0, rg_output, b"")]

            arguments = {
                "roots": [temp_project_dir],
                "query": "hello",
                "group_by_file": True,
                "output_file": "find_grep_grouped",
                "suppress_output": False,
            }

            result = await find_and_grep_tool.execute(arguments)

            # Check grouped result structure
            assert "success" in result
            assert "files" in result
            assert "count" in result

            # Check file output
            assert "output_file" in result
            assert "file_saved" in result

            # Verify file content has grouped structure
            file_path = result["file_saved"].split("Results saved to ")[1]
            output_file = Path(file_path)

            with open(output_file, encoding="utf-8") as f:
                saved_content = json.loads(f.read())

            assert "files" in saved_content
            assert isinstance(saved_content["files"], list)

    @pytest.mark.asyncio
    async def test_summary_only_with_output(self, find_and_grep_tool, temp_project_dir):
        """Test summary_only mode with file output"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock outputs
            fd_output = f"{temp_project_dir}/test1.py\n{temp_project_dir}/test2.js\n"
            rg_output = b"""{"type":"match","data":{"path":{"text":"test1.py"},"lines":{"text":"def hello_world():"},"line_number":2,"absolute_offset":1,"submatches":[{"match":{"text":"hello"},"start":4,"end":9}]}}
{"type":"match","data":{"path":{"text":"test2.js"},"lines":{"text":"function helloWorld() {"},"line_number":1,"absolute_offset":0,"submatches":[{"match":{"text":"hello"},"start":9,"end":14}]}}
"""

            mock_run.side_effect = [(0, fd_output.encode(), b""), (0, rg_output, b"")]

            arguments = {
                "roots": [temp_project_dir],
                "query": "hello",
                "summary_only": True,
                "output_file": "find_grep_summary",
                "suppress_output": True,
            }

            result = await find_and_grep_tool.execute(arguments)

            # Check summary result structure
            assert "success" in result
            assert "count" in result
            assert "output_file" in result
            assert "file_saved" in result

            # Verify file content has summary structure
            file_path = result["file_saved"].split("Results saved to ")[1]
            output_file = Path(file_path)

            with open(output_file, encoding="utf-8") as f:
                saved_content = json.loads(f.read())

            assert "summary_only" in saved_content
            assert "summary" in saved_content

    @pytest.mark.asyncio
    async def test_count_only_mode(self, find_and_grep_tool, temp_project_dir):
        """Test count_only_matches mode"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock outputs
            fd_output = f"{temp_project_dir}/test1.py\n"
            # Mock count output from ripgrep
            rg_count_output = b"test1.py:2\n"

            mock_run.side_effect = [
                (0, fd_output.encode(), b""),
                (0, rg_count_output, b""),
            ]

            arguments = {
                "roots": [temp_project_dir],
                "query": "hello",
                "count_only_matches": True,
            }

            result = await find_and_grep_tool.execute(arguments)

            # Check count-only result structure
            assert "success" in result
            assert "count_only" in result
            assert "total_matches" in result
            assert "file_counts" in result
            assert "meta" in result

    @pytest.mark.asyncio
    async def test_total_only_mode(self, find_and_grep_tool, temp_project_dir):
        """Test total_only mode"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock outputs
            fd_output = f"{temp_project_dir}/test1.py\n"
            # Mock count output from ripgrep
            rg_count_output = b"test1.py:2\n"

            mock_run.side_effect = [
                (0, fd_output.encode(), b""),
                (0, rg_count_output, b""),
            ]

            arguments = {
                "roots": [temp_project_dir],
                "query": "hello",
                "total_only": True,
            }

            result = await find_and_grep_tool.execute(arguments)

            # Check that result is just a number
            assert isinstance(result, int)
            assert result >= 0

    @pytest.mark.asyncio
    async def test_file_filtering_options(self, find_and_grep_tool, temp_project_dir):
        """Test various file filtering options with output"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock outputs
            fd_output = f"{temp_project_dir}/test1.py\n"
            rg_output = b'{"type":"match","data":{"path":{"text":"test1.py"},"lines":{"text":"def hello_world():"},"line_number":2,"absolute_offset":1,"submatches":[{"match":{"text":"hello"},"start":4,"end":9}]}}\n'

            mock_run.side_effect = [(0, fd_output.encode(), b""), (0, rg_output, b"")]

            arguments = {
                "roots": [temp_project_dir],
                "query": "hello",
                "pattern": "*.py",
                "glob": True,
                "extensions": ["py"],
                "types": ["f"],
                "exclude": ["*.md"],
                "output_file": "find_grep_filtered",
                "suppress_output": False,
            }

            result = await find_and_grep_tool.execute(arguments)

            assert result["success"] is True
            assert "output_file" in result
            assert "file_saved" in result

    @pytest.mark.asyncio
    async def test_error_handling_with_output(
        self, find_and_grep_tool, temp_project_dir
    ):
        """Test error handling when file output fails"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock successful fd and rg outputs
            fd_output = f"{temp_project_dir}/test1.py\n"
            rg_output = b'{"type":"match","data":{"path":{"text":"test1.py"},"lines":{"text":"def hello_world():"},"line_number":2,"absolute_offset":1,"submatches":[{"match":{"text":"hello"},"start":4,"end":9}]}}\n'

            mock_run.side_effect = [(0, fd_output.encode(), b""), (0, rg_output, b"")]

            # Mock FileOutputManager to raise an exception
            with patch.object(
                find_and_grep_tool.file_output_manager, "save_to_file"
            ) as mock_save:
                mock_save.side_effect = Exception("File save error")

                arguments = {
                    "roots": [temp_project_dir],
                    "query": "hello",
                    "output_file": "error_test",
                    "suppress_output": False,
                }

                result = await find_and_grep_tool.execute(arguments)

                # Check error handling
                assert "file_save_error" in result
                assert "file_saved" in result
                assert result["file_saved"] is False
                assert "File save error" in result["file_save_error"]

    @pytest.mark.asyncio
    async def test_fd_failure_handling(self, find_and_grep_tool, temp_project_dir):
        """Test handling of fd command failure"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock fd failure
            mock_run.return_value = (1, b"", b"fd error")

            arguments = {
                "roots": [temp_project_dir],
                "query": "hello",
                "output_file": "fd_error_test",
            }

            result = await find_and_grep_tool.execute(arguments)

            # Check error result
            assert result["success"] is False
            assert "error" in result
            assert result["returncode"] == 1

    @pytest.mark.asyncio
    async def test_rg_failure_handling(self, find_and_grep_tool, temp_project_dir):
        """Test handling of ripgrep command failure"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock successful fd but failed rg
            fd_output = f"{temp_project_dir}/test1.py\n"
            mock_run.side_effect = [
                (0, fd_output.encode(), b""),  # fd success
                (2, b"", b"ripgrep error"),  # rg failure
            ]

            arguments = {
                "roots": [temp_project_dir],
                "query": "hello",
                "output_file": "rg_error_test",
            }

            result = await find_and_grep_tool.execute(arguments)

            # Check error result
            assert result["success"] is False
            assert "error" in result
            assert result["returncode"] == 2

    @pytest.mark.asyncio
    async def test_no_files_found(self, find_and_grep_tool, temp_project_dir):
        """Test behavior when no files are found by fd"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock fd returning no files
            mock_run.return_value = (0, b"", b"")

            arguments = {
                "roots": [temp_project_dir],
                "query": "hello",
                "pattern": "*.nonexistent",
                "glob": True,
                "output_file": "no_files_test",
            }

            result = await find_and_grep_tool.execute(arguments)

            # Check empty result
            assert result["success"] is True
            assert result["count"] == 0
            assert result["results"] == []
            assert result["meta"]["searched_file_count"] == 0

    @pytest.mark.asyncio
    async def test_sorting_options(self, find_and_grep_tool, temp_project_dir):
        """Test file sorting options"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock fd output with multiple files
            fd_output = f"{temp_project_dir}/test1.py\n{temp_project_dir}/test2.js\n{temp_project_dir}/README.md\n"
            rg_output = b'{"type":"match","data":{"path":{"text":"test1.py"},"lines":{"text":"def hello_world():"},"line_number":2,"absolute_offset":1,"submatches":[{"match":{"text":"hello"},"start":4,"end":9}]}}\n'

            mock_run.side_effect = [(0, fd_output.encode(), b""), (0, rg_output, b"")]

            # Test path sorting
            arguments = {
                "roots": [temp_project_dir],
                "query": "hello",
                "sort": "path",
                "output_file": "sorted_results",
            }

            result = await find_and_grep_tool.execute(arguments)

            assert result["success"] is True
            assert "meta" in result
            assert result["meta"]["searched_file_count"] > 0

    def test_tool_definition_includes_new_parameters(self, find_and_grep_tool):
        """Test that tool definition includes new parameters"""
        definition = find_and_grep_tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema["properties"]

        # Check output_file parameter
        assert "output_file" in properties
        assert properties["output_file"]["type"] == "string"
        assert (
            "Optional filename to save output to file"
            in properties["output_file"]["description"]
        )

        # Check suppress_output parameter
        assert "suppress_output" in properties
        assert properties["suppress_output"]["type"] == "boolean"
        assert properties["suppress_output"]["default"] is False
        assert (
            "suppress detailed output" in properties["suppress_output"]["description"]
        )

    @pytest.mark.asyncio
    async def test_complex_workflow_with_output(
        self, find_and_grep_tool, temp_project_dir
    ):
        """Test complex workflow combining multiple features with file output"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock outputs for complex search
            fd_output = (
                f"{temp_project_dir}/test1.py\n{temp_project_dir}/subdir/nested.py\n"
            )
            rg_output = b"""{"type":"match","data":{"path":{"text":"test1.py"},"lines":{"text":"def hello_world():"},"line_number":2,"absolute_offset":1,"submatches":[{"match":{"text":"hello"},"start":4,"end":9}]}}
{"type":"match","data":{"path":{"text":"subdir/nested.py"},"lines":{"text":"def nested_hello():"},"line_number":2,"absolute_offset":1,"submatches":[{"match":{"text":"hello"},"start":11,"end":16}]}}
"""

            mock_run.side_effect = [(0, fd_output.encode(), b""), (0, rg_output, b"")]

            arguments = {
                "roots": [temp_project_dir],
                "query": "hello",
                "pattern": "*.py",
                "glob": True,
                "types": ["f"],
                "context_before": 1,
                "context_after": 1,
                "case": "insensitive",
                "group_by_file": True,
                "summary_only": True,
                "output_file": "complex_workflow",
                "suppress_output": True,
            }

            result = await find_and_grep_tool.execute(arguments)

            # Check that complex workflow works with file output
            assert "success" in result
            assert "count" in result
            assert "output_file" in result
            assert "file_saved" in result

            # Verify file was created with expected structure
            file_path = result["file_saved"].split("Results saved to ")[1]
            output_file = Path(file_path)
            assert output_file.exists()

            with open(output_file, encoding="utf-8") as f:
                saved_content = json.loads(f.read())

            # Should have both grouped and summary structure
            assert "files" in saved_content
            assert "summary" in saved_content
