"""Change-impact analysis helpers shared by MCP and CLI entry points."""

from __future__ import annotations

import logging
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ....project_graph import BlastRadius, DependencyGraph
from .call_graph_impact import compute_call_graph_impact
from .change_impact_cached_graph import load_cached_dependency_graph
from .change_impact_response import (
    LARGE_DIRTY_DIFF_THRESHOLD,
    AgentSummaryContext,
    ChangeImpactResponseContext,
    build_agent_summary,
    build_change_impact_response,
    build_no_changes_result,
)
from .change_impact_response import (
    build_agent_summary_only_response as build_agent_summary_only_response,
)
from .change_impact_verification import (
    AUTO_DISCOVER_TEST_HINT,
    DOCS_ONLY_TEST_HINT,
    _build_verification_plan,
    _is_docs_only_change,
)
from .constraint_violation_query import (
    constraint_risk_factor,
    verdict_from_violations,
    violations_for_files,
)
from .test_discovery_stems import related_stem_matches, related_test_stems_for_path
from .verification_command import (
    DefaultTestCommand,
    build_test_command,
    detect_default_test_command,
)

logger = logging.getLogger(__name__)

TESTS_TO_RUN_DISPLAY_LIMIT = 30
FOCUSED_TEST_COMMAND_LIMIT = 20
RESOURCE_PROFILE_DEFAULT = "default"
RESOURCE_PROFILE_LOCAL_LOW_IMPACT = "local_low_impact"
TEST_DIRS = {"tests/", "test/", "spec/", "__tests__/"}
TEST_SUFFIXES = (
    "_test.py",
    "_test.js",
    "_test.ts",
    "Test.java",
    ".test.py",
    ".test.js",
    ".test.ts",
    "_spec.py",
    "_spec.js",
)


@dataclass(frozen=True)
class ChangeImpactRequest:
    """Inputs needed to build a change-impact response."""

    mode: str
    changed_files: list[str]
    diff_stat: str
    project_root: str | None
    include_tests: bool
    scope_paths: list[str] | None = None
    agent_summary_only: bool = False
    resource_profile: str = RESOURCE_PROFILE_DEFAULT


def _find_test_files(
    changed_files: list[str],
    graph_nodes: set[str],
) -> dict[str, list[str]]:
    """Map changed files to related test files using stem matching."""
    test_files = {
        node
        for node in graph_nodes
        if _is_runnable_test_file(node, TEST_DIRS, TEST_SUFFIXES)
    }

    mapping: dict[str, list[str]] = {}
    for changed_file in changed_files:
        if _is_docs_only_change(changed_file):
            mapping[changed_file] = [DOCS_ONLY_TEST_HINT]
            continue

        related = [
            test_file
            for test_file in sorted(test_files)
            if _test_file_matches_change(test_file, changed_file)
        ]
        mapping[changed_file] = related or [AUTO_DISCOVER_TEST_HINT]

    return mapping


def _test_file_matches_change(test_file: str, changed_file: str) -> bool:
    """Return True when a test filename appears related to a changed file."""
    changed_stem = Path(changed_file).stem
    test_stem = Path(test_file).stem
    direct_stem = test_stem.replace("_test", "").replace("test_", "")
    if changed_stem in test_stem or direct_stem == changed_stem:
        return True
    return any(
        related_stem_matches(test_stem, related_stem)
        for related_stem in related_test_stems_for_path(changed_file)
    )


def _is_runnable_test_file(
    path: str,
    test_dirs: set[str],
    test_suffixes: tuple[str, ...],
) -> bool:
    """Return True for files that are intended to be direct pytest targets."""
    normalized = path.replace("\\", "/")
    name = Path(normalized).name
    if name in {"conftest.py", "__init__.py"}:
        return False
    in_test_dir = any(
        normalized.startswith(directory) or f"/{directory}" in normalized
        for directory in test_dirs
    )
    return (
        (in_test_dir and name.startswith("test_"))
        or name.endswith(test_suffixes)
        or (in_test_dir and (".test." in name or ".spec." in name))
    )


def _assess_risk(
    changed_files: list[str],
    affected: set[str],
    graph: Any,
) -> str:
    """Assess change risk level based on blast radius size."""
    if not changed_files:
        return "none"
    total_affected = len(affected)
    if total_affected <= 2:
        return "low"
    if total_affected <= 8:
        return "medium"
    return "high"


def _file_impact_dict(changed_file: str, graph: Any, fwd: set[str]) -> dict[str, Any]:
    """Build one file-impact row for _build_file_impacts."""
    return {
        "file": changed_file,
        "direct_dependents": sorted(graph.dependents_of(changed_file))[:20],
        "total_affected": len(fwd),
    }


def _build_file_impacts(
    changed_files: list[str],
    graph: Any | None,
) -> tuple[set[str], list[dict[str, Any]]]:
    """Build per-file impact rows and the total affected file set."""
    if graph is None:
        return set(), [{"file": changed_file} for changed_file in changed_files]

    affected: set[str] = set()
    file_impacts: list[dict[str, Any]] = []
    blast = BlastRadius(graph)
    for changed_file in changed_files:
        fwd = blast.forward(changed_file)
        affected.update(fwd)
        file_impacts.append(_file_impact_dict(changed_file, graph, fwd))

    return affected, file_impacts


def _build_test_plan(
    changed_files: list[str],
    graph: Any | None,
    include_tests: bool,
) -> tuple[dict[str, list[str]], list[str]]:
    """Build changed-file-to-test mapping and a sorted runnable test list."""
    if not include_tests or graph is None:
        return {}, []

    test_mapping = _find_test_files(changed_files, set(graph.nodes()))
    tests_to_run = sorted(
        {
            test_path
            for tests in test_mapping.values()
            for test_path in tests
            if not test_path.startswith("(")
        }
    )
    return test_mapping, tests_to_run


def _is_runnable_test_change(path: str) -> bool:
    """Return True when a changed path is itself a direct test target."""
    return _is_runnable_test_file(path, TEST_DIRS, TEST_SUFFIXES)


def _is_test_only_change_set(changed_files: list[str]) -> bool:
    """Return True when every changed file is a runnable test file."""
    return bool(changed_files) and all(
        _is_runnable_test_change(path) for path in changed_files
    )


def _load_dependency_graph(project_root: str | None) -> Any | None:
    """Build the dependency graph, returning None when analysis is unavailable."""
    cached = load_cached_dependency_graph(project_root)
    if cached is not None:
        return cached
    try:
        return DependencyGraph(project_root or ".")
    except Exception:
        return None


def _build_test_only_change_impact_result(
    request: ChangeImpactRequest,
) -> dict[str, Any]:
    """Build a fast change-impact response for test-only edits.

    Runnable test files are already the exact verification targets. Avoid
    walking the whole dependency graph, building a call graph, or syncing the
    AST cache when the diff cannot alter runtime dependency edges.
    """
    tests_to_run = sorted(dict.fromkeys(request.changed_files))
    test_mapping = {path: [path] for path in tests_to_run}
    default_test_command = detect_default_test_command(request.project_root)
    verification = _build_verification_plan(
        request.changed_files,
        tests_to_run,
        test_mapping,
        default_test_command,
    )
    strategy = _build_verification_strategy(
        changed_count=len(request.changed_files),
        tests_to_run=tests_to_run,
        verification=verification,
        resource_profile=request.resource_profile,
    )
    agent_summary = build_agent_summary(
        AgentSummaryContext(
            risk="low",
            changed_files=request.changed_files,
            scope_paths=request.scope_paths,
            verification=verification,
            strategy=strategy,
            affected_count=0,
            tests_to_run_count=len(tests_to_run),
        )
    )
    result = build_change_impact_response(
        ChangeImpactResponseContext(
            request=request,
            risk="low",
            affected=set(),
            file_impacts=[
                {
                    "file": path,
                    "direct_dependents": [],
                    "total_affected": 0,
                    "test_only": True,
                }
                for path in request.changed_files
            ],
            visible_tests=tests_to_run[:TESTS_TO_RUN_DISPLAY_LIMIT],
            all_tests=tests_to_run,
            verification=verification,
            strategy=strategy,
            test_mapping=test_mapping,
            agent_summary=agent_summary,
        )
    )
    result["analysis_fast_path"] = "test_only"
    return result


def _build_verification_strategy(
    *,
    changed_count: int,
    tests_to_run: list[str],
    verification: dict[str, Any],
    resource_profile: str = RESOURCE_PROFILE_DEFAULT,
) -> dict[str, Any]:
    """Build an action-oriented verification strategy for agents."""
    default_command = DefaultTestCommand(
        verification["test_runner"],
        verification["default_test_command"],
    )
    can_build_focused_command = 0 < len(tests_to_run) <= FOCUSED_TEST_COMMAND_LIMIT
    focused_command = (
        build_test_command(default_command, tests_to_run)
        if verification["test_required"] and can_build_focused_command
        else ""
    )
    final_command = verification["verification_command"]

    steps, strategy, hint = _select_verification_path(
        verification=verification,
        focused_command=focused_command,
        final_command=final_command,
        tests_to_run_count=len(tests_to_run),
        default_command=default_command.command,
    )
    hint = _append_large_dirty_hint(hint, changed_count)

    strategy_payload = {
        "focused_test_command": focused_command,
        "verification_strategy": strategy,
        "verification_steps": steps,
        "verification_hint": hint,
    }
    if resource_profile == RESOURCE_PROFILE_LOCAL_LOW_IMPACT:
        return _with_local_low_impact_profile(
            strategy_payload,
            verification=verification,
            focused_command=focused_command,
            final_command=final_command,
        )
    return strategy_payload


def _with_local_low_impact_profile(
    strategy: dict[str, Any],
    *,
    verification: dict[str, Any],
    focused_command: str,
    final_command: str,
) -> dict[str, Any]:
    """Attach local low-impact pytest commands while preserving CI intent."""
    if not verification["test_required"] or verification["test_runner"] != "pytest":
        return strategy

    local_source = focused_command or final_command
    local_command = _low_impact_pytest_command(local_source)
    label = (
        "local_low_impact_focused_then_ci"
        if focused_command and focused_command != final_command
        else "local_low_impact_then_ci"
    )
    hint = (
        "Run the low-impact local verification command while iterating; "
        f"keep {final_command} as the CI or queue-boundary verification command."
    )
    return {
        **strategy,
        "resource_profile": RESOURCE_PROFILE_LOCAL_LOW_IMPACT,
        "low_impact_focused_test_command": local_command if focused_command else "",
        "local_verification_command": local_command,
        "ci_verification_command": final_command,
        "verification_strategy": label,
        "verification_steps": [local_command],
        "verification_hint": hint,
    }


def _low_impact_pytest_command(command: str) -> str:
    """Rewrite a pytest command so it is friendlier to an interactive machine."""
    try:
        parts = shlex.split(command)
    except ValueError:
        return command

    prefix: list[str]
    rest: list[str]
    if parts[:3] == ["uv", "run", "pytest"]:
        prefix = parts[:3]
        rest = parts[3:]
    elif parts and parts[0].endswith("pytest"):
        prefix = parts[:1]
        rest = parts[1:]
    else:
        return command

    normalized_rest = _drop_pytest_quiet_and_worker_flags(rest)
    # nice(1) is POSIX-only; skip the prefix on Windows to keep commands runnable.
    nice_prefix = [] if sys.platform == "win32" else ["nice", "-n", "15"]
    return shlex.join([*nice_prefix, *prefix, *normalized_rest, "-n", "2", "-q"])


def _drop_pytest_quiet_and_worker_flags(parts: list[str]) -> list[str]:
    """Remove command-level pytest quiet/xdist flags before applying local caps."""
    normalized: list[str] = []
    skip_next = False
    for part in parts:
        if skip_next:
            skip_next = False
            continue
        if part == "-q":
            continue
        if part in {"-n", "--numprocesses"}:
            skip_next = True
            continue
        if part.startswith("-n=") or part.startswith("--numprocesses="):
            continue
        normalized.append(part)
    return normalized


def _select_verification_path(
    *,
    verification: dict[str, Any],
    focused_command: str,
    final_command: str,
    tests_to_run_count: int,
    default_command: str,
) -> tuple[list[str], str, str]:
    """Choose verification steps, strategy label, and hint text."""
    if not verification["test_required"]:
        return (
            ["git diff --check"],
            "docs_only",
            "Docs-only diff; skip pytest unless code changes are added.",
        )
    if focused_command and focused_command != final_command:
        return (
            [focused_command, final_command],
            "focused_then_default",
            "Run focused tests while iterating; run the default suite once at the "
            "queue boundary because unmapped runtime changes remain.",
        )
    if tests_to_run_count > FOCUSED_TEST_COMMAND_LIMIT:
        return (
            [default_command],
            "default_for_large_diff",
            f"{tests_to_run_count} mapped tests exceed the focused command limit "
            f"({FOCUSED_TEST_COMMAND_LIMIT}); use queue-specific focused tests while "
            "editing and run the default suite once at the verification boundary.",
        )
    return (
        [final_command],
        "single_command",
        "Run the recommended verification command for this diff.",
    )


def _append_large_dirty_hint(hint: str, changed_count: int) -> str:
    """Append large-diff guidance without obscuring the primary hint."""
    if changed_count > LARGE_DIRTY_DIFF_THRESHOLD:
        return (
            f"{hint} Large dirty worktree detected ({changed_count} changed files); "
            "avoid rerunning the default suite after every tiny edit."
        )
    return hint


def _ensure_ast_cache(
    project_root: str | None,
    changed_files: list[str],
) -> Any | None:
    """Return an open ASTCache, auto-indexing if the cache is empty or stale.

    Returns None when project_root is None or indexing fails entirely.
    The caller is responsible for calling cache.close() when done.
    """
    if not project_root or not changed_files:
        return None
    try:
        from ....ast_cache import ASTCache

        cache = ASTCache(project_root)
        stats = cache.get_stats()
        if stats.get("total_files", 0) == 0:
            cache.index_project(max_files=2000)
        else:
            from ....incremental_sync import IncrementalSync

            sync = IncrementalSync(cache)
            changes = sync.get_changes()
            if changes["new"] or changes["modified"] or changes["deleted"]:
                sync.sync(max_files=2000)
        return cache
    except Exception:
        logger.debug("AST cache auto-index failed", exc_info=True)
        return None


def _symbol_dict(s: dict[str, Any]) -> dict[str, Any]:
    """Build a compact symbol dict for cache-enrichment output."""
    name = s.get("name") or s.get("text", "")
    return {"name": name, "kind": s.get("kind", "unknown"), "line": s.get("line", 0)}


def _file_symbol_dict(rel: str, symbols: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the enriched file entry for _enrich_with_cache_symbols."""
    valid = [s for s in symbols if s.get("name") or s.get("text")]
    return {
        "file": rel,
        "symbol_count": len(symbols),
        "symbols": [_symbol_dict(s) for s in valid][:50],
    }


def _affected_symbol_dict(rel: str, s: dict[str, Any]) -> dict[str, Any]:
    """Build one result entry for _find_affected_symbols."""
    name = s.get("name") or s.get("text", "")
    return {
        "file": rel,
        "name": name,
        "kind": s.get("kind", "unknown"),
        "line": s.get("line", 0),
    }


def _inject_cs_into_impact(
    fi: dict[str, Any], changed_symbols: list[dict[str, Any]]
) -> None:
    """Inject changed-symbol metadata into a file-impact row (in-place)."""
    rel = fi.get("file", "")
    for cs in changed_symbols:
        if cs["file"] == rel:
            fi["symbols"] = cs["symbols"][:10]
            fi["symbol_count"] = cs["symbol_count"]
            return


def _hot_zone_factor(row: Any) -> dict[str, Any]:
    """Build one hot-zone risk-factor dict from a hot-rows query result."""
    reason = (
        f"hot zone: {row['file_path']} "
        f"symbol_id={row['symbol_id']} "
        f"modified {row['mod_count_30d']} times in 30 days"
    )
    return {
        "factor": "hot_zone",
        "reason": reason,
        "severity": "warn",
        "mod_count_30d": int(row["mod_count_30d"]),
        "file_path": row["file_path"],
    }


def _class_result_dict(
    file_path: str, language: str, class_dict: dict[str, Any]
) -> dict[str, Any]:
    """Build one semantic-classification result entry."""
    return {
        "file": file_path,
        "language": language,
        "change_count": len(class_dict.get("classifications", [])),
        **class_dict,
    }


def _enrich_with_cache_symbols(
    changed_files: list[str],
    cache: Any,
) -> list[dict[str, Any]]:
    """Enrich changed files with symbol-level detail from the AST cache.

    Returns a list of dicts, one per changed file that has indexed symbols,
    with keys: file, symbols (list of {name, kind, line}), symbol_count.
    """
    if cache is None:
        return []
    conn = cache.get_conn()
    enriched: list[dict[str, Any]] = []
    for rel in changed_files:
        try:
            row = conn.execute(
                "SELECT symbols_json FROM ast_index WHERE file_path = ?",
                (rel,),
            ).fetchone()
        except Exception:
            continue
        if row is None:
            continue
        try:
            import json

            sym_data = json.loads(row["symbols_json"])
        except Exception:
            continue
        symbols = sym_data.get("symbols", [])
        if not symbols:
            continue
        enriched.append(_file_symbol_dict(rel, symbols))
    return enriched


def _find_affected_symbols(
    affected_files: set[str],
    cache: Any,
) -> list[dict[str, Any]]:
    """Look up top-level symbols in affected (dependent) files.

    Returns a list of {file, name, kind} for each file that has symbols
    indexed in the cache.  Limited to 200 entries to keep the response small.
    """
    if cache is None or not affected_files:
        return []
    conn = cache.get_conn()
    results: list[dict[str, Any]] = []
    for rel in sorted(affected_files):
        try:
            row = conn.execute(
                "SELECT symbols_json FROM ast_index WHERE file_path = ?",
                (rel,),
            ).fetchone()
        except Exception:
            continue
        if row is None:
            continue
        try:
            import json

            sym_data = json.loads(row["symbols_json"])
        except Exception:
            continue
        for s in sym_data.get("symbols", []):
            name = s.get("name") or s.get("text", "")
            if name and s.get("kind") in (
                "function",
                "class",
                "method",
                "variable",
            ):
                results.append(_affected_symbol_dict(rel, s))
                if len(results) >= 200:
                    return results
    return results


def _build_change_impact_result(request: ChangeImpactRequest) -> dict[str, Any]:
    """Build the full change-impact response for changed files."""
    if _is_test_only_change_set(request.changed_files):
        return _build_test_only_change_impact_result(request)

    graph = _load_dependency_graph(request.project_root)
    affected, file_impacts = _build_file_impacts(request.changed_files, graph)
    risk = _assess_risk(request.changed_files, affected, graph) if graph else "unknown"
    test_mapping, all_tests = _build_test_plan(
        request.changed_files, graph, request.include_tests
    )
    default_test_command = detect_default_test_command(request.project_root)
    verification = _build_verification_plan(
        request.changed_files,
        all_tests,
        test_mapping,
        default_test_command,
    )
    strategy = _build_verification_strategy(
        changed_count=len(request.changed_files),
        tests_to_run=all_tests,
        verification=verification,
        resource_profile=request.resource_profile,
    )
    visible_tests = all_tests[:TESTS_TO_RUN_DISPLAY_LIMIT]

    call_graph_data: dict[str, Any] | None = None
    if request.project_root and request.changed_files:
        cg_result = compute_call_graph_impact(
            request.project_root,
            request.changed_files,
            allow_full_scan=not request.agent_summary_only,
        )
        if cg_result is not None:
            call_graph_data = cg_result.to_dict()
            if call_graph_data.get("high_risk_functions") and risk == "low":
                risk = "medium"

    agent_summary = build_agent_summary(
        AgentSummaryContext(
            risk=risk,
            changed_files=request.changed_files,
            scope_paths=request.scope_paths,
            verification=verification,
            strategy=strategy,
            affected_count=len(affected),
            tests_to_run_count=len(all_tests),
        )
    )

    result = build_change_impact_response(
        ChangeImpactResponseContext(
            request=request,
            risk=risk,
            affected=affected,
            file_impacts=file_impacts,
            visible_tests=visible_tests,
            all_tests=all_tests,
            verification=verification,
            strategy=strategy,
            test_mapping=test_mapping,
            agent_summary=agent_summary,
        )
    )

    if call_graph_data is not None:
        result["call_graph_impact"] = call_graph_data

    # Read temporal hot-zone risk BEFORE the auto-index re-runs — that
    # path would call ``_write_activation_for_file`` for any modified
    # source file and overwrite seeded rows. The verdict bump needs the
    # CURRENT activation state, not the freshly-recomputed one.
    result = _attach_hot_zone_risk(result, request)

    result = _attach_doc_drift_hints(result, request.changed_files)

    if request.agent_summary_only:
        return _attach_constraint_violations(result, request, affected)

    cache = _ensure_ast_cache(request.project_root, request.changed_files)
    try:
        changed_symbols = _enrich_with_cache_symbols(request.changed_files, cache)
        if changed_symbols:
            result["changed_symbols"] = changed_symbols
            total_syms = sum(f["symbol_count"] for f in changed_symbols)
            result["changed_symbol_count"] = total_syms
            for fi in file_impacts:
                _inject_cs_into_impact(fi, changed_symbols)
        affected_symbols = _find_affected_symbols(affected, cache)
        if affected_symbols:
            result["affected_symbols"] = affected_symbols
            result["affected_symbol_count"] = len(affected_symbols)
    except Exception:
        logger.debug("AST cache enrichment failed", exc_info=True)
    finally:
        if cache is not None:
            try:
                cache.close()
            except Exception:
                pass

    return _attach_constraint_violations(result, request, affected)


# Per Feature 2 spec — symbols modified >= this many times in 30 days are
# flagged as hot zones, which forces verdict at least CAUTION.
_HOT_ZONE_THRESHOLD = 5


def _attach_hot_zone_risk(
    result: dict[str, Any],
    request: ChangeImpactRequest,
) -> dict[str, Any]:
    """Decorate the change-impact result with temporal hot-zone risk factors.

    For each changed file we look up its symbols in
    ``ast_symbol_activation``. Any symbol with ``mod_count_30d >=
    _HOT_ZONE_THRESHOLD`` is treated as a "hot zone" — editing recently-
    churning code is higher risk than a stable one-off change.

    Two effects:
      1. A risk_factors entry containing the substring ``hot zone`` is
         appended (key is ``factor`` per existing schema; ``reason``
         carries human-readable detail).
      2. The verdict is promoted to ``CAUTION`` if it was looser (INFO /
         REVIEW). Constraint violations may further escalate to UNSAFE
         later via ``_attach_constraint_violations`` — that path wins.
    """
    if not request.changed_files or not request.project_root:
        result.setdefault("risk_factors", result.get("risk_factors", []))
        return result

    hot_rows = _hot_zone_symbols_for_files(request.project_root, request.changed_files)
    existing_factors = list(result.get("risk_factors", []) or [])
    if not hot_rows:
        result["risk_factors"] = existing_factors
        return result

    for row in hot_rows:
        existing_factors.append(_hot_zone_factor(row))
    result["risk_factors"] = existing_factors
    # Bump verdict — CAUTION wins over INFO / REVIEW. UNSAFE may later
    # win via constraint-violation escalation; we never downgrade.
    current = result.get("verdict", "INFO")
    if current not in ("CAUTION", "UNSAFE"):
        result["verdict"] = "CAUTION"
        summary = result.get("agent_summary")
        if isinstance(summary, dict):
            summary["verdict"] = "CAUTION"
    return result


def _hot_zone_symbols_for_files(
    project_root: str,
    changed_files: list[str],
) -> list[dict[str, Any]]:
    """Return per-symbol activation rows above the hot-zone threshold.

    Reads ``ast_symbol_activation`` from the project's cache DB; returns
    [] on missing table / missing DB so the gate tool keeps working on
    fresh repos. Each row carries ``symbol_id``, ``file_path``, and
    ``mod_count_30d``.
    """
    if not changed_files:
        return []
    db_path = Path(project_root) / ".ast-cache" / "index.db"
    if not db_path.is_file():
        return []

    placeholders = ",".join(["?"] * len(changed_files))
    # placeholders is constructed from `?` literals only — values flow through
    # parameterized binds below, so the f-string is safe.
    sql = (
        "SELECT symbol_id, file_path, mod_count_30d "  # nosec B608
        "FROM ast_symbol_activation "
        f"WHERE file_path IN ({placeholders}) "
        "AND mod_count_30d >= ? "
        "ORDER BY mod_count_30d DESC"
    )
    import sqlite3

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, [*changed_files, _HOT_ZONE_THRESHOLD]).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError as exc:
        logger.debug("hot zone lookup failed: %s", exc)
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


_CLI_SURFACE_FILES = frozenset(
    {
        "tree_sitter_analyzer/cli_main.py",
        "tree_sitter_analyzer/cli/argument_parser_builder.py",
        "tree_sitter_analyzer/mcp/_tool_registry.py",
    }
)
# Directories that, when any .py file changes, indicate CLI surface edits.
_CLI_SURFACE_PREFIXES = ("tree_sitter_analyzer/cli/argument_groups/",)
# Files that contribute to facade-actions.md generation but live outside mcp/tools/.
_FACADE_DOC_FILES = frozenset(
    {
        "tree_sitter_analyzer/mcp/facade_map.py",
        "tree_sitter_analyzer/mcp/_tool_registry.py",
    }
)
_FACADE_TOOL_PREFIX = "tree_sitter_analyzer/mcp/tools/"
_FACADE_TOOL_EXCLUDE = frozenset(
    {
        "tree_sitter_analyzer/mcp/tools/utils",
        "tree_sitter_analyzer/mcp/tools/__pycache__",
    }
)


def _attach_doc_drift_hints(
    result: dict[str, Any],
    changed_files: list[str],
) -> dict[str, Any]:
    """Append deterministic doc-drift verification steps for known CLI/MCP surfaces.

    Resolves Issue #732: when CLI argument registration or facade action
    parameters change, change-impact must surface the follow-up obligations:
    - cli_main.py / argument_groups/*.py / _tool_registry.py → README count contracts
    - mcp/tools/*.py / facade_map.py / _tool_registry.py → facade-actions.md regen
    """
    normalized = [f.replace("\\", "/") for f in changed_files]
    cli_changed = any(
        f in _CLI_SURFACE_FILES
        or any(f.startswith(pfx) and f.endswith(".py") for pfx in _CLI_SURFACE_PREFIXES)
        for f in normalized
    )
    facade_changed = any(
        f in _FACADE_DOC_FILES
        or (
            f.startswith(_FACADE_TOOL_PREFIX)
            and not any(f.startswith(ex) for ex in _FACADE_TOOL_EXCLUDE)
            and f.endswith(".py")
        )
        for f in normalized
    )

    extra_steps: list[str] = []
    if cli_changed:
        extra_steps.append(
            "uv run pytest tests/governance/test_postmortem_guards.py::test_readme_counts_match_registry -x"
        )
    if facade_changed:
        extra_steps.append(
            "uv run python scripts/generate_facade_actions_doc.py && "
            "uv run pytest tests/unit/docs/test_facade_actions_doc_drift.py -x"
        )

    if not extra_steps:
        return result

    result["doc_drift_checks"] = extra_steps
    # Append to the top-level verification_steps list that agents consume.
    # (verification_strategy is a string label, not a nested dict.)
    steps = result.get("verification_steps") or []
    result["verification_steps"] = list(steps) + extra_steps
    return result


def _attach_constraint_violations(
    result: dict[str, Any],
    request: ChangeImpactRequest,
    affected: set[str],
) -> dict[str, Any]:
    """Decorate the change-impact result with persisted constraint violations.

    Two effects (per Feature 3 spec):

    1. Always add a ``constraint_violations`` field (possibly empty)
       so agent callers can branch on its presence rather than catching
       KeyError. Cheap to compute on a fresh repo: the lookup short-
       circuits when the DB doesn't exist.

    2. When error-severity violations touch the diff (caller_file or
       callee_file is in changed_files OR the affected blast radius),
       promote the verdict to UNSAFE. Warn-only → CAUTION. "Diff says
       SAFE but constraints say UNSAFE" is the failure mode the spec
       explicitly cannot ship.
    """
    candidate_files = set(request.changed_files) | set(affected or set())
    if not candidate_files:
        result.setdefault("constraint_violations", [])
        return result

    rows = violations_for_files(request.project_root, candidate_files)
    cv_payload = [constraint_risk_factor(r) for r in rows]
    result["constraint_violations"] = cv_payload

    new_verdict = verdict_from_violations(rows)
    if new_verdict is not None:
        result["verdict"] = new_verdict
        summary = result.get("agent_summary")
        if isinstance(summary, dict):
            summary["verdict"] = new_verdict
    return result


_build_no_changes_result = build_no_changes_result
_build_agent_summary = build_agent_summary
_build_change_impact_response = build_change_impact_response


def _classify_changed_files(
    changed_files: list[str],
    project_root: str | None,
) -> list[dict[str, Any]]:
    """Run semantic_classify over a list of changed files; best-effort.

    Used by change_impact to attach a per-file semantic_change summary when
    callers opt in. Returns an empty list when:
      - no files provided
      - project_root is None (we need it to git-show old sources)
      - any individual file fails to classify (we skip, don't raise)

    Each result row mirrors the SemanticClassifyTool response shape so
    downstream agents can branch on the same keys (dominant_category,
    risk_level, change_count).
    """
    if not changed_files or not project_root:
        return []

    try:
        from ....ast_diff import ASTDiffer
        from ....project_graph import _language_from_ext
        from ....semantic_change_classifier import SemanticChangeClassifier
    except Exception:
        # If any of the required modules can't be imported (e.g. in a
        # bare-minimum install), degrade silently to "no semantic data".
        return []

    differ = ASTDiffer()
    results: list[dict[str, Any]] = []
    for file_path in changed_files:
        language = _language_from_ext(file_path) or ""
        if not language:
            continue
        try:
            import subprocess  # nosec B404 - fixed git command

            old_proc = subprocess.run(  # nosec B603,B607
                ["git", "show", f"HEAD:{file_path}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
                cwd=project_root,
            )
            old_source = old_proc.stdout if old_proc.returncode == 0 else ""
            new_path = Path(project_root) / file_path
            if new_path.is_file():
                new_source = new_path.read_text("utf-8", "replace")
            else:
                new_source = ""
            diff = differ.diff_strings(
                old_source=old_source,
                new_source=new_source,
                language=language,
                old_file=file_path,
                new_file=file_path,
            )
            classification = SemanticChangeClassifier(file_path=file_path).classify(
                diff
            )
            class_dict = classification.to_dict()
            results.append(_class_result_dict(file_path, language, class_dict))
        except Exception:
            # One bad file should not poison the whole batch.
            continue
    return results
