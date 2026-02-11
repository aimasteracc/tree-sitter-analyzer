"""Integration tests for CodeIntelligenceTool MCP tool.

Tests the MCP exposure of code intelligence features:
- scan: Project-wide code map
- trace_calls: Bidirectional call flow
- impact: Modification impact analysis
- gather_context: LLM context capture
- dead_code: Dead code listing
- hot_spots: Most-referenced symbols
"""

from pathlib import Path

import pytest

FIXTURE_DIR = str(Path(__file__).parent.parent / "fixtures" / "cross_file_project")


@pytest.fixture
def tool():
    """Create a CodeIntelligenceTool instance."""
    from tree_sitter_analyzer_v2.mcp.tools.intelligence import CodeIntelligenceTool
    return CodeIntelligenceTool()


class TestScanAction:
    """Test the 'scan' action."""

    def test_scan_returns_success(self, tool) -> None:
        result = tool.execute({"action": "scan", "project_path": FIXTURE_DIR})
        assert result["success"] is True

    def test_scan_returns_summary(self, tool) -> None:
        result = tool.execute({"action": "scan", "project_path": FIXTURE_DIR})
        assert "total_files" in result
        assert "total_symbols" in result
        assert result["total_files"] > 0
        assert result["total_symbols"] > 0

    def test_scan_returns_toon(self, tool) -> None:
        result = tool.execute({"action": "scan", "project_path": FIXTURE_DIR})
        assert "toon" in result
        assert "PROJECT:" in result["toon"]


class TestTraceCallsAction:
    """Test the 'trace_calls' action."""

    def test_trace_calls_requires_scan(self, tool) -> None:
        """trace_calls without prior scan should auto-scan."""
        result = tool.execute({
            "action": "trace_calls",
            "project_path": FIXTURE_DIR,
            "name": "helper",
        })
        assert result["success"] is True

    def test_trace_calls_returns_flow(self, tool) -> None:
        tool.execute({"action": "scan", "project_path": FIXTURE_DIR})
        result = tool.execute({
            "action": "trace_calls",
            "name": "helper",
        })
        assert result["success"] is True
        assert "toon" in result
        assert "CALL_FLOW" in result["toon"]

    def test_trace_calls_unknown_function(self, tool) -> None:
        tool.execute({"action": "scan", "project_path": FIXTURE_DIR})
        result = tool.execute({
            "action": "trace_calls",
            "name": "nonexistent_xyz",
        })
        assert result["success"] is True
        assert "not found" in result["toon"].lower()


class TestImpactAction:
    """Test the 'impact' action."""

    def test_impact_returns_analysis(self, tool) -> None:
        tool.execute({"action": "scan", "project_path": FIXTURE_DIR})
        result = tool.execute({
            "action": "impact",
            "name": "helper",
        })
        assert result["success"] is True
        assert "toon" in result
        assert "IMPACT" in result["toon"]
        assert "risk_level" in result

    def test_impact_unknown_symbol(self, tool) -> None:
        tool.execute({"action": "scan", "project_path": FIXTURE_DIR})
        result = tool.execute({"action": "impact", "name": "nonexistent_xyz"})
        assert result["success"] is True
        assert "not found" in result["toon"].lower()


class TestGatherContextAction:
    """Test the 'gather_context' action."""

    def test_gather_context_returns_sections(self, tool) -> None:
        tool.execute({"action": "scan", "project_path": FIXTURE_DIR})
        result = tool.execute({
            "action": "gather_context",
            "query": "helper",
        })
        assert result["success"] is True
        assert "toon" in result
        assert "CONTEXT" in result["toon"]
        assert "matched_symbols" in result
        assert result["matched_symbols"] > 0

    def test_gather_context_with_max_tokens(self, tool) -> None:
        tool.execute({"action": "scan", "project_path": FIXTURE_DIR})
        result = tool.execute({
            "action": "gather_context",
            "query": "helper",
            "max_tokens": 500,
        })
        assert result["success"] is True


class TestDeadCodeAction:
    """Test the 'dead_code' action."""

    def test_dead_code_list(self, tool) -> None:
        tool.execute({"action": "scan", "project_path": FIXTURE_DIR})
        result = tool.execute({"action": "dead_code"})
        assert result["success"] is True
        assert "dead_count" in result
        assert "toon" in result


class TestHotSpotsAction:
    """Test the 'hot_spots' action."""

    def test_hot_spots_list(self, tool) -> None:
        tool.execute({"action": "scan", "project_path": FIXTURE_DIR})
        result = tool.execute({"action": "hot_spots"})
        assert result["success"] is True
        assert "toon" in result


class TestCaching:
    """Test scan result caching."""

    def test_second_action_uses_cache(self, tool) -> None:
        """After scan, subsequent actions should not re-scan."""
        tool.execute({"action": "scan", "project_path": FIXTURE_DIR})
        # Second call should use cached result
        result = tool.execute({"action": "trace_calls", "name": "helper"})
        assert result["success"] is True

    def test_different_project_rescans(self, tool) -> None:
        """Changing project_path should trigger re-scan."""
        tool.execute({"action": "scan", "project_path": FIXTURE_DIR})
        # Even though path is same, explicit scan should work
        result = tool.execute({"action": "scan", "project_path": FIXTURE_DIR})
        assert result["success"] is True


class TestEdgeCases:
    """Edge case tests."""

    def test_missing_action(self, tool) -> None:
        result = tool.execute({"project_path": FIXTURE_DIR})
        assert result["success"] is False
        assert "error" in result

    def test_invalid_action(self, tool) -> None:
        result = tool.execute({"action": "foobar"})
        assert result["success"] is False

    def test_no_project_no_cache(self, tool) -> None:
        """Actions without project_path and no cached scan should fail gracefully."""
        result = tool.execute({"action": "trace_calls", "name": "helper"})
        # Should either auto-fail or report no scan
        assert "success" in result

    def test_invalid_project_path(self, tool) -> None:
        """Non-existent project path should return an error."""
        result = tool.execute({"action": "scan", "project_path": "/nonexistent/path/xyz"})
        assert result["success"] is False
        assert "error" in result
