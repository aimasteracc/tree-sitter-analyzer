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
    callee_full: str | None = None,
) -> None:
    """Insert one CALLS edge with a chosen resolution state.

    ``caller=""`` models a module-level call site: its source is the file node,
    which is what makes ``caller_name`` empty and the row "unattributed".
    ``callee_full`` defaults to ``callee``; pass it to model an attribute call
    (`list.append`) or a computed dispatch site whose full text differs from the
    bare name the resolver recorded.
    """
    full = callee_full if callee_full is not None else callee
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
            full,
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
        "SAFE",
        "CAUTION",
        "UNSAFE",
        "INFO",
        "REVIEW",
        "WARN",
        "ERROR",
        "NOT_FOUND",
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
    _insert_call(
        conn, caller="alpha", caller_line=10, resolution=_RESOLVED, callee=_OTHER
    )
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
async def test_external_resolution_does_not_poison_the_declaring_file(
    tool_with_edges,
) -> None:
    """``external`` is a terminal resolution, not an unresolved edge.

    Measured on the 2,174-file self-repo corpus: ``external`` is 2.58% of all
    CALLS edges (4,247 rows).  Counting it as unresolved barred 199 additional
    files from ever answering ``complete`` — 1,562 files gated rather than
    1,363.  ``synapse.py`` states the intent directly: ``external`` and
    ``stdlib`` are terminal, "target lives outside the project, no
    resolved_file by design", which is why the backfill refuses to re-select
    them.  A marker the writer treats as finished must not read as unfinished.
    """
    tool, conn = tool_with_edges
    _insert_call(
        conn, caller="alpha", caller_line=10, resolution="external", callee=_OTHER
    )
    conn.commit()

    result = await _call(tool)

    assert result["unresolved_in_declaring_files"] == 0
    assert result["completeness"] == "complete"


@pytest.mark.asyncio
async def test_external_edge_named_like_a_local_symbol_is_resolved(
    tool_with_edges,
) -> None:
    """An ``external`` edge stays resolved when its name matches a local symbol.

    §1 forbids presenting an *unresolved* edge as absence.  An ``external`` edge
    is not unresolved: the resolver decided the callee lives outside the project.
    ``_matches_callee`` compares bare names, so an external callee sharing a name
    with a local symbol still reaches this count; excluding it is correct,
    because the edge's target is the external symbol, not the local one.
    """
    tool, conn = tool_with_edges
    _insert_call(conn, caller="alpha", caller_line=10, resolution="external")
    conn.commit()

    result = await _call(tool)

    assert result["unresolved_inbound"] == 0
    assert result["completeness"] == "complete"


@pytest.mark.asyncio
async def test_unresolved_inbound_and_caller_count_are_different_units(
    tool_with_edges,
) -> None:
    """The two numbers answer different questions and are not meant to reconcile.

    ``caller_count`` lists distinct call sites and excludes module-level rows;
    ``unresolved_inbound`` counts every inbound edge.  A module-level unresolved
    site is therefore counted (1) and unlisted (0) at the same time, which is the
    intended reading rather than a contradiction.  Repeated edges cannot inflate
    the count: ``edges`` is UNIQUE over
    ``(source_node_id, target_node_id, kind, line)``.
    """
    tool, conn = tool_with_edges
    _insert_call(conn, caller="", caller_line=0, resolution="unknown")
    conn.commit()

    result = await _call(tool)

    assert result["caller_count"] == 0
    assert result["unresolved_inbound"] == 1
    assert result["unattributed_call_sites"] == 1
    assert result["completeness"] == "unknown"


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


# ---------------------------------------------------------------------------
# §1.2 scope guard: what may gate a file
# ---------------------------------------------------------------------------
#
# The guard asks whether an unresolved call inside a declaring file could target
# a symbol that file declares.  Before narrowing it counted every unresolved
# edge, which gated 1,562 of the 2,060 files holding CALLS edges (75.8%) and
# barred every symbol they declare from answering `complete`.  The largest
# contributors cannot name a local symbol at all — `list.append` (2,327 rows),
# `dict.get`, `set.add`, `conn.execute`, `logger.debug`.


@pytest.mark.asyncio
async def test_builtin_receiver_call_does_not_gate_the_file(tool_with_edges) -> None:
    """`list.append` cannot target a symbol the file declares, so it must not gate it."""
    tool, conn = tool_with_edges
    _insert_call(
        conn,
        caller="alpha",
        caller_line=10,
        resolution="unknown",
        callee="append",
        callee_full="list.append",
    )
    conn.commit()

    result = await _call(tool)

    assert result["unresolved_in_declaring_files"] == 0
    assert result["completeness"] == "complete"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("callee", "callee_full", "why"),
    [
        (
            'handlers["read_resource"]',
            'handlers["read_resource"]',
            "string-keyed dispatch",
        ),
        ("getattr(self, name)", "getattr(self, name)", "reflection"),
        ("self.handle", "self.handle", "own-class attribute"),
        ("cls.build", "cls.build", "classmethod attribute"),
        ("extractors.run", "extractors.run", "receiver is a local variable"),
        ("local_helper", "local_helper", "bare name in scope"),
        ("original", "original", "bare name bound at runtime"),
    ],
)
async def test_potentially_local_callee_still_gates_the_file(
    tool_with_edges, callee: str, callee_full: str, why: str
) -> None:
    """Everything that could name a local symbol keeps gating the file.

    These are the cases §1.2 exists for.  Narrowing may only remove callees it
    can *prove* cannot target the file; a receiver that is a local variable
    (`extractors.run`) may well be a project object, so it stays counted.
    """
    tool, conn = tool_with_edges
    _insert_call(
        conn,
        caller="alpha",
        caller_line=10,
        resolution="unknown",
        callee=callee,
        callee_full=callee_full,
    )
    conn.commit()

    result = await _call(tool)

    assert result["unresolved_in_declaring_files"] == 1, why
    assert result["completeness"] != "complete", why


@pytest.mark.asyncio
async def test_dotted_callee_is_judged_by_receiver_not_by_substring(
    tool_with_edges,
) -> None:
    """A dotted callee is excused by its receiver *text*, never by a substring.

    `getattr(importlib.import_module(mod), cls).from_private_bytes` contains dots,
    but its text before the first dot is `getattr(importlib` — not a builtin type
    name.  A naive reading could excuse a real dispatch site; it must keep gating.
    """
    tool, conn = tool_with_edges
    _insert_call(
        conn,
        caller="alpha",
        caller_line=10,
        resolution="unknown",
        callee="from_private_bytes",
        callee_full="getattr(importlib.import_module(mod), cls).from_private_bytes",
    )
    conn.commit()

    result = await _call(tool)

    assert result["unresolved_in_declaring_files"] == 1
    assert result["completeness"] != "complete"
