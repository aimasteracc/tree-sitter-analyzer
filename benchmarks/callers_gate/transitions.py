"""Classify every base->head answer change of one repo."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .query import ERROR_FIELDS, SITE_FIELDS

#: Change kinds, in report order.
KINDS = (
    "error",
    "verdict",
    "reasons",
    "caller_count",
    "callers",
    "sites",
    "compact",
    "other",
)
SITE_SCALARS = (
    "open_sites",
    "unresolved_inbound_sites_total",
    "unresolved_sites_total",
    "name_only_sites_total",
    "non_call_references",
)
CALLER_KEY = ("file", "name", "line", "end_line", "resolution_kind", "via")


class RowSetMismatch(ValueError):
    """Base and head did not answer the same targets (never compare partial sets)."""


def row_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (row["mode"], row["file"], row["qual"])


@dataclass
class Change:
    repo: str
    key: tuple[str, str, str]
    name: str
    base: dict[str, Any]
    head: dict[str, Any]
    kinds: list[str] = field(default_factory=list)

    @property
    def transition(self) -> str:
        return f"{self.base.get('completeness')}->{self.head.get('completeness')}"

    @property
    def new_complete(self) -> bool:
        return (
            self.head.get("completeness") == "complete"
            and self.base.get("completeness") != "complete"
        )

    def summary(self) -> dict[str, Any]:
        def side(full: dict[str, Any]) -> dict[str, Any]:
            return {
                "completeness": full.get("completeness"),
                "reasons": full.get("completeness_reasons"),
                "caller_count": full.get("caller_count"),
            }

        return {
            "repo": self.repo,
            "mode": self.key[0],
            "file": self.key[1],
            "qual": self.key[2],
            "transition": self.transition,
            "kinds": self.kinds,
            "base": side(self.base),
            "head": side(self.head),
        }

    def delta(self) -> dict[str, Any]:
        """Callers and sites removed (``-``) / added (``+``), for the reviewer."""
        out: dict[str, Any] = {}
        a, b = set(_callers(self.base)), set(_callers(self.head))
        if a != b:
            out["callers"] = {
                "-": sorted(a - b, key=repr),
                "+": sorted(b - a, key=repr),
            }
        for f in SITE_FIELDS:
            sa = {(s.get("file"), s.get("line")) for s in self.base.get(f) or []}
            sb = {(s.get("file"), s.get("line")) for s in self.head.get(f) or []}
            if sa != sb:
                out[f] = {
                    "-": sorted(sa - sb, key=repr),
                    "+": sorted(sb - sa, key=repr),
                }
        for k in SITE_SCALARS:
            if self.base.get(k) != self.head.get(k):
                out[k] = [self.base.get(k), self.head.get(k)]
        return out


def _callers(full: dict[str, Any]) -> list[tuple[Any, ...]]:
    return sorted(
        (tuple(c.get(k) for k in CALLER_KEY) for c in full.get("callers") or []),
        key=repr,
    )


def _sites(full: dict[str, Any]) -> tuple[Any, ...]:
    lists = tuple(
        sorted(
            (
                (s.get("file"), s.get("line"), s.get("callee"))
                for s in full.get(f) or []
            ),
            key=repr,
        )
        for f in SITE_FIELDS
    )
    return lists + tuple(repr(full.get(k)) for k in SITE_SCALARS)


def _compact_norm(row: dict[str, Any]) -> dict[str, Any]:
    """Compact answer with its caller lines order-insensitive (TSA does not fix their order)."""
    compact = dict(row.get("compact") or {})
    answer = compact.get("answer")
    if isinstance(answer, str):
        compact["answer"] = sorted(answer.splitlines())
    return compact


def classify_pair(base_row: dict[str, Any], head_row: dict[str, Any]) -> list[str]:
    a, b = base_row["full"], head_row["full"]
    kinds = []
    if any(f in b for f in ERROR_FIELDS) or any(
        f in head_row.get("compact", {}) for f in ERROR_FIELDS
    ):
        kinds.append("error")
    if a.get("completeness") != b.get("completeness"):
        kinds.append("verdict")
    if a.get("completeness_reasons") != b.get("completeness_reasons"):
        kinds.append("reasons")
    if a.get("caller_count") != b.get("caller_count") or len(
        a.get("callers") or []
    ) != len(b.get("callers") or []):
        kinds.append("caller_count")
    elif _callers(a) != _callers(b):
        kinds.append("callers")
    if _sites(a) != _sites(b):
        kinds.append("sites")
    head_compact = head_row.get("compact", {}).get("completeness")
    base_compact = base_row.get("compact", {}).get("completeness")
    if head_compact != b.get("completeness") and base_compact == a.get("completeness"):
        kinds.append("compact")
    if not kinds:
        rest_a = {
            k: v
            for k, v in a.items()
            if k
            not in (
                "completeness",
                "completeness_reasons",
                "caller_count",
                "callers",
                *SITE_FIELDS,
                *SITE_SCALARS,
            )
        }
        rest_b = {
            k: v
            for k, v in b.items()
            if k
            not in (
                "completeness",
                "completeness_reasons",
                "caller_count",
                "callers",
                *SITE_FIELDS,
                *SITE_SCALARS,
            )
        }
        if rest_a != rest_b or _compact_norm(base_row) != _compact_norm(head_row):
            kinds.append("other")
    return kinds


@dataclass
class RepoDiff:
    repo: str
    n: int
    transitions: Counter[str]
    changes: list[Change]
    identical: int

    def count(self, kind: str) -> int:
        return sum(1 for c in self.changes if kind in c.kinds)

    @property
    def reason_changes_same_verdict(self) -> list[Change]:
        return [
            c for c in self.changes if "reasons" in c.kinds and "verdict" not in c.kinds
        ]


def diff_repo(
    repo: str, base: list[dict[str, Any]], head: list[dict[str, Any]]
) -> RepoDiff:
    base_by = {row_key(r): r for r in base}
    head_by = {row_key(r): r for r in head}
    if len(base_by) != len(base) or len(head_by) != len(head):
        raise RowSetMismatch(f"{repo}: duplicate target rows")
    if base_by.keys() != head_by.keys():
        missing = sorted(base_by.keys() ^ head_by.keys())[:5]
        raise RowSetMismatch(
            f"{repo}: base and head answered different targets, e.g. {missing}"
        )
    transitions: Counter[str] = Counter()
    changes = []
    identical = 0
    for key, b in head_by.items():
        a = base_by[key]
        transitions[
            f"{a['full'].get('completeness')}->{b['full'].get('completeness')}"
        ] += 1
        kinds = classify_pair(a, b)
        if kinds:
            changes.append(
                Change(repo, key, b.get("name", key[2]), a["full"], b["full"], kinds)
            )
        else:
            identical += 1
    return RepoDiff(repo, len(head), transitions, changes, identical)
