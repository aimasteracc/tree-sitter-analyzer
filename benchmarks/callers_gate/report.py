"""Judge a run (policy + oracles) and write ``report.md`` / ``report.json``.

Exit status: 0 = pass, nothing to review; 3 = no failure but residual items
need a human; 1 = failure (forbidden change, GT2 / label miss, oracle
failure); 2 = the gate could not run (fail closed: never a pass).
"""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from . import corpus
from .layout import LABEL_SOURCE, REPOS, Layout
from .oracle_truth import check_rows
from .policy import Policy
from .runner import RepoRun
from .transitions import RepoDiff, RowSetMismatch, diff_repo

ORACLE_GREP = Path(__file__).with_name("oracle_grep.py")
EXIT_PASS, EXIT_FAIL, EXIT_ERROR, EXIT_REVIEW = 0, 1, 2, 3


def bare_name(qual: str) -> str:
    return qual.strip('"').rsplit(".", 1)[-1].strip('"')


def grep_oracle(
    python: Path, root: Path, items: list[dict[str, Any]], work: Path
) -> list[dict[str, Any]]:
    if not items:
        return []
    work.mkdir(parents=True, exist_ok=True)
    req, resp = work / "grep-request.json", work / "grep-response.json"
    req.write_text(json.dumps({"root": str(root), "items": items}), encoding="utf-8")
    proc = subprocess.run(
        [str(python), "-s", "-P", str(ORACLE_GREP), str(req), str(resp)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"grep oracle failed: {proc.stderr.strip()[-2000:]}")
    data = json.loads(resp.read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) != len(items):
        raise RuntimeError("grep oracle returned a malformed response")
    return data


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
        "index_built": run.index_built,
        "baseline": run.baseline_source,
        "timings": {k: round(v, 1) for k, v in run.timings.items()},
    }
    if run.error:
        out["error"] = run.error
        return out
    try:
        diff: RepoDiff = diff_repo(run.repo, run.base_rows, run.head_rows)
    except RowSetMismatch as exc:
        out["error"] = str(exc)
        return out
    out["n"] = diff.n
    out["identical_rows"] = diff.identical
    out["transitions"] = dict(sorted(diff.transitions.items()))
    out["change_counts"] = {
        k: diff.count(k)
        for k in (
            "verdict",
            "reasons",
            "caller_count",
            "callers",
            "sites",
            "compact",
            "error",
            "other",
        )
    }
    out["reason_changes_same_verdict"] = [
        c.summary() for c in diff.reason_changes_same_verdict
    ]
    violations = []
    for change in diff.changes:
        why = policy.violations(change)
        if why:
            violations.append({**change.summary(), "violations": why})
    out["violations"] = violations
    out["changes"] = [c.summary() for c in diff.changes]

    unchanged = {(r["mode"], r["file"], r["qual"]) for r in run.head_rows} - {
        c.key for c in diff.changes
    }
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
    truth = check_rows(run.repo, run.head_rows, unchanged, gt2=gt2, labels=labels)
    out["truth_failures"] = truth["failures"]
    out["truth_preexisting"] = truth["preexisting"]
    out["truth_stats"] = truth["stats"]

    new_complete = [c for c in diff.changes if c.new_complete]
    out["new_complete"] = len(new_complete)
    residual: list[dict[str, Any]] = []
    grep_summary: list[dict[str, Any]] = []
    if not pin.is_python and new_complete:
        head_by = {(r["mode"], r["file"], r["qual"]): r for r in run.head_rows}
        items = [
            {
                "key": list(c.key),
                "name": bare_name(c.key[2]),
                "file": c.key[1],
                "qual": c.key[2],
                "callers": head_by[c.key]["full"]["callers"],
            }
            for c in new_complete
        ]
        assert run.root is not None
        for result in grep_oracle(python, run.root, items, work / run.repo):
            mode, file, qual = result["key"]
            grep_summary.append(
                {"mode": mode, "file": file, "qual": qual, "counts": result["counts"]}
            )
            for hit in result["hits"]:
                if hit["class"] == "residual":
                    residual.append(
                        {
                            "repo": run.repo,
                            "target": qual,
                            "target_file": file,
                            "mode": mode,
                            **hit,
                        }
                    )
    out["grep"] = grep_summary
    out["residual"] = residual
    return out


def exit_code(repos: list[dict[str, Any]]) -> int:
    if any("error" in r for r in repos):
        return EXIT_ERROR
    if any(r["violations"] or r["truth_failures"] for r in repos):
        return EXIT_FAIL
    if any(r["residual"] for r in repos):
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


def render(meta: dict[str, Any], repos: list[dict[str, Any]], code: int) -> str:
    verdict = {
        EXIT_PASS: "PASS",
        EXIT_FAIL: "FAIL",
        EXIT_ERROR: "ERROR (gate could not run; not a pass)",
        EXIT_REVIEW: "REVIEW (no failure; residual items need a human)",
    }[code]
    lines = [f"# Callers gate: {verdict}", ""]
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
        f"- **{repo}** `{v['qual']}` ({v['mode']}, {v['file']}): {', '.join(v['violations'])} [{v['transition']}]"
        for repo, v in failures
    ]
    lines += [
        f"- **{f['repo']}** `{f['qual']}` ({f['mode']}): {f['kind']} {json.dumps(f['detail'])[:300]}"
        for f in truth
    ]
    if not (failures or truth or errors):
        lines.append("None.")
    lines += [
        "",
        "## Transitions",
        "",
        "| repo | n | identical | transitions | reasons (same verdict) | caller-count | callers | sites | other | new complete | residual | baseline | index | base s | head s |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in repos:
        if "error" in r:
            lines.append(f"| {r['repo']} | error | | | | | | | | | | | | | |")
            continue
        trans = (
            ", ".join(
                f"{k} {v}"
                for k, v in r["transitions"].items()
                if k.split("->")[0] != k.split("->")[1]
            )
            or "none changed"
        )
        cc = r["change_counts"]
        t = r["timings"]
        lines.append(
            f"| {r['repo']} | {r['n']} | {r['identical_rows']} | {trans} | {len(r['reason_changes_same_verdict'])} | {cc['caller_count']} | {cc['callers']} | {cc['sites']} | {cc['other']} | {r['new_complete']} | {len(r['residual'])} | {r['baseline']} | {'built' if r['index_built'] else 'reused'} | {t.get('base', 0)} | {t.get('head', 0)} |"
        )
    lines += ["", "## Reason changes on an unchanged verdict", ""]
    rc = [x for r in repos for x in r.get("reason_changes_same_verdict", [])]
    lines += [
        f"- {x['repo']} `{x['qual']}` ({x['mode']}) {x['head']['completeness']}: {x['base']['reasons']} -> {x['head']['reasons']}"
        for x in rc
    ] or ["None."]
    lines += ["", "## New completes and their grep classification", ""]
    for r in repos:
        for g in r.get("grep", []):
            counts = ", ".join(f"{k} {v}" for k, v in g["counts"].items() if v)
            lines.append(
                f"- {r['repo']} `{g['qual']}` ({g['mode']}): {counts or 'no occurrences'}"
            )
        if r.get("new_complete") and REPOS[r["repo"]].is_python:
            lines.append(
                f"- {r['repo']}: {r['new_complete']} new complete(s) checked against GT2 ({len([f for f in r['truth_failures'] if f['kind'].startswith('gt2')])} misses)"
            )
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
    code = exit_code(repos)
    residual = _dedupe_residual([x for r in repos for x in r.get("residual", [])])
    payload = {"exit_code": code, "residual": residual, "meta": meta, "repos": repos}
    (run_dir / "report.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    (run_dir / "report.md").write_text(render(meta, repos, code), encoding="utf-8")
    return code
