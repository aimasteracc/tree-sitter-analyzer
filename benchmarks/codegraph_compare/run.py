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
  phase smoke                         Run a named benchmark phase
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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

# ---------------------------------------------------------------------------
# Path constants  (all relative to this file so the harness is portable)
# ---------------------------------------------------------------------------

BENCHMARKS_DIR = Path(__file__).parent
REPOS_YAML = BENCHMARKS_DIR / "repos.yaml"
ARMS_YAML = BENCHMARKS_DIR / "arms.yaml"
QUESTIONS_YAML = BENCHMARKS_DIR / "questions.yaml"
RESULTS_DIR = BENCHMARKS_DIR / "results"
PREPARED_MANIFEST = RESULTS_DIR / "prepared_repos.json"


@dataclass(frozen=True)
class PhasePreset:
    """Named benchmark phase with reproducible defaults."""

    repos: str
    arms: str
    repeats: int
    min_repeats: int
    question_limit: int | None
    description: str


PHASE_PRESETS: dict[str, PhasePreset] = {
    "smoke": PhasePreset(
        repos="gin",
        arms="all",
        repeats=1,
        min_repeats=1,
        question_limit=1,
        description="1 repo, 1 question, 1 repeat, all arms",
    ),
    "pilot": PhasePreset(
        repos="gin",
        arms="all",
        repeats=4,
        min_repeats=4,
        question_limit=None,
        description="1 repo, all questions, 4 repeats, all arms",
    ),
    "full-warm": PhasePreset(
        repos="all",
        arms="native-only,codegraph-warm,tsa-warm",
        repeats=4,
        min_repeats=4,
        question_limit=None,
        description="all repos, all questions, 4 repeats, warm arms",
    ),
    "cold": PhasePreset(
        repos="all",
        arms="codegraph-cold,tsa-cold",
        repeats=4,
        min_repeats=4,
        question_limit=None,
        description="all repos, all questions, 4 repeats, cold arms",
    ),
}


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


def _questions_for_repo(questions: dict | list, repo_id: str) -> list[dict]:
    return [q for q in _all_questions(questions) if q.get("repo") == repo_id]


def _limited_questions_for_repo(
    questions: dict | list, repo_id: str, limit: int | None
) -> list[dict]:
    repo_questions = _questions_for_repo(questions, repo_id)
    if limit is None:
        return repo_questions
    if limit < 1:
        _die("--question-limit must be greater than zero")
    return repo_questions[:limit]


def _assert_question_matches_repo(question_entry: dict, repo_id: str) -> None:
    question_repo = question_entry.get("repo")
    if question_repo != repo_id:
        _die(
            f"Question '{question_entry.get('id')}' belongs to repo "
            f"'{question_repo}', not '{repo_id}'."
        )


def _repo_local_path(repo_entry: dict) -> Path:
    """Return the local path for a repo: .benchmark-repos/<id>."""
    repo_id: str = repo_entry["id"]
    return (BENCHMARKS_DIR / ".." / ".." / ".benchmark-repos" / repo_id).resolve()


# ---------------------------------------------------------------------------
# Pre-flight live-setup gate
# ---------------------------------------------------------------------------
#
# A dead or empty MCP arm silently contaminates EVERY downstream number — the
# agent gets "cache empty" / no tools and falls back to raw Read/grep, so the
# benchmark measures a broken setup instead of the tool. We wasted months on
# exactly this (validate-setup-before-scale + codegraph-benchmark-fixes
# memories). preflight() asserts, per arm, that:
#   1. the index row-count is > 0 (the index is actually populated), and
#   2. the MCP handshake succeeds, exposes the EXPECTED tool set, and a canary
#      query returns a NON-empty, tool-sourced response.
# It writes preflight.json for the audit trail and aborts LOUDLY (SystemExit)
# if any arm isn't live, so the matrix never runs against a contaminated setup.

# Expected MCP tool sets per arm family. TSA exposes 8 facade tools; CodeGraph
# exposes codegraph_* tools — the canary probe reports the live tool names and
# we assert the expected ones are present.
_EXPECTED_TSA_TOOLS: frozenset[str] = frozenset(
    {"nav", "search", "structure", "health", "edit", "project", "index", "viz"}
)


def _arm_family(arm_id: str) -> str:
    """Classify an arm into 'tsa', 'codegraph', or 'native'."""
    if arm_id.startswith("tsa"):
        return "tsa"
    if arm_id.startswith("codegraph"):
        return "codegraph"
    return "native"


def _index_row_count(arm_id: str, repo_path: Path) -> int:
    """Return the populated-row count for an arm's index, or 0 if empty/absent.

    TSA: ast_index row count from .ast-cache/index.db (reuses the adapter's own
    reader). CodeGraph: number of files under .codegraph/ (its on-disk index;
    an empty/absent dir means 0). native: not index-backed → sentinel -1 so the
    caller treats it as "no index required".
    """
    family = _arm_family(arm_id)
    if family == "tsa":
        try:
            from adapters.tree_sitter_analyzer import (  # noqa: PLC0415
                _indexed_file_count,
            )
        except ImportError:  # imported as a package submodule, not a script
            from benchmarks.codegraph_compare.adapters.tree_sitter_analyzer import (  # noqa: PLC0415
                _indexed_file_count,
            )

        index_db = repo_path / ".ast-cache" / "index.db"
        if not index_db.exists():
            return 0
        return _indexed_file_count(index_db) or 0
    if family == "codegraph":
        index_dir = repo_path / ".codegraph"
        if not index_dir.exists():
            return 0
        return sum(1 for f in index_dir.rglob("*") if f.is_file())
    return -1  # native: no index


def _missing_expected_tools(arm_id: str, tools: list[str]) -> list[str]:
    """Return expected-but-absent tool names for the arm's MCP family."""
    family = _arm_family(arm_id)
    present = set(tools)
    if family == "tsa":
        return sorted(_EXPECTED_TSA_TOOLS - present)
    if family == "codegraph":
        # CodeGraph exposes codegraph_* tools; require at least one to be live.
        if not any(t.startswith("codegraph_") for t in present):
            return ["codegraph_*"]
        return []
    return []


def _preflight_arm(
    arm_id: str,
    repo_path: Path,
    canary_probe: Callable[[str], dict[str, Any]] | None,
) -> dict[str, Any]:
    """Assess one arm's liveness. Returns a per-arm report dict (does not raise)."""
    family = _arm_family(arm_id)
    row_count = _index_row_count(arm_id, repo_path)

    if family == "native":
        # native-only is index/MCP-free; it is always live by construction.
        return {
            "arm": arm_id,
            "family": family,
            "index_row_count": row_count,
            "handshake_ok": True,
            "tools": [],
            "missing_tools": [],
            "canary_nonempty": True,
            "live": True,
            "reasons": [],
        }

    reasons: list[str] = []
    index_ok = row_count > 0
    if not index_ok:
        reasons.append(f"index empty or absent (row_count={row_count})")

    handshake_ok = False
    tools: list[str] = []
    missing_tools: list[str] = []
    canary_nonempty = False

    if canary_probe is None:
        reasons.append("no canary probe supplied for an MCP-backed arm")
    else:
        probe = canary_probe(arm_id)
        handshake_ok = bool(probe.get("handshake_ok", False))
        tools = list(probe.get("tools", []))
        canary_nonempty = bool(probe.get("canary_nonempty", False))
        if not handshake_ok:
            reasons.append("MCP handshake failed")
        missing_tools = _missing_expected_tools(arm_id, tools)
        if missing_tools:
            reasons.append(f"expected tools missing: {', '.join(missing_tools)}")
        if not canary_nonempty:
            reasons.append("canary query returned an empty / non-tool-sourced response")

    live = index_ok and handshake_ok and not missing_tools and canary_nonempty
    return {
        "arm": arm_id,
        "family": family,
        "index_row_count": row_count,
        "handshake_ok": handshake_ok,
        "tools": tools,
        "missing_tools": missing_tools,
        "canary_nonempty": canary_nonempty,
        "live": live,
        "reasons": reasons,
    }


def preflight(
    arm_ids: list[str],
    repo_path: Path,
    results_dir: Path,
    canary_probe: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assert every arm is live before benchmarking; write preflight.json.

    For each arm, checks index row-count > 0 and (for MCP arms) that the
    handshake succeeded, the expected tool set is present, and a canary query
    returned a non-empty tool-sourced response. Writes the full report to
    ``results_dir/preflight.json`` regardless of outcome, then raises SystemExit
    (loud abort) if ANY arm is not live — so the matrix never runs against a
    dead or empty setup and silently produces contaminated numbers.

    ``canary_probe(arm_id) -> {"handshake_ok", "tools", "canary_nonempty"}`` is
    injected so the gate is testable without a live MCP; the production caller
    passes a probe that drives the real agent CLI handshake + a canary query.
    """
    arms_report: dict[str, Any] = {}
    for arm_id in arm_ids:
        arms_report[arm_id] = _preflight_arm(arm_id, repo_path, canary_probe)

    all_live = all(r["live"] for r in arms_report.values())
    report: dict[str, Any] = {
        "repo_path": str(repo_path),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "all_live": all_live,
        "arms": arms_report,
    }

    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "preflight.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    if not all_live:
        dead = [
            f"  {arm}: {'; '.join(rep['reasons']) or 'not live'}"
            for arm, rep in arms_report.items()
            if not rep["live"]
        ]
        _die(
            "PRE-FLIGHT FAILED — one or more arms are not live. Refusing to run "
            "the benchmark against a dead/empty setup (it would silently produce "
            "contaminated numbers). Dead arms:\n" + "\n".join(dead) + "\n"
            f"See {results_dir / 'preflight.json'} for the full report."
        )

    return report


def _live_canary_probe(
    repo_path: Path, model: str, timeout_seconds: int
) -> Callable[[str], dict[str, Any]]:
    """Build a real canary probe that drives the agent CLI per arm.

    The probe spawns the same per-arm MCP config the benchmark uses, asks a
    trivial canary question, and inspects the stream for tool_use events that
    name the arm's MCP server. handshake_ok = the CLI produced a parseable
    stream with no startup error; tools = the MCP tool short-names it actually
    invoked or were offered; canary_nonempty = at least one tool-sourced
    response block came back. Kept here (not in claude_runner) because it is a
    setup-gate concern, not a measured run.
    """
    import os  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from adapters.claude_runner import _write_arm_mcp_config  # noqa: PLC0415

    def probe(arm_id: str) -> dict[str, Any]:
        family = _arm_family(arm_id)
        if family == "native":
            return {"handshake_ok": True, "tools": [], "canary_nonempty": True}

        mcp_cfg = _write_arm_mcp_config(arm_id, repo_path)
        prefix = (
            "mcp__tree-sitter-analyzer__" if family == "tsa" else "mcp__codegraph__"
        )
        canary_q = (
            "List the indexed entry points. Use exactly one index tool, then stop."
        )
        cmd = [
            "claude",
            "--print",
            "--output-format",
            "stream-json",
            "--verbose",
            "--no-session-persistence",
            "--model",
            model,
            "--add-dir",
            str(repo_path),
            "--strict-mcp-config",
            "--mcp-config",
            str(mcp_cfg),
        ]
        tools: list[str] = []
        handshake_ok = False
        canary_nonempty = False
        try:
            proc = subprocess.run(
                cmd,
                input=canary_q,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                cwd=str(repo_path),
                env={
                    **os.environ,
                    "MCP_TIMEOUT": "30000",
                    "MCP_TOOL_TIMEOUT": "30000",
                },
            )
            handshake_ok = bool(proc.stdout.strip()) and proc.returncode == 0
            for line in proc.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") != "assistant":
                    continue
                for block in event.get("message", {}).get("content", []):
                    name = block.get("name", "")
                    if block.get("type") == "tool_use" and name.startswith(prefix):
                        short = name[len(prefix) :]
                        tools.append(short)
                        canary_nonempty = True
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            return {
                "handshake_ok": False,
                "tools": [],
                "canary_nonempty": False,
                "error": str(exc),
            }
        return {
            "handshake_ok": handshake_ok,
            "tools": sorted(set(tools)),
            "canary_nonempty": canary_nonempty,
        }

    return probe


def _phase_to_matrix_args(args: argparse.Namespace) -> argparse.Namespace:
    """Expand a named phase into the same namespace used by run-matrix."""
    preset = PHASE_PRESETS.get(args.phase)
    if preset is None:
        known = ", ".join(sorted(PHASE_PRESETS))
        _die(f"Unknown phase '{args.phase}'. Known phases: {known}")

    repeats = args.repeats if args.repeats is not None else preset.repeats
    if repeats < preset.min_repeats:
        _die(f"Phase '{args.phase}' requires --repeats {preset.min_repeats} or higher.")

    question_limit = (
        args.question_limit
        if args.question_limit is not None
        else preset.question_limit
    )
    if question_limit is not None and question_limit < 1:
        _die("--question-limit must be greater than zero")

    return argparse.Namespace(
        repos=args.repos or preset.repos,
        arms=args.arms or preset.arms,
        repeats=repeats,
        question_limit=question_limit,
        dry_run=args.dry_run,
        skip_preflight=getattr(args, "skip_preflight", False),
        agent_backend=args.agent_backend,
        model=args.model,
        timeout_seconds=args.timeout_seconds,
        phase=args.phase,
    )


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
    _assert_question_matches_repo(question_entry, args.repo)

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
    if args.dry_run:
        print("[prepare] skipped in dry-run mode", file=sys.stderr)
    else:
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
        timeout_seconds=args.timeout_seconds,
        model=args.model,
        agent_backend=args.agent_backend,
        dry_run=getattr(args, "dry_run", False),
        session_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"),
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

    repeats: int = args.repeats if hasattr(args, "repeats") and args.repeats else 1
    question_limit = getattr(args, "question_limit", None)
    if question_limit is not None and question_limit < 1:
        _die("--question-limit must be greater than zero")

    # Lazy imports
    try:
        from adapters import get_adapter  # noqa: PLC0415
        from adapters.claude_runner import run_one  # noqa: PLC0415
    except ImportError:
        _die("Could not import adapters or adapters.claude_runner.")

    # One session id per matrix invocation so repeated runs don't overwrite each
    # other's raw transcripts (cost data must survive re-runs for n>1 analysis).
    session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    question_entries_by_repo = {
        repo_entry["id"]: _limited_questions_for_repo(
            questions_data, repo_entry["id"], question_limit
        )
        for repo_entry in repo_entries
    }
    total = (
        sum(len(items) for items in question_entries_by_repo.values())
        * len(arm_entries)
        * repeats
    )
    idx = 0
    failed = 0

    for repo_entry in repo_entries:
        repo_id: str = repo_entry["id"]
        repo_path = _repo_local_path(repo_entry)
        question_entries = question_entries_by_repo[repo_id]

        if not question_entries:
            print(f"[skip] repo={repo_id} has no questions", file=sys.stderr)
            continue

        # PRE-FLIGHT GATE (Codex P2 #342): refuse to benchmark a dead/empty setup.
        # preflight() aborts loudly (SystemExit) if any arm's MCP isn't live or its
        # index is empty — the exact failure that wasted months of contaminated
        # runs. It is in the CRITICAL PATH (not an opt-in subcommand); operators
        # must explicitly opt OUT with --skip-preflight (CI/dry-run only).
        if not args.dry_run and not getattr(args, "skip_preflight", False):
            preflight(
                arm_ids=[a["id"] for a in arm_entries],
                repo_path=repo_path,
                results_dir=RESULTS_DIR,
                canary_probe=_live_canary_probe(
                    repo_path,
                    args.model or "claude-sonnet-4-6",
                    args.timeout_seconds,
                ),
            )

        for arm_entry in arm_entries:
            arm_id: str = arm_entry["id"]
            index_mode: str = arm_entry.get("index_mode", "warm")
            cold = index_mode == "cold"

            adapter = get_adapter(arm_id)
            if args.dry_run:
                print(
                    f"[prepare] skipped dry-run  arm={arm_id}  repo={repo_id}",
                    file=sys.stderr,
                )
            else:
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
                            timeout_seconds=args.timeout_seconds,
                            model=args.model,
                            agent_backend=args.agent_backend,
                            dry_run=args.dry_run,
                            session_id=session_id,
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


def cmd_phase(args: argparse.Namespace) -> int:
    """Run a named benchmark phase with reproducible defaults."""
    matrix_args = _phase_to_matrix_args(args)
    preset = PHASE_PRESETS[args.phase]
    print(
        f"[phase] {args.phase}: {preset.description} "
        f"(repos={matrix_args.repos}, arms={matrix_args.arms}, "
        f"repeats={matrix_args.repeats}, question_limit={matrix_args.question_limit})",
        file=sys.stderr,
    )
    return cmd_run_matrix(matrix_args)


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
        arm = r.get("arm", "unknown")
        by_arm[arm] = by_arm.get(arm, 0) + 1
    print("  By arm:")
    for arm, count in sorted(by_arm.items()):
        print(f"    {arm:30s} {count}")

    # By repo
    by_repo: dict[str, int] = {}
    for r in records:
        repo = r.get("repo", "unknown")
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


def cmd_preflight(args: argparse.Namespace) -> int:
    """Assert every requested arm is live before benchmarking; abort if not."""
    repos_data = _load_yaml(REPOS_YAML)
    arms_data = _load_yaml(ARMS_YAML)

    repo_entry = _get_repo(repos_data, args.repo)
    repo_path = _repo_local_path(repo_entry)

    if not args.arms or args.arms == "all":
        arm_entries = _all_arms(arms_data)
    else:
        arm_entries = [_get_arm(arms_data, aid) for aid in args.arms.split(",")]
    arm_ids = [a["id"] for a in arm_entries]

    model = args.model or "claude-sonnet-4-6"
    probe = _live_canary_probe(repo_path, model, args.timeout_seconds)

    print(
        f"[preflight] repo={args.repo}  arms={','.join(arm_ids)}",
        file=sys.stderr,
    )
    # preflight() aborts via _die (SystemExit) if any arm is not live.
    report = preflight(
        arm_ids=arm_ids,
        repo_path=repo_path,
        results_dir=RESULTS_DIR,
        canary_probe=probe,
    )
    print(
        f"[preflight] all arms live. Report: {RESULTS_DIR / 'preflight.json'}",
        file=sys.stderr,
    )
    for arm_id, rep in report["arms"].items():
        print(
            f"  {arm_id:18s} live={rep['live']}  "
            f"rows={rep['index_row_count']}  tools={len(rep['tools'])}",
            file=sys.stderr,
        )
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
            "  python run.py phase smoke --agent-backend codex --dry-run\n"
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
    p_run.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Build prompt and record a stub without calling an agent CLI.",
    )
    p_run.add_argument(
        "--agent-backend",
        choices=["claude", "codex"],
        default="claude",
        help="Agent CLI backend to execute the run (default: claude).",
    )
    p_run.add_argument(
        "--model",
        default=None,
        help="Model name for the selected agent backend.",
    )
    p_run.add_argument(
        "--timeout-seconds",
        type=int,
        default=1200,
        help="Per-run timeout in seconds (default: 1200).",
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
            "agent CLI."
        ),
    )
    p_matrix.add_argument(
        "--skip-preflight",
        action="store_true",
        dest="skip_preflight",
        help=(
            "Opt OUT of the pre-flight live-setup gate (CI/dry-run only). By "
            "default the matrix aborts if any arm's MCP/index is not live."
        ),
    )
    p_matrix.add_argument(
        "--agent-backend",
        choices=["claude", "codex"],
        default="claude",
        help="Agent CLI backend to execute each run (default: claude).",
    )
    p_matrix.add_argument(
        "--model",
        default=None,
        help="Model name for the selected agent backend.",
    )
    p_matrix.add_argument(
        "--timeout-seconds",
        type=int,
        default=1200,
        help="Per-run timeout in seconds (default: 1200).",
    )
    p_matrix.add_argument(
        "--question-limit",
        type=int,
        default=None,
        help="Limit questions per repo; useful for smoke runs.",
    )

    # ---- phase ----
    p_phase = sub.add_parser(
        "phase",
        help="Run a named phase: smoke, pilot, full-warm, or cold.",
    )
    p_phase.add_argument(
        "phase",
        choices=sorted(PHASE_PRESETS),
        help="Benchmark phase name.",
    )
    p_phase.add_argument(
        "--repos",
        default="",
        help="Override phase repo set with comma-separated IDs or 'all'.",
    )
    p_phase.add_argument(
        "--arms",
        default="",
        help="Override phase arms with comma-separated IDs or 'all'.",
    )
    p_phase.add_argument(
        "--repeats",
        type=int,
        default=None,
        help="Override phase repeat count.",
    )
    p_phase.add_argument(
        "--question-limit",
        type=int,
        default=None,
        help="Override phase question limit per repo.",
    )
    p_phase.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Build prompts and record stubs without calling an agent CLI.",
    )
    p_phase.add_argument(
        "--skip-preflight",
        action="store_true",
        dest="skip_preflight",
        help="Opt OUT of the pre-flight live-setup gate (CI/dry-run only).",
    )
    p_phase.add_argument(
        "--agent-backend",
        choices=["claude", "codex"],
        default="claude",
        help="Agent CLI backend to execute each run (default: claude).",
    )
    p_phase.add_argument(
        "--model",
        default=None,
        help="Model name for the selected agent backend.",
    )
    p_phase.add_argument(
        "--timeout-seconds",
        type=int,
        default=1200,
        help="Per-run timeout in seconds (default: 1200).",
    )

    # ---- preflight ----
    p_preflight = sub.add_parser(
        "preflight",
        help="Assert every arm's MCP/index is live before benchmarking.",
    )
    p_preflight.add_argument("--repo", required=True, help="Repository ID.")
    p_preflight.add_argument(
        "--arms",
        default="all",
        help="Comma-separated arm IDs, or 'all' (default).",
    )
    p_preflight.add_argument(
        "--model",
        default=None,
        help="Model name for the canary handshake (default: claude-sonnet-4-6).",
    )
    p_preflight.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="Per-arm canary timeout in seconds (default: 120).",
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
        "phase": cmd_phase,
        "status": cmd_status,
        "preflight": cmd_preflight,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        _die(f"Unknown command: {args.command!r}")

    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
