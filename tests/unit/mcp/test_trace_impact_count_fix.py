"""
TDD tests for trace_impact call_count truncation bug.

Validated against spring-framework (@Component appears 695 times).

Bug: call_count was computed from len(usages) AFTER truncation by max_results,
causing impact_level to be classified as "low" when the true count is "high".
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

SPRING_BASE = Path("/workspaces/claude-source-run-version/spring-framework")

skip_if_no_spring = pytest.mark.skipif(
    not SPRING_BASE.exists(),
    reason="spring-framework not cloned at expected path",
)


@pytest.fixture
def tool():
    from tree_sitter_analyzer.mcp.tools.trace_impact_tool import TraceImpactTool
    return TraceImpactTool(str(SPRING_BASE))


class TestTraceImpactCountAccuracy:
    """call_count must reflect true match total, not the display-capped count."""

    @skip_if_no_spring
    def test_call_count_not_capped_by_max_results(self, tool):
        """With max_results=5 and 695 real matches, call_count must be 695."""
        import asyncio
        r = asyncio.get_event_loop().run_until_complete(
            tool.execute({"symbol": "Component", "max_results": 5})
        )
        call_count = r.get("call_count", 0)
        usages = r.get("usages", [])

        assert len(usages) == 5, f"usages should be capped at 5, got {len(usages)}"

        assert call_count > 5, (
            f"call_count={call_count} but @Component appears 695+ times in spring-framework. "
            "Bug: call_count was computed from len(usages) AFTER truncation."
        )
        assert call_count > 100, (
            f"@Component is a core Spring stereotype, should appear hundreds of times. "
            f"Got call_count={call_count}"
        )

    @skip_if_no_spring
    def test_impact_level_reflects_true_count(self, tool):
        """impact_level must use true total, not capped count."""
        import asyncio
        r = asyncio.get_event_loop().run_until_complete(
            tool.execute({"symbol": "Component", "max_results": 5})
        )
        impact_level = r.get("impact_level")
        assert impact_level == "high", (
            f"@Component has 695+ usages → impact must be 'high'. "
            f"Got: '{impact_level}'. Bug: impact_level computed from truncated list."
        )

    @skip_if_no_spring
    def test_truncated_flag_set_when_results_capped(self, tool):
        """truncated=True must be returned when results exceed max_results."""
        import asyncio
        r = asyncio.get_event_loop().run_until_complete(
            tool.execute({"symbol": "Component", "max_results": 5})
        )
        assert r.get("truncated") is True, (
            "truncated must be True when results are capped by max_results"
        )

    def test_unit_count_not_capped_by_mock(self):
        """Unit test without external dependency."""
        import asyncio

        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import TraceImpactTool

        # Build 100 fake matches
        fake_stdout = b"\n".join(
            f'{{"type":"match","data":{{"path":{{"text":"file{i}.java"}},'
            f'"line_number":{i},"lines":{{"text":"Component usage {i}"}}}}}}'.encode()
            for i in range(100)
        )

        with patch(
            "tree_sitter_analyzer.mcp.tools.trace_impact_tool.run_command_capture",
            new=AsyncMock(return_value=(0, fake_stdout, b"")),
        ):
            tool = TraceImpactTool("/tmp")
            r = asyncio.get_event_loop().run_until_complete(
                tool.execute({"symbol": "Component", "max_results": 5})
            )

        assert r.get("call_count") == 100, (
            f"call_count should be 100 (true total), got {r.get('call_count')}. "
            "max_results=5 should only cap the display list."
        )
        assert len(r.get("usages", [])) == 5, "usages must be capped at max_results"
        assert r.get("impact_level") == "high", (
            "100 matches → HIGH IMPACT. Should not be affected by max_results=5."
        )
        assert r.get("truncated") is True
