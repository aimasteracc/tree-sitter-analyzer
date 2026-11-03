"""CLI: ``py -3 -m benchmarks.callers_gate {setup,run,promote,precheck,report,import-legacy}``."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from . import answers, corpus, index_store, keys, sides
from .layout import DEFAULT_PYTHON, REPOS, Layout

#: Servers per side (measured cost: zod ~3.4 s/target, pydantic/fastapi ~0.5 s/target).
#: 14 servers in total for all 7 repos, one per core of the reference machine.
DEFAULT_SHARDS = {"zod": 5, "pydantic": 2, "fastapi": 2, "hono": 2}

HERE_REPO = Path(__file__).resolve().parents[2]


def _log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def _python(layout: Layout, override: str | None) -> Path:
    if override:
        return Path(override)
    return Path(corpus.load_config(layout)["python"])


def _resolve(layout: Layout, value: str, label: str, git_dir: Path) -> sides.Side:
    path = Path(value)
    if path.is_dir():
        return sides.resolve_worktree(path.resolve(), label)
    return sides.resolve_ref(layout, git_dir, value, label)


def cmd_setup(args: argparse.Namespace) -> int:
    layout = Layout.from_env(args.root)
    corpus.setup(layout, Path(args.python or DEFAULT_PYTHON), _log)
    return 0


def _shards(spec: list[str] | None) -> dict[str, int]:
    out = dict(DEFAULT_SHARDS)
    for item in spec or ():
        name, _, value = item.partition("=")
        if name not in REPOS or not value.isdigit() or int(value) < 1:
            raise SystemExit(f"--shards wants repo=N, got {item!r}")
        out[name] = int(value)
    return out


def cmd_run(args: argparse.Namespace) -> int:
    from . import report, runner
    from .policy import Policy, PolicyError

    started = time.perf_counter()
    layout = Layout.from_env(args.root)
    try:
        python = _python(layout, args.python)
        manifest = corpus.verify_corpus(layout)
        policy = Policy.load(
            Path(args.policy) if args.policy else None,
            args.allow_transition,
            caller_changes=args.allow_caller_changes,
            site_changes=args.allow_site_changes,
        )
        git_dir = (
            Path(args.git_dir).resolve()
            if args.git_dir
            else (Path(args.head).resolve() if Path(args.head).is_dir() else HERE_REPO)
        )
        head = _resolve(layout, args.head, "head", git_dir)
        base = _resolve(layout, args.base, "base", git_dir)
        env_key, version, dists = sides.environment(python)
    except (corpus.CorpusError, sides.SideError, PolicyError, OSError) as exc:
        _log(f"ERROR {exc}")
        return report.EXIT_ERROR
    repos = args.repos or list(REPOS)
    unknown = [r for r in repos if r not in REPOS]
    if unknown:
        _log(f"ERROR unknown repos {unknown}")
        return report.EXIT_ERROR
    jobs = args.jobs or runner.default_jobs()
    run_dir = layout.runs / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    resolve_s = time.perf_counter() - started
    _log(
        f"base {base.ref} tree {base.tree[:12]} | head {head.ref} tree {head.tree[:12]} | jobs {jobs} | run {run_dir}"
    )
    if base.tree == head.tree:
        _log("note: base and head have the same package tree; expecting 0 changes")
    ctx = runner.RunContext(
        layout,
        python,
        base,
        head,
        git_dir,
        env_key,
        manifest,
        run_dir,
        _shards(args.shards),
        _log,
    )
    runs = runner.run_all(ctx, repos, jobs)
    query_s = time.perf_counter() - started - resolve_s
    for run in runs:
        if run.index_key and args.keep_indexes > 0:
            index_store.prune_indexes(
                layout, REPOS[run.repo], args.keep_indexes, {run.index_key}, _log
            )
    judged = []
    for run in runs:
        try:
            judged.append(
                report.judge_repo(
                    layout, python, run, policy, manifest, run_dir / "oracle"
                )
            )
        except (corpus.CorpusError, RuntimeError, OSError, KeyError, ValueError) as exc:
            judged.append(
                {
                    "repo": run.repo,
                    "error": f"oracle: {type(exc).__name__}: {exc}",
                    "timings": run.timings,
                }
            )
    oracle_s = time.perf_counter() - started - resolve_s - query_s
    meta: dict[str, Any] = {
        "base": {"ref": base.ref, "commit": base.commit, "tree": base.tree},
        "head": {"ref": head.ref, "commit": head.commit, "tree": head.tree},
        "python": str(python),
        "python_version": version,
        "env_key": env_key,
        "jobs": jobs,
        "policy": policy.__dict__ | {"allow_items": list(policy.allow_items)},
        "query_only": list(keys.QUERY_ONLY),
        "seconds": {
            "resolve": round(resolve_s, 1),
            "repos": round(query_s, 1),
            "oracle": round(oracle_s, 1),
            "total": round(time.perf_counter() - started, 1),
        },
        "distributions": len(dists),
    }
    code = report.write_report(run_dir, meta, judged)
    _log(f"report {run_dir / 'report.md'}")
    _print_summary(judged, code, meta)
    return code


def _print_summary(
    judged: list[dict[str, Any]], code: int, meta: dict[str, Any]
) -> None:
    for r in judged:
        if "error" in r:
            print(f"  {r['repo']:9} ERROR {r['error']}")
            continue
        changed = {
            k: v
            for k, v in r["transitions"].items()
            if k.split("->")[0] != k.split("->")[1]
        }
        print(
            f"  {r['repo']:9} n={r['n']:4} identical={r['identical_rows']:4} changed-verdicts={changed or '-'} "
            f"reason-only={len(r['reason_changes_same_verdict'])} violations={len(r['violations'])} "
            f"truth-fail={len(r['truth_failures'])} residual={len(r['residual'])} t={r['timings']}"
        )
    print(f"  seconds {meta['seconds']}  exit {code}")


def cmd_promote(args: argparse.Namespace) -> int:
    layout = Layout.from_env(args.root)
    git_dir = Path(args.git_dir).resolve() if args.git_dir else HERE_REPO
    side = _resolve(layout, args.ref, "promote", git_dir)
    copied = answers.promote(layout, side.tree, _log)
    if not copied:
        _log(
            f"ERROR no validated results for tree {side.tree} ({args.ref}); the merged tree was never tested as a head"
        )
        return 2
    have = {p.stem for p in copied}
    missing = sorted(set(REPOS) - have)
    for path in copied:
        _log(f"promoted {path}")
    if missing:
        _log(
            f"warning: no results for {missing} at this tree; their base answers will be recomputed"
        )
    return 0


def cmd_import_legacy(args: argparse.Namespace) -> int:
    """Seed baseline/ from a PR-1/2/4 manual-gate JSON (``develop`` / ``branch`` rows)."""
    layout = Layout.from_env(args.root)
    python = _python(layout, args.python)
    manifest = corpus.verify_corpus(layout)
    git_dir = Path(args.git_dir).resolve() if args.git_dir else HERE_REPO
    side = _resolve(layout, args.ref, "seed", git_dir)
    env_key, _v, _d = sides.environment(python)
    data = json.loads(Path(args.json).read_text(encoding="utf-8"))
    repo = data["repo"]
    pin = REPOS[repo]
    targets, targets_sha = corpus.load_targets(layout, repo, manifest)
    rows = data[args.side]
    want = [(t["mode"], t["file"], t["qual"], t["name"]) for t in targets]
    have = [(r["mode"], r["file"], r["qual"], r["name"]) for r in rows]
    if want != have:
        _log(f"ERROR {args.json}: rows do not match the corpus targets of {repo}")
        return 2
    key = keys.index_key(
        repo=repo,
        repo_sha=pin.sha,
        package_blobs=side.blobs,
        pyproject_blob=side.pyproject_blob,
        env_fingerprint=env_key,
    )
    akey = answers.AnswerKey(
        side.tree, key, repo, pin.sha, keys.query_key(targets_sha256=targets_sha)
    )
    path = layout.baseline(side.tree, key, repo)
    answers.write_answers(
        path, akey, rows, f"imported:{Path(args.json).name}:{args.side}"
    )
    _log(f"seeded {path} ({len(rows)} rows)")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from . import report

    layout = Layout.from_env(args.root)
    run_dir = (
        Path(args.run) if args.run else max(layout.runs.iterdir(), key=lambda p: p.name)
    )
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    if args.rejudge:
        return _rejudge(layout, args, run_dir, payload)
    text = report.render(payload["meta"], payload["repos"], payload["exit_code"])
    (run_dir / "report.md").write_text(text, encoding="utf-8")
    print(text)
    return int(payload["exit_code"])


def _rejudge(
    layout: Layout, args: argparse.Namespace, run_dir: Path, payload: dict[str, Any]
) -> int:
    """Judge a finished run again from its cached answer files (new policy / oracle)."""
    from . import report, runner
    from .policy import Policy

    python = _python(layout, args.python)
    manifest = corpus.verify_corpus(layout)
    policy = Policy.load(
        Path(args.policy) if args.policy else None,
        args.allow_transition,
        caller_changes=args.allow_caller_changes,
        site_changes=args.allow_site_changes,
    )
    meta = payload["meta"]
    judged = []
    for old in payload["repos"]:
        name, key = old["repo"], old.get("index_key", "")
        pin = REPOS[name]
        _targets, sha = corpus.load_targets(layout, name, manifest)
        qkey = keys.query_key(targets_sha256=sha)
        rows = {}
        for side, path in (
            ("base", layout.baseline(meta["base"]["tree"], key, name)),
            ("head", layout.result(meta["head"]["tree"], key, name)),
        ):
            rows[side] = answers.read_answers(
                path,
                answers.AnswerKey(meta[side]["tree"], key, name, pin.sha, qkey),
                _log,
            )
        if rows["base"] is None or rows["head"] is None:
            judged.append(
                {
                    "repo": name,
                    "error": "cached answers missing or invalid; run again",
                    "timings": {},
                }
            )
            continue
        run = runner.RepoRun(
            name,
            index_key=key,
            base_rows=rows["base"],
            head_rows=rows["head"],
            root=layout.index_dir(name, key) / "tree",
            baseline_source="cache",
            timings=old.get("timings", {}),
        )
        judged.append(
            report.judge_repo(
                layout, python, run, policy, manifest, run_dir / "oracle-rejudge"
            )
        )
    meta = {
        **meta,
        "policy": policy.__dict__ | {"allow_items": list(policy.allow_items)},
        "rejudged": True,
    }
    code = report.write_report(run_dir, meta, judged)
    _print_summary(judged, code, meta)
    return code


def cmd_precheck(args: argparse.Namespace) -> int:
    from . import precheck

    layout = Layout.from_env(args.root)
    python = _python(layout, args.python)
    return precheck.run(
        Path(args.head).resolve(),
        python,
        base=args.base,
        target=args.patch_target,
        extra_tests=args.tests or [],
        log=_log,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m benchmarks.callers_gate", description=__doc__
    )
    p.add_argument(
        "--root", help="gate root (default TSA_GATE_ROOT or C:\\git-private\\tsa-gate)"
    )
    p.add_argument("--python", help="gate interpreter (default: from setup)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("setup", help="clone pinned repos, copy corpus + ground truth")
    s.set_defaults(func=cmd_setup)

    r = sub.add_parser("run", help="replay the corpus base vs head and judge the diff")
    r.add_argument(
        "--base", required=True, help="git ref (e.g. origin/develop) or worktree path"
    )
    r.add_argument(
        "--head", required=True, help="worktree path (dirty edits count) or git ref"
    )
    r.add_argument("--repos", nargs="+", choices=sorted(REPOS))
    r.add_argument(
        "--jobs", type=int, help="concurrent repos (default from CPUs and free memory)"
    )
    r.add_argument(
        "--shards",
        nargs="+",
        metavar="REPO=N",
        help="servers per side for a repo (default zod=5 pydantic=2 fastapi=2 hono=2)",
    )
    r.add_argument("--policy", help="policy JSON (see policy.py)")
    r.add_argument(
        "--allow-transition",
        action="append",
        metavar="A->B",
        help="extra allowed verdict transition",
    )
    r.add_argument("--allow-caller-changes", action="store_true")
    r.add_argument("--allow-site-changes", action="store_true")
    r.add_argument(
        "--git-dir",
        help="TSA checkout that resolves the refs (default: the head worktree)",
    )
    r.add_argument(
        "--keep-indexes",
        type=int,
        default=2,
        help="older index keys kept per repo besides the current one (default 2)",
    )
    r.set_defaults(func=cmd_run)

    pr = sub.add_parser(
        "promote", help="after a merge: results of the merged tree become the baseline"
    )
    pr.add_argument("--ref", default="origin/develop")
    pr.add_argument("--git-dir")
    pr.set_defaults(func=cmd_promote)

    pc = sub.add_parser(
        "precheck", help="ruff, format, mypy, related tests, patch coverage"
    )
    pc.add_argument("--head", default=".")
    pc.add_argument("--base", default="origin/develop")
    pc.add_argument(
        "--patch-target",
        type=float,
        help="patch coverage target %% (default: Codecov base coverage)",
    )
    pc.add_argument("--tests", nargs="+", help="extra test paths")
    pc.set_defaults(func=cmd_precheck)

    rp = sub.add_parser("report", help="re-render report.md of a run (default: latest)")
    rp.add_argument("--run")
    rp.add_argument(
        "--rejudge",
        action="store_true",
        help="re-run policy + oracles on the cached answers",
    )
    rp.add_argument("--policy")
    rp.add_argument("--allow-transition", action="append", metavar="A->B")
    rp.add_argument("--allow-caller-changes", action="store_true")
    rp.add_argument("--allow-site-changes", action="store_true")
    rp.set_defaults(func=cmd_report)

    il = sub.add_parser("import-legacy", help="seed baseline/ from a manual-gate JSON")
    il.add_argument("--json", required=True)
    il.add_argument("--side", required=True, choices=["develop", "branch"])
    il.add_argument(
        "--ref", required=True, help="the commit whose package tree produced those rows"
    )
    il.add_argument("--git-dir")
    il.set_defaults(func=cmd_import_legacy)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
