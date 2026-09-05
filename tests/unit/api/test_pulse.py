"""Tests for tree_sitter_analyzer.api.pulse.

Covers: apply_budget (immutability, truncation order, large budget),
query_pulse (empty table, no-call-graph languages).
Target coverage: ~55-65% of api/pulse.py.
"""

from __future__ import annotations

from tree_sitter_analyzer.api.pulse import (
    CommentRef,
    PulseResponse,
    SymbolInfo,
    apply_budget,
    query_pulse,
)

# ---------------------------------------------------------------------------
# Minimal symbol for constructing PulseResponse in tests
# ---------------------------------------------------------------------------

_MINIMAL_SYM = SymbolInfo(
    name="fn",
    kind="function",
    file="a.py",
    line=1,
    end_line=5,
    language="python",
)

_MINIMAL_PR = PulseResponse(symbol=_MINIMAL_SYM)


def _make_pr_with_comments(n: int = 10) -> PulseResponse:
    comments = tuple(
        CommentRef(line=i, text=f"comment {i}", kind="inline") for i in range(n)
    )
    return PulseResponse(symbol=_MINIMAL_SYM, comments=comments)


# ---------------------------------------------------------------------------
# apply_budget — immutability
# ---------------------------------------------------------------------------

def test_apply_budget_does_not_mutate_input():
    """apply_budget must not mutate the input PulseResponse (frozen dataclass)."""
    pr = _make_pr_with_comments(10)
    original_comments = pr.comments
    apply_budget(pr, token_budget=1)
    # Frozen dataclass: mutation would raise FrozenInstanceError;
    # verify the reference is unchanged (just sanity).
    assert pr.comments is original_comments


def test_apply_budget_returns_new_object():
    """apply_budget always returns a new PulseResponse object."""
    pr = _MINIMAL_PR
    result = apply_budget(pr, token_budget=999999)
    assert result is not pr


def test_apply_budget_drops_comments_first():
    """With a very tight budget, 'comments' field is among the truncated fields."""
    pr = _make_pr_with_comments(10)
    result = apply_budget(pr, token_budget=1)
    # comments is lowest priority — should be dropped
    assert "comments" in result.truncated_fields


def test_apply_budget_large_budget_no_truncation():
    """With a very large budget, no fields are truncated."""
    pr = _make_pr_with_comments(5)
    result = apply_budget(pr, token_budget=100_000)
    assert result.truncated_fields == ()


def test_apply_budget_large_budget_preserves_comments():
    """apply_budget with generous budget keeps all comments."""
    pr = _make_pr_with_comments(3)
    result = apply_budget(pr, token_budget=100_000)
    assert len(result.comments) == 3


# ---------------------------------------------------------------------------
# Helpers for seeding data in the in-memory DB
# ---------------------------------------------------------------------------

def _seed_symbol(conn, name: str, file_path: str, language: str = "python") -> int:
    cur = conn.execute(
        "INSERT INTO ast_symbol_rows (name, kind, file_path, language, line, end_line) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, "function", file_path, language, 1, 10),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# query_pulse — empty table
# ---------------------------------------------------------------------------

def test_query_pulse_empty_table(ast_cache_conn):
    """No matching symbol in empty DB → query_pulse returns None."""
    # The ast_cache_conn fixture includes ast_index (SCHEMA_V1), so the CTE
    # can run without OperationalError. An empty DB returns target_json=NULL.
    result = query_pulse(ast_cache_conn, "a.py", "fn")
    assert result is None


def test_query_pulse_no_call_graph_language(ast_cache_conn):
    """Symbol with language='sql' → call_graph_available=False, callers=(), callees=()."""
    _seed_symbol(ast_cache_conn, "my_query", "report.sql", language="sql")

    result = query_pulse(ast_cache_conn, "report.sql", "my_query")
    assert result is not None, (
        "query_pulse must return a result when the symbol exists in ast_symbol_rows"
    )
    assert result.call_graph_available is False
    assert result.callers == ()
    assert result.callees == ()


def test_query_pulse_returns_none_for_missing_symbol(ast_cache_conn):
    """Symbol that does not exist in ast_symbol_rows → None."""
    result = query_pulse(ast_cache_conn, "nonexistent.py", "ghost_fn")
    assert result is None
