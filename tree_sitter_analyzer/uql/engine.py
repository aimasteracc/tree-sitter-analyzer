"""Execute a parsed :class:`~.ir.Query` (RFC-0041 §3).

The engine owns stage semantics only: sources open a group, relations open a
new group from the current set, refinements narrow the current group in
place. Each stage records its *own* coverage; a group's *effective* coverage
folds in everything upstream, and the query total is the last effective
coverage — ``complete`` only when every stage is.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from . import relations as rel
from .backends import SELECT_CAP, Backends
from .coverage import (
    COMPLETE_COVERAGE,
    INCOMPLETE,
    MEMBERSHIP_UNKNOWN,
    SELECT_CAP_REACHED,
    SELECTOR_PREDICATE_UNPROVEN,
    UNKNOWN,
    Coverage,
    combine,
    gap,
    with_upstream,
)
from .errors import INDEX_UNAVAILABLE, INVALID_ARGUMENT, Err, Ok, QueryError, Result
from .ir import (
    HasTests,
    Query,
    Refine,
    Relate,
    Select,
    Sort,
    Stage,
    SymbolSource,
    Take,
    stage_name,
)
from .relations import Row, row_from_symbol
from .selector import relation_hint, unproven_predicates


@dataclass
class Group:
    """One output group: the rows a source or relation stage produced."""

    name: str
    rows: list[Row]
    coverage: Coverage
    files: list[str] | None = None


@dataclass
class StageReport:
    index: int
    op: str
    count: int
    own: Coverage
    effective: Coverage
    evidence: list[dict[str, Any]] = field(default_factory=list)
    note: str | None = None


@dataclass
class Execution:
    query: Query
    groups: list[Group]
    stages: list[StageReport]
    total: Coverage
    indexed_files: int


class _Memo:
    """Per-execution memo: one producer call per (relation, name, file).

    Within one query the index does not change, so a node reached by two
    stages (``callers()`` then ``tests()``, or a BFS revisit) is asked once.
    """

    def __init__(self, inner: Backends) -> None:
        self._inner = inner
        self._relations: dict[tuple[str, str, str | None], dict[str, Any]] = {}
        self._counts: dict[str, int | None] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def definition_count(self, name: str) -> int | None:
        if name not in self._counts:
            self._counts[name] = self._inner.definition_count(name)
        return self._counts[name]

    async def callers(self, name: str, file: str | None) -> dict[str, Any]:
        key = ("callers", name, file)
        if key not in self._relations:
            self._relations[key] = await self._inner.callers(name, file)
        return self._relations[key]

    async def callees(self, name: str, file: str | None) -> dict[str, Any]:
        key = ("callees", name, file)
        if key not in self._relations:
            self._relations[key] = await self._inner.callees(name, file)
        return self._relations[key]


async def run(query: Query, backends: Backends) -> Result[Execution]:
    from ..query_scope import query_scope

    # One index state per answer: producers may share invariant sub-steps.
    with query_scope():
        return await _run(query, _Memo(backends))


async def _run(query: Query, backends: Backends) -> Result[Execution]:
    state = backends.index_state()
    if state.state != "ready":
        return Err(
            QueryError(
                INDEX_UNAVAILABLE,
                f"index {state.state}" + (f": {state.detail}" if state.detail else ""),
                suggestion=(
                    "Build the index with index action=auto (CLI: --full-index), "
                    "then retry. An empty result here would not be evidence."
                ),
            )
        )
    groups: list[Group] = []
    reports: list[StageReport] = []
    upstream = COMPLETE_COVERAGE
    for index, stage in enumerate(query.stages):
        step = await _apply(stage, groups, backends)
        if isinstance(step, Err):
            return Err(
                QueryError(
                    step.error.code,
                    step.error.message,
                    stage_index=index,
                    suggestion=step.error.suggestion,
                    partial=_partial(groups, reports),
                )
            )
        own, evidence, note = step.value
        effective = with_upstream(own, upstream)
        if groups:
            groups[-1].coverage = effective
        reports.append(
            StageReport(
                index,
                stage_name(stage),
                len(groups[-1].rows) if groups else 0,
                own,
                effective,
                evidence,
                note,
            )
        )
        upstream = effective
    return Ok(Execution(query, groups, reports, upstream, state.indexed_files))


def _partial(groups: list[Group], reports: list[StageReport]) -> dict[str, Any]:
    return {
        "stages_completed": len(reports),
        "groups": {g.name: len(g.rows) for g in groups},
    }


_StepOut = tuple[Coverage, list[dict[str, Any]], str | None]


async def _apply(
    stage: Stage, groups: list[Group], backends: Backends
) -> Result[_StepOut]:
    if isinstance(stage, Select):
        return Ok(_select(stage, groups, backends))
    if isinstance(stage, SymbolSource):
        return Ok(_symbols(stage, groups, backends))
    current = groups[-1]
    if isinstance(stage, Relate):
        return Ok(await _relate(stage, groups, current.rows, backends))
    if isinstance(stage, Refine):
        return _refine(stage, current)
    if isinstance(stage, HasTests):
        return Ok(await _presence(stage, current, backends))
    if isinstance(stage, Take):
        current.rows = current.rows[: stage.n]
        return Ok((COMPLETE_COVERAGE, [], None))
    assert isinstance(stage, Sort)
    current.rows = sorted(current.rows, key=_sort_key(stage.by), reverse=stage.desc)
    return Ok((COMPLETE_COVERAGE, [], None))


def _sort_key(by: str) -> Any:
    if by == "line":
        return lambda r: (r.line or 0, r.file, r.name)
    if by == "file":
        return lambda r: (r.file, r.line or 0, r.name)
    return lambda r: (r.name, r.file, r.line or 0)


def _languages(rows: list[Row]) -> frozenset[str]:
    return frozenset(r.language for r in rows if r.language)


def _select(stage: Select, groups: list[Group], backends: Backends) -> _StepOut:
    selection = backends.select(stage.selector, SELECT_CAP)
    rows = [row_from_symbol(s) for s in selection.rows]
    groups.append(Group(_group_name("select", groups), rows, COMPLETE_COVERAGE))
    coverage, note = selection_coverage(backends, stage.selector, selection)
    return coverage, [], note


def selection_coverage(
    backends: Backends, selector: Any, selection: Any, *, capped: bool = True
) -> tuple[Coverage, str | None]:
    """Coverage of a selector's matched set (shared with ``tql_execute``).

    The index source gate, then predicate exhaustiveness: edge / history /
    rule / branch pseudo-classes read tables with no coverage proof, so they
    make the set ``unknown``. ``capped`` adds the evaluator cap as a gap; a
    caller that reports ``total`` / ``truncated`` itself passes ``False``.
    """
    rows = [row_from_symbol(s) for s in selection.rows]
    covs = [backends.source_gate(sorted({r.file for r in rows}), _languages(rows))]
    unproven = unproven_predicates(selector)
    note = None
    if unproven:
        covs.append(gap(UNKNOWN, SELECTOR_PREDICATE_UNPROVEN))
        note = f"unproven predicates: {', '.join(':' + n for n in unproven)}. " + (
            relation_hint(unproven) or ""
        )
    if capped and selection.truncated:
        covs.append(gap(INCOMPLETE, SELECT_CAP_REACHED))
    return combine(covs), note.strip() if note else None


def _symbols(stage: SymbolSource, groups: list[Group], backends: Backends) -> _StepOut:
    seen: dict[str, Row] = {}
    for name in stage.names:
        owner, _, bare = name.rpartition(".")
        for sym in backends.definitions(bare, cls=owner or None, file=stage.file):
            row = row_from_symbol(sym)
            seen.setdefault(row.key, row)
    rows = sorted(seen.values(), key=lambda r: (r.file, r.line or 0))
    groups.append(Group(_group_name("symbol", groups), rows, COMPLETE_COVERAGE))
    gate = backends.source_gate(sorted({r.file for r in rows}), _languages(rows))
    return gate, [], None


def _group_name(base: str, groups: list[Group]) -> str:
    names = {g.name for g in groups}
    if base not in names:
        return base
    n = 2
    while f"{base}#{n}" in names:
        n += 1
    return f"{base}#{n}"


async def _relate(
    stage: Relate, groups: list[Group], inputs: list[Row], backends: Backends
) -> _StepOut:
    if stage.relation == "callers":
        result = await rel.callers(backends, inputs, depth=stage.depth)
    elif stage.relation == "impact":
        result = await rel.callers(backends, inputs, depth=stage.depth, closure=True)
    elif stage.relation == "tests":
        result = await rel.tests(backends, inputs)
    else:
        result = await rel.callees(backends, inputs)
    rows = sorted(
        result.rows, key=lambda r: (r.depth or 0, r.file, r.line or 0, r.name)
    )
    files = None
    if stage.relation == "impact":
        rows = [
            replace(r, role="test" if rel.is_test_entry(r) else "caller") for r in rows
        ]
        files = sorted({r.file for r in rows} | {r.file for r in inputs})
    groups.append(
        Group(_group_name(stage.relation, groups), rows, COMPLETE_COVERAGE, files)
    )
    return result.coverage, result.evidence, None


def _refine(stage: Refine, current: Group) -> Result[_StepOut]:
    from ..mcp.tools._codegraph_query_filters import filter_symbols
    from .ir import RawStep

    by_key = {r.key: r for r in current.rows}
    try:
        kept = filter_symbols(
            [r.as_symbol() | {"_key": r.key} for r in current.rows],
            RawStep(stage.op, [], dict(stage.predicates)),
            invert=stage.op == "exclude",
        )
    except ValueError as exc:
        return Err(QueryError(INVALID_ARGUMENT, str(exc)))
    current.rows = [by_key[s["_key"]] for s in kept]
    return Ok((COMPLETE_COVERAGE, [], None))


async def _presence(stage: HasTests, current: Group, backends: Backends) -> _StepOut:
    kept: list[Row] = []
    evidence: list[dict[str, Any]] = []
    undecided = 0
    for row in current.rows:
        found = await rel.tests(backends, [row])
        evidence.extend(found.evidence)
        has_tests = bool(found.rows)
        decided = has_tests or found.coverage.complete
        if not decided:
            undecided += 1
        if has_tests == stage.want_tests or not decided:
            if decided:
                kept.append(row)
            elif not stage.want_tests:
                kept.append(replace(row, membership="unknown"))
    current.rows = kept
    if not undecided:
        return COMPLETE_COVERAGE, evidence, None
    status = UNKNOWN if not stage.want_tests else INCOMPLETE
    note = f"{undecided} row(s) could not be decided: their tests are not a census"
    return gap(status, MEMBERSHIP_UNKNOWN), evidence, note
