#!/usr/bin/env python3
"""
Pytest fixtures for MCP golden master tests.

This module provides fixtures for testing MCP tools with golden master comparison.
"""

from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.testing import MCPOutputNormalizer

# Project root and test file paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "examples"
GOLDEN_MASTER_DIR = PROJECT_ROOT / "tests" / "golden_masters" / "mcp"

# Test file for most MCP tools
TEST_FILE_JAVA = "examples/BigService.java"
TEST_FILE_PYTHON = "examples/sample.py"


@pytest.fixture
def project_root() -> Path:
    """Return the project root directory."""
    return PROJECT_ROOT


@pytest.fixture
def examples_dir() -> Path:
    """Return the examples directory."""
    return EXAMPLES_DIR


@pytest.fixture
def golden_master_dir() -> Path:
    """Return the golden master directory for MCP tools."""
    return GOLDEN_MASTER_DIR


@pytest.fixture
def normalizer() -> MCPOutputNormalizer:
    """Return a configured MCP output normalizer."""
    return MCPOutputNormalizer(
        remove_volatile=True,
        normalize_paths=True,
        sort_keys=True,
    )


@pytest.fixture
def test_file_java() -> str:
    """Return the path to the Java test file."""
    return TEST_FILE_JAVA


@pytest.fixture
def test_file_python() -> str:
    """Return the path to the Python test file."""
    return TEST_FILE_PYTHON


# MCP Tool test configurations
# Each configuration defines the tool class, input arguments, and golden master file name
MCP_TOOL_CONFIGS: list[dict[str, Any]] = [
    {
        "tool_name": "check_code_scale",
        "tool_module": "tree_sitter_analyzer.mcp.tools.analyze_scale_tool",
        "tool_class": "AnalyzeScaleTool",
        "input_args": {
            "file_path": TEST_FILE_JAVA,
            "include_guidance": True,
            "include_details": False,
            "output_format": "json",
        },
        "golden_file": "check_code_scale.json",
    },
    {
        "tool_name": "analyze_code_structure",
        "tool_module": "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool",
        "tool_class": "AnalyzeCodeStructureTool",
        "input_args": {
            "file_path": TEST_FILE_JAVA,
            "format_type": "full",
            "output_format": "json",
        },
        "golden_file": "analyze_code_structure.json",
    },
    {
        "tool_name": "extract_code_section",
        "tool_module": "tree_sitter_analyzer.mcp.tools.read_partial_tool",
        "tool_class": "ReadPartialTool",
        "input_args": {
            "file_path": TEST_FILE_JAVA,
            "start_line": 93,
            "end_line": 106,
            "output_format": "json",
        },
        "golden_file": "extract_code_section.json",
    },
    {
        "tool_name": "query_code",
        "tool_module": "tree_sitter_analyzer.mcp.tools.query_tool",
        "tool_class": "QueryTool",
        "input_args": {
            "file_path": TEST_FILE_JAVA,
            "query_key": "methods",
            "output_format": "json",
        },
        "golden_file": "query_code.json",
    },
    {
        "tool_name": "list_files",
        "tool_module": "tree_sitter_analyzer.mcp.tools.list_files_tool",
        "tool_class": "ListFilesTool",
        "input_args": {
            "roots": ["examples"],
            "extensions": ["java"],
            "output_format": "json",
        },
        "golden_file": "list_files.json",
    },
    {
        "tool_name": "search_content",
        "tool_module": "tree_sitter_analyzer.mcp.tools.search_content_tool",
        "tool_class": "SearchContentTool",
        "input_args": {
            "roots": ["examples"],
            "query": "class.*Service",
            "extensions": ["java"],
            "output_format": "json",
        },
        "golden_file": "search_content.json",
    },
    {
        "tool_name": "find_and_grep",
        "tool_module": "tree_sitter_analyzer.mcp.tools.find_and_grep_tool",
        "tool_class": "FindAndGrepTool",
        "input_args": {
            "roots": ["examples"],
            "query": "public",
            "extensions": ["java"],
            "output_format": "json",
        },
        "golden_file": "find_and_grep.json",
    },
]


@pytest.fixture(params=MCP_TOOL_CONFIGS, ids=[c["tool_name"] for c in MCP_TOOL_CONFIGS])
def mcp_tool_config(request: pytest.FixtureRequest) -> dict[str, Any]:
    """
    Parametrized fixture that provides configuration for each MCP tool.

    Returns a dictionary with:
        - tool_name: Name of the tool
        - tool_module: Module path to import
        - tool_class: Class name to instantiate
        - input_args: Arguments to pass to execute()
        - golden_file: Name of the golden master file
    """
    return request.param
