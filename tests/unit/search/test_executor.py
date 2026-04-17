"""
Unit tests for FastPathExecutor.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.search.executor import ExecutionResult, FastPathExecutor


class TestExecutionResult:
    """Test ExecutionResult dataclass."""

    def test_init_success(self) -> None:
        """Test ExecutionResult initialization for success case."""
        result = ExecutionResult(
            success=True,
            results=[{"file": "test.py", "line": 10}],
            error=None,
            execution_time=0.5,
            tool_used="ripgrep",
        )

        assert result.success is True
        assert len(result.results) == 1
        assert result.error is None
        assert result.execution_time == 0.5
        assert result.tool_used == "ripgrep"

    def test_init_failure(self) -> None:
        """Test ExecutionResult initialization for failure case."""
        result = ExecutionResult(
            success=False,
            results=[],
            error="Search failed",
        )

        assert result.success is False
        assert len(result.results) == 0
        assert result.error == "Search failed"


class TestFastPathExecutor:
    """Test FastPathExecutor class."""

    @pytest.fixture
    def executor(self, tmp_path: str) -> FastPathExecutor:
        """Get FastPathExecutor instance."""
        # Create test files
        test_dir = Path(tmp_path) / "test_project"
        test_dir.mkdir()
        (test_dir / "test.py").touch()

        return FastPathExecutor(project_root=str(test_dir))

    def test_init(self, executor: FastPathExecutor) -> None:
        """Test FastPathExecutor initialization."""
        assert executor.project_root is not None
        assert isinstance(executor.project_root, Path)

    def test_check_ripgrep(self, executor: FastPathExecutor) -> None:
        """Test ripgrep availability check."""
        # We don't know if ripgrep is installed, so just check it doesn't crash
        is_available = executor._ripgrep_available
        assert isinstance(is_available, bool)

    def test_execute_grep_by_name(self, executor: FastPathExecutor) -> None:
        """Test executing grep by name query."""
        # Create a test file with some content
        test_file = executor.project_root / "test.py"
        test_file.write_text("def authenticate():\n    pass\n")

        result = executor.execute(
            handler="grep_by_name",
            params={"name": "authenticate"},
        )

        assert result.success is True
        assert result.tool_used in ("ripgrep", "grep")
        assert len(result.results) > 0

    def test_execute_grep_by_name_no_params(self, executor: FastPathExecutor) -> None:
        """Test executing grep by name with no name parameter."""
        result = executor.execute(
            handler="grep_by_name",
            params={},
        )

        assert result.success is False
        assert result.error is not None
        assert "No name specified" in result.error

    def test_execute_grep_in_files(self, executor: FastPathExecutor) -> None:
        """Test executing grep in specific file types."""
        test_file = executor.project_root / "test.py"
        test_file.write_text("def db_query():\n    pass\n")

        result = executor.execute(
            handler="grep_in_files",
            params={1: "db_query", 2: "py"},
        )

        assert result.success is True
        assert len(result.results) > 0

    def test_execute_unknown_handler(self, executor: FastPathExecutor) -> None:
        """Test executing with unknown handler."""
        result = executor.execute(
            handler="unknown_handler",
            params={},
        )

        assert result.success is False
        assert "Unknown handler" in result.error


class TestFastPathExecutorIntegration:
    """Integration tests for FastPathExecutor."""

    @pytest.fixture
    def executor(self) -> FastPathExecutor:
        """Get FastPathExecutor instance for current repo."""
        return FastPathExecutor()

    def test_real_project_search(self, executor: FastPathExecutor) -> None:
        """Test searching in the actual project."""
        # Search for a common pattern that should exist
        result = executor.execute(
            handler="grep_by_name",
            params={"name": "class"},
        )

        assert result.success is True
        # We should find some results since this is a Python project
        assert isinstance(result.results, list)
