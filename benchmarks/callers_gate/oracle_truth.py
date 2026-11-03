"""Ground-truth checks: GT2 (Python), hand labels (hono, zod) and the compact form.

* every head ``complete`` on a Python repo must list every GT2 caller
  (``gt2_miss`` when not; an open site is *not* coverage on a complete row); a
  target GT2 does not define cannot be checked (``gt2_untracked``);
* on a new or changed Python ``complete``, every GT2 ``open_sites`` entry of the
  bare name (a call GT2 itself could not resolve) that is not inside a listed
  caller is a residual item for a human;
* every head ``unknown`` whose ``open_sites`` is enumerated must cover each GT2
  caller (Python) or labelled call (hono, zod) with a listed caller or an open
  site -- the PR-4 soundness check;
* labelled calls on a ``complete`` must be listed callers; whether a site is
  inside a listed caller comes from the grep oracle (innermost definition, see
  :mod:`.oracle_scope`), never from the answer's ``end_line``;
* a compact ``complete`` must be confirmed by the full answer and list exactly
  the full answer's callers -- on every head row, regardless of the base.

A violation on a row that is identical on base is *pre-existing*: reported, not
blamed on the PR. On a new or changed row it fails the gate. Compact failures
are never pre-existing.
"""

from __future__ import annotations

import re
from typing import Any

Key = tuple[str, str, str]
#: One caller line of the compact answer: ``name  file:line  kind``.
COMPACT_CALLER = re.compile(
    r"^(?P<name>.+?)\s{2,}(?P<file>\S+):(?P<line>\d+)\s{2,}\S+$"
)
COMPACT_HEADER = re.compile(r"^callers of .*: (?P<count>\d+)$")


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


def gt2_misses(
    row: dict[str, Any], rows: dict[str, list[tuple[Any, ...]]], *, allow_open: bool
) -> list[list[Any]]:
    """GT2 callers the answer neither lists nor (when ``allow_open``) leaves open."""
    full = row["full"]
    key = f"{row['file']}::{row['qual']}"
    have = {(c["file"], c["name"], c["line"]) for c in full["callers"]}
    have_mod = {
        (c["file"], c["line"]) for c in full["callers"] if c["name"] == "<module>"
    }
    opened = open_set(full) if allow_open else set()
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


def bare(qual: str) -> str:
    return qual.rsplit(".", 1)[-1].strip('"')


def label_for(row: dict[str, Any], labels: dict[str, Any]) -> dict[str, Any] | None:
    lab = labels.get(bare(row["qual"]))
    return lab if isinstance(lab, dict) and lab.get("file") == row["file"] else None


def label_sites(
    rows: list[dict[str, Any]], labels: dict[str, Any]
) -> list[tuple[Key, str, int, str, list[dict[str, Any]]]]:
    """(row key, file, line, name, callers) of every labelled site the label check reads."""
    out = []
    for row in rows:
        full = row["full"]
        lab = label_for(row, labels)
        if lab is None or not (
            full.get("completeness") == "complete" or enumerated(full)
        ):
            continue
        key = (row["mode"], row["file"], row["qual"])
        for site in [*lab.get("calls", []), *lab.get("refs", [])]:
            out.append((key, site[0], int(site[1]), bare(row["qual"]), full["callers"]))
    return out


def label_misses(
    row: dict[str, Any],
    lab: dict[str, Any],
    cover: dict[tuple[Key, str, int], bool],
    *,
    allow_open: bool,
) -> tuple[list[Any], list[Any]]:
    """(uncovered labelled calls, uncovered labelled refs). Unknown coverage = uncovered."""
    key = (row["mode"], row["file"], row["qual"])
    opened = open_set(row["full"]) if allow_open else set()

    def missed(sites: list[Any]) -> list[Any]:
        return [
            s
            for s in sites
            if tuple(s) not in opened and not cover.get((key, s[0], int(s[1])), False)
        ]

    return missed(lab.get("calls", [])), missed(lab.get("refs", []))


def enumerated(full: dict[str, Any]) -> bool:
    bound = full.get("open_sites")
    return (
        full.get("completeness") == "unknown"
        and isinstance(bound, dict)
        and bound.get("enumerated") is True
    )


def _inside_listed(
    callers: list[dict[str, Any]], file: str, func: str, line: int
) -> bool:
    """A GT2 site (file, enclosing function, line) is inside the listed caller of that name."""
    for c in callers:
        if c.get("file") != file or c.get("name") != func:
            continue
        start = c.get("line") or 0
        end = c.get("end_line") or start
        if start <= line <= end:
            return True
    return False


def gt2_open_residual(
    repo: str, row: dict[str, Any], gt2: dict[str, Any]
) -> list[dict[str, Any]]:
    opens = gt2.get("open_sites") or {}
    sites = opens.get(bare(row["qual"])) if isinstance(opens, dict) else None
    out = []
    for site in sites or ():
        file, func, line = site[0], site[1], int(site[2])
        if _inside_listed(row["full"]["callers"], file, func, line):
            continue
        out.append(
            {
                "repo": repo,
                "target": row["qual"],
                "target_file": row["file"],
                "mode": row["mode"],
                "file": file,
                "line": line,
                "class": "residual",
                "why": f"GT2 open site in `{func}` (a call GT2 could not resolve) is not inside a listed caller",
                "text": f"{func} (GT2 open site)",
            }
        )
    return out


def check_rows(
    repo: str,
    head: list[dict[str, Any]],
    unchanged: set[Key],
    *,
    gt2: dict[str, Any] | None,
    labels: dict[str, Any] | None,
    changed: set[Key] | None = None,
    label_cover: dict[tuple[Key, str, int], bool] | None = None,
) -> dict[str, Any]:
    """Failures (new/changed rows), pre-existing findings, residual items and counters."""
    failures: list[dict[str, Any]] = []
    preexisting: list[dict[str, Any]] = []
    residual: list[dict[str, Any]] = []
    stats = {
        "gt2_complete_checked": 0,
        "open_sites_checked": 0,
        "labels_checked": 0,
        "gt2_open_sites_checked": 0,
    }
    rows = gt2_rows(gt2) if gt2 is not None else {}
    defined = gt2_defined(gt2) if gt2 is not None else set()
    cover = label_cover or {}

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
        key = (row["mode"], row["file"], row["qual"])
        complete = full.get("completeness") == "complete"
        if gt2 is not None and complete:
            stats["gt2_complete_checked"] += 1
            if f"{row['file']}::{row['qual']}" not in defined:
                report(
                    row,
                    "gt2_untracked",
                    "target is not a GT2 definition; a complete cannot be checked",
                )
            elif miss := gt2_misses(row, rows, allow_open=False):
                report(row, "gt2_miss", miss[:10])
            if changed is not None and key in changed:
                stats["gt2_open_sites_checked"] += 1
                residual.extend(gt2_open_residual(repo, row, gt2))
        lab = label_for(row, labels) if labels is not None else None
        if lab is not None and complete:
            calls, _refs = label_misses(row, lab, cover, allow_open=False)
            stats["labels_checked"] += 1
            if calls:
                report(row, "label_call_miss", calls)
        if enumerated(full):
            stats["open_sites_checked"] += 1
            if gt2 is not None and (miss := gt2_misses(row, rows, allow_open=True)):
                report(row, "open_sites_gt2_miss", miss[:10])
            if lab is not None:
                calls, refs = label_misses(row, lab, cover, allow_open=True)
                stats["labels_checked"] += 1
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
    return {
        "failures": failures,
        "preexisting": preexisting,
        "residual": residual,
        "stats": stats,
    }


def compact_callers(answer: Any) -> tuple[int | None, set[tuple[str, str, int]]] | None:
    """(header count, caller set) of a compact answer, or None when it is not readable."""
    if not isinstance(answer, str):
        return None
    lines = answer.splitlines()
    if not lines:
        return None
    header = COMPACT_HEADER.match(lines[0].strip())
    found = set()
    for line in lines[1:]:
        m = COMPACT_CALLER.match(line.strip())
        if m:
            found.add((m.group("name"), m.group("file"), int(m.group("line"))))
    return (int(header.group("count")) if header else None), found


def check_compact(repo: str, head: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every head compact ``complete`` must be confirmed by the full answer, caller for caller."""
    failures = []
    for row in head:
        compact = row.get("compact") or {}
        if compact.get("completeness") != "complete":
            continue
        full = row["full"]

        def fail(kind: str, detail: Any, row: dict[str, Any] = row) -> None:
            failures.append(
                {
                    "repo": repo,
                    "mode": row["mode"],
                    "file": row["file"],
                    "qual": row["qual"],
                    "kind": kind,
                    "detail": detail,
                }
            )

        if full.get("completeness") != "complete":
            fail(
                "compact_unconfirmed_complete",
                f"compact says complete, full says {full.get('completeness')} {full.get('completeness_reasons')}",
            )
            continue
        parsed = compact_callers(compact.get("answer"))
        listed = {
            (c.get("name"), c.get("file"), c.get("line"))
            for c in full.get("callers") or []
        }
        if parsed is None:
            fail("compact_callers_mismatch", "compact answer is not readable")
            continue
        count, found = parsed
        if found != listed or (
            count is not None and count != len(full.get("callers") or [])
        ):
            fail(
                "compact_callers_mismatch",
                {
                    "missing_in_compact": sorted(listed - found, key=repr)[:10],
                    "extra_in_compact": sorted(found - listed, key=repr)[:10],
                    "header_count": count,
                    "full_count": len(full.get("callers") or []),
                },
            )
    return failures
