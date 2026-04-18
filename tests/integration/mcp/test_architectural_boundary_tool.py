"""Integration tests for Architectural Boundary MCP Tool."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.architectural_boundary_tool import (
    ArchitecturalBoundaryTool,
)


def _write_tmp(project_dir: str, rel_path: str, content: str) -> str:
    full = Path(project_dir) / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    return str(full)


@pytest.fixture
def tool() -> ArchitecturalBoundaryTool:
    return ArchitecturalBoundaryTool()


class TestArchitecturalBoundaryToolDefinition:
    def test_tool_name(self, tool: ArchitecturalBoundaryTool) -> None:
        defn = tool.get_tool_definition()
        assert defn["name"] == "architectural_boundary"

    def test_tool_has_description(self, tool: ArchitecturalBoundaryTool) -> None:
        defn = tool.get_tool_definition()
        assert "layer" in defn["description"].lower()
        assert "violation" in defn["description"].lower()

    def test_tool_schema_has_format(self, tool: ArchitecturalBoundaryTool) -> None:
        defn = tool.get_tool_definition()
        assert "format" in defn["inputSchema"]["properties"]

    def test_tool_schema_not_required_format(
        self, tool: ArchitecturalBoundaryTool,
    ) -> None:
        defn = tool.get_tool_definition()
        assert "required" not in defn["inputSchema"] or \
            "format" not in defn["inputSchema"].get("required", [])


class TestArchitecturalBoundaryToolExecution:
    @pytest.mark.asyncio
    async def test_execute_clean_project(
        self, tool: ArchitecturalBoundaryTool,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(tmp, "controllers/user.py",
                       "from services.user_service import UserService\n")
            _write_tmp(tmp, "services/user_service.py",
                       "from repositories.repo import Repo\n")
            _write_tmp(tmp, "repositories/repo.py", "pass\n")

            tool.project_root = tmp
            result = await tool.execute({})
            assert result["result"]["compliance_score"] == 1.0
            assert result["result"]["violation_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_with_violations(
        self, tool: ArchitecturalBoundaryTool,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(tmp, "controllers/user.py",
                       "from repositories.repo import Repo\n")
            _write_tmp(tmp, "services/svc.py", "pass\n")
            _write_tmp(tmp, "repositories/repo.py", "pass\n")

            tool.project_root = tmp
            result = await tool.execute({})
            assert result["result"]["violation_count"] > 0
            assert result["result"]["compliance_score"] < 1.0

    @pytest.mark.asyncio
    async def test_execute_toon_format(
        self, tool: ArchitecturalBoundaryTool,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_tmp(tmp, "controllers/a.py",
                       "from services.svc import Svc\n")
            _write_tmp(tmp, "services/svc.py", "pass\n")

            tool.project_root = tmp
            result = await tool.execute({"format": "toon"})
            assert "content" in result
            assert "summary" in result
            assert result["summary"]["compliance_score"] == 1.0

    @pytest.mark.asyncio
    async def test_execute_empty_project(
        self, tool: ArchitecturalBoundaryTool,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tool.project_root = tmp
            result = await tool.execute({})
            assert result["result"]["total_files"] == 0
            assert result["result"]["compliance_score"] == 1.0


class TestArchitecturalBoundaryToolValidation:
    def test_validate_valid_arguments(self, tool: ArchitecturalBoundaryTool) -> None:
        assert tool.validate_arguments({})

    def test_validate_json_format(self, tool: ArchitecturalBoundaryTool) -> None:
        assert tool.validate_arguments({"format": "json"})

    def test_validate_toon_format(self, tool: ArchitecturalBoundaryTool) -> None:
        assert tool.validate_arguments({"format": "toon"})

    def test_validate_invalid_format(self, tool: ArchitecturalBoundaryTool) -> None:
        with pytest.raises(ValueError, match="Invalid format"):
            tool.validate_arguments({"format": "xml"})
