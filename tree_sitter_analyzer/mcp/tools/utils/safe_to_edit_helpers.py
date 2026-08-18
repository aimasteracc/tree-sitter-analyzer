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

_CERTIFIED_IMPORT_LANGUAGES = frozenset(
    {"python", "javascript", "typescript", "java", "c", "cpp"}
)


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
    certified_inventory: frozenset[str] | None = None
    stale_edges: tuple[str, ...] = ()


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
        # set, so oracle-excluded files (tests/vendor/) cannot change the
        # exercising-test set or has_tests/verdict for the same identity.
        inventory = context.certified_inventory
        if inventory is None:
            inventory = snapshot_inventory(context.snapshot_conn)
        test_files = _certified_exercising_tests(
            context.snapshot_conn,
            rel_path,
            dependents,
            inventory=inventory,
        )
        certified_health = True
    else:
        test_files = find_test_files(context.resolved_path, context.project_root)
        certified_health = False
    if certified_health:
        # Codex P2 (#1299 round-13/14, C60/C61): certified reads must parse
        # the freshly recaptured bytes. The content cache key derives from
        # (path, mtime, size) too, so a same-size rewrite with a restored
        # mtime regenerates the same key and would serve a stale parse —
        # evict the whole parser cache (certified reads are rare; parse
        # correctness beats cache warmth here).
        from ....core.parser import Parser as _Parser

        _Parser.cache_clear()
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
    certified_rel_path = to_relative(
        os.path.realpath(context.resolved_path), context.project_root
    )
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
        fixture_inventory = context.certified_inventory
        if fixture_inventory is None:
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
    verification_command = summary.get("verification_command") or None
    if context.snapshot_conn is not None and _certified_import_facts_available(
        certified_rel_path
    ):
        # Constraint rows are not generation-bound until RFC-0025 P3.  An
        # empty result therefore cannot honestly mean "safe" on a certified
        # read; expose the unavailable fact as first-class ``unknown``.
        causal_envelope = {
            # These are the untruncated snapshot facts used to compute the
            # verdict. Legacy top-level list fields remain capped for wire
            # compatibility.
            "dependents": list(facts.dependents),
            "dependencies": list(facts.dependencies),
            "exercising_tests": list(facts.test_files),
            "constraint_verdict": "unknown",
            "verification_command": verification_command,
            "stale_edges": list(context.stale_edges),
        }
    else:
        # The legacy live view and languages without a complete snapshot
        # import resolver cannot prove complete causal facts. Keep legacy
        # top-level hints, but make the trust-bearing envelope unavailable.
        causal_envelope = {
            "dependents": None,
            "dependencies": None,
            "exercising_tests": None,
            "constraint_verdict": "unknown",
            "verification_command": None,
            "stale_edges": None,
        }
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
        "test_files_nearby": facts.test_files[:10],
        "pre_edit_checklist": facts.pre_edit_checklist,
        "agent_workflow": workflow,
        "causal_envelope": causal_envelope,
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
        "verification_command": (
            ""
            if workflow.get("test_verification_unidentified")
            else (after[0] if after else (boundary[0] if boundary else ""))
        ),
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
    # Codex P2 (#1299 round-11, C49): when no runner can be identified, the
    # health/impact commands must never be promoted to TEST verification.
    test_verification_unidentified = context.certified and default_command is None
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
        "test_verification_unidentified": test_verification_unidentified,
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
    if workflow.get("test_verification_unidentified"):
        return (
            "Test verification is unidentified for this project; run the "
            "project's test suite manually before and after the edit."
        )
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

    return detect_language_from_ext(Path(rel_path).suffix.lower()) or "unknown"


def _certified_import_facts_available(rel_path: str) -> bool:
    """Return whether snapshot projections cover this language's imports."""

    return _target_language(rel_path) in _CERTIFIED_IMPORT_LANGUAGES


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
        return name.endswith((".test.js", ".spec.js", ".test.jsx", ".spec.jsx"))
    if language == "typescript":
        return name.endswith((".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx"))
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


def _import_module_name(import_text: str) -> str | None:
    """Return the imported module path from one import statement text."""

    import re as _re

    m = _re.match(r"^\s*from\s+([.\w]+)\s+import\b", import_text)
    if m:
        return m.group(1)
    m = _re.search(r"(?:\bfrom\s*|^\s*import\s*)['\"]([^'\"]+)['\"]", import_text)
    if m:
        return m.group(1)
    m = _re.match(r"^\s*import\s+([.\w]+)", import_text)
    if m:
        return m.group(1)
    m = _re.search(r"\b(?:require|import)\s*\(\s*['\"]([^'\"]+)['\"]", import_text)
    if m:
        return m.group(1)
    return None


def _file_defines_any(conn: Any, file_path: str, symbols: list[str]) -> bool:
    """Return whether one indexed file defines ANY of the given symbols."""

    import json as _json

    try:
        row = conn.execute(
            "SELECT symbols_json FROM ast_index WHERE file_path = ?",
            (file_path,),
        ).fetchone()
    except Exception as exc:
        raise ValueError("CORRUPT_INDEX") from exc
    if row is None:
        raise ValueError("CORRUPT_INDEX")
    try:
        payload = _json.loads(str(row["symbols_json"]))
    except (TypeError, ValueError) as exc:
        raise ValueError("CORRUPT_INDEX") from exc
    if not isinstance(payload, dict):
        raise ValueError("CORRUPT_INDEX")
    entries = payload.get("symbols", [])
    if not isinstance(entries, list) or any(
        not isinstance(entry, dict) for entry in entries
    ):
        raise ValueError("CORRUPT_INDEX")
    defined = {
        entry.get("name") for entry in entries if isinstance(entry.get("name"), str)
    }
    return bool(defined.intersection(symbols))


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
    except Exception as exc:
        raise ValueError("CORRUPT_INDEX") from exc
    if target_row is None:
        raise ValueError("CORRUPT_INDEX")
    symbols: set[str] = set()
    try:
        payload = _json.loads(str(target_row["symbols_json"]))
    except (TypeError, ValueError) as exc:
        raise ValueError("CORRUPT_INDEX") from exc
    if not isinstance(payload, dict):
        raise ValueError("CORRUPT_INDEX")
    entries = payload.get("symbols", [])
    if not isinstance(entries, list) or any(
        not isinstance(entry, dict) for entry in entries
    ):
        raise ValueError("CORRUPT_INDEX")
    for entry in entries:
        name = entry.get("name")
        if isinstance(name, str) and not name.startswith("_"):
            symbols.add(name)
    if not symbols:
        return []

    results: list[str] = []
    for rel in sorted(inventory):
        if rel == rel_path:
            continue
        importer_language = _target_language(rel)
        if not _looks_like_test_name(Path(rel).name, importer_language):
            continue
        try:
            row = conn.execute(
                "SELECT imports_json FROM ast_index WHERE file_path = ?",
                (rel,),
            ).fetchone()
        except Exception as exc:
            raise ValueError("CORRUPT_INDEX") from exc
        if row is None:
            raise ValueError("CORRUPT_INDEX")
        # Codex P2 (#1299 round-8, C33): match symbols against the PARSED
        # import identifiers, never the serialized cell — substrings and
        # JSON keys (e.g. a symbol 'text' matching every record's "text"
        # key) would otherwise produce false has_tests=True.
        try:
            records = _json.loads(str(row["imports_json"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("CORRUPT_INDEX") from exc
        if not isinstance(records, list):
            raise ValueError("CORRUPT_INDEX")
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("CORRUPT_INDEX")
            text = record.get("text")
            if not isinstance(text, str):
                raise ValueError("CORRUPT_INDEX")
            matched = [
                symbol
                for symbol in symbols
                if re.search(rf"\b{re.escape(symbol)}\b", text)
            ]
            if not matched:
                continue
            # Codex P2 (#1299 round-12, C56): bind the import to the target
            # module — a test doing 'from other import run' must not count
            # for pkg/impl.py just because both define 'run'. Resolve the
            # imported module; if it resolves to a DIFFERENT file that
            # itself defines the symbol, the import belongs to that module.
            import_module = _import_module_name(text)
            if import_module:
                # Codex P2 (#1299 round-13, C58): relative imports resolve
                # from the IMPORTING TEST's directory, never the target's.
                resolved_module = _resolve_import_spec_from_inventory(
                    import_module, rel, inventory
                )
                if importer_language in {"javascript", "typescript"}:
                    if resolved_module != rel_path:
                        continue
                    results.append(rel)
                    break
                if importer_language == "python" and resolved_module is None:
                    continue
                if (
                    resolved_module
                    and resolved_module != rel_path
                    and _file_defines_any(conn, resolved_module, matched)
                ):
                    continue
            results.append(rel)
            break
    # Codex P2 (#1299 round-10, C42): snapshot CALL references too — a test
    # doing 'import pkg; pkg.public_fn()' references the symbol through a
    # call edge even though imports_json carries only 'import pkg'.
    # symbols is guaranteed non-empty here (the early return above).
    placeholders = ",".join("?" for _ in symbols)  # nosec B608
    try:
        # Codex P2 (#1299 round-11, C48): bind by the resolved callee file,
        # not the bare name — a same-named symbol exported by another module
        # must not attribute its tests to this target.
        call_rows = conn.execute(
            f"SELECT DISTINCT file_path FROM edges "
            f"WHERE kind = 'calls' AND callee_name IN ({placeholders}) "
            f"AND callee_resolved_file = ?",
            (*tuple(symbols), rel_path),
        ).fetchall()
    except Exception:  # nosec B110 — legacy schema degrades per call
        call_rows = []
    for row in call_rows:
        rel = str(row["file_path"])
        if (
            rel
            and rel != rel_path
            and rel in inventory
            and _looks_like_test_name(Path(rel).name, _target_language(rel))
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
    # Codex P2 (#1299 round-11, C47): a root-level target's parent is '.',
    # which would build './test_app.py' while inventory keys are normalized
    # without the leading './'.
    parent = "" if parent == "." else parent
    for filename in filenames:
        if "*" in filename:
            continue
        colocated = filename if not parent else f"{parent}/{filename}"
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
        # dependents that import the target and look like tests count —
        # an IMPORTS edge left for an excluded/unindexed path must NOT be
        # served as a certified test (Codex P2 #1299 round-12, C54).
        if (
            dep in inventory
            and _looks_like_test_name(Path(dep).name, _target_language(dep))
            and dep not in results
        ):
            results.append(dep)
    return results


def _certified_exercising_tests(
    conn: Any,
    rel_path: str,
    dependents: list[str] | tuple[str, ...],
    *,
    inventory: frozenset[str] | None = None,
) -> list[str]:
    """Return the complete deduplicated exercising-test set from a snapshot."""
    if inventory is None:
        inventory = snapshot_inventory(conn)
    test_files = [
        dep
        for dep in dependents
        if dep in inventory
        and _looks_like_test_name(Path(dep).name, _target_language(dep))
    ]
    language = _target_language(rel_path)
    if _looks_like_test_name(Path(rel_path).name, language):
        test_files.insert(0, rel_path)
    test_files.extend(
        _certified_symbol_reference_tests(
            conn, inventory, rel_path, _target_language(rel_path)
        )
    )
    return list(dict.fromkeys(test_files))


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


def _resolve_import_spec_from_inventory(
    spec: str,
    importer_rel_path: str,
    inventory: frozenset[str],
) -> str | None:
    """Resolve an import using one already captured snapshot inventory."""
    if not spec:
        return None

    # JavaScript/TypeScript module specifiers use POSIX path syntax.  Resolve
    # them separately from Python's leading-dot package syntax so a valid
    # ``../shared`` import cannot escape the repository root and ``./setup``
    # maps to the importing file's directory.
    if spec.startswith(("./", "../")):
        parts: list[str] = []
        joined = f"{Path(importer_rel_path).parent.as_posix()}/{spec}"
        for part in joined.split("/"):
            if part in {"", "."}:
                continue
            if part == "..":
                if not parts:
                    return None
                parts.pop()
            else:
                parts.append(part)
        candidate_base = "/".join(parts)
    elif spec.startswith("."):
        dot_count = len(spec) - len(spec.lstrip("."))
        dots = spec[:dot_count]
        module_tail = spec[dot_count:]
        package_parts = tuple(
            part for part in Path(importer_rel_path).parent.parts if part != "."
        )
        parent_hops = len(dots) - 1
        if not package_parts or parent_hops >= len(package_parts):
            return None
        base_parts = package_parts[: len(package_parts) - parent_hops]
        tail_parts = tuple(part for part in module_tail.split(".") if part)
        candidate_parts = (*base_parts, *tail_parts)
        candidate_base = "/".join(candidate_parts)
    else:
        candidate_base = spec.replace(".", "/")

    language = _target_language(importer_rel_path)
    if language in {"javascript", "typescript"} and not spec.startswith(("./", "../")):
        return None
    suffixes: tuple[str, ...]
    package_entries: tuple[str, ...]
    if language == "python":
        suffixes = (".py",)
        package_entries = ("__init__.py",)
    elif language == "javascript":
        suffixes = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")
        package_entries = tuple(f"index{suffix}" for suffix in suffixes)
    elif language == "typescript":
        suffixes = (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts")
        package_entries = tuple(f"index{suffix}" for suffix in suffixes)
    elif language == "java":
        suffixes = (".java",)
        package_entries = ()
    elif language == "c":
        suffixes = (".c", ".h")
        package_entries = ()
    elif language == "cpp":
        suffixes = (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h")
        package_entries = ()
    else:
        suffixes = (Path(importer_rel_path).suffix.lower(),)
        package_entries = ()

    allowed_suffixes = {suffix for suffix in suffixes if suffix}
    explicit_suffix = Path(candidate_base).suffix.lower()
    candidates: list[str] = []
    if not candidate_base:
        candidates.extend(package_entries)
    elif explicit_suffix in allowed_suffixes:
        candidates.append(candidate_base)
    elif not explicit_suffix:
        package_candidates = [f"{candidate_base}/{entry}" for entry in package_entries]
        file_candidates = [f"{candidate_base}{suffix}" for suffix in suffixes]
        if language == "python":
            candidates.extend(package_candidates)
            candidates.extend(file_candidates)
        else:
            candidates.extend(file_candidates)
            candidates.extend(package_candidates)
    for candidate in candidates:
        if candidate in inventory:
            return candidate
    infer_source_root = language in {"python", "java"} and not spec.startswith(".")
    if infer_source_root:
        for candidate in candidates:
            matches = sorted(
                indexed for indexed in inventory if indexed.endswith(f"/{candidate}")
            )
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                return None
    return None


def _python_package_initializers(resolved: str, inventory: frozenset[str]) -> set[str]:
    """Return indexed package initializers executed while importing a module."""

    initializers: set[str] = set()
    parent = Path(resolved).parent
    while parent.parts:
        candidate = (parent / "__init__.py").as_posix()
        if candidate in inventory:
            initializers.add(candidate)
        parent = parent.parent
    return initializers


def _import_targets_from_text(
    import_text: str,
    importer_rel_path: str,
    inventory: frozenset[str],
) -> set[str]:
    """Resolve every inventory-covered file named by one import statement.

    Import projections preserve source text, not a normalized target list.
    Parse the small syntax surface needed by the supported Python and
    JavaScript/TypeScript forms and always resolve against the immutable
    snapshot inventory.  In particular, a member import is bound to its
    module (``from other import app`` -> ``other/app.py``), never to an
    unrelated repository-wide basename match.
    """

    specs: set[str] = set()
    from_match = re.match(
        r"^\s*from\s+([.A-Za-z_][\w.]*)\s+import\s+(.+)$",
        import_text,
        re.S,
    )
    if from_match:
        module, imported = from_match.groups()
        specs.add(module)
        payload = "\n".join(line.split("#", 1)[0] for line in imported.splitlines())
        payload = payload.replace("(", "").replace(")", "")
        for item in payload.split(","):
            member = item.strip().split(maxsplit=1)[0] if item.strip() else ""
            if member and member != "*" and re.fullmatch(r"[A-Za-z_]\w*", member):
                separator = "" if module.endswith(".") else "."
                specs.add(f"{module}{separator}{member}")
    else:
        # Python/Java direct imports.  Multiple Python imports on one line are
        # kept distinct; aliases and Java's trailing semicolon are ignored.
        direct_match = re.match(r"^\s*import\s+(.+)$", import_text, re.S)
        if direct_match and not direct_match.group(1).lstrip().startswith(("'", '"')):
            for item in direct_match.group(1).split(","):
                spec = item.strip().split(maxsplit=1)[0].rstrip(";")
                if re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", spec):
                    specs.add(spec)

    # ESM side-effect/default/named imports and re-exports, plus CommonJS and
    # dynamic import expressions.  All capture the quoted module specifier.
    specs.update(
        re.findall(
            r"(?:\bfrom\s*|^\s*import\s*)['\"]([^'\"]+)['\"]",
            import_text,
            re.M,
        )
    )
    specs.update(
        re.findall(
            r"\b(?:require|import)\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
            import_text,
        )
    )
    include_match = re.match(r'^\s*#\s*include\s*"([^"]+)"', import_text)
    if include_match:
        specs.add(f"./{include_match.group(1)}")

    targets: set[str] = set()
    importer_language = _target_language(importer_rel_path)
    for spec in specs:
        resolved = _resolve_import_spec_from_inventory(
            spec, importer_rel_path, inventory
        )
        if resolved is None:
            continue
        targets.add(resolved)
        if importer_language == "python":
            targets.update(_python_package_initializers(resolved, inventory))
    return targets


def _edge_import_names_for_target(
    rel_path: str,
    inventory: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    """Return bounded unresolved-edge names that could identify *rel_path*."""

    path = Path(rel_path)
    without_suffix = path.with_suffix("").as_posix()
    module = without_suffix.replace("/", ".")
    parent_module = path.parent.as_posix().replace("/", ".")
    names = {
        without_suffix,
        module,
        path.stem,
        parent_module,
        ".",
        f".{path.stem}",
        f"./{path.stem}",
    }
    if path.parent.name:
        names.add(f".{path.parent.name}")
    target_module_parts = (
        path.parent.parts if path.name == "__init__.py" else path.with_suffix("").parts
    )
    target_parent_parts = target_module_parts[:-1]
    for offset in range(len(target_module_parts)):
        names.add(".".join(target_module_parts[offset:]))
    for importer in inventory:
        importer_parts = tuple(
            part for part in Path(importer).parent.parts if part != "."
        )
        common = 0
        for importer_part, target_part in zip(
            importer_parts, target_module_parts, strict=False
        ):
            if importer_part != target_part:
                break
            common += 1
        dots = "." * (len(importer_parts) - common + 1)
        module_tail = ".".join(target_module_parts[common:])
        names.add(f"{dots}{module_tail}")

        parent_common = 0
        for importer_part, target_part in zip(
            importer_parts, target_parent_parts, strict=False
        ):
            if importer_part != target_part:
                break
            parent_common += 1
        parent_dots = "." * (len(importer_parts) - parent_common + 1)
        parent_tail = ".".join(target_parent_parts[parent_common:])
        names.add(f"{parent_dots}{parent_tail}")
    if path.name == "__init__.py":
        names.discard("__init__")
    return tuple(sorted(name for name in names if name and name != ".")) + (".",)


def _projection_search_tokens(rel_path: str) -> tuple[str, ...]:
    """Return coarse SQL tokens; exact import parsing is the trust boundary."""

    path = Path(rel_path)
    tokens = _import_needles_for_target(rel_path)
    module_parts = (
        path.parent.parts if path.name == "__init__.py" else path.with_suffix("").parts
    )
    for offset in range(len(module_parts)):
        tokens.add(".".join(module_parts[offset:]))
    if path.stem and path.stem != "__init__":
        tokens.add(f"./{path.stem}")
    if path.stem == "index" and path.parent.name:
        tokens.add(path.parent.as_posix())
        tokens.add(path.parent.name)
        tokens.add(f"./{path.parent.name}")
    return tuple(sorted(tokens))


def _escape_sql_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def build_snapshot_file_dependency_view(
    conn: Any,
    rel_path: str,
    *,
    inventory: frozenset[str] | None = None,
) -> FileDependencyView:
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
    if inventory is None:
        inventory = snapshot_inventory(conn)
    dependencies: set[str] = set()
    dependents: set[str] = set()
    try:
        # P1 causal envelope: include resolved CALLS/IMPLEMENTS/etc., not only
        # IMPORTS.  ``file_path`` is the caller and ``callee_resolved_file``
        # is the definition file for every resolved cross-file edge.
        resolved_rows = conn.execute(
            "SELECT file_path, callee_resolved_file FROM edges "
            "WHERE callee_resolved_file != '' "
            "AND (file_path = ? OR callee_resolved_file = ?)",
            (rel_path, rel_path),
        ).fetchall()
        for caller_file, callee_file in resolved_rows:
            if not isinstance(caller_file, str) or not isinstance(callee_file, str):
                raise ValueError("CORRUPT_INDEX")
            if caller_file == rel_path and callee_file != rel_path:
                dependencies.add(callee_file)
            elif callee_file == rel_path and caller_file != rel_path:
                dependents.add(caller_file)
    except ValueError:
        raise
    except Exception:  # nosec B110 — legacy schema degrades to import facts
        pass
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
            resolved = _resolve_import_spec_from_inventory(module, rel_path, inventory)
            if resolved:
                dependencies.add(resolved)
        candidate_names = _edge_import_names_for_target(rel_path, inventory)
        placeholders = ", ".join("?" for _ in candidate_names)
        all_rows = conn.execute(
            "SELECT file_path, callee_name FROM edges WHERE kind = 'imports' "
            f"AND callee_name IN ({placeholders})",
            candidate_names,
        ).fetchall()
        for file_path, module in all_rows:
            if not isinstance(file_path, str) or not file_path or file_path == rel_path:
                continue
            resolved = _resolve_import_spec_from_inventory(module, file_path, inventory)
            if resolved == rel_path:
                dependents.add(file_path)
    except Exception:  # nosec B110 — snapshot schema drift degrades to empty
        pass
    try:
        # Fetch the target's own projection for outgoing dependencies and only
        # coarse candidate importers for the incoming direction.  Exact parsing
        # below remains the trust boundary; LIKE is only a bounded SQL prefilter.
        tokens = _projection_search_tokens(rel_path)
        like_terms = " OR ".join("imports_json LIKE ? ESCAPE '\\'" for _ in tokens)
        rows = conn.execute(
            "SELECT file_path, imports_json FROM ast_index WHERE file_path = ? "
            f"OR (file_path != ? AND ({like_terms}))",
            (
                rel_path,
                rel_path,
                *(f"%{_escape_sql_like(token)}%" for token in tokens),
            ),
        ).fetchall()
        for row in rows:
            file_path = row["file_path"]
            if not isinstance(file_path, str) or not file_path:
                raise ValueError("CORRUPT_INDEX")
            try:
                imports = json.loads(row["imports_json"])
            except (TypeError, ValueError) as exc:
                raise ValueError("CORRUPT_INDEX") from exc
            if not isinstance(imports, list):
                raise ValueError("CORRUPT_INDEX")
            for imp in imports:
                imp_text = imp["text"] if isinstance(imp, dict) else imp
                if not isinstance(imp_text, str):
                    raise ValueError("CORRUPT_INDEX")
                targets = _import_targets_from_text(imp_text, file_path, inventory)
                if file_path == rel_path:
                    dependencies.update(
                        target for target in targets if target != rel_path
                    )
                elif rel_path in targets:
                    dependents.add(file_path)
    except ValueError:
        raise
    except Exception:  # nosec B110 — legacy snapshot schema degrades to empty
        pass
    return FileDependencyView(
        rel_path=rel_path,
        dependencies=dependencies,
        dependents=dependents,
    )


def snapshot_stale_edges(
    conn: Any,
    rel_path: str,
    *,
    inventory: frozenset[str] | None = None,
) -> list[str]:
    """Return snapshot-bound labels for edge rows an edit may invalidate.

    An edit always invalidates its outgoing rows; it may also invalidate
    incoming rows when definitions move, disappear, or change signature.  P1
    therefore reports both directions conservatively.  A missing edge schema
    fails closed instead of reporting a misleading empty set.
    """

    if inventory is None:
        inventory = snapshot_inventory(conn)
    candidate_names = _edge_import_names_for_target(rel_path, inventory)
    placeholders = ", ".join("?" for _ in candidate_names)
    package_prefixes: tuple[str, ...] = ()
    if _target_language(rel_path) == "python" and Path(rel_path).name == "__init__.py":
        module_parts = Path(rel_path).parent.parts
        package_prefixes = tuple(
            ".".join(module_parts[offset:]) for offset in range(len(module_parts))
        )
    prefix_terms = " OR ".join(
        "callee_name LIKE ? ESCAPE '\\'" for _ in package_prefixes
    )
    unresolved_match = f"callee_name IN ({placeholders})"
    if prefix_terms:
        unresolved_match = f"({unresolved_match} OR {prefix_terms})"
    try:
        rows = conn.execute(
            "SELECT id, kind, file_path, callee_name, callee_resolved_file "
            "FROM edges WHERE file_path = ? OR callee_resolved_file = ? "
            "OR (kind = 'imports' AND callee_resolved_file = '' "
            f"AND {unresolved_match}) ORDER BY id",
            (
                rel_path,
                rel_path,
                *candidate_names,
                *(f"{_escape_sql_like(prefix)}.%" for prefix in package_prefixes),
            ),
        ).fetchall()
    except Exception as exc:
        raise ValueError("CORRUPT_INDEX") from exc

    unresolved_callers = {
        caller_file
        for _, kind, caller_file, _, resolved_file in rows
        if kind == "imports"
        and resolved_file == ""
        and isinstance(caller_file, str)
        and caller_file in inventory
    }
    needle_importers = _snapshot_needle_importers(
        conn, rel_path, unresolved_callers, inventory=inventory
    )
    labels: list[str] = []
    for row in rows:
        edge_id, kind, caller_file, callee_name, resolved_file = row
        if (
            not isinstance(edge_id, int)
            or isinstance(edge_id, bool)
            or not isinstance(kind, str)
            or not kind
            or not isinstance(caller_file, str)
            or not caller_file
            or not isinstance(callee_name, str)
            or not isinstance(resolved_file, str)
        ):
            raise ValueError("CORRUPT_INDEX")
        target_file = resolved_file
        if not target_file and kind == "imports":
            target_file = (
                _resolve_import_spec_from_inventory(callee_name, caller_file, inventory)
                or ""
            )
            # Member imports such as ``from . import app`` resolve the module
            # edge to ``pkg/__init__.py``.  The immutable imports projection
            # is the only snapshot-bound evidence that the row also touches
            # ``pkg/app.py``; mark it conservatively instead of dropping it.
            if caller_file in needle_importers:
                target_file = rel_path
        if caller_file != rel_path and target_file != rel_path:
            continue
        target = target_file or callee_name
        labels.append(f"{kind}:{caller_file}->{target}#{edge_id}")
    return labels


def _snapshot_needle_importers(
    conn: Any,
    rel_path: str,
    candidate_files: set[str] | set[bytes],
    *,
    inventory: frozenset[str] | None = None,
) -> set[str]:
    """Return unresolved importers whose recorded text names ``rel_path``."""
    if not candidate_files:
        return set()
    import json

    placeholders = ", ".join("?" for _ in candidate_files)
    try:
        rows = conn.execute(
            "SELECT file_path, imports_json FROM ast_index "
            f"WHERE file_path IN ({placeholders})",
            tuple(candidate_files),
        ).fetchall()
    except Exception as exc:
        raise ValueError("CORRUPT_INDEX") from exc

    if inventory is None:
        inventory = snapshot_inventory(conn)

    matched: set[str] = set()
    seen: set[str] = set()
    for row in rows:
        file_path = row["file_path"]
        if not isinstance(file_path, str):
            raise ValueError("CORRUPT_INDEX")
        seen.add(file_path)
        try:
            imports = json.loads(row["imports_json"])
        except (TypeError, ValueError) as exc:
            raise ValueError("CORRUPT_INDEX") from exc
        if not isinstance(imports, list):
            raise ValueError("CORRUPT_INDEX")
        for item in imports:
            text = item.get("text") if isinstance(item, dict) else item
            if not isinstance(text, str):
                raise ValueError("CORRUPT_INDEX")
            if rel_path in _import_targets_from_text(text, file_path, inventory):
                matched.add(file_path)
                break
    if seen != candidate_files:
        raise ValueError("CORRUPT_INDEX")
    return matched


def build_snapshot_syntax_causal_envelope(
    conn: Any,
    rel_path: str,
    file_path: str,
    *,
    inventory: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Build certified causal facts when live syntax blocks health analysis."""
    if not _certified_import_facts_available(rel_path):
        return {
            "dependents": None,
            "dependencies": None,
            "exercising_tests": None,
            "constraint_verdict": "unknown",
            "verification_command": None,
            "stale_edges": None,
        }
    if inventory is None:
        inventory = snapshot_inventory(conn)
    graph = build_snapshot_file_dependency_view(conn, rel_path, inventory=inventory)
    dependents = safe_dependents(graph, rel_path)
    dependencies = safe_dependencies(graph, rel_path)
    tests = _certified_exercising_tests(conn, rel_path, dependents, inventory=inventory)

    from .verification_command import certified_default_test_command

    default_command = certified_default_test_command(file_path)
    verification_command = (
        build_test_command(default_command, tests)
        if default_command is not None
        else None
    )
    return {
        "dependents": dependents,
        "dependencies": dependencies,
        "exercising_tests": tests,
        "constraint_verdict": "unknown",
        "verification_command": verification_command,
        "stale_edges": snapshot_stale_edges(conn, rel_path, inventory=inventory),
    }


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
