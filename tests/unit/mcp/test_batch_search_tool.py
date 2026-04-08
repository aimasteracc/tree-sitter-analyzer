#!/usr/bin/env python3
"""
Tests for BatchSearchTool MCP Tool.

Verifies parallel search execution, query validation, result aggregation,
match truncation, and empty result handling.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.batch_search_tool import (
    _BATCH_MAX_MATCHES_PER_QUERY,
    BatchSearchTool,
)


@pytest.fixture
def tool() -> BatchSearchTool:
    """Create a fresh BatchSearchTool instance for each test."""
    return BatchSearchTool()


def _make_fake_match(path: str = "src/foo.py", line: int = 1) -> dict[str, object]:
    """Build a minimal fake rg match dict."""
    return {
        "type": "match",
        "data": {
            "path": {"text": path},
            "line_number": line,
            "lines": {"text": "some code"},
            "submatches": [],
        },
    }


class TestBatchSearchToolInitialization:
    """Tests for tool initialization."""

    def test_init_creates_tool(self, tool: BatchSearchTool) -> None:
        """Test that initialization creates a tool instance."""
        assert tool is not None

    def test_init_with_project_root(self) -> None:
        """Test initialization with a project root."""
        t = BatchSearchTool(project_root="/srv/project")
        assert t.project_root == "/srv/project"

    def test_set_project_path(self, tool: BatchSearchTool) -> None:
        """Test that set_project_path updates project_root."""
        tool.set_project_path("/new/root")
        assert tool.project_root == "/new/root"


class TestBatchSearchToolDefinition:
    """Tests for get_tool_definition()."""

    def test_tool_definition_structure(self, tool: BatchSearchTool) -> None:
        """Test that the tool definition has correct keys."""
        defn = tool.get_tool_definition()
        assert "name" in defn
        assert "description" in defn
        assert "inputSchema" in defn

    def test_tool_definition_name(self, tool: BatchSearchTool) -> None:
        """Test that the tool name is batch_search."""
        defn = tool.get_tool_definition()
        assert defn["name"] == "batch_search"

    def test_tool_definition_description_contains_when_to_use(
        self, tool: BatchSearchTool
    ) -> None:
        """Test that the description contains WHEN TO USE section."""
        defn = tool.get_tool_definition()
        assert "WHEN TO USE" in defn["description"]

    def test_tool_definition_description_contains_when_not_to_use(
        self, tool: BatchSearchTool
    ) -> None:
        """Test that the description contains WHEN NOT TO USE section."""
        defn = tool.get_tool_definition()
        assert "WHEN NOT TO USE" in defn["description"]

    def test_queries_required_field(self, tool: BatchSearchTool) -> None:
        """Test that queries is in the required array."""
        defn = tool.get_tool_definition()
        schema = defn["inputSchema"]
        assert "queries" in schema.get("required", [])

    def test_queries_min_max_items(self, tool: BatchSearchTool) -> None:
        """Test that queries schema enforces minItems=2 and maxItems=10."""
        defn = tool.get_tool_definition()
        queries_schema = defn["inputSchema"]["properties"]["queries"]
        assert queries_schema["minItems"] == 2
        assert queries_schema["maxItems"] == 10


class TestBatchSearchToolValidation:
    """Tests for validate_arguments()."""

    def test_minimum_queries_enforced(self, tool: BatchSearchTool) -> None:
        """Test that fewer than 2 queries raises a ValueError."""
        with pytest.raises(ValueError, match="at least 2 queries"):
            tool.validate_arguments({"queries": [{"pattern": "foo"}]})

    def test_maximum_queries_enforced(self, tool: BatchSearchTool) -> None:
        """Test that more than 10 queries raises a ValueError."""
        queries = [{"pattern": f"pattern_{i}"} for i in range(11)]
        with pytest.raises(ValueError, match="at most 10 queries"):
            tool.validate_arguments({"queries": queries})

    def test_queries_not_a_list_raises(self, tool: BatchSearchTool) -> None:
        """Test that non-list queries raises ValueError."""
        with pytest.raises(ValueError, match="queries must be an array"):
            tool.validate_arguments({"queries": "not a list"})

    def test_valid_two_queries_passes(self, tool: BatchSearchTool) -> None:
        """Test that exactly two valid queries passes validation."""
        result = tool.validate_arguments(
            {"queries": [{"pattern": "alpha"}, {"pattern": "beta"}]}
        )
        assert result is True

    def test_missing_pattern_raises(self, tool: BatchSearchTool) -> None:
        """Test that a query missing pattern raises ValueError."""
        with pytest.raises(ValueError, match="pattern"):
            tool.validate_arguments({"queries": [{"label": "no pattern"}, {"pattern": "ok"}]})


class TestBatchSearchToolExecution:
    """Tests for execute() — core test class."""

    @pytest.mark.asyncio
    async def test_execute_parallel_searches(self, tool: BatchSearchTool) -> None:
        """Test that execute runs searches in parallel and returns results for each query."""
        fake_stdout = b""  # empty means 0 matches
        fake_results = [(0, fake_stdout, b""), (0, fake_stdout, b"")]

        with patch(
            "tree_sitter_analyzer.mcp.tools.batch_search_tool.fd_rg_utils.run_parallel_rg_searches",
            new_callable=AsyncMock,
            return_value=fake_results,
        ):
            result = await tool.execute(
                {
                    "queries": [
                        {"pattern": "ClassA"},
                        {"pattern": "ClassB"},
                    ]
                }
            )

        assert "queries" in result
        assert len(result["queries"]) == 2
        assert result["queries"][0]["pattern"] == "ClassA"
        assert result["queries"][1]["pattern"] == "ClassB"

    @pytest.mark.asyncio
    async def test_results_aggregated(self, tool: BatchSearchTool) -> None:
        """Test that total_matches is the sum of all individual match counts."""
        # Simulate 3 matches for first query, 2 for second
        import json

        lines_q1 = b"\n".join(
            json.dumps({"type": "match", "data": {"path": {"text": f"file{i}.py"}, "line_number": i, "lines": {"text": "x"}, "submatches": []}}).encode()
            for i in range(3)
        )
        lines_q2 = b"\n".join(
            json.dumps({"type": "match", "data": {"path": {"text": f"file{i}.py"}, "line_number": i, "lines": {"text": "x"}, "submatches": []}}).encode()
            for i in range(2)
        )
        fake_results = [(0, lines_q1, b""), (0, lines_q2, b"")]

        with patch(
            "tree_sitter_analyzer.mcp.tools.batch_search_tool.fd_rg_utils.run_parallel_rg_searches",
            new_callable=AsyncMock,
            return_value=fake_results,
        ):
            result = await tool.execute(
                {
                    "queries": [
                        {"pattern": "alpha"},
                        {"pattern": "beta"},
                    ]
                }
            )

        assert result["total_matches"] == 5

    @pytest.mark.asyncio
    async def test_matches_truncated_at_20(self, tool: BatchSearchTool) -> None:
        """Test that matches are truncated at _BATCH_MAX_MATCHES_PER_QUERY (20)."""
        import json

        num_matches = 25
        lines = b"\n".join(
            json.dumps({"type": "match", "data": {"path": {"text": f"file{i}.py"}, "line_number": i, "lines": {"text": "x"}, "submatches": []}}).encode()
            for i in range(num_matches)
        )
        fake_results = [(0, lines, b""), (0, b"", b"")]

        with patch(
            "tree_sitter_analyzer.mcp.tools.batch_search_tool.fd_rg_utils.run_parallel_rg_searches",
            new_callable=AsyncMock,
            return_value=fake_results,
        ):
            result = await tool.execute(
                {
                    "queries": [
                        {"pattern": "bigpattern"},
                        {"pattern": "small"},
                    ]
                }
            )

        first_query = result["queries"][0]
        assert first_query["match_count"] == num_matches
        assert len(first_query["matches"]) == _BATCH_MAX_MATCHES_PER_QUERY
        assert first_query["truncated"] is True

    @pytest.mark.asyncio
    async def test_empty_results(self, tool: BatchSearchTool) -> None:
        """Test that a ripgrep no-match return code produces match_count=0."""
        # rc=1 means no matches found (rg convention)
        fake_results = [(1, b"", b""), (1, b"", b"")]

        with patch(
            "tree_sitter_analyzer.mcp.tools.batch_search_tool.fd_rg_utils.run_parallel_rg_searches",
            new_callable=AsyncMock,
            return_value=fake_results,
        ):
            result = await tool.execute(
                {
                    "queries": [
                        {"pattern": "notfound1"},
                        {"pattern": "notfound2"},
                    ]
                }
            )

        assert result["total_matches"] == 0
        for q in result["queries"]:
            assert q["match_count"] == 0
            assert q["matches"] == []
            assert q["truncated"] is False

    @pytest.mark.asyncio
    async def test_label_defaults_to_pattern(self, tool: BatchSearchTool) -> None:
        """Test that when no label is provided, the pattern is used as the label."""
        fake_results = [(1, b"", b""), (1, b"", b"")]

        with patch(
            "tree_sitter_analyzer.mcp.tools.batch_search_tool.fd_rg_utils.run_parallel_rg_searches",
            new_callable=AsyncMock,
            return_value=fake_results,
        ):
            result = await tool.execute(
                {
                    "queries": [
                        {"pattern": "my_func"},
                        {"pattern": "other_func"},
                    ]
                }
            )

        assert result["queries"][0]["label"] == "my_func"

    @pytest.mark.asyncio
    async def test_custom_label_used(self, tool: BatchSearchTool) -> None:
        """Test that a provided label is used in the result."""
        fake_results = [(1, b"", b""), (1, b"", b"")]

        with patch(
            "tree_sitter_analyzer.mcp.tools.batch_search_tool.fd_rg_utils.run_parallel_rg_searches",
            new_callable=AsyncMock,
            return_value=fake_results,
        ):
            result = await tool.execute(
                {
                    "queries": [
                        {"pattern": "fn1", "label": "My Search Label"},
                        {"pattern": "fn2"},
                    ]
                }
            )

        assert result["queries"][0]["label"] == "My Search Label"

    @pytest.mark.asyncio
    async def test_execution_note_mentions_count(self, tool: BatchSearchTool) -> None:
        """Test that execution_note mentions the number of searches run."""
        fake_results = [(1, b"", b""), (1, b"", b""), (1, b"", b"")]

        with patch(
            "tree_sitter_analyzer.mcp.tools.batch_search_tool.fd_rg_utils.run_parallel_rg_searches",
            new_callable=AsyncMock,
            return_value=fake_results,
        ):
            result = await tool.execute(
                {
                    "queries": [
                        {"pattern": "a"},
                        {"pattern": "b"},
                        {"pattern": "c"},
                    ]
                }
            )

        assert "3" in result["execution_note"]
