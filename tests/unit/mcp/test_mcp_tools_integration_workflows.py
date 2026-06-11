#!/usr/bin/env python3
"""
Workflow integration tests for MCP tools.

Tests multi-step workflows combining multiple MCP tools
(analyze → extract, search → query, find → extract, large project).
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


class TestMCPWorkflowIntegration:
    @pytest.mark.asyncio
    async def test_workflow_analyze_then_extract(
        self, all_tools, comprehensive_project
    ):
        main_py = Path(comprehensive_project) / "main.py"

        with patch.object(
            all_tools["analyze_scale"].analysis_engine, "analyze"
        ) as mock_analyze:
            mock_result = AsyncMock()
            mock_result.success = True
            mock_result.elements = []
            mock_analyze.return_value = mock_result

            analyze_args = {
                "file_path": str(main_py),
                "include_guidance": True,
                "output_format": "json",
            }
            analyze_result = await all_tools["analyze_scale"].execute(analyze_args)

            assert "llm_guidance" in analyze_result
            assert "size_category" in analyze_result["llm_guidance"]

        extract_args = {
            "file_path": str(main_py),
            "start_line": 10,
            "end_line": 20,
            "format": "json",
            "output_file": "extracted_main_section",
            "suppress_output": True,
        }

        extract_result = await all_tools["read_partial"].execute(extract_args)

        assert "content_length" in extract_result
        assert "output_file_path" in extract_result
        assert "file_saved" in extract_result

        output_file = Path(extract_result["output_file_path"])
        assert output_file.exists()

    @pytest.mark.asyncio
    async def test_workflow_search_then_query(self, all_tools, comprehensive_project):
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
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

            assert "count" in search_result
            assert "output_file" in search_result

        main_py = Path(comprehensive_project) / "main.py"

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
                "output_file": "detailed_functions",
                "suppress_output": True,
            }

            query_result = await all_tools["query"].execute(query_args)

            assert "count" in query_result
            assert "output_file_path" in query_result

    @pytest.mark.asyncio
    async def test_workflow_find_and_grep_then_extract(
        self, all_tools, comprehensive_project
    ):
        with patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture"
        ) as mock_run:
            fd_output = (
                f"{comprehensive_project}/main.py\n{comprehensive_project}/utils.py\n"
            )
            rg_output = b'{"type":"match","data":{"path":{"text":"main.py"},"lines":{"text":"class Application:"},"line_number":15,"absolute_offset":200,"submatches":[{"match":{"text":"class"},"start":0,"end":5}]}}\n'

            mock_run.side_effect = [
                (0, fd_output.encode(), b""),
                (0, rg_output, b""),
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

            assert "count" in find_result
            assert "output_file" in find_result

        main_py = Path(comprehensive_project) / "main.py"

        extract_args = {
            "file_path": str(main_py),
            "start_line": 15,
            "end_line": 25,
            "format": "raw",
            "output_file": "extracted_class",
            "suppress_output": False,
            "output_format": "json",
        }

        extract_result = await all_tools["read_partial"].execute(extract_args)

        assert "content_length" in extract_result
        assert "output_file_path" in extract_result
        assert "partial_content_result" in extract_result

    @pytest.mark.asyncio
    async def test_large_project_workflow(self, all_tools, comprehensive_project):
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

            assert "count" in search_result
            assert "output_file" in search_result

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

                analyze_args = {
                    "file_path": str(file_path),
                    "include_guidance": True,
                    "output_format": "json",
                }

                analyze_result = await all_tools["analyze_scale"].execute(analyze_args)
                analysis_results.append((file_name, analyze_result))

        for file_name, analysis in analysis_results:
            if analysis["file_metrics"]["total_lines"] > 10:
                file_path = Path(comprehensive_project) / file_name

                extract_args = {
                    "file_path": str(file_path),
                    "start_line": 15,
                    "end_line": 30,
                    "format": "json",
                    "output_file": f"extracted_{file_name.replace('.', '_')}_classes",
                    "suppress_output": True,
                }

                extract_result = await all_tools["read_partial"].execute(extract_args)

                assert "content_length" in extract_result
                assert "output_file_path" in extract_result

        assert len(analysis_results) == 2
        for _file_name, analysis in analysis_results:
            assert "file_metrics" in analysis
            assert "llm_guidance" in analysis
