"""RFC-0027 L6.2 — a route declares what it will cost before it runs.

The load-bearing assertion is that ``estimated_ms`` stays ``None``: the RFC
forbids a hardcoded guess, and a number invented here would be indistinguishable
from a measured one.  Tiers, by contrast, are derived from state this process
can observe.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.cache import query_cost as qc


@pytest.fixture
def indexed_project(tmp_path):
    """A project whose on-disk index holds rows."""
    source = tmp_path / "a.py"
    source.write_text("def target_symbol():\n    return 1\n", encoding="utf-8")
    from tree_sitter_analyzer.ast_cache import ASTCache

    cache = ASTCache(str(tmp_path))
    try:
        assert cache.index_file(str(source))["status"] == "indexed"
    finally:
        cache.close()
    return str(tmp_path)


def test_unlisted_route_declares_nothing() -> None:
    # An ordinary route pays nothing to be asked, and so does its envelope.
    assert qc.query_cost("structure", "outline", None) is None
    assert qc.cost_fields(None) == {}


def test_estimated_ms_is_never_guessed(indexed_project) -> None:
    for tool, action in qc.EXPENSIVE_ROUTES:
        cost = qc.query_cost(tool, action, indexed_project, {})
        assert cost is not None
        assert cost.estimated_ms is None, (
            "no observation source exists yet; a number here would be a guess "
            "the RFC forbids"
        )


def test_route_reading_the_index_reports_index_build_when_absent(tmp_path) -> None:
    cost = qc.query_cost("nav", "callers", str(tmp_path), {"symbol": "x"})
    assert cost is not None
    assert (cost.tier, cost.requires_index_build) == ("index_build", True)
    assert cost.cheaper_alternative == "nav action=context (1-hop, warm)"


def test_route_not_reading_the_index_is_not_charged_for_one(tmp_path) -> None:
    """``edit action=safe`` computed in 3453 ms with the index ABSENT.

    The L5 baseline recorded ``ast_index_before.status: ABSENT`` for the run
    that produced that number, so a missing index is not a cost for this route
    and reporting ``index_build`` would overstate it.
    """
    cost = qc.query_cost("edit", "safe", str(tmp_path), {"file_path": "a.py"})
    assert cost is not None
    assert (cost.tier, cost.requires_index_build) == ("warm", False)


def test_cacheable_route_reports_cold_on_a_miss(indexed_project, monkeypatch) -> None:
    class _MissCache:
        def lookup(self, key):  # noqa: ANN001, ANN201 - stub
            return None

    monkeypatch.setattr(qc, "get_answer_cache", lambda: _MissCache())

    cost = qc.query_cost(
        "edit", "safe", indexed_project, {"file_path": "tree_sitter_analyzer/latency.py"}
    )
    assert cost is not None
    # The cache miss is the expensive call: 3453 ms computed against 51-69 ms
    # for the cached repeats in the same baseline run.
    assert cost.tier == "cold"


def test_cacheable_route_reports_cached_on_a_hit(indexed_project, monkeypatch) -> None:
    class _HitCache:
        def lookup(self, key):  # noqa: ANN001, ANN201 - stub
            return object()

    monkeypatch.setattr(qc, "get_answer_cache", lambda: _HitCache())

    cost = qc.query_cost(
        "edit", "safe", indexed_project, {"file_path": "tree_sitter_analyzer/latency.py"}
    )
    assert cost is not None
    assert cost.tier == "cached"


def test_cost_fields_renders_the_declaration(indexed_project) -> None:
    fields = qc.cost_fields(
        qc.query_cost("nav", "callers", indexed_project, {"symbol": "x"})
    )
    assert set(fields) == {"query_cost"}
    assert set(fields["query_cost"]) == {
        "tier",
        "estimated_ms",
        "requires_index_build",
        "cheaper_alternative",
    }


@pytest.mark.parametrize("tool", ["nav", "edit", "health"])
def test_no_declared_route_is_silently_droppable(tool: str) -> None:
    """Every listed route must be reachable by name, so a typo cannot hide."""
    assert any(key[0] == tool for key in qc.EXPENSIVE_ROUTES)
