"""Judge a run (policy + oracles) and write ``report.md`` / ``report.json``.

Exit status: 0 = pass, nothing to review; 3 = no failure but residual items
need a human (or the run was PARTIAL); 1 = failure (forbidden change, GT2 /
label / compact miss, oracle failure); 2 = the gate could not run (fail
closed: never a pass).

Comparisons per repo: ``same_index`` (base code vs head code, both on the
head-built index) always; ``own_index`` (base code on the base's own index vs
head code on the head index) when the index keys differ, i.e. the PR changes
code the index build uses. The policy is applied to both. "Pre-existing" is
judged against ``own_index`` when it exists; every head ``complete`` that
differs from either base answer set goes through the oracles.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from . import corpus
from .layout import LABEL_SOURCE, REPOS, Layout
from .oracle_truth import check_compact, check_rows, label_sites
from .policy import Policy
from .runner import RepoRun, budget_limited, check_missing
from .transitions import KINDS, RepoDiff, RowSetMismatch, diff_repo, row_key

#: The package root that holds ``benchmarks/`` (the oracle runs as a module from it).
GATE_CODE_ROOT = Path(__file__).resolve().parents[2]
ORACLE_MODULE = "benchmarks.callers_gate.oracle_grep"
EXIT_PASS, EXIT_FAIL, EXIT_ERROR, EXIT_REVIEW = 0, 1, 2, 3
COMPARISON_LABELS = {
    "same_index": "base code on the head index (query-path change)",
    "own_index": "base code on its own index (indexer change)",
}
BUDGET_NOTE = (
    "still a violation: a wall-clock budget limited this answer on one side even "
    "after the retries, so load may explain it; re-run on a quiet machine to "
    "confirm, and treat it as a real regression until a re-run clears it"
)

Key = tuple[str, str, str]


def bare_name(qual: str) -> str:
    return qual.strip('"').rsplit(".", 1)[-1].strip('"')


def _oracle(
    python: Path, request: dict[str, Any], expect: int, work: Path, name: str
) -> list[Any]:
    work.mkdir(parents=True, exist_ok=True)
    req, resp = work / f"{name}-request.json", work / f"{name}-response.json"
    req.write_text(json.dumps(request), encoding="utf-8")
    proc = subprocess.run(
        [str(python), "-s", "-P", "-m", ORACLE_MODULE, str(req), str(resp)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(GATE_CODE_ROOT)},
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{name} oracle failed: {proc.stderr.strip()[-2000:]}")
    data = json.loads(resp.read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) != expect:
        raise RuntimeError(f"{name} oracle returned a malformed response")
    return data


def grep_oracle(
    python: Path, root: Path, items: list[dict[str, Any]], work: Path
) -> list[dict[str, Any]]:
    if not items:
        return []
    return _oracle(
        python, {"root": str(root), "items": items}, len(items), work, "grep"
    )


def label_cover(
    python: Path,
    root: Path,
    rows: list[dict[str, Any]],
    labels: dict[str, Any],
    work: Path,
) -> dict[tuple[Key, str, int], bool]:
    """Whether each labelled site is inside a listed caller (innermost definition)."""
    sites = label_sites(rows, labels)
    if not sites:
        return {}
    request = {
        "mode": "cover",
        "root": str(root),
        "sites": [
            {"file": f, "line": ln, "name": n, "callers": callers}
            for _key, f, ln, n, callers in sites
        ],
    }
    verdicts = _oracle(python, request, len(sites), work, "cover")
    return {
        (key, f, ln): bool(v)
        for (key, f, ln, _n, _c), v in zip(sites, verdicts, strict=True)
    }


def oracle_keys(diffs: list[RepoDiff]) -> list[Key]:
    """Every head ``complete`` that differs from any base answer set (corpus order kept)."""
    seen: dict[Key, None] = {}
    for diff in diffs:
        for change in diff.changes:
            if change.head.get("completeness") == "complete":
                seen.setdefault(change.key, None)
    return list(seen)


def _comparison(diff: RepoDiff, label: str) -> dict[str, Any]:
    return {
        "label": label,
        "n": diff.n,
        "identical_rows": diff.identical,
        "transitions": dict(sorted(diff.transitions.items())),
        "change_counts": {k: diff.count(k) for k in KINDS},
        "reason_changes_same_verdict": [
            c.summary() for c in diff.reason_changes_same_verdict
        ],
        "changes": [c.summary() for c in diff.changes],
    }


def _violations(
    diffs: dict[str, RepoDiff], policy: Policy, limited: set[Key]
) -> list[dict[str, Any]]:
    out = []
    for name, diff in diffs.items():
        for change in diff.changes:
            why = policy.violations(change)
            if not why:
                continue
            if change.key in limited:
                why = [*why, BUDGET_NOTE]
            out.append(
                {
                    **change.summary(),
                    "comparison": name,
                    "violations": why,
                    "delta": change.delta(),
                }
            )
    return out


def judge_repo(
    layout: Layout,
    python: Path,
    run: RepoRun,
    policy: Policy,
    manifest: dict[str, str],
    work: Path,
) -> dict[str, Any]:
    pin = REPOS[run.repo]
    out: dict[str, Any] = {
        "repo": run.repo,
        "index_key": run.index_key,
        "base_index_key": run.base_index_key or run.index_key,
        "index_built": run.index_built,
        "baseline": run.baseline_source,
        "cross_baseline": run.cross_source,
        "timings": {k: round(v, 1) for k, v in run.timings.items()},
    }
    if run.error:
        out["error"] = run.error
        return out
    diffs: dict[str, RepoDiff] = {}
    try:
        diffs["same_index"] = diff_repo(run.repo, run.base_rows, run.head_rows)
        if run.cross_rows:
            diffs["own_index"] = diff_repo(run.repo, run.cross_rows, run.head_rows)
    except RowSetMismatch as exc:
        out["error"] = str(exc)
        return out
    reference = diffs.get("own_index") or diffs["same_index"]
    out["comparisons"] = {
        name: _comparison(diff, COMPARISON_LABELS[name]) for name, diff in diffs.items()
    }
    ref = out["comparisons"]["own_index" if "own_index" in diffs else "same_index"]
    for field in ("n", "identical_rows", "transitions", "change_counts"):
        out[field] = ref[field]
    out["reason_changes_same_verdict"] = ref["reason_changes_same_verdict"]
    out["changes"] = ref["changes"]
    limited = {
        c.key
        for diff in diffs.values()
        for c in diff.changes
        if check_missing({"full": c.base}) != check_missing({"full": c.head})
    } | {
        row_key(r)
        for r in run.base_rows + run.head_rows + run.cross_rows
        if budget_limited(r)
    }
    out["violations"] = _violations(diffs, policy, limited)
    out["budget_retries"] = run.retried

    changed_any = {c.key for diff in diffs.values() for c in diff.changes}
    unchanged = {row_key(r) for r in run.head_rows} - {c.key for c in reference.changes}
    gt2 = (
        corpus.load_json_truth(layout.gt2(run.repo), manifest, layout)
        if pin.is_python
        else None
    )
    labels = (
        corpus.load_json_truth(layout.labels(run.repo), manifest, layout)
        if run.repo in LABEL_SOURCE
        else None
    )
    cover = {}
    if labels is not None:
        assert run.root is not None
        cover = label_cover(python, run.root, run.head_rows, labels, work / run.repo)
    truth = check_rows(
        run.repo,
        run.head_rows,
        unchanged,
        gt2=gt2,
        labels=labels,
        changed=changed_any,
        label_cover=cover,
    )
    out["truth_failures"] = truth["failures"] + check_compact(run.repo, run.head_rows)
    out["truth_preexisting"] = truth["preexisting"]
    out["truth_stats"] = truth["stats"]

    keys = oracle_keys(list(diffs.values()))
    out["new_complete"] = sum(1 for c in reference.changes if c.new_complete)
    out["changed_complete"] = len(keys)
    residual: list[dict[str, Any]] = list(truth["residual"])
    grep_summary: list[dict[str, Any]] = []
    if not pin.is_python and keys:
        assert run.root is not None
        head_by = {row_key(r): r for r in run.head_rows}
        items = [
            {
                "key": list(k),
                "name": bare_name(k[2]),
                "file": k[1],
                "qual": k[2],
                "callers": head_by[k]["full"]["callers"],
            }
            for k in keys
        ]
        for result in grep_oracle(python, run.root, items, work / run.repo):
            mode, file, qual = result["key"]
            grep_summary.append(
                {"mode": mode, "file": file, "qual": qual, "counts": result["counts"]}
            )
            residual.extend(
                {
                    "repo": run.repo,
                    "target": qual,
                    "target_file": file,
                    "mode": mode,
                    **hit,
                }
                for hit in result["hits"]
                if hit["class"] == "residual"
            )
    out["grep"] = grep_summary
    out["residual"] = residual
    return out


def exit_code(
    repos: list[dict[str, Any]], *, partial: bool = False, allow_partial: bool = False
) -> int:
    if any("error" in r for r in repos):
        return EXIT_ERROR
    if any(r["violations"] or r["truth_failures"] for r in repos):
        return EXIT_FAIL
    if any(r["residual"] for r in repos) or (partial and not allow_partial):
        return EXIT_REVIEW
    return EXIT_PASS


def _dedupe_residual(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen, out = set(), []
    for item in items:
        key = (
            item["repo"],
            item["target_file"],
            item["target"],
            item["file"],
            item["line"],
        )
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _verdict(code: int, meta: dict[str, Any]) -> str:
    text = {
        EXIT_PASS: "PASS",
        EXIT_FAIL: "FAIL",
        EXIT_ERROR: "ERROR (gate could not run; not a pass)",
        EXIT_REVIEW: "REVIEW (no failure; residual items need a human)",
    }[code]
    if meta.get("partial"):
        skipped = ", ".join(meta.get("skipped_repos") or [])
        text += f" -- PARTIAL run (not run: {skipped})"
    return text


def _transition_rows(r: dict[str, Any], comparison: dict[str, Any]) -> str:
    trans = (
        ", ".join(
            f"{k} {v}"
            for k, v in comparison["transitions"].items()
            if k.split("->")[0] != k.split("->")[1]
        )
        or "none changed"
    )
    cc = comparison["change_counts"]
    t = r["timings"]
    return (
        f"| {r['repo']} | {comparison['n']} | {comparison['identical_rows']} | {trans} | "
        f"{len(comparison['reason_changes_same_verdict'])} | {cc['caller_count']} | {cc['callers']} | "
        f"{cc['sites']} | {cc['other']} | {r['new_complete']} | {r.get('changed_complete', r['new_complete'])} | "
        f"{len(r['residual'])} | {r['baseline']} | {'built' if r['index_built'] else 'reused'} | "
        f"{t.get('base', 0)} | {t.get('head', 0)} |"
    )


TABLE_HEAD = [
    "| repo | n | identical | transitions | reasons (same verdict) | caller-count | callers | sites | other | new complete | changed complete | residual | baseline | index | base s | head s |",
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
]


def _transitions(repos: list[dict[str, Any]]) -> list[str]:
    names = sorted(
        {name for r in repos for name in (r.get("comparisons") or {"same_index": 0})},
        key=list(COMPARISON_LABELS).index,
    )
    lines: list[str] = ["", "## Transitions", ""]
    if "own_index" in names:
        lines += [
            "The index keys differ on at least one repo (the PR changes code the index "
            "build uses), so each such repo is compared twice. Pre-existing findings "
            "are judged against the base code on its own index.",
            "",
        ]
    for name in names:
        if len(names) > 1:
            lines += [f"### {COMPARISON_LABELS[name]}", ""]
        lines += TABLE_HEAD
        for r in repos:
            if "error" in r:
                lines.append(f"| {r['repo']} | error |" + " |" * 14)
                continue
            comparisons = r.get("comparisons") or {"same_index": r}
            if name in comparisons:
                lines.append(_transition_rows(r, comparisons[name]))
            elif name == "own_index":
                lines.append(f"| {r['repo']} | same index key: see above |" + " |" * 14)
        lines.append("")
    return lines


def _evidence(repos: list[dict[str, Any]]) -> list[str]:
    """One line per changed row: transition, kinds, the head's finding and next_step."""
    out = []
    for r in repos:
        for name, comparison in (r.get("comparisons") or {}).items():
            for x in comparison.get("changes", []):
                head = x["head"]
                step = " ".join(str(head.get("next_step") or "-").split())[:300]
                out.append(
                    f"- {r['repo']} `{x['qual']}` ({x['mode']}, {x['file']}; {name}) "
                    f"[{x['transition']}] kinds={','.join(x['kinds'])} | finding: "
                    f"{head['completeness']} {head.get('reasons')} callers={head.get('caller_count')} "
                    f"delta={json.dumps(x.get('delta') or {}, default=str)[:300]} | next_step: {step}"
                )
    return out


def render(meta: dict[str, Any], repos: list[dict[str, Any]], code: int) -> str:
    lines = [f"# Callers gate: {_verdict(code, meta)}", ""]
    residual = _dedupe_residual([x for r in repos for x in r.get("residual", [])])
    lines += [f"## Residual items for human review ({len(residual)})", ""]
    if residual:
        lines += ["| repo | target | hit | why | text |", "|---|---|---|---|---|"]
        lines += [
            f"| {x['repo']} | `{x['target']}` | {x['file']}:{x['line']} | {x['why']} | `{x['text'].replace('|', '/')[:100]}` |"
            for x in residual
        ]
    else:
        lines.append("None.")
    failures = [(r["repo"], v) for r in repos for v in r.get("violations", [])]
    truth = [f for r in repos for f in r.get("truth_failures", [])]
    errors = [(r["repo"], r["error"]) for r in repos if "error" in r]
    lines += ["", f"## Failures ({len(failures) + len(truth) + len(errors)})", ""]
    lines += [f"- **{repo}** error: {err}" for repo, err in errors]
    lines += [
        f"- **{repo}** `{v['qual']}` ({v['mode']}, {v['file']}; {COMPARISON_LABELS[v.get('comparison', 'same_index')]}): "
        f"{', '.join(v['violations'])} [{v['transition']}] {json.dumps(v.get('delta') or {})[:400]}"
        for repo, v in failures
    ]
    lines += [
        f"- **{f['repo']}** `{f['qual']}` ({f['mode']}): {f['kind']} {json.dumps(f['detail'])[:300]}"
        for f in truth
    ]
    if not (failures or truth or errors):
        lines.append("None.")
    lines += _transitions(repos)
    lines += ["## Reason changes on an unchanged verdict", ""]
    rc = [x for r in repos for x in r.get("reason_changes_same_verdict", [])]
    lines += [
        f"- {x['repo']} `{x['qual']}` ({x['mode']}) {x['head']['completeness']}: {x['base']['reasons']} -> {x['head']['reasons']}"
        for x in rc
    ] or ["None."]
    lines += ["", "## Evidence for every changed row (head answer)", ""]
    lines += _evidence(repos) or ["None."]
    lines += ["", "## Changed completes and their grep classification", ""]
    for r in repos:
        for g in r.get("grep", []):
            counts = ", ".join(f"{k} {v}" for k, v in g["counts"].items() if v)
            lines.append(
                f"- {r['repo']} `{g['qual']}` ({g['mode']}): {counts or 'no occurrences'}"
            )
        if r.get("changed_complete") and REPOS[r["repo"]].is_python:
            lines.append(
                f"- {r['repo']}: {r['changed_complete']} changed complete(s) checked against GT2 "
                f"({len([f for f in r['truth_failures'] if f['kind'].startswith('gt2')])} misses)"
            )
    retried = [x for r in repos for x in r.get("budget_retries", [])]
    lines += ["", f"## Budget-limited answers re-asked ({len(retried)})", ""]
    lines += [
        f"- {x['qual']} ({x['mode']}, {x['side']} attempt {x['attempt']}): {x['before']} -> {x['after']} {'conclusive' if x['conclusive'] else 'STILL LIMITED'}"
        for x in retried
    ] or ["None."]
    pre = [f for r in repos for f in r.get("truth_preexisting", [])]
    lines += [
        "",
        f"## Pre-existing ground-truth findings on unchanged rows ({len(pre)}, not blamed on this change)",
        "",
    ]
    kinds = Counter(f"{f['repo']}:{f['kind']}" for f in pre)
    lines += [f"- {k}: {v}" for k, v in sorted(kinds.items())] or ["None."]
    lines += ["", "## Run", "", "```json", json.dumps(meta, indent=1), "```", ""]
    return "\n".join(lines)


def write_report(
    run_dir: Path, meta: dict[str, Any], repos: list[dict[str, Any]]
) -> int:
    code = exit_code(
        repos,
        partial=bool(meta.get("partial")),
        allow_partial=bool(meta.get("allow_partial")),
    )
    residual = _dedupe_residual([x for r in repos for x in r.get("residual", [])])
    payload = {"exit_code": code, "residual": residual, "meta": meta, "repos": repos}
    (run_dir / "report.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    (run_dir / "report.md").write_text(render(meta, repos, code), encoding="utf-8")
    return code
