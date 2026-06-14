#!/usr/bin/env python3
"""
Tests for ModificationGuardTool MCP Tool.

Verifies safety verdicts, required actions generation, callers-by-file grouping,
project path propagation, and argument validation.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.modification_guard_tool import ModificationGuardTool


@pytest.fixture
def tool() -> ModificationGuardTool:
    """Create a fresh ModificationGuardTool instance for each test."""
    return ModificationGuardTool()


def _trace_result(
    total_count: int,
    usages: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Build a fake trace_impact result dict."""
    return {
        "success": True,
        "call_count": total_count,
        "usages": usages or [],
    }


class TestModificationGuardToolInitialization:
    """Tests for tool initialization."""

    def test_init_creates_tool(self, tool: ModificationGuardTool) -> None:
        """Test that initialization creates a tool instance."""
        assert tool is not None

    def test_init_creates_trace_impact_tool(self, tool: ModificationGuardTool) -> None:
        """Test that initialization also creates an inner TraceImpactTool."""
        assert hasattr(tool, "_trace_impact_tool")

    def test_set_project_path_propagates(self) -> None:
        """Test that set_project_path propagates to the inner trace_impact tool."""
        t = ModificationGuardTool()
        t.set_project_path("/updated/path")
        assert t.project_root == "/updated/path"
        assert t._trace_impact_tool.project_root == "/updated/path"


class TestModificationGuardToolDefinition:
    """Tests for get_tool_definition()."""

    def test_description_contains_when_to_use(
        self, tool: ModificationGuardTool
    ) -> None:
        """Test that the description contains WHEN TO USE section."""
        defn = tool.get_tool_definition()
        assert "WHEN TO USE" in defn["description"]

    def test_description_contains_when_not_to_use(
        self, tool: ModificationGuardTool
    ) -> None:
        """Test that the description contains WHEN NOT TO USE section."""
        defn = tool.get_tool_definition()
        assert "WHEN NOT TO USE" in defn["description"]

    def test_required_fields(self, tool: ModificationGuardTool) -> None:
        """Test that symbol and modification_type are required."""
        defn = tool.get_tool_definition()
        required = defn["inputSchema"].get("required", [])
        assert "symbol" in required
        assert "modification_type" in required

    def test_modification_type_enum(self, tool: ModificationGuardTool) -> None:
        """Test that modification_type has correct enum values."""
        defn = tool.get_tool_definition()
        mt_prop = defn["inputSchema"]["properties"]["modification_type"]
        assert "rename" in mt_prop["enum"]
        assert "delete" in mt_prop["enum"]
        assert "signature_change" in mt_prop["enum"]


class TestModificationGuardToolValidation:
    """Tests for validate_arguments()."""

    def test_missing_symbol_raises(self, tool: ModificationGuardTool) -> None:
        """Test that missing symbol raises ValueError."""
        with pytest.raises(ValueError, match="symbol"):
            tool.validate_arguments({"modification_type": "rename"})

    def test_empty_symbol_raises(self, tool: ModificationGuardTool) -> None:
        """Test that empty symbol raises ValueError."""
        with pytest.raises(ValueError, match="symbol"):
            tool.validate_arguments({"symbol": "   ", "modification_type": "rename"})

    def test_invalid_modification_type_raises(
        self, tool: ModificationGuardTool
    ) -> None:
        """Test that an invalid modification_type raises ValueError."""
        with pytest.raises(ValueError, match="modification_type"):
            tool.validate_arguments({"symbol": "foo", "modification_type": "explode"})

    def test_valid_arguments_pass(self, tool: ModificationGuardTool) -> None:
        """Test that valid arguments pass validation."""
        result = tool.validate_arguments(
            {"symbol": "myFunc", "modification_type": "rename"}
        )
        assert result is True


class TestModificationGuardToolExecution:
    """Tests for execute() — core test class."""

    @pytest.mark.asyncio
    async def test_safe_verdict_no_callers(self, tool: ModificationGuardTool) -> None:
        """Test that 0 callers produces safety_verdict=SAFE."""
        with patch.object(
            tool._trace_impact_tool,
            "execute",
            new_callable=AsyncMock,
            return_value=_trace_result(0),
        ):
            result = await tool.execute(
                {"symbol": "orphanFunc", "modification_type": "delete"}
            )

        assert result["success"] is True
        assert result["safety_verdict"] == "SAFE"
        assert result["total_callers"] == 0

    @pytest.mark.asyncio
    async def test_unknown_symbol_is_not_found_not_safe(
        self, tool: ModificationGuardTool
    ) -> None:
        """Wave 1b (audit edit-08): a symbol that resolves to ZERO occurrences
        (trace_impact found=False / NOT_FOUND) must NOT be reported as SAFE —
        that is a dangerous false-safe. It must return verdict=NOT_FOUND."""
        not_found_trace = {
            "success": True,
            "call_count": 0,
            "usages": [],
            "found": False,
            "verdict": "NOT_FOUND",
        }
        with patch.object(
            tool._trace_impact_tool,
            "execute",
            new_callable=AsyncMock,
            return_value=not_found_trace,
        ):
            result = await tool.execute(
                {
                    "symbol": "this_symbol_does_not_exist_xyz",
                    "modification_type": "rename",
                }
            )

        assert result["success"] is True
        assert result["verdict"] == "NOT_FOUND"
        assert result["safety_verdict"] == "NOT_FOUND"
        assert result["agent_summary"]["verdict"] == "NOT_FOUND"
        # The dangerous old behavior — never claim SAFE for an unknown symbol.
        assert result["safety_verdict"] != "SAFE"
        # agent_summary must carry ``risk`` on EVERY path (no KeyError for
        # consumers reading agent_summary["risk"] on the NOT_FOUND branch).
        assert result["agent_summary"]["risk"] == "unknown"

    @pytest.mark.asyncio
    async def test_known_symbol_zero_callers_is_still_safe_not_notfound(
        self, tool: ModificationGuardTool
    ) -> None:
        """The distinction edit-08 requires: a KNOWN symbol with 0 callers
        (found=True, no NOT_FOUND verdict) stays SAFE — only an UNKNOWN symbol
        is NOT_FOUND."""
        known_zero = {
            "success": True,
            "call_count": 0,
            "usages": [],
            "found": True,
        }
        with patch.object(
            tool._trace_impact_tool,
            "execute",
            new_callable=AsyncMock,
            return_value=known_zero,
        ):
            result = await tool.execute(
                {"symbol": "definedButUncalled", "modification_type": "delete"}
            )
        assert result["safety_verdict"] == "SAFE"
        assert result["verdict"] == "SAFE"
        assert result["verdict"] != "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_caution_verdict_few_callers(
        self, tool: ModificationGuardTool
    ) -> None:
        """Test that 3 callers (low impact) produces safety_verdict=CAUTION."""
        usages = [{"file": "src/a.py"}, {"file": "src/b.py"}, {"file": "src/c.py"}]
        with patch.object(
            tool._trace_impact_tool,
            "execute",
            new_callable=AsyncMock,
            return_value=_trace_result(3, usages),
        ):
            result = await tool.execute(
                {"symbol": "smallFunc", "modification_type": "rename"}
            )

        assert result["safety_verdict"] == "CAUTION"
        assert result["total_callers"] == 3
        assert result["ripgrep_occurrences"] == 3
        assert result["count_unit"] == "ripgrep_occurrences"
        assert "callers=3" not in result["summary_line"]
        assert "ripgrep_occurrences=3" in result["summary_line"]
        assert "count_caveat" in result

    @pytest.mark.asyncio
    async def test_review_verdict_many_callers(
        self, tool: ModificationGuardTool
    ) -> None:
        """Test that 10 callers (medium impact) produces safety_verdict=REVIEW."""
        usages = [{"file": f"src/file{i}.py"} for i in range(10)]
        with patch.object(
            tool._trace_impact_tool,
            "execute",
            new_callable=AsyncMock,
            return_value=_trace_result(10, usages),
        ):
            result = await tool.execute(
                {"symbol": "mediumFunc", "modification_type": "signature_change"}
            )

        assert result["safety_verdict"] == "REVIEW"
        assert result["total_callers"] == 10

    @pytest.mark.asyncio
    async def test_unsafe_verdict_high_callers(
        self, tool: ModificationGuardTool
    ) -> None:
        """Test that 25 callers (high impact) produces safety_verdict=UNSAFE."""
        usages = [{"file": f"src/file{i}.py"} for i in range(25)]
        with patch.object(
            tool._trace_impact_tool,
            "execute",
            new_callable=AsyncMock,
            return_value=_trace_result(25, usages),
        ):
            result = await tool.execute(
                {"symbol": "bigFunc", "modification_type": "delete"}
            )

        assert result["safety_verdict"] == "UNSAFE"
        assert result["total_callers"] == 25
        assert result["impact_badge"] == "🚨 HIGH IMPACT — 25 RIPGREP OCCURRENCES"
        assert "source ripgrep occurrence(s)" in result["impact_guidance"]

    @pytest.mark.asyncio
    async def test_ast_caller_count_surfaced_when_file_path_given(
        self, tool: ModificationGuardTool
    ) -> None:
        """Guard exposes AST caller count alongside trace-derived occurrences."""
        usages = [{"file": f"src/file{i}.py"} for i in range(25)]
        with (
            patch.object(
                tool._trace_impact_tool,
                "execute",
                new_callable=AsyncMock,
                return_value=_trace_result(25, usages),
            ),
            patch.object(
                tool,
                "_try_ast_caller_count",
                new_callable=AsyncMock,
                return_value=11,
            ) as mock_ast_count,
        ):
            result = await tool.execute(
                {
                    "symbol": "bigFunc",
                    "modification_type": "delete",
                    "file_path": "src/big.py",
                }
            )

        mock_ast_count.assert_awaited_once_with("bigFunc", "src/big.py")
        assert result["ripgrep_occurrences"] == 25
        assert result["ast_caller_count"] == 11

    @pytest.mark.asyncio
    async def test_try_ast_caller_count_calls_codegraph_tool(
        self, tool: ModificationGuardTool
    ) -> None:
        """AST reconciliation uses callers_tool and returns its integer count."""
        fake_callers_tool = Mock()
        fake_callers_tool.execute = AsyncMock(return_value={"caller_count": 7})

        with patch(
            "tree_sitter_analyzer.mcp.tools.callers_tool.CodeGraphCallersTool",
            return_value=fake_callers_tool,
        ) as callers_cls:
            count = await tool._try_ast_caller_count("sharedFunc", "src/shared.py")

        callers_cls.assert_called_once_with(tool.project_root)
        fake_callers_tool.execute.assert_awaited_once_with(
            {
                "function_name": "sharedFunc",
                "file_path": "src/shared.py",
                "limit": 1,
                "output_format": "json",
            }
        )
        assert count == 7

    @pytest.mark.asyncio
    async def test_try_ast_caller_count_returns_none_on_tool_error(
        self, tool: ModificationGuardTool
    ) -> None:
        """AST reconciliation is best-effort and must not fail the guard."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.callers_tool.CodeGraphCallersTool",
            side_effect=RuntimeError("index unavailable"),
        ):
            count = await tool._try_ast_caller_count("sharedFunc", "src/shared.py")

        assert count is None

    @pytest.mark.asyncio
    async def test_try_ast_caller_count_ignores_non_integer_count(
        self, tool: ModificationGuardTool
    ) -> None:
        """Only integer caller_count values are surfaced."""
        fake_callers_tool = Mock()
        fake_callers_tool.execute = AsyncMock(return_value={"caller_count": "many"})

        with patch(
            "tree_sitter_analyzer.mcp.tools.callers_tool.CodeGraphCallersTool",
            return_value=fake_callers_tool,
        ):
            count = await tool._try_ast_caller_count("sharedFunc", "src/shared.py")

        assert count is None

    @pytest.mark.asyncio
    async def test_required_actions_populated_for_unsafe(
        self, tool: ModificationGuardTool
    ) -> None:
        """Test that UNSAFE verdict includes a non-empty required_actions list."""
        usages = [{"file": f"src/f{i}.py"} for i in range(25)]
        with patch.object(
            tool._trace_impact_tool,
            "execute",
            new_callable=AsyncMock,
            return_value=_trace_result(25, usages),
        ):
            result = await tool.execute(
                {"symbol": "bigFunc", "modification_type": "rename"}
            )

        assert isinstance(result["required_actions"], list)
        assert len(result["required_actions"]) > 0

    @pytest.mark.asyncio
    async def test_callers_by_file(self, tool: ModificationGuardTool) -> None:
        """Test that callers_by_file groups usages correctly by file."""
        usages = [
            {"file": "src/a.py"},
            {"file": "src/a.py"},
            {"file": "src/b.py"},
        ]
        with patch.object(
            tool._trace_impact_tool,
            "execute",
            new_callable=AsyncMock,
            return_value=_trace_result(3, usages),
        ):
            result = await tool.execute(
                {"symbol": "sharedFunc", "modification_type": "refactor"}
            )

        by_file = result["callers_by_file"]
        assert by_file.get("src/a.py") == 2
        assert by_file.get("src/b.py") == 1

    @pytest.mark.asyncio
    async def test_trace_impact_failure_surfaces_error(
        self, tool: ModificationGuardTool
    ) -> None:
        """Test that a trace_impact failure surfaces an error in the result."""
        with patch.object(
            tool._trace_impact_tool,
            "execute",
            new_callable=AsyncMock,
            return_value={"success": False, "error": "rg not found"},
        ):
            result = await tool.execute(
                {"symbol": "someFunc", "modification_type": "rename"}
            )

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_symbol_returned_in_result(self, tool: ModificationGuardTool) -> None:
        """Test that the result includes the queried symbol."""
        with patch.object(
            tool._trace_impact_tool,
            "execute",
            new_callable=AsyncMock,
            return_value=_trace_result(0),
        ):
            result = await tool.execute(
                {"symbol": "mySpecialFunc", "modification_type": "delete"}
            )

        assert result["symbol"] == "mySpecialFunc"

    @pytest.mark.asyncio
    async def test_modification_type_returned_in_result(
        self, tool: ModificationGuardTool
    ) -> None:
        """Test that modification_type is echoed back in the result."""
        with patch.object(
            tool._trace_impact_tool,
            "execute",
            new_callable=AsyncMock,
            return_value=_trace_result(0),
        ):
            result = await tool.execute(
                {"symbol": "func", "modification_type": "behavior_change"}
            )

        assert result["modification_type"] == "behavior_change"


# ---------------------------------------------------------------------------
# PageRank critical_nodes integration
# ---------------------------------------------------------------------------


class TestCriticalNodesIntegration:
    """modification_guard reads critical_nodes.json and boosts warnings."""

    @pytest.mark.asyncio
    async def test_critical_node_adds_architecture_warning(
        self, tmp_path: Path
    ) -> None:
        """If symbol is in critical_nodes.json, result includes architecture info."""

        cache = tmp_path / ".tree-sitter-cache"
        cache.mkdir()
        (cache / "critical_nodes.json").write_text(
            json.dumps(
                [
                    {"name": "BeanFactory", "pagerank": 0.0156, "inbound_refs": 16},
                    {
                        "name": "InitializingBean",
                        "pagerank": 0.0089,
                        "inbound_refs": 171,
                    },
                ]
            )
        )

        tool = ModificationGuardTool(project_root=str(tmp_path))
        with patch.object(
            tool._trace_impact_tool,
            "execute",
            new_callable=AsyncMock,
            return_value=_trace_result(5),
        ):
            result = await tool.execute(
                {"symbol": "BeanFactory", "modification_type": "rename"}
            )

        assert "architecture_rank" in result
        assert result["architecture_rank"] == 1
        assert "architecture_warning" in result
        assert "BeanFactory" in result["architecture_warning"]

    @pytest.mark.asyncio
    async def test_critical_node_boosts_verdict(self, tmp_path: Path) -> None:
        """Top-10 critical node boosts safety verdict by one level."""

        cache = tmp_path / ".tree-sitter-cache"
        cache.mkdir()
        (cache / "critical_nodes.json").write_text(
            json.dumps(
                [
                    {"name": "BeanFactory", "pagerank": 0.0156, "inbound_refs": 16},
                ]
            )
        )

        tool = ModificationGuardTool(project_root=str(tmp_path))
        # 5 callers would normally be CAUTION
        with patch.object(
            tool._trace_impact_tool,
            "execute",
            new_callable=AsyncMock,
            return_value=_trace_result(5),
        ):
            result = await tool.execute(
                {"symbol": "BeanFactory", "modification_type": "rename"}
            )

        # Boosted from CAUTION → REVIEW because it's a top architecture node
        assert result["safety_verdict"] == "REVIEW"

    @pytest.mark.asyncio
    async def test_non_critical_node_no_architecture_info(self, tmp_path: Path) -> None:
        """Symbols not in critical_nodes.json have no architecture fields."""

        cache = tmp_path / ".tree-sitter-cache"
        cache.mkdir()
        (cache / "critical_nodes.json").write_text(
            json.dumps(
                [
                    {"name": "BeanFactory", "pagerank": 0.0156, "inbound_refs": 16},
                ]
            )
        )

        tool = ModificationGuardTool(project_root=str(tmp_path))
        with patch.object(
            tool._trace_impact_tool,
            "execute",
            new_callable=AsyncMock,
            return_value=_trace_result(3),
        ):
            result = await tool.execute(
                {"symbol": "helperFunc", "modification_type": "rename"}
            )

        assert "architecture_rank" not in result

    @pytest.mark.asyncio
    async def test_no_critical_nodes_file_still_works(
        self, tool: ModificationGuardTool
    ) -> None:
        """Without critical_nodes.json, tool works normally (no crash)."""
        with patch.object(
            tool._trace_impact_tool,
            "execute",
            new_callable=AsyncMock,
            return_value=_trace_result(10),
        ):
            result = await tool.execute(
                {"symbol": "func", "modification_type": "rename"}
            )

        assert result["success"] is True
        assert "architecture_rank" not in result
