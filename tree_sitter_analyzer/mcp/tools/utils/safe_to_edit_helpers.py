"""Shared helpers for safe-to-edit reports."""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ....health_scorer import HealthScorer
from ....security.fixture_detector import fixture_to_verdict, is_fixture
from ..file_health_tool import _build_signal
from .constraint_violation_query import (
    constraint_risk_factor,
    verdict_from_violations,
    violations_for_files,
)
from .safe_to_edit_risk import build_checklist, compute_risk
from .test_discovery import find_test_files
from .verification_command import build_test_command, detect_default_test_command


@dataclass(frozen=True)
class SafeToEditContext:
    """Inputs needed to build a safe-to-edit response.

    ``snapshot_conn`` is the certified index-snapshot connection on the
    read_existing route; when set, constraint violations are read from the
    snapshot and fixture detection runs read-only (Codex P1 #1299: the
    certified route must never open or write the live ``.ast-cache``).
    """

    file_path: str
    edit_type: str
    resolved_path: str
    project_root: str
    graph: Any
    scorer: HealthScorer
    snapshot_conn: Any | None = None


class FileDependencyView:
    """Small graph-like view for one file's immediate import surface."""

    def __init__(
        self,
        *,
        rel_path: str,
        dependencies: set[str],
        dependents: set[str],
    ) -> None:
        self._nodes = {rel_path, *dependencies, *dependents}
        self._deps = {rel_path: dependencies}
        self._dependents = {rel_path: dependents}

    def has_node(self, file_rel: str) -> bool:
        """Return True if *file_rel* is a node in this view (O(1) set lookup)."""
        return file_rel in self._nodes

    def node_count(self) -> int:
        """Return the number of nodes in this view."""
        return len(self._nodes)

    def nodes(self) -> list[str]:
        """Return all nodes as a sorted list."""
        return sorted(self._nodes)

    def dependencies_of(self, file_rel: str) -> list[str]:
        return sorted(self._deps.get(file_rel, set()))

    def dependents_of(self, file_rel: str) -> list[str]:
        return sorted(self._dependents.get(file_rel, set()))


@dataclass(frozen=True)
class AgentWorkflowContext:
    """Inputs needed to build the structured agent edit workflow.

    ``certified`` (Codex P2 #1299 round-6): on snapshot-certified routes the
    workflow's default test command must not be derived from live
    non-inventoried config files (package.json/go.mod/...) that can drift
    for the same snapshot identity.
    """

    file_path: str
    risk: str
    edit_type: str
    has_tests: bool
    test_files: list[str]
    health_grade: str
    project_root: str
    certified: bool = False


@dataclass(frozen=True)
class SafeToEditFacts:
    """Derived data for a safe-to-edit response."""

    dependents: list[str]
    dependencies: list[str]
    health: Any
    test_files: list[str]
    has_tests: bool
    risk: str
    risk_factors: list[dict[str, str]]
    pre_edit_checklist: list[str]


def build_safe_to_edit_result(context: SafeToEditContext) -> dict[str, Any]:
    """Build the MCP response payload for a safe-to-edit request."""
    facts = _collect_safe_to_edit_facts(context)
    return _format_safe_to_edit_result(context, facts)


def _collect_safe_to_edit_facts(context: SafeToEditContext) -> SafeToEditFacts:
    """Collect graph, health, test, and risk facts for a file."""
    # Canonicalize before relativising: on macOS the security validator's
    # abspath (/var/folders/...) and a canonical project_root
    # (/private/var/folders/...) differ by symlink, which would make
    # to_relative fall back to the absolute path and miss every graph node
    # (CLAUDE.md §2 resolution contract) — downstream facts would silently
    # undercount on macOS while Linux CI saw them.
    rel_path = to_relative(
        os.path.realpath(context.resolved_path), context.project_root
    )
    dependents = safe_dependents(context.graph, rel_path)
    dependencies = safe_dependencies(context.graph, rel_path)
    if context.snapshot_conn is not None:
        # Codex P1 (#1299 round-3/4): test facts must come from inventory-
        # covered paths only — discovery runs over the snapshot's ast_index
        # set, so oracle-excluded files (tests/vendor/) can neither fill the
        # discovery cap nor change has_tests/verdict for the same identity.
        inventory = snapshot_inventory(context.snapshot_conn)
        test_files = _certified_test_files(inventory, rel_path, dependents)
        test_files.extend(
            _certified_symbol_reference_tests(
                context.snapshot_conn, inventory, rel_path, _target_language(rel_path)
            )
        )
        test_files = list(dict.fromkeys(test_files))[:10]
        certified_health = True
    else:
        test_files = find_test_files(context.resolved_path, context.project_root)
        certified_health = False
    health = context.scorer.score_file(
        context.resolved_path,
        fast_dependencies=True,
        certified=certified_health,
    )
    has_tests = bool(test_files)
    risk, risk_factors = compute_risk(
        forward_count=len(dependents),
        dep_count=len(dependencies),
        health_grade=health.grade,
        has_tests=has_tests,
        edit_type=context.edit_type,
        is_init_file=is_init_file(context.resolved_path),
    )
    pre_edit_checklist = build_checklist(
        risk,
        len(dependents),
        has_tests,
        test_files,
        context.edit_type,
        health_grade=health.grade,
        file_path=context.file_path,
        project_root=context.project_root,
        certified=context.snapshot_conn is not None,
    )
    return SafeToEditFacts(
        dependents=dependents,
        dependencies=dependencies,
        health=health,
        test_files=test_files,
        has_tests=has_tests,
        risk=risk,
        risk_factors=risk_factors,
        pre_edit_checklist=pre_edit_checklist,
    )


def _format_safe_to_edit_result(
    context: SafeToEditContext,
    facts: SafeToEditFacts,
) -> dict[str, Any]:
    """Format the public safe-to-edit response."""
    workflow_context = AgentWorkflowContext(
        file_path=context.file_path,
        risk=facts.risk,
        edit_type=context.edit_type,
        has_tests=facts.has_tests,
        test_files=facts.test_files,
        health_grade=facts.health.grade,
        project_root=context.project_root,
        certified=context.snapshot_conn is not None,
    )
    workflow = build_agent_workflow(workflow_context)
    # ``risk_level`` is the canonical field; ``verdict`` mirrors it for
    # symmetry with modification_guard's API (both tools answer the
    # same question — "is this safe to edit?"). ``recommendation`` is
    # the one-line human-readable next step distilled from the
    # workflow's first ``next_step``.
    risk = facts.risk
    base_verdict = _risk_to_verdict(risk)
    # Constraint violations promote the verdict: an error-severity
    # violation referencing this file forces UNSAFE; warn-only forces
    # CAUTION. The base_verdict (derived from risk_level) is the floor.
    if context.snapshot_conn is not None:
        # Codex P1 (#1299): the certified read_existing route runs the
        # certified fixture probe — never the live .ast-cache DB and never
        # the live allowlist/cache (both are outside the source generation
        # and could drift after snapshot publication). The inventory
        # restriction keeps the fixture scan on generation-certified test
        # files only (round-3: oracle-pruned paths such as tests/vendor/
        # must not influence escalation). Constraint rows are OMITTED on
        # the certified route: reindexing stamps the manifest without
        # recomputing ast_constraint_violations, so the rows cannot prove
        # they match the published generation (round-4; an evaluation epoch
        # bound to the index generation is the tracked follow-up).
        violations: list[dict[str, Any]] = []
        fixture_inventory = snapshot_inventory(context.snapshot_conn)
        fixture_certified = True
    else:
        violations = violations_for_files(
            context.project_root, [_relative_for_constraints(context)]
        )
        fixture_inventory = None
        fixture_certified = False
    constraint_verdict = verdict_from_violations(violations)
    # P3: also check whether the file is a registered test fixture; that
    # promotes the verdict on top of any constraint-derived escalation.
    # The chokepoint design (see PRD §P3) is "every override flows
    # through _max_verdict" — so chaining is the only safe composition.
    fixture_fact = is_fixture(
        context.resolved_path,
        context.project_root,
        certified=fixture_certified,
        inventory=fixture_inventory,
    )
    fixture_verdict = fixture_to_verdict(fixture_fact)
    verdict = _max_verdict(
        _max_verdict(base_verdict, constraint_verdict), fixture_verdict
    )
    risk_factors = list(facts.risk_factors)
    if violations:
        risk_factors.extend(constraint_risk_factor(row) for row in violations)
    if fixture_fact.is_fixture:
        risk_factors.append(_fixture_risk_factor(fixture_fact, context.file_path))
    # #1027: build the recommendation from the FINAL (possibly escalated)
    # verdict, never the un-escalated ``risk``. A constraint/fixture
    # promotion that lifts SAFE→UNSAFE must lift the recommendation too,
    # otherwise the envelope self-contradicts (verdict=UNSAFE next to a
    # "SAFE to edit" recommendation) and an agent reads opposite instructions.
    recommendation = _format_recommendation(verdict, facts, workflow)
    # #781: pass the (possibly escalated) verdict so summary_line AND
    # summary["verdict"] are both built from it — never a CAUTION/UNSAFE split.
    summary = build_agent_summary(workflow_context, workflow, verdict_override=verdict)
    return {
        "success": True,
        "file_path": context.file_path,
        "risk_level": risk,
        "verdict": verdict,
        "recommendation": recommendation,
        "agent_summary": summary,
        "risk_factors": risk_factors,
        "health_grade": facts.health.grade,
        "health_score": facts.health.total,
        "health_signal": _build_signal(facts.health.dimensions),
        "downstream_files": facts.dependents[:20],
        "downstream_count": len(facts.dependents),
        "dependencies": facts.dependencies[:10],
        "dependency_count": len(facts.dependencies),
        "test_files_nearby": facts.test_files,
        "pre_edit_checklist": facts.pre_edit_checklist,
        "agent_workflow": workflow,
    }


def _relative_for_constraints(context: SafeToEditContext) -> str:
    """Return the project-relative path that constraint rows are keyed on.

    Constraint rows store relative paths (e.g. ``tree_sitter_analyzer/...``).
    On macOS, ``resolved_path`` may be ``/private/tmp/...`` while
    ``project_root`` is ``/tmp/...`` due to the ``/var → /private/var``
    symlink. Try the input ``file_path`` first (already relative), then
    fall back to the strict ``to_relative`` for safety.
    """
    if not Path(context.file_path).is_absolute():
        return context.file_path
    # Both resolved through realpath to align symlinked tmp paths.
    try:
        root_real = Path(context.project_root).resolve()
        resolved_real = Path(context.resolved_path).resolve()
        return str(resolved_real.relative_to(root_real))
    except (ValueError, OSError):
        return to_relative(context.resolved_path, context.project_root)


# Verdict severity order — higher index = more severe. Used to promote
# the safe_to_edit verdict when constraint violations imply a stricter
# answer than the risk-level-derived one.
_VERDICT_SEVERITY: dict[str, int] = {
    "SAFE": 0,
    "INFO": 0,
    "REVIEW": 1,
    "CAUTION": 2,
    "UNSAFE": 3,
    "ERROR": 3,
}


def _max_verdict(base: str, override: str | None) -> str:
    """Return whichever verdict is more severe, preferring the override on ties."""
    if not override:
        return base
    base_rank = _VERDICT_SEVERITY.get(base, 0)
    override_rank = _VERDICT_SEVERITY.get(override, 0)
    return override if override_rank >= base_rank else base


def _risk_to_verdict(risk: str) -> str:
    """Map ``risk_level`` to the modification_guard verdict vocabulary.

    safe → SAFE; caution → CAUTION; dangerous / high → UNSAFE.
    """
    risk_lower = (risk or "").lower()
    if risk_lower in ("dangerous", "high", "unsafe"):
        return "UNSAFE"
    if risk_lower in ("caution", "medium"):
        return "CAUTION"
    return "SAFE"


def _fixture_risk_factor(fact: Any, file_path: str) -> dict[str, Any]:
    """Build a ``risk_factors`` entry for a detected test-fixture file.

    Mirrors the shape of :func:`constraint_risk_factor` — a flat dict
    with ``factor`` / ``reason_code`` / ``detail`` plus evidence so the
    consumer agent can verify without a second tool call. See PRD §P3
    and ``feedback_test-fixture-files`` for why this needs to land in
    the response envelope (and not just the verdict).
    """

    return {
        "factor": "test_fixture",
        "reason_code": "TEST_FIXTURE",
        "confidence": fact.confidence,
        "source": fact.source,
        "evidence": list(fact.evidence),
        "note": fact.note,
        "detail": (
            f"{file_path} is referenced as a test fixture (confidence "
            f"{fact.confidence:.2f}, source {fact.source}). Refactoring "
            "this file will likely break the tests in the evidence "
            "list — edit the test references first."
        ),
    }


def _format_recommendation(
    verdict: str,
    facts: SafeToEditFacts,
    workflow: dict[str, Any],
) -> str:
    """One-line agent-readable summary of what to do next.

    #1027: built from the FINAL (possibly escalated) verdict so it can never
    contradict the structured ``verdict`` field. ``ERROR`` collapses into the
    UNSAFE bucket and ``REVIEW`` into the CAUTION bucket (mirroring
    ``_VERDICT_SEVERITY``); everything else is the SAFE bucket.
    """
    grade = facts.health.grade
    downstream = len(facts.dependents)
    verdict = (verdict or "").lower()
    if verdict in ("unsafe", "error"):
        return (
            f"UNSAFE to edit: health grade {grade}, {downstream} downstream "
            f"file(s) depend on this. Refactor in stages with tests after each."
        )
    if verdict in ("caution", "review"):
        return (
            f"CAUTION: health grade {grade}, {downstream} downstream file(s). "
            "Run tests in the affected scope before and after the edit."
        )
    return (
        f"SAFE to edit (health {grade}, {downstream} downstream). "
        "Standard test pass after the edit is sufficient."
    )


def build_agent_summary(
    context: AgentWorkflowContext,
    workflow: dict[str, Any],
    verdict_override: str | None = None,
) -> dict[str, Any]:
    """Build the compact first-read decision summary for agents.

    N1 (round-27): include ``summary_line`` + ``verdict`` so the
    cross-tool envelope contract (``TestEnvelopeContractSnapshot``) is
    satisfied. ``mirror_summary_line`` then copies the line to the
    top-level envelope for direct callers that bypass the dispatch hook.

    #781: ``verdict_override`` lets the caller pass an escalated verdict (from a
    constraint-violation or fixture promotion) so it flows into BOTH the
    ``summary_line`` and ``summary["verdict"]`` — the one-line decision surface
    must never disagree with the structured verdict.
    """
    before = workflow["before_edit_commands"]
    after = workflow["after_edit_commands"]
    boundary = workflow["queue_boundary_commands"]
    # verdict_override is a floor-raiser (escalation), never a downgrade:
    # _max_verdict keeps the more severe of the risk-derived base and the
    # override (and tolerates a None override), so a future caller can't use it
    # to silently lower the verdict below the risk level.
    verdict = _max_verdict(_risk_to_verdict(context.risk), verdict_override)
    summary_line = (
        f"{context.file_path} risk={context.risk} verdict={verdict} "
        f"health={context.health_grade} "
        f"tests={'yes' if context.has_tests else 'no'}"
    )
    summary = {
        "summary_line": summary_line,
        "verdict": verdict,
        "risk": context.risk,
        "edit_strategy": workflow["edit_strategy"],
        "next_step": _agent_next_step(context, workflow),
        "verification_command": after[0]
        if after
        else (boundary[0] if boundary else ""),
        "stop_condition": _agent_stop_condition(context, workflow),
    }
    if before:
        summary["preflight_command"] = before[0]
    if boundary:
        summary["queue_boundary_command"] = boundary[0]
    if workflow["guardrails"]:
        summary["guardrails"] = workflow["guardrails"]
    return summary


def build_agent_workflow(context: AgentWorkflowContext) -> dict[str, Any]:
    """Build a machine-friendly edit workflow for autonomous agents."""
    if context.certified:
        # Codex P2 (#1299 round-6/7/8): snapshot-bound default — live config
        # detection would read non-inventoried files, so the runner is
        # inferred from the target's extension; ambiguous ecosystems omit
        # the command entirely (None) rather than guessing.
        from .verification_command import certified_default_test_command

        default_command = certified_default_test_command(context.file_path)
    else:
        default_command = detect_default_test_command(context.project_root)
    focused_command = (
        build_test_command(default_command, context.test_files)
        if context.has_tests and default_command is not None
        else ""
    )
    boundary_command = default_command.command if default_command is not None else ""
    quoted_path = shlex.quote(context.file_path)
    pre_edit_commands = [focused_command] if focused_command else []
    post_edit_commands = [
        command
        for command in (
            focused_command or boundary_command,
            (
                "uv run python -m tree_sitter_analyzer "
                f"{quoted_path} --file-health --format json"
            ),
            "uv run python -m tree_sitter_analyzer --change-impact --format json",
        )
        if command
    ]

    return {
        "edit_strategy": _edit_strategy(context.risk, context.edit_type),
        "before_edit_commands": pre_edit_commands,
        "after_edit_commands": post_edit_commands,
        "queue_boundary_commands": [boundary_command] if boundary_command else [],
        "guardrails": _agent_guardrails(
            context.risk,
            context.edit_type,
            context.health_grade,
            context.has_tests,
        ),
    }


def _edit_strategy(risk: str, edit_type: str) -> str:
    """Return a compact edit strategy label for agents."""
    if risk == "dangerous":
        return "split_into_atomic_edits"
    if edit_type == "rename":
        return "trace_references_before_edit"
    if risk == "caution":
        return "focused_edit_with_tests"
    return "direct_focused_edit"


def _agent_guardrails(
    risk: str,
    edit_type: str,
    health_grade: str,
    has_tests: bool,
) -> list[str]:
    """Return concise guardrails for an autonomous edit."""
    guardrails: list[str] = []
    if risk == "dangerous":
        guardrails.append("do not expand scope; split work into smaller edits")
    if edit_type == "refactor":
        guardrails.append("preserve public API signatures")
    if edit_type == "rename":
        guardrails.append("find and update all references before verification")
    if health_grade in {"D", "F"}:
        guardrails.append("run refactoring_suggestions before editing")
    if not has_tests:
        guardrails.append("add or identify verification before changing behavior")
    return guardrails


def _agent_next_step(
    context: AgentWorkflowContext,
    workflow: dict[str, Any],
) -> str:
    """Return one immediate action for the safe-to-edit decision."""
    before = workflow["before_edit_commands"]
    if context.risk == "dangerous":
        return "Split this edit into smaller scoped changes before editing."
    if before:
        return f"Run pre-edit verification first: {before[0]}"
    if not context.has_tests:
        return "Identify verification before changing behavior."
    return "Proceed with a focused edit."


def _agent_stop_condition(
    context: AgentWorkflowContext,
    workflow: dict[str, Any],
) -> str:
    """Describe when this edit queue can be considered safe to close."""
    after = workflow["after_edit_commands"]
    boundary = workflow["queue_boundary_commands"]
    verify = after[0] if after else (boundary[0] if boundary else "")
    if context.risk == "dangerous":
        return "Each smaller edit passes focused verification before scope expands."
    if verify and boundary and verify != boundary[0]:
        return f"{verify} passes; run {boundary[0]} at the queue boundary."
    if verify:
        return f"{verify} exits successfully."
    return "A concrete verification command has been identified and run."


def to_relative(abs_path: str, project_root: str) -> str:
    """Return a path relative to the project root when possible."""
    try:
        return str(Path(abs_path).relative_to(project_root))
    except ValueError:
        return abs_path


_DEPENDENCY_SKIP_DIRS = frozenset(
    {
        "node_modules",
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        "htmlcov",
        ".cache",
        ".eggs",
        ".idea",
        ".vscode",
        ".claude",
    }
)
_DEPENDENCY_SOURCE_EXTS = frozenset(
    {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".c", ".cpp", ".h"}
)


def build_file_dependency_view(
    resolved_path: str, project_root: str
) -> FileDependencyView:
    """Build a fast graph-like dependency view for one file.

    ``safe_to_edit`` is latency-sensitive. A whole-project tree-sitter
    dependency graph is useful, but cold-building it for every MCP process
    makes the common pre-edit check too slow. This view keeps the same lookup
    contract while limiting work to the target file plus a pruned text scan for
    obvious importers.
    """
    root = Path(project_root).resolve()
    target = Path(resolved_path).resolve()
    rel_path = to_relative(str(target), str(root)).replace("\\", "/")
    dependencies = _target_dependencies(target, rel_path, root)
    dependents = _target_dependents(target, rel_path, root)
    return FileDependencyView(
        rel_path=rel_path,
        dependencies=dependencies,
        dependents=dependents,
    )


def _target_dependencies(target: Path, rel_path: str, root: Path) -> set[str]:
    try:
        source = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()

    dependencies: set[str] = set()
    for spec in _extract_import_specs(source, target.suffix.lower()):
        resolved = _resolve_import_spec(spec, rel_path, root)
        if resolved:
            dependencies.add(resolved)
    return dependencies


def _target_dependents(target: Path, rel_path: str, root: Path) -> set[str]:
    needles = _import_needles_for_target(rel_path)
    if not needles:
        return set()

    dependents: set[str] = set()
    for path in _iter_dependency_source_files(root):
        if path == target:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(needle in text for needle in needles):
            dependents.add(to_relative(str(path), str(root)).replace("\\", "/"))
    return dependents


def _iter_dependency_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in _DEPENDENCY_SKIP_DIRS and not name.startswith(".")
        ]
        for filename in filenames:
            if filename.startswith("."):
                continue
            if Path(filename).suffix.lower() in _DEPENDENCY_SOURCE_EXTS:
                files.append(Path(dirpath) / filename)
    return files


def _extract_import_specs(source: str, suffix: str) -> set[str]:
    specs: set[str] = set()
    if suffix == ".py":
        specs.update(re.findall(r"^\s*import\s+([A-Za-z_][\w.]*)", source, re.M))
        specs.update(re.findall(r"^\s*from\s+([.\w]+)\s+import\b", source, re.M))
    elif suffix in {".js", ".jsx", ".ts", ".tsx"}:
        specs.update(re.findall(r"\bfrom\s+['\"]([^'\"]+)['\"]", source))
        specs.update(re.findall(r"\brequire\(\s*['\"]([^'\"]+)['\"]\s*\)", source))
    elif suffix == ".java":
        specs.update(re.findall(r"^\s*import\s+([\w.]+);", source, re.M))
    return specs


def _resolve_import_spec(spec: str, rel_path: str, root: Path) -> str | None:
    if not spec or spec.startswith(".."):
        return None
    if spec.startswith("."):
        base = Path(rel_path).parent
        candidate_base = (base / spec.lstrip("./")).as_posix()
    else:
        candidate_base = spec.replace(".", "/")

    candidates = [
        candidate_base,
        f"{candidate_base}.py",
        f"{candidate_base}.js",
        f"{candidate_base}.ts",
        f"{candidate_base}.tsx",
        f"{candidate_base}.java",
        f"{candidate_base}/__init__.py",
        f"{candidate_base}/index.js",
        f"{candidate_base}/index.ts",
    ]
    for candidate in candidates:
        if (root / candidate).is_file():
            return candidate
    return None


def _import_needles_for_target(rel_path: str) -> set[str]:
    path = Path(rel_path)
    suffix = path.suffix
    without_suffix = path.with_suffix("").as_posix()
    module = without_suffix.replace("/", ".")
    basename = path.stem
    needles = {without_suffix, module}
    if suffix == ".py" and path.name == "__init__.py":
        package = path.parent.as_posix()
        needles.add(package)
        needles.add(package.replace("/", "."))
    if basename and basename != "__init__":
        needles.add(basename)
    return {needle for needle in needles if needle}


def _require_edges_callee_name(conn: Any) -> None:
    """Raise ``CORRUPT_INDEX`` when ``edges`` exists but lacks ``callee_name``.

    The snapshot reader's pass 1 selects ``edges.callee_name``; a partially
    migrated or damaged index would otherwise make that query fail inside the
    broad degrade handler, returning an empty dependency view and
    undercounting risk instead of classifying the snapshot as incompatible.
    """

    try:
        table_row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='edges' LIMIT 1"
        ).fetchone()
        if table_row is None:
            return  # legacy schema without the table: degrade to empty
        columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(edges)").fetchall()
        }
    except Exception:  # nosec B110 — unreadable conn degrades to legacy
        return
    if "callee_name" not in columns:
        raise ValueError("CORRUPT_INDEX")


def _target_language(rel_path: str) -> str:
    """Return the test-discovery language name for one relative path."""

    from .test_discovery import detect_language_from_ext

    return detect_language_from_ext(Path(rel_path).suffix.lower()) or "python"


def _looks_like_test_name(name: str, language: str) -> bool:
    """Mirror is_existing_test_file's NAME conventions over certified inputs.

    The certified route has no filesystem to probe (and oracle-excluded
    paths must not influence facts), so only the file-name conventions of
    :func:`test_discovery_predicates.is_existing_test_file` are applied.
    Unknown languages (never produced by the current extension map, but
    possible after a future plugin addition) return False — the honest
    "not recognized as a test" answer.
    """

    if language == "python":
        return name.endswith(("_test.py", "_tests.py")) or name.startswith("test_")
    if language == "go":
        return name.endswith("_test.go")
    if language == "rust":
        return name.endswith(("_test.rs", "_tests.rs"))
    if language == "java":
        return name.endswith(("Test.java", "Tests.java"))
    if language == "javascript":
        return name.endswith((".test.js", ".spec.js", ".test.jsx"))
    if language == "typescript":
        return name.endswith((".test.ts", ".spec.ts", ".test.tsx"))
    if language == "c":
        return name.startswith("test_") and name.endswith((".c", ".h"))
    if language == "cpp":
        return name.startswith("test_") and name.endswith((".cpp", ".hpp"))
    if language == "csharp":
        return name.endswith(("Test.cs", "Tests.cs"))
    if language == "kotlin":
        return name.endswith(("Test.kt", "Tests.kt"))
    if language == "ruby":
        return name.endswith(("_test.rb", "_spec.rb")) or name.startswith("test_")
    if language == "php":
        return name.endswith(("Test.php", "test.php"))
    return False


def _certified_symbol_reference_tests(
    conn: Any, inventory: frozenset[str], rel_path: str, language: str
) -> list[str]:
    """Symbol-reference test discovery over snapshot-owned data.

    The legacy ``_find_symbol_reference_tests`` scans live test bytes for
    the target's public symbols; the certified variant (Codex P2 #1299
    round-7, C31) scans the snapshot's recorded import statements
    (``imports_json``) of inventory-covered, test-named files for the
    target's INDEXED public symbol names — tests that use ``from pkg
    import public_fn`` are found even when they import a package, not the
    defining file.
    """

    import json as _json

    try:
        target_row = conn.execute(
            "SELECT symbols_json FROM ast_index WHERE file_path = ?",
            (rel_path,),
        ).fetchone()
    except Exception:  # nosec B110 — legacy schema degrades to no matches
        return []
    if target_row is None:
        return []
    symbols: set[str] = set()
    try:
        payload = _json.loads(str(target_row["symbols_json"]))
    except (TypeError, ValueError):
        return []
    if not isinstance(payload, dict):
        # Codex P2 (#1299 round-8, C34): valid JSON of the wrong top-level
        # shape must degrade, never crash with AttributeError outside the
        # classified exception set.
        return []
    for entry in payload.get("symbols", []):
        name = entry.get("name") if isinstance(entry, dict) else None
        if isinstance(name, str) and not name.startswith("_"):
            symbols.add(name)
    if not symbols:
        return []

    results: list[str] = []
    for rel in sorted(inventory):
        if rel == rel_path:
            continue
        if not _looks_like_test_name(Path(rel).name, language):
            continue
        try:
            row = conn.execute(
                "SELECT imports_json FROM ast_index WHERE file_path = ?",
                (rel,),
            ).fetchone()
        except Exception:  # nosec B110 — legacy schema degrades per row
            continue
        if row is None:
            continue
        # Codex P2 (#1299 round-8, C33): match symbols against the PARSED
        # import identifiers, never the serialized cell — substrings and
        # JSON keys (e.g. a symbol 'text' matching every record's "text"
        # key) would otherwise produce false has_tests=True.
        try:
            records = _json.loads(str(row["imports_json"]))
        except (TypeError, ValueError):
            continue
        if not isinstance(records, list):
            continue
        for record in records:
            text = record.get("text") if isinstance(record, dict) else None
            if not isinstance(text, str):
                continue
            if any(re.search(rf"\b{re.escape(symbol)}\b", text) for symbol in symbols):
                results.append(rel)
                break
    # Codex P2 (#1299 round-10, C42): snapshot CALL references too — a test
    # doing 'import pkg; pkg.public_fn()' references the symbol through a
    # call edge even though imports_json carries only 'import pkg'.
    # symbols is guaranteed non-empty here (the early return above).
    placeholders = ",".join("?" for _ in symbols)  # nosec B608
    try:
        call_rows = conn.execute(
            f"SELECT DISTINCT file_path FROM edges "
            f"WHERE kind = 'calls' AND callee_name IN ({placeholders})",
            tuple(symbols),
        ).fetchall()
    except Exception:  # nosec B110 — legacy schema degrades per call
        call_rows = []
    for row in call_rows:
        rel = str(row["file_path"])
        if (
            rel
            and rel != rel_path
            and rel in inventory
            and _looks_like_test_name(Path(rel).name, language)
            and rel not in results
        ):
            results.append(rel)
    return results


def _certified_test_files(
    inventory: frozenset[str],
    rel_path: str,
    dependents: list[str] | tuple[str, ...] = (),
) -> list[str]:
    """Find inventory-covered test files for one target (RELATIVE posix path).

    Codex P1 (#1299 round-3/4): snapshot-certified test discovery walks the
    snapshot's ``ast_index`` file set instead of the live filesystem, so
    oracle-excluded paths (e.g. ``tests/vendor/``) can never influence
    ``has_tests`` and the discovery cap cannot be filled by un-certified
    candidates. Pattern and colocated conventions mirror the live axis:
    basenames are matched with the patterns' GLOB semantics (round-5, e.g.
    ``test_app_*.py``) and ``test_dirs`` of ``"."`` (Go's co-located
    convention) accept any inventory path (round-5). The legacy
    ``_is_existing_test_file`` and ``_find_symbol_reference_tests`` modes are
    preserved over certified inputs: a target that is itself a test file
    counts, and inventory-covered dependents whose names match the test
    patterns (tests that import the target) count (round-6).
    """

    import fnmatch

    from .test_discovery import (
        _TEST_DIRS,
        _TEST_PATTERNS,
        _format_pattern,
        detect_language_from_ext,
    )

    p = Path(rel_path)
    stem = p.stem
    language = detect_language_from_ext(p.suffix.lower()) or "python"
    patterns = _TEST_PATTERNS.get(language, ["test_{stem}.py"])
    test_dirs = _TEST_DIRS.get(language, ["tests"])
    filenames = [_format_pattern(pattern, stem) for pattern in patterns]

    def matches_test_pattern(name: str) -> bool:
        return any(fnmatch.fnmatchcase(name, pattern) for pattern in filenames)

    results: list[str] = []
    if _looks_like_test_name(p.name, language):
        # The target itself is a test file (legacy _is_existing_test_file).
        results.append(rel_path)
    for rel in sorted(inventory):
        if rel == rel_path:
            continue
        if not matches_test_pattern(Path(rel).name):
            continue
        if any(
            test_dir == "." or rel.startswith(f"{test_dir}/") for test_dir in test_dirs
        ):
            results.append(rel)
    parent = p.parent.as_posix()
    for filename in filenames:
        if "*" in filename:
            continue
        colocated = f"{parent}/{filename}"
        if colocated in inventory and colocated not in results:
            results.append(colocated)
    if language == "python":
        # Codex P2 (#1299 round-8, C36): preserve the live route's
        # package-family convention (test_<plugin>.py) over the inventory.
        from .test_discovery_stems import python_package_test_stems

        for package_stem in python_package_test_stems(rel_path):
            for pattern in (
                f"test_{package_stem}.py",
                f"test_{package_stem}_*.py",
            ):
                for rel in sorted(inventory):
                    if rel == rel_path:
                        continue
                    if (
                        fnmatch.fnmatchcase(Path(rel).name, pattern)
                        and any(
                            test_dir == "." or rel.startswith(f"{test_dir}/")
                            for test_dir in test_dirs
                        )
                        and rel not in results
                    ):
                        results.append(rel)
    for dep in dependents:
        # Symbol-reference mode over certified inputs: inventory-covered
        # dependents that import the target and look like tests count.
        if _looks_like_test_name(Path(dep).name, language) and dep not in results:
            results.append(dep)
    return results[:10]


def snapshot_inventory(conn: Any) -> frozenset[str]:
    """Return the snapshot's ``ast_index`` relative file set.

    Codex P1 (#1299 round-3): certified reads must derive facts only from
    inventory-covered paths (the source oracle prunes e.g. ``tests/vendor``
    from the generation). An unreadable inventory degrades to the empty
    set — the conservative, fail-closed direction for certified facts.
    """

    try:
        rows = conn.execute("SELECT file_path FROM ast_index").fetchall()
    except Exception:  # nosec B110 — legacy/partial schema
        return frozenset()
    return frozenset(str(row["file_path"]) for row in rows)


def _snapshot_file_indexed(conn: Any, rel_path: str) -> bool:
    """Return whether the snapshot connection has indexed one relative file."""
    try:
        row = conn.execute(
            "SELECT 1 FROM ast_index WHERE file_path = ? LIMIT 1", (rel_path,)
        ).fetchone()
    except Exception:  # nosec B110 — legacy/partial schema degrades to missing
        return False
    return row is not None


def _resolve_import_spec_in_snapshot(
    conn: Any, spec: str, importer_rel_path: str
) -> str | None:
    """Mirror :func:`_resolve_import_spec` against the snapshot's ``ast_index``.

    The live variant probes ``(root / candidate).is_file()``; the snapshot
    variant asks the immutable connection instead, so no live filesystem byte
    is consulted to build the dependency view.
    """
    if not spec or spec.startswith(".."):
        return None
    if spec.startswith("."):
        base = Path(importer_rel_path).parent
        candidate_base = (base / spec.lstrip("./")).as_posix()
    else:
        candidate_base = spec.replace(".", "/")

    candidates = [
        candidate_base,
        f"{candidate_base}.py",
        f"{candidate_base}.js",
        f"{candidate_base}.ts",
        f"{candidate_base}.tsx",
        f"{candidate_base}.java",
        f"{candidate_base}/__init__.py",
        f"{candidate_base}/index.js",
        f"{candidate_base}/index.ts",
    ]
    for candidate in candidates:
        if _snapshot_file_indexed(conn, candidate):
            return candidate
    return None


def build_snapshot_file_dependency_view(conn: Any, rel_path: str) -> FileDependencyView:
    """Build the one-file import view from the snapshot connection.

    RFC-0022 P0.4 read_existing: the live ``build_file_dependency_view``
    re-parses the filesystem; this variant reads only the immutable snapshot
    connection. Two passes mirror the legacy axis:

    1. ``edges`` IMPORTS rows: exact module-path resolution (``callee_name``
       resolved against the indexed files).
    2. ``ast_index.imports_json`` needle pass: ``from pkg import app`` and
       ``from . import app`` store the module path (``pkg`` / ``.``), which
       exact resolution cannot map to the member file ``pkg/app.py``; the
       legacy axis scans source text for import needles, so the snapshot
       variant matches the same needles against each importer's recorded
       import-statement text instead (no live bytes are consulted).

    A missing/legacy schema degrades to an empty view so the route can still
    classify honestly. A current-version but damaged ``edges`` table (present
    yet missing the ``callee_name`` column this reader requires) raises
    ``CORRUPT_INDEX`` instead of degrading silently — an empty view would
    undercount risk (Codex P2 #1299).
    """
    import json

    _require_edges_callee_name(conn)
    dependencies: set[str] = set()
    dependents: set[str] = set()
    try:
        import_rows = conn.execute(
            "SELECT callee_name FROM edges WHERE kind = 'imports' AND file_path = ?",
            (rel_path,),
        ).fetchall()
        for (module,) in import_rows:
            if not isinstance(module, str):
                # Codex P2 (#1299 round-10, C44): a BLOB callee_name would
                # raise TypeError at startswith and abandon the whole pass.
                continue
            resolved = _resolve_import_spec_in_snapshot(conn, module, rel_path)
            if resolved:
                dependencies.add(resolved)
        all_rows = conn.execute(
            "SELECT file_path, callee_name FROM edges WHERE kind = 'imports'",
        ).fetchall()
        for file_path, module in all_rows:
            if not file_path or file_path == rel_path:
                continue
            if not isinstance(module, str):
                continue
            resolved = _resolve_import_spec_in_snapshot(conn, module, file_path)
            if resolved == rel_path:
                dependents.add(file_path)
    except Exception:  # nosec B110 — snapshot schema drift degrades to empty
        pass
    try:
        # _import_needles_for_target always yields at least one needle for a
        # non-empty rel_path, so no guard is needed around the scan.
        needles = _import_needles_for_target(rel_path)
        rows = conn.execute("SELECT file_path, imports_json FROM ast_index").fetchall()
        for row in rows:
            file_path = row["file_path"]
            if not file_path or file_path == rel_path:
                continue
            try:
                imports = json.loads(row["imports_json"])
            except (TypeError, ValueError):
                continue
            if not isinstance(imports, list):
                # Codex P2 (#1299 round-9, C40): a non-array cell would
                # otherwise raise TypeError and abandon the WHOLE needle
                # pass, dropping later member-import dependents; skip the
                # malformed row only.
                continue
            for imp in imports:
                imp_text = imp["text"] if isinstance(imp, dict) else imp
                if not isinstance(imp_text, str):
                    continue
                if any(needle in imp_text for needle in needles):
                    dependents.add(file_path)
                    break
    except Exception:  # nosec B110 — snapshot schema drift degrades to empty
        pass
    return FileDependencyView(
        rel_path=rel_path,
        dependencies=dependencies,
        dependents=dependents,
    )


def safe_dependents(graph: Any, rel_path: str) -> list[str]:
    """Return files that depend on rel_path, tolerating stale graph data."""
    return _safe_graph_lookup(graph, rel_path, graph.dependents_of)


def safe_dependencies(graph: Any, rel_path: str) -> list[str]:
    """Return files rel_path depends on, tolerating stale graph data."""
    return _safe_graph_lookup(graph, rel_path, graph.dependencies_of)


def is_init_file(file_path: str) -> bool:
    """Return whether a path points at a package __init__.py file."""
    return Path(file_path).name == "__init__.py"


def _safe_graph_lookup(
    graph: Any,
    rel_path: str,
    lookup: Any,
) -> list[str]:
    """Look up graph edges directly or via suffix match."""
    try:
        node = _matching_node(graph, rel_path)
        return lookup(node) if node else []
    except Exception:  # nosec B110 - graph lookup failure returns no edges
        return []


def _matching_node(graph: Any, rel_path: str) -> str | None:
    """Find the graph node matching a relative path."""
    if graph.has_node(rel_path):
        return rel_path
    normalized = rel_path.replace("\\", "/")
    suffix = f"/{normalized}"
    return next((node for node in graph.nodes() if node.endswith(suffix)), None)
