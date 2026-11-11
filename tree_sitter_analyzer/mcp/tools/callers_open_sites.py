"""PR-4: ``open_sites`` -- a machine-readable bound on an ``unknown`` answer.

An ``unknown`` answer with 0 callers sends an agent back to grep, even when the
answer already lists every site that keeps it from being ``complete``. This
module says so explicitly::

    "open_sites": {"total": 3, "enumerated": true,
                   "fields": ["unresolved_inbound_sites", "name_only_sites"]}

Meaning: the ``total`` distinct ``(file, line)`` sites in the named fields are
**all** the evidence that blocks ``complete``. If none of them reaches the target
(calls it, or passes / rebinds it for a later call), the answer is ``complete``.
The verdict stays ``unknown``: with 0 known callers, ``incomplete`` would claim a
caller exists.

``enumerated: true`` is a trust claim, gated like ``complete``. It holds only
when, for every failed check:

* the check produces a site list (``UNRESOLVED_INBOUND``,
  ``UNRESOLVED_IN_DECLARING_FILE``, ``NAME_ONLY_INBOUND``, ``NON_CALL_REFERENCES``);
* the list is not truncated (its total equals its length);
* name-only sites carry real call lines (no fallback to a caller's definition);
* the review gates that the edge layer short-circuited were run as well, and
  either all pass or only the non-call reference gate fails, with every gate
  after it passing.

Anything else (an accessor, a decorator, unattributed module-level sites, an
unchecked or stale gate, a truncated list) is ``{"enumerated": false, "reason":
...}``; see :data:`TRUNCATED` and :data:`NO_SITE_LIST`.

#1923: when a review gate could not run on this call (a ``*_UNCHECKED`` code, or
``SOURCE_SCOPE_UNKNOWN`` from a freshness scan that ran out of time), the bound
is ``{"enumerated": false, "reason": "REVIEW_UNCHECKED", "unchecked": <code>}``,
not ``NO_SITE_LIST``: it failed for a load-dependent cause, and the compact
projection carries it (``open: unchecked (<code>)``) instead of silently
omitting the bound. The verdict is unaffected: it is still ``unknown``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .callers_absence import NON_CALL_REASON, AbsenceVerdict
from .callers_checks import REQUIRED_CHECKS, REVIEW
from .callers_compact import OPEN_SITES_FIELD as FIELD
from .callers_compact import REVIEW_UNCHECKED, UNCHECKED_KEY, site_refs, unchecked
from .callers_outcomes import Checked, NotChecked
from .callers_reasons import (
    DECLARING_FILE_REASON,
    EDGE_REASONS,
    NAME_ONLY_REASON,
    UNRESOLVED_INBOUND_REASON,
)
from .relation_freshness import UNKNOWN_REASON as FRESHNESS_UNKNOWN_REASON

#: A blocking check's site list was capped.
TRUNCATED = "SITES_TRUNCATED"
#: A blocking check has no exhaustive site list (accessor, decorator, unattributed
#: module-level sites, a gate that did not run, approximate name-only lines).
NO_SITE_LIST = "NO_SITE_LIST"

#: Edge reason -> (site list field, exact total field).
EDGE_SITE_FIELDS: Mapping[str, tuple[str, str]] = {
    UNRESOLVED_INBOUND_REASON: (
        "unresolved_inbound_sites",
        "unresolved_inbound_sites_total",
    ),
    DECLARING_FILE_REASON: ("unresolved_sites", "unresolved_sites_total"),
    NAME_ONLY_REASON: ("name_only_sites", "name_only_sites_total"),
}
NON_CALL_FIELDS = ("non_call_reference_sites", "non_call_references")
_REVIEW_NAMES = tuple(spec.name for spec in REQUIRED_CHECKS if spec.layer == REVIEW)

#: (sites with their field, failure code or None)
_Bound = tuple[list[tuple[str, dict[str, Any]]], str | None]


def open_sites(
    result: Mapping[str, Any],
    reasons: list[str],
    *,
    name_only_exact: bool,
    review: Callable[[], AbsenceVerdict | None],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """``(open_sites, extra response fields)`` for an ``unknown`` answer.

    ``review`` returns the review-gate verdict over the same target: the gates
    that ran, or (when the edge layer decided) a run made only for this bound.
    It is called only when every edge reason is fully enumerated.
    """
    edge_sites, failure = _edge_bound(result, reasons, name_only_exact)
    if failure is not None:
        return _not_enumerated(failure), {}
    verdict = review()
    review_sites, failure, extra = _review_bound(verdict)
    if failure is not None:
        return _not_enumerated(failure, extra.get(UNCHECKED_KEY)), {}
    sites = edge_sites + review_sites
    distinct = {(str(site.get("file")), site.get("line")) for _field, site in sites}
    if not distinct:
        return _not_enumerated(NO_SITE_LIST), {}
    fields = list(dict.fromkeys(field for field, _site in sites))
    return {"total": len(distinct), "enumerated": True, "fields": fields}, extra


def open_sites_step(func_name: str, answer: Mapping[str, Any]) -> str | None:
    """next_step for an exhaustive bound: read the k sites instead of searching."""
    refs = site_refs(answer)
    if not refs:
        return None
    named = "; ".join(refs[:3]) + (
        f"; and {len(refs) - 3} more" if len(refs) > 3 else ""
    )
    return (
        f"The bound is exhaustive (`open_sites`): these {len(refs)} site(s) are "
        f"all that keep {func_name!r} from a complete answer: {named}. Read them "
        f"instead of searching; if none of them calls {func_name!r} or passes it "
        "on for a later call, nothing else in the indexed project does."
    )


def _not_enumerated(code: str, gate_code: str | None = None) -> dict[str, Any]:
    bound: dict[str, Any] = {"enumerated": False, "reason": code}
    if gate_code is not None:
        bound[UNCHECKED_KEY] = gate_code
    return bound


def _transient(reason: str) -> bool:
    """#1923: a review gate's NotChecked code for a transient cause (a budget ran
    out, a file could not be read), as opposed to a structural skip."""
    return unchecked(reason) or reason == FRESHNESS_UNKNOWN_REASON


def _edge_bound(
    result: Mapping[str, Any], reasons: list[str], name_only_exact: bool
) -> _Bound:
    sites: list[tuple[str, dict[str, Any]]] = []
    for reason in reasons:
        if reason not in EDGE_REASONS:
            continue
        if reason not in EDGE_SITE_FIELDS:
            return [], NO_SITE_LIST
        if reason == NAME_ONLY_REASON and not name_only_exact:
            return [], NO_SITE_LIST
        field, total_field = EDGE_SITE_FIELDS[reason]
        listed = _listed(result, field, total_field)
        if isinstance(listed, str):
            return [], listed
        sites.extend((field, site) for site in listed)
    return sites, None


def _review_bound(
    verdict: AbsenceVerdict | None,
) -> tuple[list[tuple[str, dict[str, Any]]], str | None, dict[str, Any]]:
    """Sites behind the review gates: none when all pass, the non-call list when
    that gate alone fails and every gate after it passes."""
    if verdict is None:
        return [], NO_SITE_LIST, {}
    outcomes = dict(verdict.checks) | dict(verdict.trailing)
    failed: list[tuple[str, tuple[str, ...]]] = []
    for name in _REVIEW_NAMES:
        found = outcomes.get(name)
        if isinstance(found, NotChecked) and _transient(found.reason):
            if any(failed_name != "non_call_references" for failed_name, _ in failed):
                return [], NO_SITE_LIST, {}  # already structural either way
            # #1923: the gate ran out of time (or could not read a file) on this
            # call. Say so instead of a structural NO_SITE_LIST, so the answer
            # (and its compact projection) names a transient cause.
            return [], REVIEW_UNCHECKED, {UNCHECKED_KEY: found.reason}
        if not isinstance(found, Checked):
            return [], NO_SITE_LIST, {}
        if found.problems:
            failed.append((name, found.problems))
    if not failed:
        return [], None, {}
    if failed != [("non_call_references", (NON_CALL_REASON,))]:
        return [], NO_SITE_LIST, {}
    site_field, total_field = NON_CALL_FIELDS
    listed = _listed(verdict.fields, site_field, total_field)
    if isinstance(listed, str):
        return [], listed, {}
    extra = {site_field: listed, total_field: len(listed)}
    return [(site_field, site) for site in listed], None, extra


def _listed(
    source: Mapping[str, Any], field: str, total_field: str
) -> list[dict[str, Any]] | str:
    """The full site list, or the failure code when it is missing or capped."""
    listed = source.get(field)
    total = source.get(total_field)
    if not isinstance(listed, list) or not isinstance(total, int):
        return NO_SITE_LIST
    if total != len(listed):
        return TRUNCATED
    if not all(isinstance(site, Mapping) and site.get("file") for site in listed):
        return NO_SITE_LIST
    return list(listed)


__all__ = [
    "EDGE_SITE_FIELDS",
    "FIELD",
    "NO_SITE_LIST",
    "NON_CALL_FIELDS",
    "TRUNCATED",
    "open_sites",
    "open_sites_step",
    "site_refs",
]
