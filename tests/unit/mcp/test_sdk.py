"""
TDD tests for the SDK embedding API.

Tests the create_analyzer factory and CodeAnalyzer programmatic interface.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.sdk import create_analyzer

SAMPLE_PYTHON = '''
"""Sample module for SDK tests."""

class Calculator:
    """A simple calculator."""

    def add(self, x: int, y: int) -> int:
        return x + y

    def multiply(self, x: int, y: int) -> int:
        return x * y


def helper_function() -> str:
    return "hello"
'''


class TestCreateAnalyzer:
    """Factory function tests."""

    def test_create_without_project_root(self) -> None:
        analyzer = create_analyzer()
        assert analyzer is not None
        assert analyzer.project_root is None

    def test_create_with_project_root(self, tmp_path: Path) -> None:
        analyzer = create_analyzer(str(tmp_path))
        assert analyzer.project_root == str(tmp_path)

    def test_create_with_invalid_root_raises(self) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            create_analyzer("/nonexistent/path")

    def test_set_project_root_returns_new_instance(self, tmp_path: Path) -> None:
        original = create_analyzer()
        updated = original.set_project_root(str(tmp_path))
        assert updated is not original
        assert updated.project_root == str(tmp_path)
        assert original.project_root is None


class TestCodeAnalyzerIntegration:
    """Integration tests with real MCP tools."""

    @pytest.mark.asyncio
    async def test_analyze_structure(self) -> None:
        analyzer = create_analyzer()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(SAMPLE_PYTHON)
            temp_path = f.name

        try:
            result = await analyzer.analyze_structure(temp_path)
            assert result["success"] is True
            assert "table_output" in result
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_check_scale(self) -> None:
        analyzer = create_analyzer()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(SAMPLE_PYTHON)
            temp_path = f.name

        try:
            result = await analyzer.check_scale(temp_path)
            assert "summary" in result or "file_metrics" in result
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_get_outline(self) -> None:
        analyzer = create_analyzer()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(SAMPLE_PYTHON)
            temp_path = f.name

        try:
            result = await analyzer.get_outline(temp_path)
            text = result.get("content", [{}])[0].get("text", "")
            assert len(text) > 0
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_query_methods(self) -> None:
        analyzer = create_analyzer()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(SAMPLE_PYTHON)
            temp_path = f.name

        try:
            result = await analyzer.query(temp_path, query_key="methods")
            assert result["success"] is True
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_extract_section(self) -> None:
        analyzer = create_analyzer()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(SAMPLE_PYTHON)
            temp_path = f.name

        try:
            result = await analyzer.extract_section(temp_path, 4, 7)
            assert result["success"] is True
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_immutability(self, tmp_path: Path) -> None:
        """set_project_root returns a new instance without mutating original."""
        original = create_analyzer()
        updated = original.set_project_root(str(tmp_path))
        assert original.project_root is None
        assert updated.project_root == str(tmp_path)
