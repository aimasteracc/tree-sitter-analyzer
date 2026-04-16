"""
TDD tests for the public SDK facade.

The Analyzer class provides a synchronous Python API for tree-sitter-analyzer,
enabling easy embedding into applications without MCP protocol overhead.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAnalyzerInit:
    """Analyzer initialization and configuration."""

    def test_create_with_project_root(self, tmp_path) -> None:
        from tree_sitter_analyzer.sdk import Analyzer

        analyzer = Analyzer(project_root=str(tmp_path))
        assert analyzer.project_root == str(tmp_path)

    def test_create_without_project_root_uses_cwd(self) -> None:
        from tree_sitter_analyzer.sdk import Analyzer
        import os

        analyzer = Analyzer()
        assert analyzer.project_root == os.getcwd()

    def test_set_project_path(self, tmp_path) -> None:
        from tree_sitter_analyzer.sdk import Analyzer

        analyzer = Analyzer(project_root=str(tmp_path))
        new_path = str(tmp_path / "sub")
        new_path = new_path  # just verify the method exists
        assert hasattr(analyzer, "set_project_path")


class TestAnalyzerCallCheckCodeScale:
    """Synchronous wrapper for check_code_scale."""

    def test_check_code_scale(self, tmp_path) -> None:
        from tree_sitter_analyzer.sdk import Analyzer

        # Create a test Java file
        java_file = tmp_path / "Test.java"
        java_file.write_text("public class Test { }\n")

        analyzer = Analyzer(project_root=str(tmp_path))
        result = analyzer.check_code_scale(file_path=str(java_file))

        assert isinstance(result, dict)
        assert result.get("success") is True


class TestAnalyzerAnalyzeCodeStructure:
    """Synchronous wrapper for analyze_code_structure."""

    def test_analyze_code_structure(self, tmp_path) -> None:
        from tree_sitter_analyzer.sdk import Analyzer

        java_file = tmp_path / "Hello.java"
        java_file.write_text("public class Hello { void greet() {} }\n")

        analyzer = Analyzer(project_root=str(tmp_path))
        result = analyzer.analyze_code_structure(file_path=str(java_file))

        assert isinstance(result, dict)
        assert result.get("success") is True


class TestAnalyzerContextManager:
    """Analyzer supports context manager for resource cleanup."""

    def test_context_manager(self, tmp_path) -> None:
        from tree_sitter_analyzer.sdk import Analyzer

        with Analyzer(project_root=str(tmp_path)) as analyzer:
            assert analyzer.project_root == str(tmp_path)
