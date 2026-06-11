"""Tests for the HyphaeSelectTool MCP wrapper."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.hyphae_select_tool import HyphaeSelectTool


class _FakeCache:
    def get_functions(self):
        return [
            {
                "name": "save",
                "file": "svc/UserService.java",
                "line": 10,
                "language": "java",
                "class": "UserService",
            },
            {
                "name": "find",
                "file": "svc/UserRepo.java",
                "line": 8,
                "language": "java",
                "class": "UserRepo",
            },
        ]

    def search_symbols_cascade(self, query, limit=100):
        return [f for f in self.get_functions() if f["name"] == query]

    def get_symbols_by_kind(self, kind, limit=50000):
        return []

    def query_edges(self, kind, caller_name=None, callee_name=None, limit=10000):
        if kind == "calls" and callee_name == "UserRepo":
            return [
                {
                    "caller_name": "save",
                    "callee_name": "UserRepo",
                    "file_path": "svc/UserService.java",
                }
            ]
        return []


class _FakeCacheWithManyCallers:
    """Cache that returns ``n`` callers (default 150 > cap of 100)."""

    def __init__(self, n: int = 150) -> None:
        self._n = n

    def get_functions(self):
        return [
            {
                "name": f"caller_{i}",
                "file": f"src/caller_{i}.java",
                "line": 10 + i,
                "language": "java",
                "class": f"Caller{i}",
            }
            for i in range(self._n)
        ]

    def search_symbols_cascade(self, query, limit=100):
        return []

    def get_symbols_by_kind(self, kind, limit=50000):
        return []

    def query_edges(self, kind, caller_name=None, callee_name=None, limit=10000):
        # Return 150 edges when querying for callers of "Target"
        if kind == "calls" and callee_name == "Target":
            return [
                {
                    "caller_name": f"caller_{i}",
                    "callee_name": "Target",
                    "file_path": f"src/caller_{i}.java",
                }
                for i in range(150)
            ]
        return []


def _tool():
    t = HyphaeSelectTool("/tmp")
    t._cache = _FakeCache()
    return t


def test_tool_definition_names_hyphae():
    defn = HyphaeSelectTool("/tmp").get_tool_definition()
    assert defn["name"] == "hyphae_select"
    assert "selector" in defn["inputSchema"]["properties"]
    assert defn["inputSchema"]["required"] == ["selector"]


def test_selector_required():
    with pytest.raises(ValueError):
        _tool().validate_arguments({"selector": "  "})


@pytest.mark.asyncio
async def test_execute_calls_selector_json():
    res = await _tool().execute(
        {"selector": ".method:calls(#UserRepo)", "output_format": "json"}
    )
    assert res["success"] is True
    assert res["count"] == 1
    assert res["symbols"][0]["name"] == "save"


@pytest.mark.asyncio
async def test_execute_syntax_error_is_graceful():
    res = await _tool().execute({"selector": "> broken", "output_format": "json"})
    assert res["success"] is False
    assert "syntax error" in res["error"].lower()
    assert res["symbols"] == []


@pytest.mark.asyncio
async def test_execute_capped_at_100_with_150_total():
    """When 150 matches exceed the default cap of 100, truncated=True and total_matches=150."""
    t = HyphaeSelectTool("/tmp")
    t._cache = _FakeCacheWithManyCallers()
    res = await t.execute(
        {"selector": ".function:calls(#Target)", "output_format": "json"}
    )
    assert res["success"] is True
    assert res["count"] == 100
    assert len(res["symbols"]) == 100
    assert res["truncated"] is True
    assert res["total_matches"] == 150


@pytest.mark.asyncio
async def test_execute_under_cap_not_truncated():
    """When results are under the cap, truncated=False."""
    res = await _tool().execute(
        {"selector": ".method:calls(#UserRepo)", "output_format": "json"}
    )
    assert res["success"] is True
    assert res["count"] == 1
    assert res["truncated"] is False
    assert res["total_matches"] == 1


@pytest.mark.asyncio
async def test_next_step_includes_narrowing_hint_when_truncated():
    """When truncated, next_step should mention narrowing options."""
    t = HyphaeSelectTool("/tmp")
    t._cache = _FakeCacheWithManyCallers()
    res = await t.execute(
        {"selector": ".function:calls(#Target)", "output_format": "json"}
    )
    assert res["success"] is True
    assert res["truncated"] is True
    assert "narrow" in res["agent_summary"]["next_step"].lower()


# ─── Codex P2 (#489): boundary + reentrancy ──────────────────────────────────


def test_exactly_max_results_not_truncated() -> None:
    """Exactly 100 unique matches is a COMPLETE result, not a capped one."""
    from tree_sitter_analyzer.hyphae.evaluator import Evaluator
    from tree_sitter_analyzer.hyphae.parser import parse

    cache = _FakeCacheWithManyCallers(n=100)
    ev = Evaluator(cache, max_results=100)
    out = ev.eval(parse(".function"))
    assert len(out) == 100
    assert ev.total_matches() == 100
    assert ev.was_truncated() is False


def test_not_pseudo_does_not_clobber_counters() -> None:
    """:not(...) re-enters eval(); outer counters must survive (reentrancy)."""
    from tree_sitter_analyzer.hyphae.evaluator import Evaluator
    from tree_sitter_analyzer.hyphae.parser import parse

    cache = _FakeCacheWithManyCallers(n=150)
    ev = Evaluator(cache, max_results=100)
    out = ev.eval(parse(".function:not(#no_such_symbol)"))
    assert len(out) == 100
    assert ev.total_matches() == 150
    assert ev.was_truncated() is True


def test_multi_selector_recount_covers_remaining_selectors() -> None:
    """Cap hit in selector 1 of a list — selector 2's matches still counted."""
    from tree_sitter_analyzer.hyphae.evaluator import Evaluator
    from tree_sitter_analyzer.hyphae.parser import parse

    cache = _FakeCacheWithManyCallers(n=120)
    ev = Evaluator(cache, max_results=100)
    # ".function, .function" — second selector yields only duplicates (all
    # seen), exercising both recount loops without changing the total.
    out = ev.eval(parse(".function, .function"))
    assert len(out) == 100
    assert ev.total_matches() == 120
    assert ev.was_truncated() is True


def test_duplicate_symbols_across_selectors_deduped() -> None:
    """The same symbol matched by two selectors counts once."""
    from tree_sitter_analyzer.hyphae.evaluator import Evaluator
    from tree_sitter_analyzer.hyphae.parser import parse

    cache = _FakeCacheWithManyCallers(n=10)
    ev = Evaluator(cache, max_results=100)
    out = ev.eval(parse(".function, .function"))
    assert len(out) == 10
    assert ev.total_matches() == 10
    assert ev.was_truncated() is False
