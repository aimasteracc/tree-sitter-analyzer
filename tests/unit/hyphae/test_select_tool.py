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

    def get_stats(self):
        # Ready index with 2 files
        return {"total_files": 2, "total_symbols": 2}


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

    def get_stats(self):
        # Ready index with many files
        return {"total_files": self._n, "total_symbols": self._n}


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


# ─── Issue #491: Index state detection ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_index_reports_missing_state() -> None:
    """Empty index (no files) → count:0 + index_state:missing + next_step warns."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create a project with empty cache (no indexed files yet)
        tool = HyphaeSelectTool(tmp_dir)
        # Windows: close the tool's lazy ASTCache before TemporaryDirectory
        # cleanup — an open index.db handle is WinError 32 (#492 precedent).
        try:
            result = await tool.execute(
                {"selector": ".function", "output_format": "json"}
            )

            assert result["success"] is True
            assert result["count"] == 0
            assert "index_state" in result
            assert result["index_state"] in ("missing", "empty")
            assert "index missing" in result["agent_summary"]["next_step"].lower()
        finally:
            if tool._cache is not None:
                tool._cache.close()


@pytest.mark.asyncio
async def test_zero_matches_on_ready_index_is_not_a_warning() -> None:
    """Zero matches on a ready index → count:0 + index_state:ready + normal next_step."""
    tool = _tool()
    result = await tool.execute({"selector": ".nonexistent", "output_format": "json"})

    assert result["success"] is True
    assert result["count"] == 0
    # The test cache is considered "ready" because it has symbols
    # (via the FakeCache mock that returns data from get_functions)
    # The next_step should NOT say "index missing"
    assert "index_state" in result
    assert result["index_state"] == "ready"
    assert "index missing" not in result["agent_summary"]["next_step"].lower()
    assert result["agent_summary"]["verdict"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_valid_matches_on_ready_index_succeeds() -> None:
    """Valid matches on ready index → count>0 + index_state:ready + info verdict."""
    tool = _tool()
    result = await tool.execute(
        {"selector": ".method:calls(#UserRepo)", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["count"] == 1
    assert result["index_state"] == "ready"
    assert result["agent_summary"]["verdict"] == "INFO"
    assert "index missing" not in result["agent_summary"]["next_step"].lower()


@pytest.mark.asyncio
async def test_truncated_results_show_narrowing_hint_on_ready_index() -> None:
    """Truncated results on ready index → next_step mentions narrowing."""
    t = HyphaeSelectTool("/tmp")
    t._cache = _FakeCacheWithManyCallers()
    result = await t.execute(
        {"selector": ".function:calls(#Target)", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["truncated"] is True
    assert result["index_state"] == "ready"
    assert result["agent_summary"]["verdict"] == "INFO"
    assert "narrow" in result["agent_summary"]["next_step"].lower()


class _EmptyCache:
    """A cache that reports zero indexed files (empty)."""

    def get_functions(self):
        return []

    def search_symbols_cascade(self, query, limit=100):
        return []

    def get_symbols_by_kind(self, kind, limit=50000):
        return []

    def query_edges(self, kind, caller_name=None, callee_name=None, limit=10000):
        return []

    def get_stats(self):
        # Empty index: 0 files
        return {"total_files": 0, "total_symbols": 0}


@pytest.mark.asyncio
async def test_any_selector_on_empty_index_warns() -> None:
    """Any selector on empty index → warns about missing index."""
    tool = HyphaeSelectTool("/tmp")
    tool._cache = _EmptyCache()
    result = await tool.execute({"selector": ".function", "output_format": "json"})

    assert result["success"] is True
    assert result["count"] == 0
    assert result["index_state"] == "empty"
    assert result["agent_summary"]["verdict"] == "WARN"
    assert "index missing" in result["agent_summary"]["next_step"].lower()


class _BrokenCache:
    """A cache that raises an exception on get_stats."""

    def get_functions(self):
        return []

    def search_symbols_cascade(self, query, limit=100):
        return []

    def get_symbols_by_kind(self, kind, limit=50000):
        return []

    def query_edges(self, kind, caller_name=None, callee_name=None, limit=10000):
        return []

    def get_stats(self):
        raise RuntimeError("Cache corrupted")


@pytest.mark.asyncio
async def test_selector_on_missing_cache_warns() -> None:
    """Selector on missing/broken cache → warns about missing index."""
    tool = HyphaeSelectTool("/tmp")
    tool._cache = _BrokenCache()
    result = await tool.execute({"selector": ".function", "output_format": "json"})

    assert result["success"] is True
    assert result["count"] == 0
    assert result["index_state"] == "missing"
    assert result["agent_summary"]["verdict"] == "WARN"
    assert "index missing" in result["agent_summary"]["next_step"].lower()


@pytest.mark.asyncio
async def test_ready_zero_matches_reports_indexed_file_count() -> None:
    """opencode P2 (#497): partial cache classifies ready — the indexed-file
    count must be surfaced so 0 matches is judgeable (original #491 repro)."""
    tool = _tool()
    result = await tool.execute({"selector": ".nonexistent", "output_format": "json"})
    assert result["index_state"] == "ready"
    assert result["indexed_files"] == 2  # FakeCache reports total_files=2
    next_step = result["agent_summary"]["next_step"]
    assert "indexed file(s)" in next_step
    assert "run index action=auto to complete the index" in next_step


# ─── Issue #540 — Leg 3: selector echo cap ────────────────────────────────────


@pytest.mark.asyncio
async def test_selector_echo_capped_at_200_chars() -> None:
    """A 16 KB selector must be echoed back truncated to ≤ ~250 chars."""
    tool = _tool()
    long_selector = ".function" + ("x" * 16000)  # 16009 chars total
    result = await tool.execute({"selector": long_selector, "output_format": "json"})
    # selector processing is unchanged — only the echo is capped
    echoed = result["selector"]
    assert len(echoed) <= 250, (
        f"Echoed selector length {len(echoed)} exceeds 250-char cap"
    )
    # The ellipsis marker must be present so the agent knows it was truncated
    assert "…" in echoed or "..." in echoed, (
        "Truncated selector echo must contain an ellipsis marker"
    )
    # The total length must be reported in the echo
    assert "chars total" in echoed, (
        "Truncated selector echo must include total char count"
    )


@pytest.mark.asyncio
async def test_short_selector_not_truncated() -> None:
    """A short selector (≤ 200 chars) must be echoed verbatim."""
    tool = _tool()
    short_selector = ".method:calls(#UserRepo)"
    result = await tool.execute({"selector": short_selector, "output_format": "json"})
    assert result["selector"] == short_selector, (
        "Short selector must be echoed verbatim (no truncation)"
    )
