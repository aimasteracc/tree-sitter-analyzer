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
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .transitions import Change

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

    @classmethod
    def load(
        cls,
        path: Path | None,
        extra_transitions: list[str] | None = None,
        *,
        caller_changes: bool = False,
        site_changes: bool = False,
        other_changes: bool = False,
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
                verdict_ok = self.transition_allowed(change.transition)
                if not verdict_ok:
                    lost = change.base.get("completeness") == "complete"
                    out.append(
                        f"{'lost complete' if lost else 'transition'} {change.transition}"
                    )
            elif kind == "reasons" and not self.allow_reason_changes:
                out.append("reasons")
            elif kind in ("caller_count", "callers") and not self.allow_caller_changes:
                out.append(kind)
            elif kind == "other" and not self.allow_other_changes:
                out.append(kind)
        if (
            "sites" in change.kinds
            and not self._item_allows(change, "sites")
            and not self.allow_site_changes
        ):
            explained = ("verdict" in change.kinds and verdict_ok) or (
                "reasons" in change.kinds and self.allow_reason_changes
            )
            if not explained:
                out.append("sites")
        return out
