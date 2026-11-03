"""Ground-truth checks: GT2 (Python) and hand labels (hono, zod).

* every head ``complete`` on a Python repo must list every GT2 caller
  (``gt2_miss`` when not); a target GT2 does not define cannot be checked
  (``gt2_untracked``);
* every head ``unknown`` whose ``open_sites`` is enumerated must cover each GT2
  caller (Python) or labelled call (hono, zod) with a listed caller or an open
  site -- the PR-4 soundness check.

A violation on a row that is identical on base is *pre-existing*: reported, not
blamed on the PR. On a new or changed row it fails the gate.
"""

from __future__ import annotations

from typing import Any


def gt2_rows(gt2: dict[str, Any]) -> dict[str, list[tuple[Any, ...]]]:
    rows: dict[str, list[tuple[Any, ...]]] = {}
    for key, value in list(gt2["callers"].items()) + list(
        gt2["module_callers"].items()
    ):
        rows.setdefault(key, []).extend(tuple(r) for r in value)
    return rows


def gt2_defined(gt2: dict[str, Any]) -> set[str]:
    return {d["key"] for d in gt2.get("defs") or ()}


def open_set(full: dict[str, Any]) -> set[tuple[str, int]]:
    bound = full.get("open_sites") or {}
    if not isinstance(bound, dict):
        return set()
    return {
        (s["file"], s["line"])
        for f in bound.get("fields") or ()
        for s in full.get(f) or ()
    }


def covered(callers: list[dict[str, Any]], file: str, line: int) -> bool:
    for c in callers:
        if c.get("file") != file:
            continue
        start = c.get("line") or 0
        end = c.get("end_line") or start
        if start <= line <= end:
            return True
    return False


def gt2_misses(
    row: dict[str, Any], rows: dict[str, list[tuple[Any, ...]]]
) -> list[list[Any]]:
    """GT2 callers the answer neither lists nor leaves open."""
    full = row["full"]
    key = f"{row['file']}::{row['qual']}"
    have = {(c["file"], c["name"], c["line"]) for c in full["callers"]}
    have_mod = {
        (c["file"], c["line"]) for c in full["callers"] if c["name"] == "<module>"
    }
    opened = open_set(full)
    miss = []
    for f, cname, dline, _src, cline in rows.get(key, ()):
        if (f, cname, dline) in have or (
            cname == "<module>" and (f, cline) in have_mod
        ):
            continue
        if (f, cline) in opened:
            continue
        miss.append([f, cname, dline, cline])
    return miss


def label_misses(
    row: dict[str, Any], labels: dict[str, Any]
) -> tuple[list[Any], list[Any], bool]:
    """(uncovered labelled calls, uncovered labelled refs, whether a label applies)."""
    name = row["qual"].rsplit(".", 1)[-1].strip('"')
    lab = labels.get(name)
    if not isinstance(lab, dict) or lab.get("file") != row["file"]:
        return [], [], False
    full = row["full"]
    opened = open_set(full)
    calls = [
        s
        for s in lab.get("calls", [])
        if tuple(s) not in opened and not covered(full["callers"], *s)
    ]
    refs = [
        s
        for s in lab.get("refs", [])
        if tuple(s) not in opened and not covered(full["callers"], *s)
    ]
    return calls, refs, True


def enumerated(full: dict[str, Any]) -> bool:
    bound = full.get("open_sites")
    return (
        full.get("completeness") == "unknown"
        and isinstance(bound, dict)
        and bound.get("enumerated") is True
    )


def check_rows(
    repo: str,
    head: list[dict[str, Any]],
    unchanged: set[tuple[str, str, str]],
    *,
    gt2: dict[str, Any] | None,
    labels: dict[str, Any] | None,
) -> dict[str, Any]:
    """Failures (new/changed rows), pre-existing findings and counters for one repo."""
    failures: list[dict[str, Any]] = []
    preexisting: list[dict[str, Any]] = []
    stats = {"gt2_complete_checked": 0, "open_sites_checked": 0, "labels_checked": 0}
    rows = gt2_rows(gt2) if gt2 is not None else {}
    defined = gt2_defined(gt2) if gt2 is not None else set()

    def report(row: dict[str, Any], kind: str, detail: Any) -> None:
        key = (row["mode"], row["file"], row["qual"])
        entry = {
            "repo": repo,
            "mode": key[0],
            "file": key[1],
            "qual": key[2],
            "kind": kind,
            "detail": detail,
        }
        (preexisting if key in unchanged else failures).append(entry)

    for row in head:
        full = row["full"]
        if gt2 is not None and full.get("completeness") == "complete":
            stats["gt2_complete_checked"] += 1
            if f"{row['file']}::{row['qual']}" not in defined:
                report(
                    row,
                    "gt2_untracked",
                    "target is not a GT2 definition; a complete cannot be checked",
                )
            elif miss := gt2_misses(row, rows):
                report(row, "gt2_miss", miss[:10])
        if labels is not None and full.get("completeness") == "complete":
            calls, _refs, applies = label_misses(row, labels)
            stats["labels_checked"] += applies
            if calls:
                report(row, "label_call_miss", calls)
        if enumerated(full):
            stats["open_sites_checked"] += 1
            if gt2 is not None and (miss := gt2_misses(row, rows)):
                report(row, "open_sites_gt2_miss", miss[:10])
            if labels is not None:
                calls, refs, applies = label_misses(row, labels)
                stats["labels_checked"] += applies
                if calls:
                    report(row, "open_sites_label_call_miss", calls)
                if refs:
                    preexisting.append(
                        {
                            "repo": repo,
                            "mode": row["mode"],
                            "file": row["file"],
                            "qual": row["qual"],
                            "kind": "open_sites_label_ref_miss (info)",
                            "detail": refs,
                        }
                    )
    return {"failures": failures, "preexisting": preexisting, "stats": stats}
