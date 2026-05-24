#!/usr/bin/env python3
"""
Security regression tests for BuildProjectIndexTool.validate_arguments (r37fB).

Attack vector: pass roots=["/etc"] or roots=["../"] to trigger unbounded
filesystem traversal and write index data to an attacker-controlled path.

Fix: validate_arguments now resolves every root to an absolute path and
rejects anything outside self.project_root with a ValueError before any
filesystem traversal begins.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.build_project_index_tool import (
    BuildProjectIndexTool,
)


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Minimal project directory used as project_root for all security tests."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x = 1\n")
    return tmp_path


@pytest.fixture
def tool(project_dir: Path) -> BuildProjectIndexTool:
    """Tool bound to the temp project directory."""
    return BuildProjectIndexTool(project_root=str(project_dir))


# ---------------------------------------------------------------------------
# Scenario 1: absolute path outside project root  →  ValueError
# ---------------------------------------------------------------------------


class TestAbsolutePathOutsideProject:
    """roots=['/etc'] must raise ValueError (path traversal attack)."""

    def test_etc_raises(self, tool: BuildProjectIndexTool) -> None:
        with pytest.raises(ValueError, match="Refusing to index outside project"):
            tool.validate_arguments({"roots": ["/etc"]})

    def test_tmp_raises_when_not_project(self, tool: BuildProjectIndexTool) -> None:
        """Any absolute path not under project_root must be refused."""
        with pytest.raises(ValueError, match="Refusing to index outside project"):
            tool.validate_arguments({"roots": ["/tmp"]})

    def test_home_dot_ssh_raises(self, tool: BuildProjectIndexTool) -> None:
        """Sensitive absolute paths must be refused."""
        import os

        ssh_path = os.path.expanduser("~/.ssh")
        with pytest.raises(ValueError, match="Refusing to index outside project"):
            tool.validate_arguments({"roots": [ssh_path]})


# ---------------------------------------------------------------------------
# Scenario 2: relative traversal outside project root  →  ValueError
# ---------------------------------------------------------------------------


class TestRelativeTraversalOutsideProject:
    """roots=['../'] resolves outside project_root and must be refused."""

    def test_dotdot_slash_raises(self, tool: BuildProjectIndexTool) -> None:
        with pytest.raises(ValueError, match="Refusing to index outside project"):
            tool.validate_arguments({"roots": ["../"]})

    def test_dotdot_raises(self, tool: BuildProjectIndexTool) -> None:
        with pytest.raises(ValueError, match="Refusing to index outside project"):
            tool.validate_arguments({"roots": [".."]})

    def test_deep_traversal_raises(self, tool: BuildProjectIndexTool) -> None:
        with pytest.raises(ValueError, match="Refusing to index outside project"):
            tool.validate_arguments({"roots": ["../../etc/passwd"]})


# ---------------------------------------------------------------------------
# Scenario 3: valid path within project root  →  success
# ---------------------------------------------------------------------------


class TestValidRootsWithinProject:
    """roots=['.'] and roots=[project_root] must pass validation."""

    def test_dot_succeeds(self, tool: BuildProjectIndexTool, project_dir: Path) -> None:
        # Validation must not raise and must return True.
        result = tool.validate_arguments({"roots": ["."]})
        assert result is True

    def test_absolute_project_root_succeeds(
        self, tool: BuildProjectIndexTool, project_dir: Path
    ) -> None:
        result = tool.validate_arguments({"roots": [str(project_dir)]})
        assert result is True

    def test_subdirectory_succeeds(
        self, tool: BuildProjectIndexTool, project_dir: Path
    ) -> None:
        result = tool.validate_arguments({"roots": [str(project_dir / "src")]})
        assert result is True


# ---------------------------------------------------------------------------
# Scenario 4: empty / missing roots  →  default to project_root
# ---------------------------------------------------------------------------


class TestEmptyOrMissingRoots:
    """Omitted or empty roots fall back to project_root without error."""

    def test_missing_roots_key_uses_project_root(
        self, tool: BuildProjectIndexTool, project_dir: Path
    ) -> None:
        args: dict = {}
        result = tool.validate_arguments(args)
        assert result is True
        # validate_arguments injects the default.
        assert args["roots"] == [str(project_dir)]

    def test_empty_list_uses_project_root(
        self, tool: BuildProjectIndexTool, project_dir: Path
    ) -> None:
        args: dict = {"roots": []}
        result = tool.validate_arguments(args)
        assert result is True
        assert args["roots"] == [str(project_dir)]

    def test_none_uses_project_root(
        self, tool: BuildProjectIndexTool, project_dir: Path
    ) -> None:
        args: dict = {"roots": None}
        result = tool.validate_arguments(args)
        assert result is True
        assert args["roots"] == [str(project_dir)]


# ---------------------------------------------------------------------------
# Scenario 5: nonexistent path  →  ValueError
# ---------------------------------------------------------------------------


class TestNonExistentPath:
    """roots=['nonexistent_path'] must raise ValueError (directory does not exist)."""

    def test_nonexistent_relative_raises(self, tool: BuildProjectIndexTool) -> None:
        with pytest.raises(ValueError):
            tool.validate_arguments({"roots": ["nonexistent_subdir_xyz"]})

    def test_nonexistent_absolute_within_project_raises(
        self, tool: BuildProjectIndexTool, project_dir: Path
    ) -> None:
        """Even within project_root, nonexistent directories are rejected."""
        ghost = str(project_dir / "does_not_exist_xyz")
        with pytest.raises(ValueError):
            tool.validate_arguments({"roots": [ghost]})


# ---------------------------------------------------------------------------
# Scenario 6: execute() returns canonical error envelope for invalid roots
# ---------------------------------------------------------------------------


class TestExecuteSecurityEnvelope:
    """execute() must NOT propagate ValueError — it must return a safe envelope."""

    @pytest.mark.asyncio
    async def test_etc_returns_error_envelope(
        self, tool: BuildProjectIndexTool
    ) -> None:
        result = await tool.execute({"roots": ["/etc"]})
        assert result["success"] is False
        assert result["error_type"] == "security"
        assert "Refusing to index outside project" in result["error"]
        assert result["verdict"] == "ERROR"

    @pytest.mark.asyncio
    async def test_dotdot_returns_error_envelope(
        self, tool: BuildProjectIndexTool
    ) -> None:
        result = await tool.execute({"roots": ["../"]})
        assert result["success"] is False
        assert result["error_type"] == "security"
        assert result["verdict"] == "ERROR"
