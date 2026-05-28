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
    """Inputs needed to build a safe-to-edit response."""

    file_path: str
    edit_type: str
    resolved_path: str
    project_root: str
    graph: Any
    scorer: HealthScorer


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
    """Inputs needed to build the structured agent edit workflow."""

    file_path: str
    risk: str
    edit_type: str
    has_tests: bool
    test_files: list[str]
    health_grade: str
    project_root: str


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
    rel_path = to_relative(context.resolved_path, context.project_root)
    dependents = safe_dependents(context.graph, rel_path)
    dependencies = safe_dependencies(context.graph, rel_path)
    health = context.scorer.score_file(context.resolved_path, fast_dependencies=True)
    test_files = find_test_files(context.resolved_path, context.project_root)
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
    violations = violations_for_files(
        context.project_root, [_relative_for_constraints(context)]
    )
    constraint_verdict = verdict_from_violations(violations)
    # P3: also check whether the file is a registered test fixture; that
    # promotes the verdict on top of any constraint-derived escalation.
    # The chokepoint design (see PRD §P3) is "every override flows
    # through _max_verdict" — so chaining is the only safe composition.
    fixture_fact = is_fixture(context.resolved_path, context.project_root)
    fixture_verdict = fixture_to_verdict(fixture_fact)
    verdict = _max_verdict(
        _max_verdict(base_verdict, constraint_verdict), fixture_verdict
    )
    risk_factors = list(facts.risk_factors)
    if violations:
        risk_factors.extend(constraint_risk_factor(row) for row in violations)
    if fixture_fact.is_fixture:
        risk_factors.append(_fixture_risk_factor(fixture_fact, context.file_path))
    recommendation = _format_recommendation(risk, facts, workflow)
    summary = build_agent_summary(workflow_context, workflow)
    # Promote agent_summary.verdict when constraint violations escalate
    # beyond the risk-level-derived verdict.
    if verdict != base_verdict:
        summary["verdict"] = verdict
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
    risk: str,
    facts: SafeToEditFacts,
    workflow: dict[str, Any],
) -> str:
    """One-line agent-readable summary of what to do next."""
    grade = facts.health.grade
    downstream = len(facts.dependents)
    verdict = _risk_to_verdict(risk).lower()
    if verdict == "unsafe":
        return (
            f"UNSAFE to edit: health grade {grade}, {downstream} downstream "
            f"file(s) depend on this. Refactor in stages with tests after each."
        )
    if verdict == "caution":
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
) -> dict[str, Any]:
    """Build the compact first-read decision summary for agents.

    N1 (round-27): include ``summary_line`` + ``verdict`` so the
    cross-tool envelope contract (``TestEnvelopeContractSnapshot``) is
    satisfied. ``mirror_summary_line`` then copies the line to the
    top-level envelope for direct callers that bypass the dispatch hook.
    """
    before = workflow["before_edit_commands"]
    after = workflow["after_edit_commands"]
    boundary = workflow["queue_boundary_commands"]
    verdict = _risk_to_verdict(context.risk)
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
    default_command = detect_default_test_command(context.project_root)
    focused_command = (
        build_test_command(default_command, context.test_files[:3])
        if context.has_tests
        else ""
    )
    boundary_command = default_command.command
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
        "queue_boundary_commands": [boundary_command],
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
