"""
Unit tests for Mermaid dependency graph generation.

Sprint 9: to_mermaid() on CodeMapResult.
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.core.code_map import ProjectCodeMap


@pytest.fixture
def cross_file_project():
    return Path(__file__).parent.parent / "fixtures" / "cross_file_project"


@pytest.fixture
def result(cross_file_project):
    mapper = ProjectCodeMap()
    return mapper.scan(str(cross_file_project), extensions=[".py"])


class TestMermaidGraphExists:
    """Test that to_mermaid() exists."""

    def test_method_exists(self, result):
        assert hasattr(result, "to_mermaid")
        assert callable(result.to_mermaid)

    def test_returns_string(self, result):
        mermaid = result.to_mermaid()
        assert isinstance(mermaid, str)

    def test_starts_with_graph(self, result):
        """Mermaid output should start with graph directive."""
        mermaid = result.to_mermaid()
        assert mermaid.strip().startswith("graph")

    def test_contains_arrows(self, result):
        """Should contain --> arrows for dependencies."""
        mermaid = result.to_mermaid()
        if result.module_dependencies:
            assert "-->" in mermaid


class TestMermaidGraphContent:
    """Test Mermaid graph content correctness."""

    def test_module_nodes_present(self, result):
        """All modules with dependencies should appear as nodes."""
        mermaid = result.to_mermaid()
        for src, dst in result.module_dependencies:
            # Node IDs are sanitized versions of module paths
            assert src.split("/")[-1].replace(".py", "") in mermaid or \
                   dst.split("/")[-1].replace(".py", "") in mermaid

    def test_no_self_loops(self, result):
        """Should not have A --> A self-loops."""
        mermaid = result.to_mermaid()
        for line in mermaid.splitlines():
            if "-->" in line:
                parts = line.strip().split("-->")
                if len(parts) == 2:
                    src = parts[0].strip()
                    dst = parts[1].strip()
                    assert src != dst, f"Self-loop: {line}"


class TestMermaidInheritance:
    """Test inheritance graph generation."""

    def test_inheritance_mermaid(self, result):
        """to_mermaid(kind='inheritance') should show class hierarchy."""
        mermaid = result.to_mermaid(kind="inheritance")
        assert isinstance(mermaid, str)
        assert mermaid.strip().startswith("graph")


class TestMcpMermaidAction:
    """Test MCP tool exposure."""

    def test_mermaid_action(self):
        from tree_sitter_analyzer_v2.mcp.tools.intelligence import _VALID_ACTIONS
        assert "mermaid" in _VALID_ACTIONS
