"""#1941: a function is listed as dead only where ``nav action=callers`` certifies it.

The dead-code surfaces (``codegraph_overview`` and ``health action=dead``) used
to read only the resolved edges of the in-memory call graph. A call through an
attribute receiver whose type is not inferred (``self.console.set_live()``)
is never a resolved edge, so ``Console.set_live`` was listed as dead while
``callers`` answered ``unknown`` and named the site that calls it.

Here every candidate is asked through the callers tool itself (one batch, one
certified index read), so the dead-code claim and the callers answer come from
the same evidence: name-only and unresolved inbound sites, non-call references,
dynamic supertypes, decorators, a stale index all block it. Two further gates
run first, because ``callers`` answers about *project* callers and a dead-code
claim is about all callers:

* a Python method whose class has a base outside the project may be called by
  that base's code (:mod:`.dead_code_overrides`);
* a method in another language is not walked for such bases and is never
  certified.

A candidate is certified when its callers answer is ``complete`` and every
caller it lists is itself a certified candidate (a function reachable only from
dead code, :func:`resolve_dead`). Asking is bounded by a time budget; what was
not asked is reported as unchecked, never as dead.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ...call_graph import FunctionRef
from .callers_compact import site_refs
from .dead_code_overrides import (
    EXTERNAL_SUPERTYPE_REASON,
    OVERRIDE_UNCHECKED_REASON,
    external_override,
)

#: Seconds spent asking callers before the rest is reported unchecked.
CERTIFY_BUDGET_SECONDS = 30.0
#: Candidates asked per callers batch (the budget is checked between batches).
_BATCH = 16
#: Callers listed per answer; an answer with more callers is not certified.
_CALLERS_LIMIT = 50
#: Open sites named per uncertified entry.
_SITES_NAMED = 3

#: Status of a list whose every entry was certified by the callers evidence.
STATUS_CERTIFIED = "certified"
#: The callers answer is complete but a caller it lists is not certified dead.
LIVE_CALLER_REASON = "LIVE_CALLER"
#: The time budget ran out before the candidate was asked.
BUDGET_REASON = "CERTIFICATION_BUDGET"
#: The callers tool could not answer for the candidate.
NO_ANSWER_REASON = "CALLERS_UNANSWERED"


@dataclass(frozen=True)
class Verdict:
    """What the callers evidence says about one candidate."""

    certified: bool
    reasons: tuple[str, ...] = ()
    detail: str = ""
    open_sites: tuple[str, ...] = ()
    #: ``(file, definition line)`` of every caller the answer lists.
    callers: tuple[tuple[str, int], ...] = ()


@dataclass
class Certification:
    verdicts: dict[FunctionRef, Verdict] = field(default_factory=dict)
    #: Candidates the budget left unasked (in the order given).
    unchecked: list[FunctionRef] = field(default_factory=list)
    elapsed_seconds: float = 0.0


def query_name(func: FunctionRef) -> str:
    """The callers query for ``func``: ``Class.method`` for a member."""
    return f"{func.receiver}.{func.name}" if func.receiver else func.name


async def certify(
    project_root: str,
    funcs: Iterable[FunctionRef],
    *,
    budget_seconds: float = CERTIFY_BUDGET_SECONDS,
    stop_after: int | None = None,
) -> Certification:
    """Ask callers about each of ``funcs`` (in order) within ``budget_seconds``.

    ``stop_after``: stop asking once that many candidates are certified (a
    capped listing does not need the rest); the rest is ``unchecked``.
    """
    from .callers_tool import CodeGraphCallersTool

    started = time.perf_counter()
    tool = CodeGraphCallersTool(project_root)
    cache = tool._try_get_cache()
    try:
        result = await _certify(
            project_root, list(funcs), tool, cache, budget_seconds, stop_after, started
        )
    finally:
        if cache is not None:
            cache.close()
    result.elapsed_seconds = round(time.perf_counter() - started, 2)
    return result


async def _certify(
    project_root: str,
    funcs: list[FunctionRef],
    tool: Any,
    cache: Any,
    budget_seconds: float,
    stop_after: int | None,
    started: float,
) -> Certification:
    from .callers_supertypes import python_project_tops

    result = Certification()
    tops_value: list[frozenset[str] | None] = []

    def tops() -> frozenset[str] | None:
        if not tops_value:
            tops_value.append(python_project_tops(cache))
        return tops_value[0]

    pending: list[FunctionRef] = []
    for func in funcs:
        gate = _override_gate(project_root, func, tops)
        if gate is not None:
            result.verdicts[func] = gate
        else:
            pending.append(func)

    certified = 0
    for index in range(0, len(pending), _BATCH):
        out_of_budget = time.perf_counter() - started >= budget_seconds
        if out_of_budget or (stop_after is not None and certified >= stop_after):
            result.unchecked = pending[index:]
            break
        batch = pending[index : index + _BATCH]
        answers = await tool.execute_batch([_request(func) for func in batch])
        for func, answer in zip(batch, _answers_for(batch, answers), strict=True):
            verdict = _verdict(answer)
            result.verdicts[func] = verdict
            certified += verdict.certified
    return result


async def certify_transitive(
    project_root: str,
    scoped: list[FunctionRef],
    everything: list[FunctionRef],
) -> tuple[set[FunctionRef], Certification]:
    """The ``scoped`` candidates certified dead, judged against ``everything``.

    Every candidate is asked (``scoped`` first, so the budget favours what is
    reported), because a function called only from another candidate is dead
    only if that caller is.
    """
    order = list(dict.fromkeys([*scoped, *everything]))
    cert = await certify(project_root, order) if order else Certification()
    dead = resolve_dead(order, cert)
    return {func for func in scoped if func in dead}, cert


def resolve_dead(
    candidates: Iterable[FunctionRef], certification: Certification
) -> set[FunctionRef]:
    """Candidates whose answer is complete and whose every caller is dead too.

    A fixpoint: a caller that is not certified (alive, blocked or unchecked)
    keeps its callee alive, which may in turn keep the callee's callees alive.
    """
    pool = set(candidates)
    by_site: dict[tuple[str, int], list[FunctionRef]] = {}
    for func in pool:
        by_site.setdefault((func.file_path, func.start_line), []).append(func)
    dead = {
        func
        for func, verdict in certification.verdicts.items()
        if verdict.certified and func in pool
    }

    def caller_dead(site: tuple[str, int]) -> bool:
        found = by_site.get(site) or []
        return bool(found) and all(func in dead for func in found)

    changed = True
    while changed:
        changed = False
        for func in list(dead):
            verdict = certification.verdicts[func]
            if not all(caller_dead(site) for site in verdict.callers):
                dead.discard(func)
                changed = True
    return dead


def uncertified_entry(
    func: FunctionRef, certification: Certification, dead: set[FunctionRef]
) -> dict[str, Any]:
    """The serialized reason a candidate is not listed as dead."""
    verdict = certification.verdicts.get(func)
    entry: dict[str, Any] = {
        "name": func.name,
        "qualified_name": query_name(func),
        "file": func.file_path,
        "line": func.start_line,
        "language": func.language,
    }
    if verdict is None:
        entry["reasons"] = [BUDGET_REASON]
        return entry
    reasons = list(verdict.reasons)
    if verdict.certified and func not in dead:
        reasons = [LIVE_CALLER_REASON]
    entry["reasons"] = reasons
    if verdict.detail:
        entry["detail"] = verdict.detail
    if verdict.open_sites:
        entry["open_sites"] = list(verdict.open_sites)
    return entry


def _override_gate(project_root: str, func: FunctionRef, tops: Any) -> Verdict | None:
    if not func.receiver:
        return None
    if func.language != "python":
        detail = (
            f"`{query_name(func)}` may override a method of a supertype outside "
            "the project; that is not checked for this language"
        )
        return Verdict(False, (OVERRIDE_UNCHECKED_REASON,), detail)
    try:
        why = external_override(
            project_root, func.file_path, func.start_line, func.name, tops
        )
    except Exception as exc:  # noqa: BLE001 — a failed walk cannot certify
        why = f"the supertype walk failed ({type(exc).__name__})"
    if why is None:
        return None
    return Verdict(False, (EXTERNAL_SUPERTYPE_REASON,), why)


def _request(func: FunctionRef) -> dict[str, Any]:
    return {
        "function_name": query_name(func),
        "file_path": func.file_path,
        "include_bodies": False,
        "limit": _CALLERS_LIMIT,
    }


def _answers_for(
    batch: list[FunctionRef], answers: list[dict[str, Any]]
) -> list[Mapping[str, Any] | None]:
    """``execute_batch`` answers in request order, one per request.

    A batch that came back with a different length cannot be matched to its
    requests, so none of them is taken as an answer.
    """
    if len(answers) != len(batch):
        return [None] * len(batch)
    return list(answers)


def _verdict(answer: Mapping[str, Any] | None) -> Verdict:
    if not isinstance(answer, Mapping) or answer.get("success") is False:
        return Verdict(False, (NO_ANSWER_REASON,))
    callers = tuple(
        (str(caller.get("file") or ""), int(caller.get("line") or 0))
        for caller in answer.get("callers") or ()
        if isinstance(caller, Mapping)
    )
    count = int(answer.get("caller_count") or 0)
    reasons = tuple(str(r) for r in answer.get("completeness_reasons") or ())
    if answer.get("completeness") == "complete" and count == len(callers):
        return Verdict(True, callers=callers)
    sites = tuple(site_refs(answer)[:_SITES_NAMED])
    reason = answer.get("completeness_reason")
    if not reasons and reason:
        reasons = (str(reason),)
    return Verdict(False, reasons or ("NOT_COMPLETE",), open_sites=sites)
