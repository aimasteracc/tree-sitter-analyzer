"""Top-level CLI for the CodeGraph comparison benchmark harness.

Usage
-----
  python benchmarks/codegraph_compare/run.py --help

Subcommands
-----------
  prepare --repo <id>                 Prepare one repo by ID
  prepare --all                       Prepare all repos listed in repos.yaml
  run --repo <id> --question <id>     Run one (repo, question, arm, repeat) trial
       --arm <arm-id> --repeat <n>
  run-matrix --repos all              Run all combinations
             --arms native-only,tsa-warm
             --repeats 4
             [--dry-run]
  status                              Show prepared repos + last run stats

Config files are resolved relative to this file:
  repos.yaml        — repository registry
  arms.yaml         — arm definitions
  questions.yaml    — question registry
  results/          — output directory
  results/prepared_repos.json  — manifest written by prepare
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

# ---------------------------------------------------------------------------
# Path constants  (all relative to this file so the harness is portable)
# ---------------------------------------------------------------------------

BENCHMARKS_DIR = Path(__file__).parent
REPOS_YAML = BENCHMARKS_DIR / "repos.yaml"
ARMS_YAML = BENCHMARKS_DIR / "arms.yaml"
QUESTIONS_YAML = BENCHMARKS_DIR / "questions.yaml"
RESULTS_DIR = BENCHMARKS_DIR / "results"
PREPARED_MANIFEST = RESULTS_DIR / "prepared_repos.json"


# ---------------------------------------------------------------------------
# YAML helpers  (lazy import keeps --help snappy without pydantic/PyYAML)
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict | list:
    """Load a YAML file and return the parsed content.

    Raises SystemExit with a clear message on missing or malformed files so
    all YAML-reading code paths share a single error surface.
    """
    if not path.exists():
        if path == QUESTIONS_YAML:
            _die(
                "questions.yaml not found. Run question setup first.\n"
                f"Expected location: {path}"
            )
        _die(f"Config file not found: {path}")

    try:
        import yaml  # noqa: PLC0415 — lazy import intentional
    except ImportError:
        _die(
            "PyYAML is not installed. Run:  pip install pyyaml\n"
            "Or with uv:                    uv pip install pyyaml"
        )

    try:
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception as exc:  # noqa: BLE001
        _die(f"Failed to parse {path}: {exc}")


def _die(message: str, code: int = 1) -> NoReturn:
    """Print *message* to stderr and exit with *code*."""
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------------------
# Data accessors
# ---------------------------------------------------------------------------


def _get_repo(repos: dict | list, repo_id: str) -> dict:
    """Return the repo entry matching *repo_id* from the loaded repos config."""
    items: list[dict] = repos if isinstance(repos, list) else repos.get("repos", [])
    for item in items:
        if item.get("id") == repo_id:
            return item
    known = [r.get("id", "?") for r in items]
    _die(f"Repo '{repo_id}' not found in repos.yaml. Known: {', '.join(known)}")


def _get_arm(arms: dict | list, arm_id: str) -> dict:
    """Return the arm entry matching *arm_id* from the loaded arms config."""
    items: list[dict] = arms if isinstance(arms, list) else arms.get("arms", [])
    for item in items:
        if item.get("id") == arm_id:
            return item
    known = [a.get("id", "?") for a in items]
    _die(f"Arm '{arm_id}' not found in arms.yaml. Known: {', '.join(known)}")


def _get_question(questions: dict | list, question_id: str) -> dict:
    """Return the question entry matching *question_id* from loaded questions config."""
    items: list[dict] = (
        questions if isinstance(questions, list) else questions.get("questions", [])
    )
    for item in items:
        if item.get("id") == question_id:
            return item
    known = [q.get("id", "?") for q in items]
    _die(
        f"Question '{question_id}' not found in questions.yaml. "
        f"Known: {', '.join(known)}"
    )


def _all_repos(repos: dict | list) -> list[dict]:
    return repos if isinstance(repos, list) else repos.get("repos", [])


def _all_arms(arms: dict | list) -> list[dict]:
    return arms if isinstance(arms, list) else arms.get("arms", [])


def _all_questions(questions: dict | list) -> list[dict]:
    return questions if isinstance(questions, list) else questions.get("questions", [])


def _repo_local_path(repo_entry: dict) -> Path:
    """Return the local path for a repo: .benchmark-repos/<id>."""
    repo_id: str = repo_entry["id"]
    return (BENCHMARKS_DIR / ".." / ".." / ".benchmark-repos" / repo_id).resolve()


# ---------------------------------------------------------------------------
# Sub-command implementations
# ---------------------------------------------------------------------------


def cmd_prepare(args: argparse.Namespace) -> int:
    """Prepare one or all repos — delegates to repo_prep."""
    try:
        from repo_prep import (  # noqa: PLC0415
            load_repos_config,
            prepare_all,
            prepare_repo,
            save_prepared_manifest,
        )
    except ImportError:
        _die(
            "repo_prep module not found. Expected at benchmarks/codegraph_compare/repo_prep.py"
        )

    base_dir = (BENCHMARKS_DIR / ".." / ".." / ".benchmark-repos").resolve()

    if args.all:
        repos = load_repos_config(REPOS_YAML)
        print(f"Preparing {len(repos)} repo(s)...", file=sys.stderr)
        prepared = prepare_all(repos, base_dir=base_dir)
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        save_prepared_manifest(prepared, PREPARED_MANIFEST)
        print(f"Done. Manifest written to {PREPARED_MANIFEST}", file=sys.stderr)
        return 0

    if not args.repo:
        _die("Specify --repo <id> or --all")

    repos = load_repos_config(REPOS_YAML)
    matches = [r for r in repos if r.id == args.repo]
    if not matches:
        _die(f"Repo '{args.repo}' not found in repos.yaml")
    repo_spec = matches[0]
    repo_path = base_dir / repo_spec.id
    print(f"Preparing repo '{args.repo}' at {repo_path} ...", file=sys.stderr)
    prepared = prepare_repo(repo_spec, base_dir=base_dir)
    if prepared.error:
        print(f"WARNING: {prepared.error}", file=sys.stderr)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    # Merge into existing manifest
    from repo_prep import PreparedRepo, load_prepared_manifest  # noqa: PLC0415

    existing: dict[str, PreparedRepo] = {}
    if PREPARED_MANIFEST.exists():
        for pr in load_prepared_manifest(PREPARED_MANIFEST):
            existing[pr.id] = pr
    existing[prepared.id] = prepared
    save_prepared_manifest(list(existing.values()), PREPARED_MANIFEST)
    print(f"Done. commit={prepared.actual_commit}", file=sys.stderr)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run a single (repo, question, arm, repeat) trial."""
    repos_data = _load_yaml(REPOS_YAML)
    arms_data = _load_yaml(ARMS_YAML)
    questions_data = _load_yaml(QUESTIONS_YAML)

    repo_entry = _get_repo(repos_data, args.repo)
    arm_entry = _get_arm(arms_data, args.arm)
    question_entry = _get_question(questions_data, args.question)

    repo_path = _repo_local_path(repo_entry)
    arm_id: str = arm_entry["id"]
    question_id: str = question_entry["id"]
    question_prompt: str = question_entry["prompt"]
    repeat: int = args.repeat

    # Lazy adapter import
    try:
        from adapters import get_adapter  # noqa: PLC0415
    except ImportError:
        _die("Could not import adapters package. Check PYTHONPATH.")

    adapter = get_adapter(arm_id)

    # Prepare index (warm by default unless index_mode says cold)
    index_mode: str = arm_entry.get("index_mode", "warm")
    cold = index_mode == "cold"
    print(
        f"[prepare] arm={arm_id}  repo={args.repo}  cold={cold}",
        file=sys.stderr,
    )
    index_stats = adapter.prepare_index(repo_path, cold=cold)
    print(
        f"[prepare] done  build_s={index_stats.build_seconds:.2f}"
        f"  files={index_stats.file_count}"
        f"  size={index_stats.index_size_bytes} bytes",
        file=sys.stderr,
    )

    run_config = adapter.build_run_config(repo_path, question_prompt)

    # Lazy claude_runner import
    try:
        from adapters.claude_runner import run_one  # noqa: PLC0415
    except ImportError:
        _die("Could not import adapters.claude_runner.")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print(
        f"[run] question={question_id}  arm={arm_id}  repeat={repeat:02d}",
        file=sys.stderr,
    )
    record = run_one(
        question_id=question_id,
        question_prompt=question_prompt,
        arm_id=arm_id,
        repo_path=repo_path,
        repeat=repeat,
        run_config=run_config,
        results_dir=RESULTS_DIR,
    )

    # Print result summary
    answer_snippet = (record["answer"] or "")[:120].replace("\n", " ")
    print(
        f"run_id:          {record['run_id']}\n"
        f"answer:          {answer_snippet}...\n"
        f"input_tokens:    {record['input_tokens']}\n"
        f"output_tokens:   {record['output_tokens']}\n"
        f"total_tokens:    {record['total_tokens']}\n"
        f"cost_usd:        ${record['estimated_cost_usd']:.4f}\n"
        f"tool_calls:      {record['tool_calls']} "
        f"(reads={record['file_reads']} search={record['search_calls']} idx={record['index_queries']})\n"
        f"elapsed_seconds: {record['elapsed_seconds']}\n"
        f"error:           {record['error']}"
    )
    return 0


def cmd_run_matrix(args: argparse.Namespace) -> int:
    """Run all combinations of repos × arms × questions × repeats."""
    repos_data = _load_yaml(REPOS_YAML)
    arms_data = _load_yaml(ARMS_YAML)
    questions_data = _load_yaml(QUESTIONS_YAML)

    # Resolve repos
    if args.repos in ("all", None):
        repo_entries = _all_repos(repos_data)
    else:
        repo_entries = [_get_repo(repos_data, rid) for rid in args.repos.split(",")]

    # Resolve arms
    if not args.arms or args.arms == "all":
        arm_entries = _all_arms(arms_data)
    else:
        arm_entries = [_get_arm(arms_data, aid) for aid in args.arms.split(",")]

    question_entries = _all_questions(questions_data)
    repeats: int = args.repeats if hasattr(args, "repeats") and args.repeats else 1

    # Lazy imports
    try:
        from adapters import get_adapter  # noqa: PLC0415
        from adapters.claude_runner import run_one  # noqa: PLC0415
    except ImportError:
        _die("Could not import adapters or adapters.claude_runner.")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    total = len(repo_entries) * len(arm_entries) * len(question_entries) * repeats
    idx = 0
    failed = 0

    for repo_entry in repo_entries:
        repo_id: str = repo_entry["id"]
        repo_path = _repo_local_path(repo_entry)

        for arm_entry in arm_entries:
            arm_id: str = arm_entry["id"]
            index_mode: str = arm_entry.get("index_mode", "warm")
            cold = index_mode == "cold"

            adapter = get_adapter(arm_id)
            adapter.prepare_index(repo_path, cold=cold)
            run_config_cache: dict = {}

            for question_entry in question_entries:
                question_id: str = question_entry["id"]
                question_prompt: str = question_entry["prompt"]

                if question_id not in run_config_cache:
                    run_config_cache[question_id] = adapter.build_run_config(
                        repo_path, question_prompt
                    )
                run_config = run_config_cache[question_id]

                for repeat in range(repeats):
                    idx += 1
                    label = (
                        f"[{idx}/{total}] repo={repo_id}"
                        f"  arm={arm_id}"
                        f"  q={question_id}"
                        f"  r={repeat:02d}"
                    )
                    print(label, file=sys.stderr, flush=True)

                    try:
                        record = run_one(
                            question_id=question_id,
                            question_prompt=question_prompt,
                            arm_id=arm_id,
                            repo_path=repo_path,
                            repeat=repeat,
                            run_config=run_config,
                            results_dir=RESULTS_DIR,
                        )
                        status = "DRY_RUN" if record["answer"] == "DRY_RUN" else "ok"
                        print(
                            f"  -> {status}  elapsed={record['elapsed_seconds']}s",
                            file=sys.stderr,
                        )
                    except Exception as exc:  # noqa: BLE001
                        failed += 1
                        print(f"  -> ERROR: {exc}", file=sys.stderr)

    print(
        f"\nMatrix complete: {idx} trials, {failed} errors.",
        file=sys.stderr,
    )
    print(f"Results: {RESULTS_DIR / 'runs.jsonl'}", file=sys.stderr)
    return 0 if failed == 0 else 1


def cmd_status(_args: argparse.Namespace) -> int:
    """Print summary of prepared repos and run statistics."""
    # Prepared repos manifest
    print("=== Prepared Repos ===")
    if PREPARED_MANIFEST.exists():
        try:
            manifest = json.loads(PREPARED_MANIFEST.read_text(encoding="utf-8"))
            repos_list = (
                manifest if isinstance(manifest, list) else manifest.get("repos", [])
            )
            if repos_list:
                for entry in repos_list:
                    print(
                        f"  {entry.get('id', '?'):20s}  path={entry.get('path', '?')}"
                    )
            else:
                print("  (no repos recorded)")
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  (could not read manifest: {exc})")
    else:
        print(f"  (manifest not found at {PREPARED_MANIFEST})")

    # Run stats from runs.jsonl
    runs_jsonl = RESULTS_DIR / "runs.jsonl"
    print("\n=== Run Statistics ===")
    if not runs_jsonl.exists():
        print("  (no runs.jsonl found — no runs recorded yet)")
        return 0

    records: list[dict] = []
    try:
        with runs_jsonl.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except OSError as exc:
        print(f"  (could not read runs.jsonl: {exc})")
        return 1

    if not records:
        print("  (runs.jsonl is empty)")
        return 0

    print(f"  Total runs:    {len(records)}")

    # By arm
    by_arm: dict[str, int] = {}
    for r in records:
        arm = r.get("arm_id", "unknown")
        by_arm[arm] = by_arm.get(arm, 0) + 1
    print("  By arm:")
    for arm, count in sorted(by_arm.items()):
        print(f"    {arm:30s} {count}")

    # By repo
    by_repo: dict[str, int] = {}
    for r in records:
        repo = Path(r.get("repo_path", "unknown")).name
        by_repo[repo] = by_repo.get(repo, 0) + 1
    print("  By repo:")
    for repo, count in sorted(by_repo.items()):
        print(f"    {repo:30s} {count}")

    # Last run time
    last_ended = max(
        (r.get("ended_at", "") for r in records if r.get("ended_at")),
        default=None,
    )
    if last_ended:
        print(f"  Last run at:   {last_ended}")

    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python run.py",
        description="CodeGraph comparison benchmark harness.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python run.py prepare --repo tsa-self\n"
            "  python run.py prepare --all\n"
            "  python run.py run --repo tsa-self --question q01 "
            "--arm native-only --repeat 0\n"
            "  python run.py run-matrix --repos all "
            "--arms native-only,tsa-warm --repeats 3\n"
            "  python run.py run-matrix --repos all --arms all "
            "--repeats 1 --dry-run\n"
            "  python run.py status\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # ---- prepare ----
    p_prepare = sub.add_parser("prepare", help="Prepare one or all repos.")
    p_prepare.add_argument(
        "--repo",
        default="",
        help="Repository ID as listed in repos.yaml.",
    )
    p_prepare.add_argument(
        "--all",
        action="store_true",
        help="Prepare every repo in repos.yaml.",
    )

    # ---- run ----
    p_run = sub.add_parser("run", help="Run a single benchmark trial.")
    p_run.add_argument("--repo", required=True, help="Repository ID.")
    p_run.add_argument("--question", required=True, help="Question ID.")
    p_run.add_argument("--arm", required=True, help="Arm ID.")
    p_run.add_argument(
        "--repeat",
        type=int,
        default=0,
        help="Zero-based repeat index (default: 0).",
    )

    # ---- run-matrix ----
    p_matrix = sub.add_parser(
        "run-matrix",
        help="Run all combinations of repos × arms × questions × repeats.",
    )
    p_matrix.add_argument(
        "--repos",
        default="all",
        help="Comma-separated repo IDs, or 'all' (default).",
    )
    p_matrix.add_argument(
        "--arms",
        default="all",
        help=(
            "Comma-separated arm IDs (e.g. 'native-only,tsa-warm'), or 'all' (default)."
        ),
    )
    p_matrix.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="Number of repeat runs per (question, arm, repo) triple (default: 1).",
    )
    p_matrix.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help=(
            "Dry-run mode: build prompts and record stubs without calling the "
            "Claude API. (Currently the default behaviour — flag is a no-op until "
            "real API calls are wired up.)"
        ),
    )

    # ---- status ----
    sub.add_parser("status", help="Show prepared repos and last run statistics.")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the appropriate sub-command handler."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    dispatch: dict[str, Callable[[argparse.Namespace], int]] = {
        "prepare": cmd_prepare,
        "run": cmd_run,
        "run-matrix": cmd_run_matrix,
        "status": cmd_status,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        _die(f"Unknown command: {args.command!r}")

    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
