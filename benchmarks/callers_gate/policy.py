"""Which answer changes a PR may make. Everything not allowed is a violation.

Default policy (no file, no flags):

* verdict transitions: only ``X->complete`` (``*->complete``); every other
  transition, including any loss of ``complete``, is a violation;
* reason changes: allowed (they are listed in the report for reading);
* site-list changes: allowed only on a row whose verdict transition is allowed
  or whose reasons changed (the sites are the evidence for the reason); a site
  change with the same verdict and the same reasons is a violation;
* caller-count and caller-list changes (a ``confidence_tier`` change included):
  violations;
* ``other`` (any kept field outside the kinds above, including the compact
  answer text): a violation;
* compact/full disagreement that base did not have, and query errors: always
  violations (no flag can allow them).

Policy file (JSON)::

    {"allow_transitions": ["*->complete", "unknown->incomplete"],
     "allow_reason_changes": true,
     "allow_caller_changes": false,
     "allow_site_changes": false,
     "allow_other_changes": false,
     "allow_items": [{"repo": "gson", "mode": "bare", "file": "gson/src/.../JsonWriter.java",
                      "qual": "JsonWriter.value", "kinds": ["callers"]}]}

An ``allow_items`` entry names exactly one row: ``repo``, ``mode``, ``file`` and
``qual`` are all required. Allowing a change never skips an oracle: every
changed head ``complete`` is still checked (see ``report``).

``run --scip`` adds one rule set (``scip_evidence``): the SCIP evidence layer may
only *add* callers whose ``confidence_tier`` is ``scip`` (no caller removed, the
count grows by exactly the added ones), *close* open sites (every head site
list is a subset of the base list; a non-call reference list may appear only
where the base never ran that check), add ``SCIP_RESOLVED_OTHER`` to
``excluded_by_reason`` and change ``next_step``. ``unknown->incomplete`` is
allowed when SCIP added a caller. Losing ``complete`` stays a violation.
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .query import SITE_FIELDS
from .transitions import CALLER_KEY, SITE_SCALARS, Change, _callers

NEVER_ALLOWED = ("error", "compact")
ITEM_KEYS = frozenset({"repo", "mode", "file", "qual", "kinds"})


class PolicyError(ValueError):
    pass


@dataclass(frozen=True)
class Policy:
    allow_transitions: tuple[str, ...] = ("*->complete",)
    allow_reason_changes: bool = True
    allow_caller_changes: bool = False
    allow_site_changes: bool = False
    allow_items: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    allow_other_changes: bool = False
    #: ``run --scip``: the additive SCIP rules (module docstring).
    scip_evidence: bool = False

    @classmethod
    def load(
        cls,
        path: Path | None,
        extra_transitions: list[str] | None = None,
        *,
        caller_changes: bool = False,
        site_changes: bool = False,
        other_changes: bool = False,
        scip_evidence: bool = False,
    ) -> Policy:
        data: dict[str, Any] = {}
        if path is not None:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise PolicyError(f"policy file unreadable: {path}: {exc}") from exc
            if not isinstance(data, dict):
                raise PolicyError("policy file must hold a JSON object")
            unknown = set(data) - {
                "allow_transitions",
                "allow_reason_changes",
                "allow_caller_changes",
                "allow_site_changes",
                "allow_other_changes",
                "allow_items",
                "_note",
            }
            if unknown:
                raise PolicyError(f"unknown policy keys: {sorted(unknown)}")
        transitions = tuple(
            data.get("allow_transitions", cls.allow_transitions)
        ) + tuple(extra_transitions or ())
        for pattern in transitions:
            if not isinstance(pattern, str) or "->" not in pattern:
                raise PolicyError(
                    f"transition pattern must look like 'A->B': {pattern!r}"
                )
        items = tuple(data.get("allow_items", ()))
        for item in items:
            if not isinstance(item, dict) or not ITEM_KEYS <= set(item):
                raise PolicyError(
                    f"allow_items entries need {', '.join(sorted(ITEM_KEYS))}: {item!r}"
                )
            if set(item["kinds"]) & set(NEVER_ALLOWED):
                raise PolicyError(f"{NEVER_ALLOWED} can never be allowed: {item!r}")
        return cls(
            allow_transitions=transitions,
            allow_reason_changes=bool(data.get("allow_reason_changes", True)),
            allow_caller_changes=bool(data.get("allow_caller_changes", False))
            or caller_changes,
            allow_site_changes=bool(data.get("allow_site_changes", False))
            or site_changes,
            allow_items=items,
            allow_other_changes=bool(data.get("allow_other_changes", False))
            or other_changes,
            scip_evidence=scip_evidence,
        )

    def transition_allowed(self, transition: str) -> bool:
        return any(
            fnmatch.fnmatchcase(transition, pattern)
            for pattern in self.allow_transitions
        )

    def _item_allows(self, change: Change, kind: str) -> bool:
        """An entry naming exactly this row (an entry without file or mode never matches)."""
        mode, file, qual = change.key
        return any(
            item.get("repo") == change.repo
            and item.get("mode") == mode
            and item.get("file") == file
            and item.get("qual") == qual
            and kind in item.get("kinds", ())
            for item in self.allow_items
        )

    def violations(self, change: Change) -> list[str]:
        """Human-readable reasons this change is not allowed (empty = allowed)."""
        out = []
        verdict_ok = True
        for kind in change.kinds:
            if kind in NEVER_ALLOWED:
                out.append(kind)
                continue
            if self._item_allows(change, kind):
                continue
            if kind == "verdict":
                verdict_ok = self.transition_allowed(change.transition) or (
                    self.scip_evidence
                    and change.transition == "unknown->incomplete"
                    and scip_additions_only(change)
                )
                if not verdict_ok:
                    lost = change.base.get("completeness") == "complete"
                    out.append(
                        f"{'lost complete' if lost else 'transition'} {change.transition}"
                    )
            elif kind == "reasons" and not self.allow_reason_changes:
                out.append("reasons")
            elif kind in ("caller_count", "callers") and not self.allow_caller_changes:
                if not (self.scip_evidence and scip_additions_only(change)):
                    out.append(kind)
            elif kind == "other" and not self.allow_other_changes:
                if not (self.scip_evidence and scip_other_only(change)):
                    out.append(kind)
        if (
            "sites" in change.kinds
            and not self._item_allows(change, "sites")
            and not self.allow_site_changes
        ):
            explained = ("verdict" in change.kinds and verdict_ok) or (
                "reasons" in change.kinds and self.allow_reason_changes
            )
            if not explained and not (self.scip_evidence and scip_sites_shrink(change)):
                out.append("sites")
        return out


_TIER = CALLER_KEY.index("confidence_tier")
SCIP_TIER = "scip"
SCIP_OTHER_REASON = "SCIP_RESOLVED_OTHER"


def scip_additions_only(change: Change) -> bool:
    """Head callers = base callers + callers of tier ``scip`` (and the count agrees)."""
    base, head = _callers(change.base), _callers(change.head)
    rest = list(head)
    for caller in base:
        if caller not in rest:
            return False
        rest.remove(caller)
    if not rest or any(caller[_TIER] != SCIP_TIER for caller in rest):
        return False
    before, after = change.base.get("caller_count"), change.head.get("caller_count")
    return isinstance(before, int) and after == before + len(rest)


def scip_sites_shrink(change: Change) -> bool:
    """Every head site list is a subset of the base list; totals never grow."""
    for name in SITE_FIELDS:
        base, head = change.base.get(name), change.head.get(name)
        if head is None:
            if base is not None:
                return False
            continue
        if base is None:
            # A review-gate list where the base never ran the gate (edges blocked).
            if name != "non_call_reference_sites":
                return False
            continue
        key = lambda s: (s.get("file"), s.get("line"), s.get("callee"))  # noqa: E731
        if not {key(s) for s in head} <= {key(s) for s in base}:
            return False
    for name in SITE_SCALARS:
        base, head = change.base.get(name), change.head.get(name)
        if name == "open_sites" or base == head:
            continue
        if name == "non_call_references":
            if base is not None:
                return False
            continue
        if not (isinstance(base, int) and isinstance(head, int) and head <= base):
            return False
    return True


def scip_other_only(change: Change) -> bool:
    """The only other differences are ``next_step`` and SCIP exclusions."""
    keys = set(change.base) | set(change.head)
    for name in keys - {"next_step", "excluded_by_reason"}:
        if name in ("scip", "callers", *SITE_FIELDS, *SITE_SCALARS):
            continue
        if change.base.get(name) != change.head.get(name):
            return False
    base = dict(change.base.get("excluded_by_reason") or {})
    head = dict(change.head.get("excluded_by_reason") or {})
    head.pop(SCIP_OTHER_REASON, None)
    base.pop(SCIP_OTHER_REASON, None)
    return base == head
