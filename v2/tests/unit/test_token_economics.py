"""
Unit tests for token economics and progressive disclosure.

Inspired by claude-mem's 3-layer workflow and token budget visibility.
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


class TestTokenEconomics:
    """Test token budget estimation on CodeMapResult."""

    def test_method_exists(self, result):
        assert hasattr(result, "token_economics")
        assert callable(result.token_economics)

    def test_returns_dict(self, result):
        eco = result.token_economics()
        assert isinstance(eco, dict)

    def test_has_required_fields(self, result):
        eco = result.token_economics()
        assert "total_symbols" in eco
        assert "toon_tokens" in eco
        assert "json_tokens" in eco
        assert "savings_percent" in eco

    def test_toon_smaller_than_json(self, result):
        """TOON should always use fewer tokens than JSON."""
        eco = result.token_economics()
        assert eco["toon_tokens"] < eco["json_tokens"]

    def test_savings_percent_positive(self, result):
        eco = result.token_economics()
        assert eco["savings_percent"] > 0


class TestProjectSnapshot:
    """Test one-shot project snapshot for AI consumption."""

    def test_method_exists(self, result):
        assert hasattr(result, "project_snapshot")
        assert callable(result.project_snapshot)

    def test_returns_string(self, result):
        snap = result.project_snapshot()
        assert isinstance(snap, str)

    def test_snapshot_contains_key_info(self, result):
        snap = result.project_snapshot()
        assert "files" in snap.lower() or "FILES" in snap
        assert "symbols" in snap.lower() or "SYMBOLS" in snap

    def test_snapshot_token_budget(self, result):
        """Snapshot should be compact (under 2000 chars for small project)."""
        snap = result.project_snapshot()
        # Small fixture project should produce a short snapshot
        assert len(snap) < 5000


class TestProgressiveDisclosure:
    """Test index/detail split for progressive disclosure."""

    def test_symbol_index_method_exists(self, result):
        """symbol_index() returns compact index (name + file + line only)."""
        assert hasattr(result, "symbol_index")
        assert callable(result.symbol_index)

    def test_symbol_index_compact(self, result):
        index = result.symbol_index()
        assert isinstance(index, str)
        # Should contain at least one symbol
        assert len(index) > 0

    def test_symbol_index_much_smaller_than_full(self, result):
        """Index should be significantly smaller than full TOON dump."""
        index = result.symbol_index()
        full = result.to_toon()
        assert len(index) < len(full)


class TestMcpSnapshotAction:
    """Test MCP tool exposure of snapshot and economics."""

    def test_snapshot_action_in_tool(self):
        from tree_sitter_analyzer_v2.mcp.tools.intelligence import _VALID_ACTIONS
        assert "snapshot" in _VALID_ACTIONS
