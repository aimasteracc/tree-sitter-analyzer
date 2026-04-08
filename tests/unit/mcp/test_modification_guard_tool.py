#!/usr/bin/env python3
"""
Tests for ModificationGuardTool MCP Tool.

Verifies safety verdicts, required actions generation, callers-by-file grouping,
project path propagation, and argument validation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

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

    def test_init_with_project_root(self) -> None:
        """Test initialization with a project root sets project_root."""
        t = ModificationGuardTool(project_root="/opt/project")
        assert t.project_root == "/opt/project"

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

    def test_tool_definition_structure(self, tool: ModificationGuardTool) -> None:
        """Test that the tool definition has correct keys."""
        defn = tool.get_tool_definition()
        assert "name" in defn
        assert "description" in defn
        assert "inputSchema" in defn

    def test_tool_definition_name(self, tool: ModificationGuardTool) -> None:
        """Test that the tool name is modification_guard."""
        defn = tool.get_tool_definition()
        assert defn["name"] == "modification_guard"

    def test_description_contains_when_to_use(self, tool: ModificationGuardTool) -> None:
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

    def test_invalid_modification_type_raises(self, tool: ModificationGuardTool) -> None:
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
