#!/usr/bin/env python3
"""
Consistency integration tests for MCP tools.

Tests file-output consistency, path consistency, error handling,
schema consistency, performance, and concurrent file output.
"""

import asyncio
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


@pytest.fixture(autouse=True)
def mock_external_commands(monkeypatch):
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.check_external_command",
        lambda cmd: True,
    )


@pytest.fixture
def comprehensive_project():
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

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
def all_tools(comprehensive_project):
    return {
        "search_content": SearchContentTool(comprehensive_project),
        "find_and_grep": FindAndGrepTool(comprehensive_project),
        "read_partial": ReadPartialTool(comprehensive_project),
        "query": QueryTool(comprehensive_project),
        "analyze_scale": AnalyzeScaleTool(comprehensive_project),
    }


class TestMCPConsistencyIntegration:
    @pytest.mark.asyncio
    async def test_cross_tool_file_output_consistency(
        self, all_tools, comprehensive_project
    ):
        main_py = Path(comprehensive_project) / "main.py"

        test_scenarios = []

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

        read_partial_args = {
            "file_path": str(main_py),
            "start_line": 1,
            "end_line": 10,
            "output_file": "consistency_read_partial",
            "suppress_output": True,
        }

        read_partial_result = await all_tools["read_partial"].execute(read_partial_args)
        test_scenarios.append(("read_partial", read_partial_result))

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

        for tool_name, result in test_scenarios:
            assert "count" in result or "content_length" in result, (
                f"{tool_name} missing count/content_length"
            )

            file_output_indicators = [
                "output_file_path" in result,
                "file_saved" in result,
                "output_file" in result,
            ]
            assert any(file_output_indicators), (
                f"{tool_name} missing file output indicators"
            )

    @pytest.mark.asyncio
    async def test_file_output_path_consistency(self, all_tools, comprehensive_project):
        main_py = Path(comprehensive_project) / "main.py"
        created_files = []

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

                    assert file_path.exists(), f"{tool_name} file not created"
                    assert file_path.resolve().is_relative_to(
                        Path(comprehensive_project).resolve()
                    ), f"{tool_name} file not in project directory"

        if created_files:
            base_dirs = [file_path.parent for _, file_path in created_files]
            assert len(set(base_dirs)) <= 2, "Files created in inconsistent locations"

    @pytest.mark.asyncio
    async def test_error_handling_consistency(self, all_tools, comprehensive_project):
        from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError

        tools_with_file_output = ["search_content", "read_partial", "query"]

        for tool_name in tools_with_file_output:
            tool = all_tools[tool_name]

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.side_effect = Exception("File save error")

                if tool_name == "search_content":
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

                    assert "file_save_error" in result, (
                        f"{tool_name} missing file_save_error"
                    )
                    assert "file_saved" in result, f"{tool_name} missing file_saved"
                    assert result["file_saved"] is False, (
                        f"{tool_name} file_saved should be False"
                    )
                    assert "File save error" in result["file_save_error"], (
                        f"{tool_name} error message incorrect"
                    )
                except AnalysisError as e:
                    error_msg = str(e).lower()
                    if "no such file or directory" in error_msg and "rg" in error_msg:
                        pytest.skip(
                            f"Skipping {tool_name} test due to missing rg command"
                        )
                    else:
                        assert "File save error" in str(e), (
                            f"{tool_name} AnalysisError should contain 'File save error'"
                        )
                except Exception as e:
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

    def test_tool_schema_consistency(self, all_tools):
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

            assert "output_file" in properties
            assert "suppress_output" in properties

    @pytest.mark.asyncio
    async def test_performance_with_file_output(self, all_tools, comprehensive_project):
        main_py = Path(comprehensive_project) / "main.py"

        test_cases = [
            ("without_file_output", {"suppress_output": False}),
            ("with_file_output", {"output_file": "perf_test", "suppress_output": True}),
        ]

        for case_name, extra_args in test_cases:
            base_args = {"file_path": str(main_py), "start_line": 1, "end_line": 10}
            args = {**base_args, **extra_args}

            start_time = time.time()

            result = await all_tools["read_partial"].execute(args)

            end_time = time.time()
            execution_time = end_time - start_time

            assert execution_time < 1.0, f"{case_name} took too long: {execution_time}s"

            assert "content_length" in result

            if "output_file" in extra_args:
                assert "output_file_path" in result or "file_saved" in result

    @pytest.mark.asyncio
    async def test_concurrent_file_output(self, all_tools, comprehensive_project):
        main_py = Path(comprehensive_project) / "main.py"

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

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            assert not isinstance(result, Exception), f"Task {i} failed: {result}"
            assert isinstance(result, dict), f"Task {i} returned invalid result"

            file_indicators = ["output_file_path", "file_saved", "output_file"]
            assert any(key in result for key in file_indicators), (
                f"Task {i} missing file output"
            )
