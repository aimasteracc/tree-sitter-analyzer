#!/usr/bin/env python3
"""
Test file output feature for MCP tools

Tests the new output_file and suppress_output functionality
across all MCP tools that support it.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


@pytest.fixture(autouse=True)
def mock_external_commands(monkeypatch):
    """Auto-mock external command availability checks for all tests in this module."""
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )


class TestFileOutputFeature:
    """Test file output functionality across MCP tools"""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with test files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create test files
            test_file = project_path / "test.py"
            test_file.write_text(
                """
def hello_world():
    print("Hello, World!")
    return "success"

class TestClass:
    def __init__(self):
        self.value = 42

    def get_value(self):
        return self.value
"""
            )

            test_java_file = project_path / "Test.java"
            test_java_file.write_text(
                """
public class Test {
    private int value = 42;

    public Test() {
        this.value = 42;
    }

    public int getValue() {
        return this.value;
    }
}
"""
            )

            yield str(project_path)

    @pytest.fixture
    def search_content_tool(self, temp_project_dir):
        """Create SearchContentTool instance"""
        return SearchContentTool(project_root=temp_project_dir)

    @pytest.fixture
    def find_and_grep_tool(self, temp_project_dir):
        """Create FindAndGrepTool instance"""
        return FindAndGrepTool(project_root=temp_project_dir)

    @pytest.fixture
    def read_partial_tool(self, temp_project_dir):
        """Create ReadPartialTool instance"""
        return ReadPartialTool(project_root=temp_project_dir)

    @pytest.fixture
    def query_tool(self, temp_project_dir):
        """Create QueryTool instance"""
        return QueryTool(project_root=temp_project_dir)

    @pytest.mark.asyncio
    async def test_search_content_output_file_basic(
        self, search_content_tool, temp_project_dir
    ):
        """Test basic file output functionality for search_content"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock ripgrep output
            mock_output = b'{"type":"match","data":{"path":{"text":"test.py"},"lines":{"text":"def hello_world():"},"line_number":2,"absolute_offset":1,"submatches":[{"match":{"text":"hello"},"start":4,"end":9}]}}\n'
            mock_run.return_value = (0, mock_output, b"")

            arguments = {
                "roots": [temp_project_dir],
                "query": "hello",
                "output_file": "search_results",
                "suppress_output": False,
            }

            result = await search_content_tool.execute(arguments)

            # Check that file output info is included
            assert "output_file_path" in result
            assert "file_saved" in result
            # file_saved can be True or a string message
            assert result["file_saved"] is True or isinstance(result["file_saved"], str)

            # Check that the file was created
            output_file_path = Path(result["output_file_path"])
            assert output_file_path.exists()

            # Check file content
            with open(output_file_path, encoding="utf-8") as f:
                saved_content = json.loads(f.read())

            assert "success" in saved_content
            assert "results" in saved_content

    @pytest.mark.asyncio
    async def test_search_content_suppress_output(
        self, search_content_tool, temp_project_dir
    ):
        """Test suppress_output functionality for search_content"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock ripgrep output
            mock_output = b'{"type":"match","data":{"path":{"text":"test.py"},"lines":{"text":"def hello_world():"},"line_number":2,"absolute_offset":1,"submatches":[{"match":{"text":"hello"},"start":4,"end":9}]}}\n'
            mock_run.return_value = (0, mock_output, b"")

            arguments = {
                "roots": [temp_project_dir],
                "query": "hello",
                "output_file": "search_results_suppressed",
                "suppress_output": True,
            }

            result = await search_content_tool.execute(arguments)

            # Check that detailed results are suppressed
            assert "results" not in result
            assert "success" in result
            assert "count" in result
            assert "output_file" in result
            assert "file_saved" in result

    @pytest.mark.asyncio
    async def test_search_content_summary_only_with_output_file(
        self, search_content_tool, temp_project_dir
    ):
        """Test summary_only mode with file output"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock ripgrep output
            mock_output = b'{"type":"match","data":{"path":{"text":"test.py"},"lines":{"text":"def hello_world():"},"line_number":2,"absolute_offset":1,"submatches":[{"match":{"text":"hello"},"start":4,"end":9}]}}\n'
            mock_run.return_value = (0, mock_output, b"")

            arguments = {
                "roots": [temp_project_dir],
                "query": "hello",
                "summary_only": True,
                "output_file": "summary_results",
                "suppress_output": True,
            }

            result = await search_content_tool.execute(arguments)

            # Check minimal response
            assert "success" in result
            assert "count" in result
            assert "output_file" in result
            assert "file_saved" in result

            # Check that the file was created with summary content
            output_file_path = Path(result["file_saved"].split("Results saved to ")[1])
            assert output_file_path.exists()

    @pytest.mark.asyncio
    async def test_find_and_grep_output_file(
        self, find_and_grep_tool, temp_project_dir
    ):
        """Test file output functionality for find_and_grep"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock fd output (file discovery)
            fd_output = f"{temp_project_dir}/test.py\n"
            # Mock ripgrep output (content search)
            rg_output = b'{"type":"match","data":{"path":{"text":"test.py"},"lines":{"text":"def hello_world():"},"line_number":2,"absolute_offset":1,"submatches":[{"match":{"text":"hello"},"start":4,"end":9}]}}\n'

            # First call for fd, second call for rg
            mock_run.side_effect = [
                (0, fd_output.encode(), b""),  # fd result
                (0, rg_output, b""),  # rg result
            ]

            arguments = {
                "roots": [temp_project_dir],
                "query": "hello",
                "pattern": "*.py",
                "glob": True,
                "output_file": "find_grep_results",
                "suppress_output": False,
            }

            result = await find_and_grep_tool.execute(arguments)

            # Check that file output info is included
            assert "output_file" in result
            assert "file_saved" in result

            # Check that the file was created
            output_file_path = Path(result["file_saved"].split("Results saved to ")[1])
            assert output_file_path.exists()

    @pytest.mark.asyncio
    async def test_find_and_grep_suppress_output(
        self, find_and_grep_tool, temp_project_dir
    ):
        """Test suppress_output functionality for find_and_grep"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock fd output (file discovery)
            fd_output = f"{temp_project_dir}/test.py\n"
            # Mock ripgrep output (content search)
            rg_output = b'{"type":"match","data":{"path":{"text":"test.py"},"lines":{"text":"def hello_world():"},"line_number":2,"absolute_offset":1,"submatches":[{"match":{"text":"hello"},"start":4,"end":9}]}}\n'

            # First call for fd, second call for rg
            mock_run.side_effect = [
                (0, fd_output.encode(), b""),  # fd result
                (0, rg_output, b""),  # rg result
            ]

            arguments = {
                "roots": [temp_project_dir],
                "query": "hello",
                "pattern": "*.py",
                "glob": True,
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

    @pytest.mark.asyncio
    async def test_read_partial_output_file_formats(
        self, read_partial_tool, temp_project_dir
    ):
        """Test different output formats for read_partial"""
        test_file = Path(temp_project_dir) / "test.py"

        # Test text format (default)
        arguments = {
            "file_path": str(test_file),
            "start_line": 1,
            "end_line": 5,
            "format": "text",
            "output_file": "partial_text",
            "suppress_output": False,
        }

        result = await read_partial_tool.execute(arguments)

        assert "output_file_path" in result
        assert "file_saved" in result
        assert result["file_saved"] is True

        # Check that the file was created
        output_file_path = Path(result["output_file_path"])
        assert output_file_path.exists()

        # Test JSON format
        arguments["format"] = "json"
        arguments["output_file"] = "partial_json"

        result = await read_partial_tool.execute(arguments)

        assert "output_file_path" in result
        output_file_path = Path(result["output_file_path"])
        assert output_file_path.exists()

        # Verify JSON content
        with open(output_file_path, encoding="utf-8") as f:
            json_content = json.loads(f.read())

        assert "file_path" in json_content
        assert "content" in json_content

    @pytest.mark.asyncio
    async def test_read_partial_suppress_output(
        self, read_partial_tool, temp_project_dir
    ):
        """Test suppress_output functionality for read_partial"""
        test_file = Path(temp_project_dir) / "test.py"

        arguments = {
            "file_path": str(test_file),
            "start_line": 1,
            "end_line": 5,
            "output_file": "partial_suppressed",
            "suppress_output": True,
        }

        result = await read_partial_tool.execute(arguments)

        # Check that partial_content_result is suppressed
        assert "partial_content_result" not in result
        assert "file_path" in result
        assert "content_length" in result
        assert "output_file_path" in result

    @pytest.mark.asyncio
    async def test_query_tool_output_file(self, query_tool, temp_project_dir):
        """Test file output functionality for query_tool"""
        test_file = Path(temp_project_dir) / "test.py"

        with patch.object(query_tool.query_service, "execute_query") as mock_query:
            # Mock query results
            mock_results = [
                {
                    "capture_name": "function",
                    "content": "def hello_world():",
                    "start_line": 2,
                    "end_line": 4,
                    "node_type": "function_definition",
                }
            ]
            mock_query.return_value = mock_results

            arguments = {
                "file_path": str(test_file),
                "query_key": "functions",
                "output_file": "query_results",
                "suppress_output": False,
            }

            result = await query_tool.execute(arguments)

            assert "output_file_path" in result
            assert "file_saved" in result
            assert result["file_saved"] is True

            # Check that the file was created
            output_file_path = Path(result["output_file_path"])
            assert output_file_path.exists()

            # Verify JSON content
            with open(output_file_path, encoding="utf-8") as f:
                json_content = json.loads(f.read())

            assert "success" in json_content
            assert "results" in json_content

    @pytest.mark.asyncio
    async def test_query_tool_suppress_output(self, query_tool, temp_project_dir):
        """Test suppress_output functionality for query_tool"""
        test_file = Path(temp_project_dir) / "test.py"

        with patch.object(query_tool.query_service, "execute_query") as mock_query:
            # Mock query results
            mock_results = [
                {
                    "capture_name": "function",
                    "content": "def hello_world():",
                    "start_line": 2,
                    "end_line": 4,
                    "node_type": "function_definition",
                }
            ]
            mock_query.return_value = mock_results

            arguments = {
                "file_path": str(test_file),
                "query_key": "functions",
                "output_file": "query_suppressed",
                "suppress_output": True,
            }

            result = await query_tool.execute(arguments)

            # Check that detailed results are suppressed
            assert "results" not in result
            assert "success" in result
            assert "count" in result
            assert "output_file_path" in result

    @pytest.mark.asyncio
    async def test_file_output_error_handling(
        self, search_content_tool, temp_project_dir
    ):
        """Test error handling for file output"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock ripgrep output
            mock_output = b'{"type":"match","data":{"path":{"text":"test.py"},"lines":{"text":"def hello_world():"},"line_number":2,"absolute_offset":1,"submatches":[{"match":{"text":"hello"},"start":4,"end":9}]}}\n'
            mock_run.return_value = (0, mock_output, b"")

            # Mock FileOutputManager to raise an exception
            with patch.object(
                search_content_tool.file_output_manager, "save_to_file"
            ) as mock_save:
                mock_save.side_effect = Exception("File save error")

                arguments = {
                    "roots": [temp_project_dir],
                    "query": "hello",
                    "output_file": "error_test",
                    "suppress_output": False,
                }

                try:
                    result = await search_content_tool.execute(arguments)

                    # Check error handling
                    assert "file_save_error" in result
                    assert "file_saved" in result
                    assert result["file_saved"] is False
                    assert "File save error" in result["file_save_error"]
                except Exception as e:
                    # If the error is wrapped in an AnalysisError, that's also acceptable
                    assert "File save error" in str(e)

    def test_tool_schema_includes_new_parameters(self):
        """Test that tool schemas include the new output_file and suppress_output parameters"""
        tools = [SearchContentTool(), FindAndGrepTool(), ReadPartialTool(), QueryTool()]

        for tool in tools:
            definition = tool.get_tool_definition()
            schema = definition["inputSchema"]
            properties = schema["properties"]

            # Check that output_file parameter exists
            assert "output_file" in properties
            assert properties["output_file"]["type"] == "string"
            assert (
                "Optional filename to save output to file"
                in properties["output_file"]["description"]
            )

            # Check that suppress_output parameter exists
            assert "suppress_output" in properties
            assert properties["suppress_output"]["type"] == "boolean"
            assert properties["suppress_output"]["default"] is False
            assert "suppress" in properties["suppress_output"]["description"].lower()

    @pytest.mark.asyncio
    async def test_cross_tool_file_output_consistency(self, temp_project_dir):
        """Test that file output behavior is consistent across tools"""
        test_file = Path(temp_project_dir) / "test.py"

        # Test all tools with similar parameters
        tools_and_args = [
            (
                SearchContentTool(temp_project_dir),
                {
                    "roots": [temp_project_dir],
                    "query": "hello",
                    "output_file": "search_consistency",
                    "suppress_output": True,
                },
            ),
            (
                FindAndGrepTool(temp_project_dir),
                {
                    "roots": [temp_project_dir],
                    "query": "hello",
                    "pattern": "*.py",
                    "glob": True,
                    "output_file": "find_consistency",
                    "suppress_output": True,
                },
            ),
            (
                ReadPartialTool(temp_project_dir),
                {
                    "file_path": str(test_file),
                    "start_line": 1,
                    "end_line": 5,
                    "output_file": "read_consistency",
                    "suppress_output": True,
                },
            ),
            (
                QueryTool(temp_project_dir),
                {
                    "file_path": str(test_file),
                    "query_key": "functions",
                    "output_file": "query_consistency",
                    "suppress_output": True,
                },
            ),
        ]

        # Mock external dependencies
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock outputs for search and find_and_grep tools
            mock_output = b'{"type":"match","data":{"path":{"text":"test.py"},"lines":{"text":"def hello_world():"},"line_number":2,"absolute_offset":1,"submatches":[{"match":{"text":"hello"},"start":4,"end":9}]}}\n'
            fd_output = f"{temp_project_dir}/test.py\n"
            mock_run.side_effect = [
                (0, mock_output, b""),  # search_content
                (0, fd_output.encode(), b""),  # find_and_grep fd
                (0, mock_output, b""),  # find_and_grep rg
            ]

            # Mock query service for query_tool
            query_tool = tools_and_args[3][0]  # Get the QueryTool instance
            with patch.object(
                query_tool.query_service, "execute_query"
            ) as mock_query_service:
                mock_query_service.return_value = [
                    {
                        "capture_name": "function",
                        "content": "def hello_world():",
                        "start_line": 2,
                        "end_line": 4,
                        "node_type": "function_definition",
                    }
                ]

                for tool, args in tools_and_args:
                    result = await tool.execute(args)

                    # Check consistent behavior for suppress_output
                    # ReadPartialTool returns different structure, so check appropriately
                    if isinstance(tool, ReadPartialTool):
                        assert "file_path" in result
                        assert "content_length" in result
                    else:
                        assert "success" in result
                        assert "count" in result

                    # All tools should have some form of file output indication
                    file_output_indicators = [
                        "output_file_path" in result,
                        "file_saved" in result,
                        "output_file" in result,
                    ]
                    assert any(file_output_indicators), (
                        f"Tool {tool.__class__.__name__} missing file output indicators"
                    )


class TestFileOutputManagerIntegration:
    """Test FileOutputManager integration with MCP tools"""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    def test_file_output_manager_initialization(self, temp_project_dir):
        """Test that FileOutputManager is properly initialized in tools"""
        tools = [
            SearchContentTool(temp_project_dir),
            FindAndGrepTool(temp_project_dir),
            ReadPartialTool(temp_project_dir),
            QueryTool(temp_project_dir),
        ]

        for tool in tools:
            assert hasattr(tool, "file_output_manager")
            assert tool.file_output_manager is not None
            assert tool.file_output_manager.project_root == temp_project_dir

    @pytest.mark.asyncio
    async def test_file_output_path_resolution(self, temp_project_dir):
        """Test that file output paths are properly resolved"""
        tool = SearchContentTool(temp_project_dir)

        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            mock_output = b'{"type":"match","data":{"path":{"text":"test.py"},"lines":{"text":"test"},"line_number":1,"absolute_offset":0,"submatches":[{"match":{"text":"test"},"start":0,"end":4}]}}\n'
            mock_run.return_value = (0, mock_output, b"")

            arguments = {
                "roots": [temp_project_dir],
                "query": "test",
                "output_file": "test_output",
            }

            result = await tool.execute(arguments)

            # Check that output file path is absolute and within project
            if "output_file_path" in result:
                output_path = Path(result["output_file_path"])
                assert output_path.is_absolute()
                assert str(output_path).startswith(temp_project_dir)
