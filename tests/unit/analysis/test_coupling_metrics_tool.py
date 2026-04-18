"""Tests for Coupling Metrics MCP Tool."""
from __future__ import annotations

import asyncio
import tempfile

import pytest

from tree_sitter_analyzer.mcp.tools.coupling_metrics_tool import (
    CouplingMetricsTool,
)


@pytest.fixture
def tool() -> CouplingMetricsTool:
    with tempfile.TemporaryDirectory() as tmp:
        yield CouplingMetricsTool(project_root=tmp)


def _run(tool: CouplingMetricsTool, args: dict) -> dict:
    return asyncio.get_event_loop().run_until_complete(tool.execute(args))


class TestCouplingMetricsTool:
    def test_tool_definition(self, tool: CouplingMetricsTool) -> None:
        definition = tool.get_tool_definition()
        assert definition["name"] == "coupling_metrics"
        assert "inputSchema" in definition

    def test_execute_json_format(self, tool: CouplingMetricsTool) -> None:
        result = _run(tool, {"format": "json"})
        assert "result" in result
        data = result["result"]
        assert "total_files" in data
        assert "avg_fan_out" in data

    def test_execute_toon_format(self, tool: CouplingMetricsTool) -> None:
        result = _run(tool, {"format": "toon"})
        text = result["content"][0]["text"]
        assert "Coupling Metrics" in text

    def test_validate_arguments_valid(
        self, tool: CouplingMetricsTool
    ) -> None:
        assert tool.validate_arguments({}) is True
        assert tool.validate_arguments({"format": "json"}) is True

    def test_validate_arguments_invalid_format(
        self, tool: CouplingMetricsTool
    ) -> None:
        with pytest.raises(ValueError, match="Invalid format"):
            tool.validate_arguments({"format": "xml"})

    def test_summary_in_toon(self, tool: CouplingMetricsTool) -> None:
        result = _run(tool, {"format": "toon"})
        summary = result["summary"]
        assert "total_files" in summary
        assert "unstable_count" in summary
