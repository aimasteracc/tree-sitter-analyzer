#!/usr/bin/env python3
"""
MCP Golden Master Tests

This module contains golden master regression tests for all MCP tools.
These tests ensure that MCP tool outputs remain stable across code changes.

Golden masters are stored in tests/golden_masters/mcp/ directory.
To update golden masters after intentional changes, run:
    uv run python scripts/update_golden_masters.py --mcp
"""

import importlib
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.testing import (
    MCPOutputNormalizer,
    generate_diff,
    load_golden_master,
    save_golden_master,
)

# Mark all tests in this module as regression tests
pytestmark = pytest.mark.regression


class TestMCPGoldenMasters:
    """Golden master tests for MCP tools."""

    @pytest.fixture(autouse=True)
    def setup(self, project_root: Path, normalizer: MCPOutputNormalizer) -> None:
        """Set up test dependencies."""
        self.project_root = project_root
        self.normalizer = normalizer
        self.golden_master_dir = project_root / "tests" / "golden_masters" / "mcp"

    def _get_tool_instance(self, tool_module: str, tool_class: str) -> Any:
        """Dynamically import and instantiate a tool class."""
        module = importlib.import_module(tool_module)
        cls = getattr(module, tool_class)
        return cls(project_root=str(self.project_root))

    def _load_or_create_golden_master(
        self, tool_name: str, actual: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Load golden master or create if it doesn't exist.

        When running in CI or when golden master doesn't exist,
        the test should fail with a clear message.
        """
        try:
            return load_golden_master(
                tool_name,
                category="mcp",
                base_dir=self.project_root / "tests" / "golden_masters",
            )
        except FileNotFoundError:
            # In test mode, save the golden master for initial creation
            # This allows first-time setup, but will fail in CI until committed
            golden_path = save_golden_master(
                actual,
                tool_name,
                category="mcp",
                base_dir=self.project_root / "tests" / "golden_masters",
            )
            pytest.skip(
                f"Golden master created at {golden_path}. "
                f"Please review and commit it, then re-run tests."
            )
            return actual  # Never reached, but satisfies type checker

    @pytest.mark.asyncio
    async def test_check_code_scale_golden_master(self) -> None:
        """Test check_code_scale tool output against golden master."""
        tool = self._get_tool_instance(
            "tree_sitter_analyzer.mcp.tools.analyze_scale_tool",
            "AnalyzeScaleTool",
        )

        result = await tool.execute(
            {
                "file_path": "examples/BigService.java",
                "include_guidance": True,
                "include_details": False,
                "output_format": "json",
            }
        )

        normalized = self.normalizer.normalize(result)
        expected = self._load_or_create_golden_master("check_code_scale", normalized)

        if normalized != expected:
            diff = generate_diff(normalized, expected)
            pytest.fail(f"check_code_scale output differs from golden master:\n{diff}")

    @pytest.mark.asyncio
    async def test_analyze_code_structure_golden_master(self) -> None:
        """Test analyze_code_structure tool output against golden master."""
        tool = self._get_tool_instance(
            "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool",
            "AnalyzeCodeStructureTool",
        )

        result = await tool.execute(
            {
                "file_path": "examples/BigService.java",
                "format_type": "full",
                "output_format": "json",
            }
        )

        normalized = self.normalizer.normalize(result)
        expected = self._load_or_create_golden_master(
            "analyze_code_structure", normalized
        )

        if normalized != expected:
            diff = generate_diff(normalized, expected)
            pytest.fail(
                f"analyze_code_structure output differs from golden master:\n{diff}"
            )

    @pytest.mark.asyncio
    async def test_extract_code_section_golden_master(self) -> None:
        """Test extract_code_section tool output against golden master."""
        tool = self._get_tool_instance(
            "tree_sitter_analyzer.mcp.tools.read_partial_tool",
            "ReadPartialTool",
        )

        result = await tool.execute(
            {
                "file_path": "examples/BigService.java",
                "start_line": 93,
                "end_line": 106,
                "output_format": "json",
            }
        )

        normalized = self.normalizer.normalize(result)
        expected = self._load_or_create_golden_master(
            "extract_code_section", normalized
        )

        if normalized != expected:
            diff = generate_diff(normalized, expected)
            pytest.fail(
                f"extract_code_section output differs from golden master:\n{diff}"
            )

    @pytest.mark.asyncio
    async def test_query_code_golden_master(self) -> None:
        """Test query_code tool output against golden master."""
        tool = self._get_tool_instance(
            "tree_sitter_analyzer.mcp.tools.query_tool",
            "QueryTool",
        )

        result = await tool.execute(
            {
                "file_path": "examples/BigService.java",
                "query_key": "methods",
                "output_format": "json",
            }
        )

        normalized = self.normalizer.normalize(result)
        expected = self._load_or_create_golden_master("query_code", normalized)

        if normalized != expected:
            diff = generate_diff(normalized, expected)
            pytest.fail(f"query_code output differs from golden master:\n{diff}")

    @pytest.mark.asyncio
    async def test_list_files_golden_master(self) -> None:
        """Test list_files tool output against golden master."""
        tool = self._get_tool_instance(
            "tree_sitter_analyzer.mcp.tools.list_files_tool",
            "ListFilesTool",
        )

        result = await tool.execute(
            {
                "roots": ["examples"],
                "extensions": ["java"],
                "output_format": "json",
            }
        )

        # Additional normalization for list_files - sort results list for determinism
        if "results" in result:
            result["results"] = sorted(
                result["results"], key=lambda x: x.get("path", x.get("name", ""))
            )

        normalized = self.normalizer.normalize(result)
        expected = self._load_or_create_golden_master("list_files", normalized)

        if normalized != expected:
            diff = generate_diff(normalized, expected)
            pytest.fail(f"list_files output differs from golden master:\n{diff}")

    @pytest.mark.asyncio
    async def test_search_content_golden_master(self) -> None:
        """Test search_content tool output against golden master."""
        tool = self._get_tool_instance(
            "tree_sitter_analyzer.mcp.tools.search_content_tool",
            "SearchContentTool",
        )

        result = await tool.execute(
            {
                "roots": ["examples"],
                "query": "class.*Service",
                "extensions": ["java"],
                "output_format": "json",
            }
        )

        # Sort results for deterministic comparison
        if "results" in result:
            result["results"] = sorted(
                result["results"], key=lambda x: x.get("file", "")
            )

        normalized = self.normalizer.normalize(result)
        expected = self._load_or_create_golden_master("search_content", normalized)

        if normalized != expected:
            diff = generate_diff(normalized, expected)
            pytest.fail(f"search_content output differs from golden master:\n{diff}")

    @pytest.mark.asyncio
    async def test_find_and_grep_golden_master(self) -> None:
        """Test find_and_grep tool output against golden master."""
        tool = self._get_tool_instance(
            "tree_sitter_analyzer.mcp.tools.find_and_grep_tool",
            "FindAndGrepTool",
        )

        result = await tool.execute(
            {
                "roots": ["examples"],
                "query": "public",
                "extensions": ["java"],
                "output_format": "json",
            }
        )

        # Sort results for deterministic comparison
        if "results" in result:
            result["results"] = sorted(
                result["results"], key=lambda x: (x.get("file", ""), x.get("line", 0))
            )

        normalized = self.normalizer.normalize(result)
        expected = self._load_or_create_golden_master("find_and_grep", normalized)

        if normalized != expected:
            diff = generate_diff(normalized, expected)
            pytest.fail(f"find_and_grep output differs from golden master:\n{diff}")


class TestMCPOutputNormalizer:
    """Unit tests for the MCP output normalizer."""

    def test_removes_volatile_fields(self) -> None:
        """Test that volatile fields are removed."""
        normalizer = MCPOutputNormalizer()

        data = {
            "success": True,
            "timestamp": "2025-01-19T12:00:00",
            "duration_ms": 150,
            "cache_hit": True,
            "result": {"key": "value"},
        }

        normalized = normalizer.normalize(data)

        assert "timestamp" not in normalized
        assert "duration_ms" not in normalized
        assert "cache_hit" not in normalized
        assert normalized["success"] is True
        assert normalized["result"] == {"key": "value"}

    def test_normalizes_paths(self) -> None:
        """Test that file paths are normalized."""
        normalizer = MCPOutputNormalizer()

        data = {
            "file_path": "C:\\git\\project\\examples\\test.java",
            "other_field": "C:\\git\\project\\src\\main.py",
        }

        normalized = normalizer.normalize(data)

        # Paths should have forward slashes and be relative
        assert "\\" not in normalized["file_path"]
        assert normalized["file_path"].startswith("/examples/")

    def test_sorts_keys(self) -> None:
        """Test that dictionary keys are sorted."""
        normalizer = MCPOutputNormalizer()

        data = {"zebra": 1, "alpha": 2, "middle": 3}

        normalized = normalizer.normalize(data)

        keys = list(normalized.keys())
        assert keys == sorted(keys)

    def test_nested_normalization(self) -> None:
        """Test normalization of nested structures."""
        normalizer = MCPOutputNormalizer()

        data = {
            "outer": {
                "timestamp": "2025-01-19",
                "inner": {
                    "duration_ms": 100,
                    "value": "test",
                },
            },
            "list": [
                {"timestamp": "2025-01-19", "item": 1},
                {"timestamp": "2025-01-20", "item": 2},
            ],
        }

        normalized = normalizer.normalize(data)

        assert "timestamp" not in normalized["outer"]
        assert "duration_ms" not in normalized["outer"]["inner"]
        assert normalized["outer"]["inner"]["value"] == "test"
        assert all("timestamp" not in item for item in normalized["list"])

    def test_custom_volatile_fields(self) -> None:
        """Test adding custom volatile fields."""
        normalizer = MCPOutputNormalizer(
            custom_volatile_fields={"custom_field", "another_field"}
        )

        data = {
            "success": True,
            "timestamp": "2025-01-19",
            "custom_field": "should be removed",
            "another_field": "also removed",
            "keep_this": "value",
        }

        normalized = normalizer.normalize(data)

        assert "timestamp" not in normalized
        assert "custom_field" not in normalized
        assert "another_field" not in normalized
        assert normalized["keep_this"] == "value"

    def test_round_floats(self) -> None:
        """Test floating point rounding."""
        normalizer = MCPOutputNormalizer()

        data = {"precise": 3.141592653589793, "nested": {"float": 2.718281828459045}}

        rounded = normalizer.round_floats(data, precision=2)

        assert rounded["precise"] == 3.14
        assert rounded["nested"]["float"] == 2.72
