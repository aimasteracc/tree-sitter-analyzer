"""Relation stages over the ``nav`` producers (RFC-0041 §3, §5).

Every relation consumes the producer's own coverage (``coverage.from_producer``)
for each input it examined; a stage is ``complete`` only when every one of
those inputs was. Rows keep their provenance (``via``) so the detail view can
show which input produced them, and each examined input is recorded as
evidence with a ready-to-call ``nav`` request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .backends import Backends
from .coverage import (
    CALLEE_UNRESOLVED,
    CALLEES_COVERAGE_UNREPORTED,
    COMPLETE_COVERAGE,
    INCOMPLETE,
    RELATION_DEPTH_LIMIT,
    RELATION_NODE_BUDGET,
    TEST_HELPER_DEPTH,
    UNKNOWN,
    Coverage,
    combine_or_complete,
    from_producer,
    gap,
)

#: Producer calls one relation stage may spend; beyond it the stage is a
#: lower bound (``RELATION_NODE_BUDGET``), never silently truncated.
NODE_BUDGET = 400
MODULE_SCOPE = "<module>"


@dataclass(frozen=True)
class Row:
    name: str
    file: str
    line: int | None
    cls: str | None = None
    kind: str | None = None
    language: str | None = None
    depth: int | None = None
    via: str | None = None
    role: str | None = None
    membership: str | None = None

    @property
    def key(self) -> str:
        return f"{self.file}:{self.line}:{self.name}"

    def as_symbol(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "file": self.file,
            "line": self.line,
            "class": self.cls,
            "kind": self.kind,
            "language": self.language,
        }


@dataclass
class RelationResult:
    rows: list[Row]
    coverage: Coverage
    evidence: list[dict[str, Any]] = field(default_factory=list)


def row_from_symbol(sym: dict[str, Any]) -> Row:
    line = sym.get("line")
    return Row(
        name=str(sym.get("name") or ""),
        file=str(sym.get("file") or ""),
        line=int(line) if isinstance(line, int) else None,
        cls=sym.get("class") or None,
        kind=sym.get("kind") or None,
        language=sym.get("language") or None,
    )


def _evidence(
    op: str,
    row: Row,
    scope: str | None,
    cov: Coverage,
    listed: int,
    response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # The handle is the exact request that was sent, so replaying it shows
    # the producer evidence this stage consumed.
    request: dict[str, Any] = {"action": op, "function_name": row.name}
    if scope:
        request["file_path"] = scope
    item: dict[str, Any] = {
        "input": row.key,
        "completeness": cov.status,
        "listed": listed,
        "nav": request,
    }
    if cov.reasons:
        item["reasons"] = list(cov.reasons)
    # RFC-0040: the producer's bounded per-check proof, carried unchanged so
    # detail="full" shows what was examined for this input.
    checks = (response or {}).get("completeness_checks")
    if checks is not None:
        item["checks"] = checks
    return item


def _related_rows(
    response: dict[str, Any], key: str, parent: Row, depth: int
) -> list[Row]:
    rows: list[Row] = []
    for entry in response.get(key) or []:
        name = str(entry.get("name") or "")
        if not name:
            continue
        line = entry.get("line")
        rows.append(
            Row(
                name=name,
                file=str(entry.get("file") or ""),
                line=int(line) if isinstance(line, int) else None,
                language=entry.get("language") or None,
                depth=depth,
                via=parent.key,
            )
        )
    return rows


def _scope(backends: Backends, row: Row) -> str | None:
    """The ``file_path`` to send with a producer request for ``row``.

    A bare name with exactly one indexed definition already names that
    definition, so it is sent unscoped. With a ``file_path`` the callers tool
    rewrites a lone method to ``Class.method`` (#1759), whose path is
    measurably less complete today (RFC-0041 §7: ``get_truecolor`` on rich
    lists 2 callers (NAME_ONLY_INBOUND) scoped vs 6 bare; both incomplete).
    Several definitions keep the file so the answer is about this one.
    Tracked as #1798 (scoped vs bare callers divergence).
    """
    if not row.file:
        return None
    return None if backends.definition_count(row.name) == 1 else row.file


def _requests(backends: Backends, rows: list[Row]) -> list[tuple[Row, str | None]]:
    """One producer request per distinct question about ``rows``.

    When the rows hold every indexed definition of a name, the unscoped bare
    name asks exactly about that set (the callers tool answers a bare name
    with several definitions as their union, never more confident than any
    one of them, #1740), so it is one request instead of one per definition.
    """
    by_name: dict[str, list[Row]] = {}
    for row in rows:
        by_name.setdefault(row.name, []).append(row)
    out: list[tuple[Row, str | None]] = []
    for name, group in by_name.items():
        count = backends.definition_count(name)
        if len(group) > 1 and count is not None and len(group) >= count:
            out.append((group[0], None))
            continue
        out.extend((row, _scope(backends, row)) for row in group)
    return out


class _Budget:
    def __init__(self) -> None:
        self.spent = 0

    def take(self) -> bool:
        if self.spent >= NODE_BUDGET:
            return False
        self.spent += 1
        return True


async def callers(
    backends: Backends, inputs: list[Row], *, depth: int, closure: bool = False
) -> RelationResult:
    """Callers up to ``depth`` hops (BFS, one producer call per expanded node).

    ``closure=True`` (``impact()``) means the question is the whole transitive
    closure: an unexpanded frontier at the depth cap is a gap
    (``RELATION_DEPTH_LIMIT``). For ``callers(depth=N)`` the bound is the
    question itself, so it is not.
    """
    budget = _Budget()
    covs: list[Coverage] = []
    evidence: list[dict[str, Any]] = []
    out: dict[str, Row] = {}
    expanded: set[str] = set()
    frontier = [r for r in inputs if r.name != MODULE_SCOPE]
    for level in range(1, depth + 1):
        nxt: list[Row] = []
        pending = [r for r in frontier if r.key not in expanded]
        expanded.update(r.key for r in pending)
        for row, scope in _requests(backends, pending):
            if not budget.take():
                covs.append(gap(INCOMPLETE, RELATION_NODE_BUDGET))
                return RelationResult(
                    list(out.values()), combine_or_complete(covs), evidence
                )
            response = await backends.callers(row.name, scope)
            cov = from_producer(response)
            covs.append(cov)
            found = _related_rows(response, "callers", row, level)
            evidence.append(_evidence("callers", row, scope, cov, len(found), response))
            for item in found:
                if item.key not in out:
                    out[item.key] = item
                if item.name != MODULE_SCOPE and item.key not in expanded:
                    nxt.append(item)
        frontier = nxt
    if closure and frontier:
        covs.append(gap(INCOMPLETE, RELATION_DEPTH_LIMIT))
    return RelationResult(list(out.values()), combine_or_complete(covs), evidence)


def _is_test_entry(row: Row) -> bool:
    from ..mcp.tools.nav_facade import _is_collectible_caller
    from ..utils.test_detection import is_test_file

    return bool(is_test_file(row.file)) and _is_collectible_caller(
        row.file, row.name, row.language or ""
    )


def _in_test_file(row: Row) -> bool:
    from ..utils.test_detection import is_test_file

    return bool(is_test_file(row.file))


async def tests(backends: Backends, inputs: list[Row]) -> RelationResult:
    """Test entry points reaching each input directly or via one test helper.

    Same definition as ``nav action=test_map`` (RFC-0014 Phase B), but derived
    from ``nav action=callers`` so it carries callers' coverage: an input's
    tests are a census only if its callers are, and so are the callers of
    every helper walked through.
    """
    budget = _Budget()
    covs: list[Coverage] = []
    evidence: list[dict[str, Any]] = []
    out: dict[str, Row] = {}
    candidates = [r for r in inputs if r.name != MODULE_SCOPE]
    for row, scope in _requests(backends, candidates):
        if not budget.take():
            covs.append(gap(INCOMPLETE, RELATION_NODE_BUDGET))
            break
        response = await backends.callers(row.name, scope)
        cov = from_producer(response)
        covs.append(cov)
        direct = _related_rows(response, "callers", row, 1)
        evidence.append(_evidence("callers", row, scope, cov, len(direct), response))
        for caller in direct:
            if not _in_test_file(caller):
                continue
            if _is_test_entry(caller):
                out.setdefault(caller.key, _as_test(caller, row))
                continue
            covs.append(
                await _walk_helper(backends, caller, row, budget, out, evidence)
            )
    return RelationResult(list(out.values()), combine_or_complete(covs), evidence)


def _as_test(test: Row, target: Row) -> Row:
    return Row(
        name=test.name,
        file=test.file,
        line=test.line,
        language=test.language,
        depth=test.depth,
        via=target.key,
        role="test",
    )


async def _walk_helper(
    backends: Backends,
    helper: Row,
    target: Row,
    budget: _Budget,
    out: dict[str, Row],
    evidence: list[dict[str, Any]],
) -> Coverage:
    if not budget.take():
        return gap(INCOMPLETE, RELATION_NODE_BUDGET)
    scope = _scope(backends, helper)
    response = await backends.callers(helper.name, scope)
    cov = from_producer(response)
    parents = _related_rows(response, "callers", helper, 2)
    evidence.append(_evidence("callers", helper, scope, cov, len(parents), response))
    nested = False
    for parent in parents:
        if not _in_test_file(parent):
            continue
        if _is_test_entry(parent):
            out.setdefault(parent.key, _as_test(parent, target))
        else:
            nested = True
    if nested:
        return combine_or_complete([cov, gap(INCOMPLETE, TEST_HELPER_DEPTH)])
    return cov


async def callees(backends: Backends, inputs: list[Row]) -> RelationResult:
    """Project callees via ``nav action=callees``.

    ``nav callees`` makes no coverage claim, so this stage is never
    ``complete``: ``incomplete`` when some callees did not resolve to a
    project definition (the listed set is a lower bound), else ``unknown``.
    """
    covs: list[Coverage] = []
    evidence: list[dict[str, Any]] = []
    out: dict[str, Row] = {}
    for row in inputs:
        if row.name == MODULE_SCOPE:
            continue
        scope = _scope(backends, row)
        response = await backends.callees(row.name, scope)
        unresolved = 0
        listed = 0
        for entry in response.get("callees") or []:
            if entry.get("callee_resolution") != "project":
                unresolved += 1
                continue
            name = str(entry.get("name") or "")
            target = str(entry.get("callee_resolved_file") or "")
            listed += 1
            out.setdefault(
                f"{target}::{name}",
                Row(name=name, file=target, line=None, depth=1, via=row.key),
            )
        cov = (
            gap(INCOMPLETE, CALLEE_UNRESOLVED)
            if unresolved
            else gap(UNKNOWN, CALLEES_COVERAGE_UNREPORTED)
        )
        if response.get("success") is False:
            cov = from_producer(response)
        covs.append(cov)
        item = _evidence("callees", row, scope, cov, listed, response)
        item["unresolved"] = unresolved
        evidence.append(item)
    return RelationResult(list(out.values()), combine_or_complete(covs), evidence)


def is_test_entry(row: Row) -> bool:
    return _is_test_entry(row)


__all__ = [
    "COMPLETE_COVERAGE",
    "NODE_BUDGET",
    "RelationResult",
    "Row",
    "callees",
    "callers",
    "is_test_entry",
    "row_from_symbol",
    "tests",
]
