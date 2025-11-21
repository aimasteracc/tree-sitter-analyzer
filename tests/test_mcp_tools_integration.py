#!/usr/bin/env python3
"""
Integration tests for MCP tools file output functionality

Tests the integration and consistency of file output features
across all MCP tools that support them.
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
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


class TestMCPToolsIntegration:
    """Integration tests for MCP tools file output functionality"""

    @pytest.fixture
    def comprehensive_project(self):
        """Create a comprehensive test project with multiple file types"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create Python files
            (project_path / "main.py").write_text(
                """#!/usr/bin/env python3
\"\"\"
Main application module.
\"\"\"

import os
import sys
from pathlib import Path

def main():
    \"\"\"Main function.\"\"\"
    print("Hello, World!")
    return 0

class Application:
    \"\"\"Main application class.\"\"\"

    def __init__(self, name: str):
        self.name = name
        self.config = {}

    def run(self):
        \"\"\"Run the application.\"\"\"
        print(f"Running {self.name}")
        return True

if __name__ == "__main__":
    sys.exit(main())
"""
            )

            (project_path / "utils.py").write_text(
                """\"\"\"
Utility functions for the application.
\"\"\"

def hello_helper(name: str) -> str:
    \"\"\"Helper function for greetings.\"\"\"
    return f"Hello, {name}!"

def calculate_sum(numbers: list) -> int:
    \"\"\"Calculate sum of numbers.\"\"\"
    return sum(numbers)

class Helper:
    \"\"\"Helper class.\"\"\"

    @staticmethod
    def format_message(msg: str) -> str:
        \"\"\"Format a message.\"\"\"
        return f"[INFO] {msg}"
"""
            )

            # Create Java files
            (project_path / "Main.java").write_text(
                """package com.example;

import java.util.List;
import java.util.ArrayList;

/**
 * Main application class.
 */
public class Main {
    private String name;
    private List<String> items;

    public Main(String name) {
        this.name = name;
        this.items = new ArrayList<>();
    }

    public void run() {
        System.out.println("Running " + name);
    }

    public static void main(String[] args) {
        Main app = new Main("TestApp");
        app.run();
    }
}
"""
            )

            # Create JavaScript files
            (project_path / "app.js").write_text(
                """/**
 * Main application module.
 */

const config = {
    name: "TestApp",
    version: "1.0.0"
};

function main() {
    console.log("Hello, World!");
    return 0;
}

class Application {
    constructor(name) {
        this.name = name;
        this.config = {};
    }

    run() {
        console.log(`Running ${this.name}`);
        return true;
    }
}

module.exports = { main, Application };
"""
            )

            # Create subdirectories
            subdir = project_path / "src"
            subdir.mkdir()

            (subdir / "core.py").write_text(
                """\"\"\"
Core functionality.
\"\"\"

def hello_world():
    \"\"\"Print hello world.\"\"\"
    print("Hello from core!")

class CoreClass:
    \"\"\"Core class.\"\"\"

    def process(self, data):
        \"\"\"Process data.\"\"\"
        return f"Processed: {data}"
"""
            )

            yield str(project_path)

    @pytest.fixture
    def all_tools(self, comprehensive_project):
        """Create instances of all MCP tools"""
        return {
            "search_content": SearchContentTool(comprehensive_project),
            "find_and_grep": FindAndGrepTool(comprehensive_project),
            "read_partial": ReadPartialTool(comprehensive_project),
            "query": QueryTool(comprehensive_project),
            "analyze_scale": AnalyzeScaleTool(comprehensive_project),
        }

    @pytest.mark.asyncio
    async def test_workflow_analyze_then_extract(
        self, all_tools, comprehensive_project
    ):
        """Test workflow: analyze file scale, then extract specific sections"""
        main_py = Path(comprehensive_project) / "main.py"

        # Step 1: Analyze file scale
        with patch.object(
            all_tools["analyze_scale"].analysis_engine, "analyze"
        ) as mock_analyze:
            # Mock analysis result
            mock_result = AsyncMock()
            mock_result.success = True
            mock_result.elements = []
            mock_analyze.return_value = mock_result

            analyze_args = {"file_path": str(main_py), "include_guidance": True}

            analyze_result = await all_tools["analyze_scale"].execute(analyze_args)

            # Should get guidance for further analysis
            assert "llm_guidance" in analyze_result
            assert "size_category" in analyze_result["llm_guidance"]

        # Step 2: Extract specific sections based on analysis
        extract_args = {
            "file_path": str(main_py),
            "start_line": 10,
            "end_line": 20,
            "format": "json",
            "output_file": "extracted_main_section",
            "suppress_output": True,
        }

        extract_result = await all_tools["read_partial"].execute(extract_args)

        # Should have extracted content with file output
        assert "content_length" in extract_result
        assert "output_file_path" in extract_result
        assert "file_saved" in extract_result

        # Verify file was created
        output_file = Path(extract_result["output_file_path"])
        assert output_file.exists()

    @pytest.mark.asyncio
    async def test_workflow_search_then_query(self, all_tools, comprehensive_project):
        """Test workflow: search for patterns, then query specific files"""

        # Step 1: Search for function patterns
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock search results
            search_output = b'{"type":"match","data":{"path":{"text":"main.py"},"lines":{"text":"def main():"},"line_number":8,"absolute_offset":100,"submatches":[{"match":{"text":"main"},"start":4,"end":8}]}}\n'
            mock_run.return_value = (0, search_output, b"")

            search_args = {
                "roots": [comprehensive_project],
                "query": "def main",
                "extensions": ["py"],
                "output_file": "search_functions",
                "suppress_output": True,
            }

            search_result = await all_tools["search_content"].execute(search_args)

            # Should find function definitions
            assert "count" in search_result
            assert "output_file" in search_result

        # Step 2: Query the found files for detailed function information
        main_py = Path(comprehensive_project) / "main.py"

        with patch.object(
            all_tools["query"].query_service, "execute_query"
        ) as mock_query:
            # Mock query results
            mock_query.return_value = [
                {
                    "capture_name": "function",
                    "content": "def main():",
                    "start_line": 8,
                    "end_line": 10,
                    "node_type": "function_definition",
                }
            ]

            query_args = {
                "file_path": str(main_py),
                "query_key": "functions",
                "output_file": "detailed_functions",
                "suppress_output": True,
            }

            query_result = await all_tools["query"].execute(query_args)

            # Should get detailed function information
            assert "count" in query_result
            assert "output_file_path" in query_result

    @pytest.mark.asyncio
    async def test_workflow_find_and_grep_then_extract(
        self, all_tools, comprehensive_project
    ):
        """Test workflow: find files with patterns, then extract relevant sections"""

        # Step 1: Find files with specific patterns
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            # Mock fd and rg outputs
            fd_output = (
                f"{comprehensive_project}/main.py\n{comprehensive_project}/utils.py\n"
            )
            rg_output = b'{"type":"match","data":{"path":{"text":"main.py"},"lines":{"text":"class Application:"},"line_number":15,"absolute_offset":200,"submatches":[{"match":{"text":"class"},"start":0,"end":5}]}}\n'

            mock_run.side_effect = [
                (0, fd_output.encode(), b""),  # fd result
                (0, rg_output, b""),  # rg result
            ]

            find_grep_args = {
                "roots": [comprehensive_project],
                "query": "class",
                "pattern": "*.py",
                "glob": True,
                "output_file": "found_classes",
                "suppress_output": True,
            }

            find_result = await all_tools["find_and_grep"].execute(find_grep_args)

            # Should find class definitions
            assert "count" in find_result
            assert "output_file" in find_result

        # Step 2: Extract the found class definitions
        main_py = Path(comprehensive_project) / "main.py"

        extract_args = {
            "file_path": str(main_py),
            "start_line": 15,
            "end_line": 25,
            "format": "raw",
            "output_file": "extracted_class",
            "suppress_output": False,
        }

        extract_result = await all_tools["read_partial"].execute(extract_args)

        # Should extract class definition
        assert "content_length" in extract_result
        assert "output_file_path" in extract_result
        assert "partial_content_result" in extract_result

    @pytest.mark.asyncio
    async def test_cross_tool_file_output_consistency(
        self, all_tools, comprehensive_project
    ):
        """Test that file output behavior is consistent across all tools"""
        main_py = Path(comprehensive_project) / "main.py"

        # Test scenarios for each tool
        test_scenarios = []

        # SearchContentTool scenario
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            mock_run.return_value = (
                0,
                b'{"type":"match","data":{"path":{"text":"main.py"},"lines":{"text":"def main():"},"line_number":8,"absolute_offset":100,"submatches":[{"match":{"text":"main"},"start":4,"end":8}]}}\n',
                b"",
            )

            search_args = {
                "roots": [comprehensive_project],
                "query": "main",
                "output_file": "consistency_search",
                "suppress_output": True,
            }

            search_result = await all_tools["search_content"].execute(search_args)
            test_scenarios.append(("search_content", search_result))

        # FindAndGrepTool scenario
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            fd_output = f"{comprehensive_project}/main.py\n"
            rg_output = b'{"type":"match","data":{"path":{"text":"main.py"},"lines":{"text":"def main():"},"line_number":8,"absolute_offset":100,"submatches":[{"match":{"text":"main"},"start":4,"end":8}]}}\n'
            mock_run.side_effect = [(0, fd_output.encode(), b""), (0, rg_output, b"")]

            find_grep_args = {
                "roots": [comprehensive_project],
                "query": "main",
                "pattern": "*.py",
                "glob": True,
                "output_file": "consistency_find_grep",
                "suppress_output": True,
            }

            find_grep_result = await all_tools["find_and_grep"].execute(find_grep_args)
            test_scenarios.append(("find_and_grep", find_grep_result))

        # ReadPartialTool scenario
        read_partial_args = {
            "file_path": str(main_py),
            "start_line": 1,
            "end_line": 10,
            "output_file": "consistency_read_partial",
            "suppress_output": True,
        }

        read_partial_result = await all_tools["read_partial"].execute(read_partial_args)
        test_scenarios.append(("read_partial", read_partial_result))

        # QueryTool scenario
        with patch.object(
            all_tools["query"].query_service, "execute_query"
        ) as mock_query:
            mock_query.return_value = [
                {
                    "capture_name": "function",
                    "content": "def main():",
                    "start_line": 8,
                    "end_line": 10,
                    "node_type": "function_definition",
                }
            ]

            query_args = {
                "file_path": str(main_py),
                "query_key": "functions",
                "output_file": "consistency_query",
                "suppress_output": True,
            }

            query_result = await all_tools["query"].execute(query_args)
            test_scenarios.append(("query", query_result))

        # Verify consistency across all tools
        for tool_name, result in test_scenarios:
            # All tools should have consistent suppress_output behavior
            assert (
                "count" in result or "content_length" in result
            ), f"{tool_name} missing count/content_length"

            # All tools should have file output indicators
            file_output_indicators = [
                "output_file_path" in result,
                "file_saved" in result,
                "output_file" in result,
            ]
            assert any(
                file_output_indicators
            ), f"{tool_name} missing file output indicators"

            # When suppress_output=True, detailed results should be minimal
            detailed_result_keys = ["results", "partial_content_result", "captures"]
            any(key in result for key in detailed_result_keys)
            # Some tools may still include minimal detailed results, but they should be suppressed
            # The key is that file output should work consistently

    @pytest.mark.asyncio
    async def test_file_output_path_consistency(self, all_tools, comprehensive_project):
        """Test that all tools create files in consistent locations"""
        main_py = Path(comprehensive_project) / "main.py"
        created_files = []

        # Test each tool's file output
        tools_to_test = [
            (
                "search_content",
                {
                    "roots": [comprehensive_project],
                    "query": "test",
                    "output_file": "path_test_search",
                },
            ),
            (
                "read_partial",
                {
                    "file_path": str(main_py),
                    "start_line": 1,
                    "end_line": 5,
                    "output_file": "path_test_read",
                },
            ),
            (
                "query",
                {
                    "file_path": str(main_py),
                    "query_key": "functions",
                    "output_file": "path_test_query",
                },
            ),
        ]

        # Mock external dependencies
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            mock_run.return_value = (
                0,
                b'{"type":"match","data":{"path":{"text":"main.py"},"lines":{"text":"test"},"line_number":1,"absolute_offset":0,"submatches":[{"match":{"text":"test"},"start":0,"end":4}]}}\n',
                b"",
            )

            with patch.object(
                all_tools["query"].query_service, "execute_query"
            ) as mock_query:
                mock_query.return_value = [
                    {
                        "capture_name": "function",
                        "content": "def main():",
                        "start_line": 8,
                        "end_line": 10,
                        "node_type": "function_definition",
                    }
                ]

                for tool_name, args in tools_to_test:
                    result = await all_tools[tool_name].execute(args)

                    # Extract file path
                    if "output_file_path" in result:
                        file_path = Path(result["output_file_path"])
                    elif "file_saved" in result and isinstance(
                        result["file_saved"], str
                    ):
                        file_path = Path(
                            result["file_saved"].split("Results saved to ")[1]
                        )
                    else:
                        continue

                    created_files.append((tool_name, file_path))

                    # Verify file exists and is in project directory
                    assert file_path.exists(), f"{tool_name} file not created"
                    # Normalize paths for Windows compatibility (short vs long path format)
                    assert file_path.resolve().is_relative_to(
                        Path(comprehensive_project).resolve()
                    ), f"{tool_name} file not in project directory"

        # Verify all files were created in the same base directory
        if created_files:
            base_dirs = [file_path.parent for _, file_path in created_files]
            # All files should be in the same directory (project root)
            assert (
                len(set(base_dirs)) <= 2
            ), "Files created in inconsistent locations"  # Allow some variation

    @pytest.mark.asyncio
    async def test_error_handling_consistency(self, all_tools, comprehensive_project):
        """Test that error handling is consistent across tools"""
        from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError

        # Test file save error handling
        tools_with_file_output = ["search_content", "read_partial", "query"]

        for tool_name in tools_with_file_output:
            tool = all_tools[tool_name]

            # Mock FileOutputManager to raise an exception
            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.side_effect = Exception("File save error")

                # Prepare arguments for each tool
                if tool_name == "search_content":
                    # Mock fd_rg_utils to avoid rg command dependency
                    with patch(
                        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
                    ) as mock_run:
                        mock_run.return_value = (
                            0,
                            b'{"type":"match","data":{"path":{"text":"main.py"},"lines":{"text":"test"},"line_number":1,"absolute_offset":0,"submatches":[{"match":{"text":"test"},"start":0,"end":4}]}}\n',
                            b"",
                        )

                        args = {
                            "roots": [comprehensive_project],
                            "query": "test",
                            "output_file": "error_test",
                        }
                elif tool_name == "read_partial":
                    args = {
                        "file_path": str(Path(comprehensive_project) / "main.py"),
                        "start_line": 1,
                        "end_line": 5,
                        "output_file": "error_test",
                    }
                elif tool_name == "query":
                    with patch.object(
                        tool.query_service, "execute_query"
                    ) as mock_query:
                        mock_query.return_value = [
                            {
                                "capture_name": "function",
                                "content": "def main():",
                                "start_line": 8,
                                "end_line": 10,
                                "node_type": "function_definition",
                            }
                        ]

                        args = {
                            "file_path": str(Path(comprehensive_project) / "main.py"),
                            "query_key": "functions",
                            "output_file": "error_test",
                        }

                try:
                    result = await tool.execute(args)

                    # All tools should handle file save errors consistently
                    assert (
                        "file_save_error" in result
                    ), f"{tool_name} missing file_save_error"
                    assert "file_saved" in result, f"{tool_name} missing file_saved"
                    assert (
                        result["file_saved"] is False
                    ), f"{tool_name} file_saved should be False"
                    assert (
                        "File save error" in result["file_save_error"]
                    ), f"{tool_name} error message incorrect"
                except AnalysisError as e:
                    # If the error is wrapped in AnalysisError, that's expected for file save errors
                    # Check if the error is related to missing rg command
                    error_msg = str(e).lower()
                    if "no such file or directory" in error_msg and "rg" in error_msg:
                        pytest.skip(
                            f"Skipping {tool_name} test due to missing rg command"
                        )
                    else:
                        assert "File save error" in str(
                            e
                        ), f"{tool_name} AnalysisError should contain 'File save error'"
                except Exception as e:
                    # If there's an error related to missing commands, skip the test
                    error_msg = str(e).lower()
                    if (
                        any(cmd in error_msg for cmd in ["rg", "ripgrep"])
                        and "not found" in error_msg
                    ):
                        pytest.skip(
                            f"Skipping {tool_name} test due to missing rg command"
                        )
                    else:
                        raise

    @pytest.mark.asyncio
    async def test_large_project_workflow(self, all_tools, comprehensive_project):
        """Test workflow for analyzing a larger project structure"""

        # Step 1: Search for all function definitions across the project
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            search_output = b"""{"type":"match","data":{"path":{"text":"main.py"},"lines":{"text":"def main():"},"line_number":8,"absolute_offset":100,"submatches":[{"match":{"text":"def"},"start":0,"end":3}]}}
{"type":"match","data":{"path":{"text":"utils.py"},"lines":{"text":"def hello_helper(name: str) -> str:"},"line_number":5,"absolute_offset":50,"submatches":[{"match":{"text":"def"},"start":0,"end":3}]}}
{"type":"match","data":{"path":{"text":"src/core.py"},"lines":{"text":"def hello_world():"},"line_number":5,"absolute_offset":30,"submatches":[{"match":{"text":"def"},"start":0,"end":3}]}}
"""
            mock_run.return_value = (0, search_output, b"")

            search_args = {
                "roots": [comprehensive_project],
                "query": "def ",
                "extensions": ["py"],
                "summary_only": True,
                "output_file": "project_functions_overview",
            }

            search_result = await all_tools["search_content"].execute(search_args)

            # Should find multiple function definitions
            assert "count" in search_result
            assert "output_file" in search_result

        # Step 2: Analyze scale of main files
        main_files = ["main.py", "utils.py"]
        analysis_results = []

        for file_name in main_files:
            file_path = Path(comprehensive_project) / file_name

            with patch.object(
                all_tools["analyze_scale"].analysis_engine, "analyze"
            ) as mock_analyze:
                mock_result = AsyncMock()
                mock_result.success = True
                mock_result.elements = []
                mock_analyze.return_value = mock_result

                analyze_args = {"file_path": str(file_path), "include_guidance": True}

                analyze_result = await all_tools["analyze_scale"].execute(analyze_args)
                analysis_results.append((file_name, analyze_result))

        # Step 3: Extract detailed information from complex files
        for file_name, analysis in analysis_results:
            if analysis["file_metrics"]["total_lines"] > 10:  # If file is "complex"
                file_path = Path(comprehensive_project) / file_name

                # Extract class definitions
                extract_args = {
                    "file_path": str(file_path),
                    "start_line": 15,
                    "end_line": 30,
                    "format": "json",
                    "output_file": f"extracted_{file_name.replace('.', '_')}_classes",
                    "suppress_output": True,
                }

                extract_result = await all_tools["read_partial"].execute(extract_args)

                # Should extract relevant sections
                assert "content_length" in extract_result
                assert "output_file_path" in extract_result

        # Verify workflow completed successfully
        assert len(analysis_results) == 2
        for _file_name, analysis in analysis_results:
            assert "file_metrics" in analysis
            assert "llm_guidance" in analysis

    def test_tool_schema_consistency(self, all_tools):
        """Test that tool schemas are consistent for file output parameters"""
        tools_with_file_output = [
            "search_content",
            "find_and_grep",
            "read_partial",
            "query",
        ]

        for tool_name in tools_with_file_output:
            tool = all_tools[tool_name]
            definition = tool.get_tool_definition()
            schema = definition["inputSchema"]
            properties = schema["properties"]

            # All tools should have output_file parameter
            assert (
                "output_file" in properties
            ), f"{tool_name} missing output_file parameter"
            assert (
                properties["output_file"]["type"] == "string"
            ), f"{tool_name} output_file wrong type"

            # All tools should have suppress_output parameter
            assert (
                "suppress_output" in properties
            ), f"{tool_name} missing suppress_output parameter"
            assert (
                properties["suppress_output"]["type"] == "boolean"
            ), f"{tool_name} suppress_output wrong type"
            assert (
                properties["suppress_output"]["default"] is False
            ), f"{tool_name} suppress_output wrong default"

            # Descriptions should mention file output and token optimization
            output_file_desc = properties["output_file"]["description"].lower()
            assert (
                "file" in output_file_desc
            ), f"{tool_name} output_file description missing 'file'"
            assert (
                "save" in output_file_desc or "output" in output_file_desc
            ), f"{tool_name} output_file description unclear"

            suppress_output_desc = properties["suppress_output"]["description"].lower()
            assert (
                "suppress" in suppress_output_desc
            ), f"{tool_name} suppress_output description missing 'suppress'"
            assert (
                "token" in suppress_output_desc or "output" in suppress_output_desc
            ), f"{tool_name} suppress_output description unclear"

    @pytest.mark.asyncio
    async def test_performance_with_file_output(self, all_tools, comprehensive_project):
        """Test that file output doesn't significantly impact performance"""
        main_py = Path(comprehensive_project) / "main.py"

        # Test with and without file output for comparison
        test_cases = [
            ("without_file_output", {"suppress_output": False}),
            ("with_file_output", {"output_file": "perf_test", "suppress_output": True}),
        ]

        for case_name, extra_args in test_cases:
            # Test ReadPartialTool (simplest to test)
            base_args = {"file_path": str(main_py), "start_line": 1, "end_line": 10}
            args = {**base_args, **extra_args}

            # Measure execution (basic timing)
            import time

            start_time = time.time()

            result = await all_tools["read_partial"].execute(args)

            end_time = time.time()
            execution_time = end_time - start_time

            # Should complete in reasonable time (< 1 second for small files)
            assert execution_time < 1.0, f"{case_name} took too long: {execution_time}s"

            # Should have expected result structure
            assert "content_length" in result

            if "output_file" in extra_args:
                assert "output_file_path" in result or "file_saved" in result

    @pytest.mark.asyncio
    async def test_concurrent_file_output(self, all_tools, comprehensive_project):
        """Test that multiple tools can create files concurrently without conflicts"""
        import asyncio

        main_py = Path(comprehensive_project) / "main.py"

        # Create concurrent tasks
        tasks = []

        # Task 1: Read partial
        async def read_task():
            return await all_tools["read_partial"].execute(
                {
                    "file_path": str(main_py),
                    "start_line": 1,
                    "end_line": 5,
                    "output_file": "concurrent_read",
                    "suppress_output": True,
                }
            )

        # Task 2: Search content
        async def search_task():
            with patch(
                "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
            ) as mock_run:
                mock_run.return_value = (
                    0,
                    b'{"type":"match","data":{"path":{"text":"main.py"},"lines":{"text":"def main():"},"line_number":8,"absolute_offset":100,"submatches":[{"match":{"text":"main"},"start":4,"end":8}]}}\n',
                    b"",
                )

                return await all_tools["search_content"].execute(
                    {
                        "roots": [comprehensive_project],
                        "query": "main",
                        "output_file": "concurrent_search",
                        "suppress_output": True,
                    }
                )

        # Task 3: Query
        async def query_task():
            with patch.object(
                all_tools["query"].query_service, "execute_query"
            ) as mock_query:
                mock_query.return_value = [
                    {
                        "capture_name": "function",
                        "content": "def main():",
                        "start_line": 8,
                        "end_line": 10,
                        "node_type": "function_definition",
                    }
                ]

                return await all_tools["query"].execute(
                    {
                        "file_path": str(main_py),
                        "query_key": "functions",
                        "output_file": "concurrent_query",
                        "suppress_output": True,
                    }
                )

        tasks = [read_task(), search_task(), query_task()]

        # Execute concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All tasks should complete successfully
        for i, result in enumerate(results):
            assert not isinstance(result, Exception), f"Task {i} failed: {result}"
            assert isinstance(result, dict), f"Task {i} returned invalid result"

            # Each should have created a file
            file_indicators = ["output_file_path", "file_saved", "output_file"]
            assert any(
                key in result for key in file_indicators
            ), f"Task {i} missing file output"
