"""#1840: one ``callers`` answer reads each target's direct inbound edges once.

The unattributed-site check and the unresolved-inbound check both read the direct
inbound edges of the same ``(name, file)``.  Sharing that read inside one request
must not change the answer, and must not leak across requests (an edit between two
requests has to be seen).  Pins the work done, by counts, never by timing.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer import call_graph_memo, call_graph_snapshot_inputs
from tree_sitter_analyzer.graph import edge_store
from tree_sitter_analyzer.mcp.tools import certification_timeouts
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_AN_HOUR_NS = 3600 * 1_000_000_000

_WIDGET = (
    "class Widget:\n"
    "    def used(self):\n"
    "        return 1\n\n\n"
    "def run(w: Widget):\n"
    "    return w.used()\n"
)
_HELPER = "def helper():\n    return 3\n\n\ndef top():\n    return helper()\n"
_SECOND_CALLER = "\n\ndef again():\n    return helper()\n"


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(certification_timeouts.DIR_ENV, str(tmp_path / "timeouts"))
    for reset in (
        certification_timeouts.clear,
        call_graph_memo.clear,
        call_graph_snapshot_inputs.clear,
    ):
        reset()
    yield
    for reset in (
        certification_timeouts.clear,
        call_graph_memo.clear,
        call_graph_snapshot_inputs.clear,
    ):
        reset()


def _backdate(root: Path) -> None:
    stamp = time.time_ns() - _AN_HOUR_NS
    for path in [*root.rglob("*.py"), root / "pkg", root]:
        os.utime(path, ns=(stamp, stamp))


async def _index(root: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    result = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert result["published"] is True


@pytest.fixture
async def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / "widget.py").write_text(_WIDGET, encoding="utf-8")
    (root / "pkg" / "helper.py").write_text(_HELPER, encoding="utf-8")
    _backdate(root)
    await _index(root)
    return root


def _count_reads(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str | None]]:
    """Every real read of the direct inbound edges, as ``(name, file)``."""
    reads: list[tuple[str, str | None]] = []
    read = edge_store._read_direct_callers

    def counting(conn: sqlite3.Connection, name: str, file: str | None) -> Any:
        reads.append((name, file))
        return read(conn, name, file)

    monkeypatch.setattr(edge_store, "_read_direct_callers", counting)
    return reads


def _args(name: str, file_path: str) -> dict[str, Any]:
    return {"function_name": name, "file_path": file_path, "include_bodies": False}


_QUERIES = [
    ("used", "widget.py"),  # bare, one method: rewritten to Widget.used
    ("Widget.used", "widget.py"),  # qualified
    ("helper", "pkg/helper.py"),  # bare module function: SQL path
]


@pytest.mark.asyncio
@pytest.mark.parametrize("name, file_path", _QUERIES)
async def test_one_direct_inbound_read_per_target_per_request(
    project: Path, monkeypatch: pytest.MonkeyPatch, name: str, file_path: str
) -> None:
    tool = CodeGraphCallersTool(str(project))
    await tool.execute(_args(name, file_path))  # warm: graph, snapshot
    reads = _count_reads(monkeypatch)

    await tool.execute(_args(name, file_path))

    assert reads, "the query must read the direct inbound edges"
    assert len(reads) == len(set(reads)), f"a target was read twice: {reads}"


@pytest.mark.asyncio
@pytest.mark.parametrize("name, file_path", _QUERIES)
async def test_sharing_the_read_does_not_change_the_answer(
    project: Path, monkeypatch: pytest.MonkeyPatch, name: str, file_path: str
) -> None:
    tool = CodeGraphCallersTool(str(project))
    shared = await tool.execute(_args(name, file_path))

    # Without the memo every read goes to the index, as in 3.0.0.
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.callers_tool.direct_callers_memo", _no_memo
    )
    live = await CodeGraphCallersTool(str(project)).execute(_args(name, file_path))

    assert shared == live


@pytest.mark.asyncio
async def test_reads_are_not_shared_across_requests(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = CodeGraphCallersTool(str(project))
    before = await tool.execute(_args("helper", "pkg/helper.py"))
    assert {c["name"] for c in before["callers"]} == {"top"}

    (project / "pkg" / "helper.py").write_text(
        _HELPER + _SECOND_CALLER, encoding="utf-8"
    )
    _backdate(project)
    await _index(project)

    after = await tool.execute(_args("helper", "pkg/helper.py"))
    assert {c["name"] for c in after["callers"]} == {"top", "again"}


def test_memo_is_scoped_and_returns_independent_lists() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = edge_store.EdgeStore(conn)
    store.upsert_edges(
        [
            edge_store.Edge(
                "a.py:caller:1", "b.py:target:1", edge_store.EdgeKind.CALLS, line=2
            )
        ]
    )
    reads: list[int] = []
    read = edge_store._read_direct_callers

    def counting(c: sqlite3.Connection, name: str, file: str | None) -> Any:
        reads.append(1)
        return read(c, name, file)

    original = edge_store._read_direct_callers
    edge_store._read_direct_callers = counting  # type: ignore[assignment]
    try:
        edge_store._direct_callers(conn, "target", None)
        edge_store._direct_callers(conn, "target", None)
        assert len(reads) == 2  # no scope: every call reads live
        with edge_store.direct_callers_memo():
            first = edge_store._direct_callers(conn, "target", None)
            second = edge_store._direct_callers(conn, "target", None)
            edge_store._direct_callers(conn, "target", "b.py")
            assert len(reads) == 4  # one more for the same name, other file only
            assert first == second and first is not second
            first.clear()
            assert edge_store._direct_callers(conn, "target", None) == second
        edge_store._direct_callers(conn, "target", None)
        assert len(reads) == 5  # scope gone: live again
    finally:
        edge_store._read_direct_callers = original  # type: ignore[assignment]


class _no_memo:  # noqa: N801 — stands in for the context manager
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_exc: object) -> None:
        return None
