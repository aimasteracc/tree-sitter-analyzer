"""#1873: an interrupted read on the certified snapshot is "not read", never "no rows".

The snapshot connection interrupts any statement that runs past the request
deadline. ``alias_edges`` and ``es_import_sites`` turned that interrupt into
``[]``, so an RFC-0040 check counted 0 and the answer could still be proven
``complete``. These tests force a real SQLite interrupt (progress handler) into
the readers of a ``nav callers`` answer on a real certified snapshot:

* every single statement of the certified answer, one at a time: the answer is
  either not produced (its read failed; the request falls back) or not
  ``complete``. On develop the alias and ES import readers (and two more that
  kept a default) gave ``complete`` here;
* the ES import and alias readers inside the RFC-0040 checks: the checks are
  ``not_checked``, the verdict ``unknown``, and nothing is memoized;
* the real deadline (clock past it during the read): the request's answer is
  the uncertified fallback, read in full; nothing of the interrupted certified
  read reaches it (develop already held here: the after-read deadline check of
  the snapshot scope drops the certified answer).
"""

from __future__ import annotations

import os
import sqlite3
import time
import traceback
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer import (
    call_graph_memo,
    call_graph_snapshot_inputs,
    index_snapshot,
    index_snapshot_query,
)
from tree_sitter_analyzer.graph import alias_edges, es_import_sites
from tree_sitter_analyzer.index_snapshot_query import CertifiedSnapshotCache
from tree_sitter_analyzer.mcp.tools import certification_timeouts
from tree_sitter_analyzer.mcp.tools.callers_reasons import (
    UNATTRIBUTED_UNCHECKED_REASON,
    UNCHECKED_REASON,
)
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool
from tree_sitter_analyzer.resident import snapshot_memo

_SOURCES = {
    "pkg/__init__.py": "from .helper import helper\n",
    "pkg/helper.py": "def helper():\n    return 3\n\n\ndef top():\n    return helper()\n",
    "router.py": (
        "from pkg.helper import helper as assist\n\n\ndef used():\n    return assist()\n"
    ),
    "app.py": "from pkg.helper import top\n\n\ndef main():\n    return top()\n",
    "widget.py": (
        "class Widget:\n"
        "    def spin(self):\n"
        "        return 1\n\n\n"
        "def run(w: Widget):\n"
        "    return w.spin()\n"
    ),
    "lib/jws.ts": "export default function signer(x: number) {\n  return x;\n}\n",
    "lib/use.ts": (
        "import makeSig from './jws';\n\n"
        "export function run() {\n  return makeSig(1);\n}\n"
    ),
}
#: Answers proven ``complete`` without interrupts (asserted: the sweep needs them).
_COMPLETE = [
    ("top", "pkg/helper.py"),
    ("signer", "lib/jws.ts"),
    ("used", "router.py"),
    ("Widget.spin", "widget.py"),
]
_AN_HOUR_NS = 3600 * 1_000_000_000


class _Interrupter:
    """Wraps the snapshot connection; interrupts chosen statements for real.

    ``choose(index, sql, frames)`` picks the statements: SQLite then aborts them
    through a progress handler (``OperationalError: interrupted``), exactly as
    the owner's deadline handler does.
    """

    def __init__(self) -> None:
        self.choose: Callable[[int, str, list[str]], bool] = lambda *_: False
        self.on_hit: Callable[[], None] | None = None
        self.count = 0
        self.hits: list[str] = []

    def reset(self, choose: Callable[[int, str, list[str]], bool]) -> None:
        self.choose, self.count, self.hits = choose, 0, []

    def wrap(self, conn: sqlite3.Connection) -> Any:
        return _Proxy(conn, self)


class _Proxy:
    def __init__(self, conn: sqlite3.Connection, owner: _Interrupter) -> None:
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_owner", owner)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._conn, name, value)

    def execute(self, sql: str, *args: Any) -> Any:
        owner = self._owner
        index = owner.count
        owner.count += 1
        frames = [
            f"{Path(f.filename).stem}.{f.name}"
            for f in traceback.extract_stack()[:-1]
            if "tree_sitter_analyzer" in f.filename
        ]
        if not owner.choose(index, sql, frames):
            return self._conn.execute(sql, *args)
        owner.hits.append(frames[-1] if frames else "?")
        if owner.on_hit is not None:  # the real deadline: let its handler fire
            owner.on_hit()
            return self._conn.execute(sql, *args)
        self._conn.set_progress_handler(lambda: 1, 1)
        try:
            return self._conn.execute(sql, *args)
        finally:
            self._conn.set_progress_handler(None, 0)


def _cold() -> None:
    index_snapshot.REGISTRY.close_all()
    call_graph_memo.clear()
    call_graph_snapshot_inputs.clear()
    certification_timeouts.clear()


def _fresh_memos() -> None:
    snapshot_memo.clear()
    alias_edges._JOIN_MEMO.clear()
    index_snapshot_query._BUILT_SNAPSHOTS.clear()


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    import asyncio

    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    root = tmp_path_factory.mktemp("interrupt") / "proj"
    for rel, text in _SOURCES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    stamp = time.time_ns() - _AN_HOUR_NS
    for path in [*root.rglob("*"), root]:
        os.utime(path, ns=(stamp, stamp))
    result = asyncio.run(
        CodeGraphFullIndexTool(str(root)).execute({"mode": "full", "max_files": 50})
    )
    assert result["published"] is True
    yield root
    _cold()


@pytest.fixture
def interrupter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[_Interrupter]:
    monkeypatch.setenv(certification_timeouts.DIR_ENV, str(tmp_path / "timeouts"))
    _cold()
    _fresh_memos()
    hook = _Interrupter()
    original = CertifiedSnapshotCache.get_conn
    proxies: dict[int, Any] = {}

    def get_conn(self: CertifiedSnapshotCache) -> Any:
        conn = original(self)
        if id(conn) not in proxies:
            proxies[id(conn)] = hook.wrap(conn)
        return proxies[id(conn)]

    monkeypatch.setattr(CertifiedSnapshotCache, "get_conn", get_conn)
    yield hook
    _fresh_memos()
    _cold()


def _args(name: str, file_path: str) -> dict[str, Any]:
    return {"function_name": name, "file_path": file_path, "include_bodies": False}


async def _bound_answer(
    root: Path,
    query: tuple[str, str],
    interrupter: _Interrupter,
    choose: Callable[[int, str, list[str]], bool],
) -> dict[str, Any] | None:
    """The certified answer alone (``None``: its read failed, the request falls back).

    Statements are counted (and chosen) from the start of the answer.
    """
    tool = CodeGraphCallersTool(str(root))
    with index_snapshot.certified_index_read(str(root)) as owner:
        assert owner is not None
        cache = owner.query_cache()
        interrupter.reset(choose)
        answers = await tool._answer_all(
            [_args(*query)], cache, owner.read_source, fallible=True
        )
    return answers[0]


def _never(*_: Any) -> bool:
    return False


def _from(module: Any) -> Callable[[int, str, list[str]], bool]:
    """Every statement issued from ``module`` (its innermost TSA frame)."""
    stem = Path(module.__file__).stem

    def choose(_index: int, _sql: str, frames: list[str]) -> bool:
        return bool(frames) and frames[-1].startswith(stem + ".")

    return choose


async def _uncertified_answer(root: Path, query: tuple[str, str]) -> dict[str, Any]:
    """The request's fallback answer: the live index, no snapshot, no interrupt."""
    answers = await CodeGraphCallersTool(str(root))._answer_all(
        [_args(*query)], None, None
    )
    assert answers[0] is not None
    return answers[0]


def _stable(answer: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in answer.items() if k != "query_cost"}


# --------------------------------------------------------------------------- #
# Every statement of the answer
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("query", _COMPLETE, ids=lambda q: q[0])
async def test_any_interrupted_read_leaves_the_answer_unproven(
    project: Path,
    interrupter: _Interrupter,
    monkeypatch: pytest.MonkeyPatch,
    query: tuple[str, str],
) -> None:
    await _bound_answer(project, query, interrupter, _never)  # builds the graph
    _fresh_memos()
    baseline = await _bound_answer(project, query, interrupter, _never)
    assert baseline is not None and baseline["completeness"] == "complete"
    statements = interrupter.count
    assert statements > 0
    wrong = []
    routed: list[dict[str, Any]] = []
    for index in range(statements):
        _fresh_memos()
        answer = await _bound_answer(
            project, query, interrupter, lambda i, _sql, _frames, k=index: i == k
        )
        assert interrupter.hits, f"statement {index} was not issued"
        if answer is None or answer["completeness"] != "complete":
            continue
        if interrupter.hits[0].startswith("callgraph_state."):
            routed.append(_stable(answer))
        else:
            wrong.append((index, interrupter.hits[0]))
    assert wrong == [], f"complete although a read was interrupted: {wrong}"
    # The built-marker probe is routing, not evidence: unread, it is "not built",
    # and the answer takes the graph listing path, which runs every RFC-0040 check
    # itself. Such an answer is exactly the graph path's own uninterrupted answer.
    if routed:
        with monkeypatch.context() as patch:
            patch.setattr(CertifiedSnapshotCache, "call_graph_built", lambda _s: False)
            _fresh_memos()
            graph_path = await _bound_answer(project, query, interrupter, _never)
        assert graph_path is not None
        assert all(answer == _stable(graph_path) for answer in routed)


# --------------------------------------------------------------------------- #
# The two readers of #1873 inside the RFC-0040 checks
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "query", "not_checked"),
    [
        (
            es_import_sites,
            ("signer", "lib/jws.ts"),
            {"unresolved_inbound": UNCHECKED_REASON},
        ),
        (
            # A qualified query lists callers from the graph: the alias rows are
            # read only by the unattributed and unresolved_inbound checks.
            alias_edges,
            ("Widget.spin", "widget.py"),
            {
                "unresolved_inbound": UNCHECKED_REASON,
                "unattributed": UNATTRIBUTED_UNCHECKED_REASON,
            },
        ),
    ],
    ids=["es_import_sites", "alias_edges"],
)
async def test_interrupted_check_read_is_not_checked_and_not_remembered(
    project: Path,
    interrupter: _Interrupter,
    module: Any,
    query: tuple[str, str],
    not_checked: dict[str, str],
) -> None:
    answer = await _bound_answer(project, query, interrupter, _from(module))
    assert interrupter.hits, "the reader ran no statement"
    assert answer is not None
    assert answer["completeness"] == "unknown"
    assert answer["completeness_reason"] == UNCHECKED_REASON
    assert answer["completeness_checks"]["not_checked"] == not_checked
    assert answer["unresolved_inbound"] is None
    # "Not read" is never memoized: the same snapshot answers again in full.
    again = await _bound_answer(project, query, interrupter, _never)
    assert again is not None and again["completeness"] == "complete"


@pytest.mark.asyncio
async def test_interrupted_listing_read_drops_the_certified_answer(
    project: Path, interrupter: _Interrupter
) -> None:
    """A bare query reads the alias rows to list callers: no certified answer."""
    query = ("top", "pkg/helper.py")
    assert await _bound_answer(project, query, interrupter, _from(alias_edges)) is None
    assert interrupter.hits


# --------------------------------------------------------------------------- #
# The real deadline
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "query"),
    [
        (es_import_sites, ("signer", "lib/jws.ts")),
        (alias_edges, ("top", "pkg/helper.py")),
        (alias_edges, ("Widget.spin", "widget.py")),
    ],
    ids=["es_import_sites", "alias_edges", "alias_edges-qualified"],
)
async def test_deadline_during_the_read_answers_from_a_full_read(
    project: Path,
    interrupter: _Interrupter,
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    query: tuple[str, str],
) -> None:
    fallback = _stable(await _uncertified_answer(project, query))
    real_clock = index_snapshot._clock
    late = {"by": 0.0}
    monkeypatch.setattr(index_snapshot, "_clock", lambda: real_clock() + late["by"])

    def past_the_deadline() -> None:
        late["by"] = 3600.0

    interrupter.on_hit = past_the_deadline
    interrupter.reset(_from(module))
    answer = await CodeGraphCallersTool(str(project)).execute(_args(*query))
    assert interrupter.hits, "the reader ran no statement"
    assert late["by"] > 0
    # The certified answer is dropped; the request answers from the live index,
    # read in full (no interrupt there), exactly as the fallback alone does.
    assert _stable(answer) == fallback
