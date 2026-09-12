"""RFC-0028 §1.1 — the callers response declares its own completeness.

The invariant is one-directional. TSA need not *resolve* every inbound call
edge; it must never present an unresolved one as a confident absence. A bare
``caller_count: 0`` over an unresolved edge is the single answer that leads an
agent to conclude "safe to change" and be wrong.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cache.callgraph_state import mark_call_graph_built_strict
from tree_sitter_analyzer.graph.edge_store import file_node, symbol_node
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_TARGET = "target_symbol"
_OTHER = "other_symbol"
_RESOLVED = "project"


def _insert_call(
    conn,
    *,
    caller: str,
    caller_line: int,
    resolution: str,
    callee: str = _TARGET,
) -> None:
    """Insert one CALLS edge with a chosen resolution state.

    ``caller=""`` models a module-level call site: its source is the file node,
    which is what makes ``caller_name`` empty and the row "unattributed".
    """
    source = symbol_node("a.py", caller, caller_line) if caller else file_node("a.py")
    conn.execute(
        """INSERT INTO edges
           (source_node_id, target_node_id, kind, line, provenance, metadata,
            caller_name, callee_name, file_path, caller_line, callee_full,
            callee_line, language, callee_resolution, callee_resolved_file)
           VALUES (?, ?, 'calls', ?, 'tree-sitter', '{}',
                   ?, ?, 'a.py', ?, ?, 1, 'python', ?, ?)""",
        (
            source,
            symbol_node("a.py", callee, 1),
            caller_line,
            caller,
            callee,
            caller_line,
            callee,
            resolution,
            "a.py" if resolution == _RESOLVED else "",
        ),
    )


@pytest.fixture
def tool_with_edges(tmp_path):
    """A real cache with the call graph marked built, and its edges cleared."""
    source = tmp_path / "a.py"
    source.write_text("def target_symbol():\n    return 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    assert cache.index_file(str(source))["status"] == "indexed"
    conn = cache.get_conn()
    conn.execute("DELETE FROM edges")
    mark_call_graph_built_strict(conn)
    conn.commit()
    try:
        yield CodeGraphCallersTool(str(tmp_path)), conn
    finally:
        cache.close()


async def _call(tool) -> dict:
    return await tool.execute({"function_name": _TARGET, "output_format": "json"})


@pytest.mark.asyncio
async def test_complete_when_every_inbound_edge_resolved(tool_with_edges) -> None:
    tool, conn = tool_with_edges
    _insert_call(conn, caller="alpha", caller_line=10, resolution=_RESOLVED)
    _insert_call(conn, caller="beta", caller_line=20, resolution=_RESOLVED)
    conn.commit()

    result = await _call(tool)

    assert (result["verdict"], result["completeness"]) == ("INFO", "complete")
    assert result["unresolved_inbound"] == 0


@pytest.mark.asyncio
async def test_incomplete_when_a_caller_exists_beside_an_unresolved_edge(
    tool_with_edges,
) -> None:
    tool, conn = tool_with_edges
    _insert_call(conn, caller="alpha", caller_line=10, resolution=_RESOLVED)
    _insert_call(conn, caller="beta", caller_line=20, resolution="unknown")
    conn.commit()

    result = await _call(tool)

    # Callers were found, and at least one inbound edge is unresolved, so the
    # list is a lower bound rather than a census.
    assert (result["verdict"], result["completeness"]) == ("INFO", "incomplete")
    assert result["unresolved_inbound"] == 1


@pytest.mark.asyncio
async def test_unknown_never_reports_absence(tool_with_edges) -> None:
    """The case RFC-0028 §1 names: today's ``NOT_FOUND`` over an unresolved edge."""
    tool, conn = tool_with_edges
    _insert_call(conn, caller="", caller_line=0, resolution="unknown")
    conn.commit()

    result = await _call(tool)

    assert (result["verdict"], result["caller_count"]) == ("NOT_FOUND", 0)
    assert result["completeness"] == "unknown"
    # The epistemic status rides beside the existing verdict, which stays legal:
    # no ninth member is added to a closed cross-surface vocabulary.
    assert result["verdict"] in {
        "SAFE", "CAUTION", "UNSAFE", "INFO", "REVIEW", "WARN", "ERROR", "NOT_FOUND",
    }

    next_step = str(result["next_step"])
    assert "not in the index" not in next_step
    assert "unresolved" in next_step
    # The summary names the caller it found rather than only disclaiming
    # absence: a module-level site is a real caller that #638 counts rather than
    # lists, and saying "not evidence of absence" without saying why was the
    # weaker version of this line.
    summary_line = result["agent_summary"]["summary_line"]
    assert "0 caller(s)" not in summary_line
    assert "module-level call site(s)" in summary_line


@pytest.mark.asyncio
async def test_real_zero_is_complete_and_may_say_not_in_index(tool_with_edges) -> None:
    """A zero over an indexed graph is a fact, and may be stated as one.

    The graph must hold edges somewhere, or the tool answers from parsing rather
    than from resolved edges and completeness is genuinely unknown.
    """
    tool, conn = tool_with_edges
    _insert_call(conn, caller="alpha", caller_line=10, resolution=_RESOLVED, callee=_OTHER)
    conn.commit()

    result = await _call(tool)

    assert (result["verdict"], result["completeness"]) == ("NOT_FOUND", "complete")
    assert "not in the index" in str(result["next_step"])
    assert result["agent_summary"]["summary_line"] == (
        f"callers: {_TARGET!r} has 0 caller(s)"
    )


@pytest.mark.asyncio
async def test_cold_graph_reports_unknown_not_complete(tool_with_edges) -> None:
    """With no resolved edges at all, a zero is not evidence of absence."""
    tool, conn = tool_with_edges
    conn.commit()

    result = await _call(tool)

    assert result["completeness"] == "unknown"
    assert "not in the index" not in str(result["next_step"])


@pytest.mark.asyncio
async def test_resolved_module_level_caller_is_not_a_certified_zero(
    tool_with_edges,
) -> None:
    """A counted-but-unlisted caller must not become a confident zero.

    #638 counts module-level call sites instead of listing them, so the listed
    count is not a census. Measured before this test existed: a symbol with two
    resolved module-level callers answered `complete` with `caller_count: 0`,
    `agent_summary` "has 0 caller(s)", and the next_step "Symbol not in the
    index" — the exact false zero RFC-0028 §1 forbids, produced by the change
    written to prevent it. Every edge was resolved, so the per-edge signal was
    silent; only the unattributed count knew.
    """
    tool, conn = tool_with_edges
    _insert_call(conn, caller="", caller_line=0, resolution=_RESOLVED)
    conn.commit()

    result = await _call(tool)

    assert result["caller_count"] == 0
    assert result["unattributed_call_sites"] == 1
    assert result["completeness"] == "incomplete", (
        "a symbol with a real, resolved module-level caller must never certify "
        "an empty caller list"
    )
    assert "not in the index" not in str(result["next_step"])
    assert "0 caller(s)" not in result["agent_summary"]["summary_line"]


@pytest.mark.asyncio
async def test_an_unresolved_module_level_site_does_not_claim_unreadable(
    tool_with_edges,
) -> None:
    """A successfully-read count is not a failure to read.

    The reason chain once tested `if unresolved_inbound:`, so a read `0` beside a
    non-zero declaring-file count fell through to "its inbound edges could not be
    read" — a false statement about a successful read.
    """
    tool, conn = tool_with_edges
    _insert_call(conn, caller="", caller_line=0, resolution="unknown")
    conn.commit()

    result = await _call(tool)

    next_step = str(result["next_step"])
    assert "could not be read" not in next_step


def test_unrecognised_resolution_marker_counts_as_unresolved(tmp_path) -> None:
    """An unknown marker must degrade toward incomplete, never toward complete.

    The resolution vocabulary is a closed set; a marker this version does not
    know is not evidence that an edge was resolved.
    """
    source = tmp_path / "a.py"
    source.write_text("def target_symbol():\n    return 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        assert cache.index_file(str(source))["status"] == "indexed"
        conn = cache.get_conn()
        conn.execute("DELETE FROM edges")
        _insert_call(conn, caller="alpha", caller_line=10, resolution="a_future_marker")
        conn.commit()

        assert cache.count_unresolved_callers(_TARGET) == 1
    finally:
        cache.close()
