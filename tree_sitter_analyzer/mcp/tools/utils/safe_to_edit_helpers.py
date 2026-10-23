"""Shared helpers for safe-to-edit reports.

This module builds the safe-to-edit response and is the stable import
surface for every safe-to-edit helper. The implementation is split by
concern into sibling modules and re-exported here, so existing
``safe_to_edit_helpers.<name>`` imports keep working:

* :mod:`.safe_to_edit_paths` — path/language/graph-lookup primitives
* :mod:`.safe_to_edit_workflow` — verdict vocabulary and agent workflow
* :mod:`.safe_to_edit_live_deps` — live-filesystem dependency view
* :mod:`.safe_to_edit_import_parsing` — projected import-text parsers
* :mod:`.safe_to_edit_inventory_resolver` — inventory-bound import resolution
* :mod:`.safe_to_edit_projection` — projection completeness predicates
* :mod:`.safe_to_edit_snapshot_view` — certified dependency view / stale edges
* :mod:`.safe_to_edit_snapshot_tests` — certified exercising-test discovery

The response builders below look their collaborators up in THIS module's
namespace (``snapshot_inventory``, ``_certified_exercising_tests``,
``is_fixture``, ``to_relative``, ``find_test_files``, the projection
predicates, ...), so patching them here keeps steering the builders.
"""

from __future__ import annotations

import os
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
from .safe_to_edit_import_parsing import (  # noqa: F401 — re-exports
    _import_module_name,
    _jsts_projected_alias_spec,
    _python_ast_name,
    _python_dynamic_loader_names_from_projection,
    _python_projected_call,
    _python_projected_call_has_simple_arguments,
    _python_static_import_specs,
)
from .safe_to_edit_inventory_resolver import (  # noqa: F401 — re-exports
    _import_targets_from_text,
    _java_wildcard_targets,
    _python_import_root,
    _python_package_initializers,
    _quoted_include_matches,
    _resolve_import_spec_from_inventory,
)
from .safe_to_edit_live_deps import (  # noqa: F401 — re-exports
    _DEPENDENCY_SKIP_DIRS,
    _DEPENDENCY_SOURCE_EXTS,
    _extract_import_specs,
    _import_needles_for_target,
    _iter_dependency_source_files,
    _resolve_import_spec,
    _target_dependencies,
    _target_dependents,
    _target_dependents_by_scan,
    build_file_dependency_view,
)
from .safe_to_edit_paths import (  # noqa: F401 — re-exports
    _CERTIFIED_IMPORT_LANGUAGES,
    _TYPESCRIPT_SOURCE_SUBSTITUTIONS,
    FileDependencyView,
    _matching_node,
    _module_path_without_suffix,
    _normalize_relative_path,
    _safe_graph_lookup,
    _target_language,
    _typescript_emitted_import_paths,
    is_init_file,
    safe_dependencies,
    safe_dependents,
    to_relative,
)
from .safe_to_edit_projection import (  # noqa: F401 — re-exports
    _java_inventory_matches,
    _java_reflection_projection_complete,
    _java_same_package_projection_complete,
    _jsts_import_projection_complete,
    _python_absolute_inventory_match_is_rooted,
    _python_from_import_is_ambiguous,
    _python_import_projection_complete,
    _python_inventory_case_ambiguous,
    _python_inventory_matches,
    _python_relative_package_root_ambiguous,
    _quoted_include_projection_complete,
    _snapshot_import_texts,
    _symbol_walk_projections_complete,
)
from .safe_to_edit_risk import build_checklist, compute_risk
from .safe_to_edit_snapshot_tests import (  # noqa: F401 — re-exports
    _certified_exercising_tests,
    _certified_symbol_reference_tests,
    _certified_test_files,
    _file_defines_any,
    _looks_like_test_name,
    _looks_like_test_path,
    _pytest_exercising_projection_complete,
    _python_package_symbol_providers,
    _snapshot_reverse_dependencies,
)
from .safe_to_edit_snapshot_view import (  # noqa: F401 — re-exports
    _edge_import_names_for_target,
    _escape_sql_like,
    _projection_search_tokens,
    _require_edges_callee_name,
    _snapshot_needle_importers,
    build_snapshot_file_dependency_view,
    snapshot_inventory,
    snapshot_stale_edges,
)
from .safe_to_edit_workflow import (  # noqa: F401 — re-exports
    _VERDICT_SEVERITY,
    AgentWorkflowContext,
    _agent_guardrails,
    _agent_next_step,
    _agent_stop_condition,
    _edit_strategy,
    _max_verdict,
    _risk_to_verdict,
    build_agent_summary,
    build_agent_workflow,
)
from .test_discovery import find_test_files
from .verification_command import (  # noqa: F401 — re-exports
    build_test_command,
    detect_default_test_command,
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
    test_projection_complete: bool = True


def _unavailable_causal_envelope() -> dict[str, Any]:
    """Return the trust-bearing envelope with every causal fact unavailable."""
    return {
        "dependents": None,
        "dependencies": None,
        "exercising_tests": None,
        "constraint_verdict": "unknown",
        "verification_command": None,
        "stale_edges": None,
    }


def build_safe_to_edit_result(context: SafeToEditContext) -> dict[str, Any]:
    """Build the MCP response payload for a safe-to-edit request."""
    facts = _collect_safe_to_edit_facts(context)
    return _format_safe_to_edit_result(context, facts)


def _context_relative_path(context: SafeToEditContext) -> str:
    """Return the snapshot-keyed relative path of the context's target.

    Canonicalize both sides before relativising. On macOS the security
    validator's abspath (/var/folders/...) differs from a canonical root
    (/private/var/folders/...) by symlink. On any platform, a relative
    project_root ("." or "..") causes Path(abs).relative_to(rel) to raise
    ValueError, so to_relative falls back to the absolute path — the returned
    key then misses every node in FileDependencyView._dependents, which is
    keyed by resolved-relative paths (build_file_dependency_view §L1).
    (CLAUDE.md §2 resolution contract)
    """
    return _normalize_relative_path(
        to_relative(
            os.path.realpath(context.resolved_path),
            os.path.realpath(context.project_root),
        )
    )


def _collect_safe_to_edit_facts(context: SafeToEditContext) -> SafeToEditFacts:
    """Collect graph, health, test, and risk facts for a file."""
    rel_path = _context_relative_path(context)
    dependents = safe_dependents(context.graph, rel_path)
    dependencies = safe_dependencies(context.graph, rel_path)
    if context.snapshot_conn is not None:
        test_files, test_projection_complete = _certified_test_facts(
            context, rel_path, dependents
        )
        certified_health = True
    else:
        test_files = find_test_files(context.resolved_path, context.project_root)
        test_projection_complete = True
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
        test_projection_complete=test_projection_complete,
        has_tests=has_tests,
        risk=risk,
        risk_factors=risk_factors,
        pre_edit_checklist=pre_edit_checklist,
    )


def _certified_test_facts(
    context: SafeToEditContext, rel_path: str, dependents: list[str]
) -> tuple[list[str], bool]:
    """Return ``(test_files, projection_complete)`` from the snapshot.

    Codex P1 (#1299 round-3/4): test facts must come from inventory-
    covered paths only — discovery runs over the snapshot's ast_index
    set, so oracle-excluded files (tests/vendor/) cannot change the
    exercising-test set or has_tests/verdict for the same identity.
    """
    inventory = context.certified_inventory
    if inventory is None:
        inventory = snapshot_inventory(context.snapshot_conn)
    reverse_dependencies = _snapshot_reverse_dependencies(
        context.snapshot_conn, inventory
    )
    test_files = _certified_exercising_tests(
        context.snapshot_conn,
        rel_path,
        dependents,
        inventory=inventory,
        reverse_dependencies=reverse_dependencies,
    )
    test_projection_complete = _pytest_exercising_projection_complete(
        rel_path,
        dependents,
        inventory,
        reverse_dependencies=reverse_dependencies,
    )
    return test_files, test_projection_complete


def _constraint_and_fixture_inputs(
    context: SafeToEditContext,
) -> tuple[list[dict[str, Any]], frozenset[str] | None, bool]:
    """Return ``(violations, fixture_inventory, fixture_certified)``.

    Codex P1 (#1299): the certified read_existing route runs the
    certified fixture probe — never the live .ast-cache DB and never
    the live allowlist/cache (both are outside the source generation
    and could drift after snapshot publication). The inventory
    restriction keeps the fixture scan on generation-certified test
    files only (round-3: oracle-pruned paths such as tests/vendor/
    must not influence escalation). Constraint rows are OMITTED on
    the certified route: reindexing stamps the manifest without
    recomputing ast_constraint_violations, so the rows cannot prove
    they match the published generation (round-4; an evaluation epoch
    bound to the index generation is the tracked follow-up).
    """
    if context.snapshot_conn is None:
        violations = violations_for_files(
            context.project_root, [_relative_for_constraints(context)]
        )
        return violations, None, False
    fixture_inventory = context.certified_inventory
    if fixture_inventory is None:
        fixture_inventory = snapshot_inventory(context.snapshot_conn)
    return [], fixture_inventory, True


def _uncertified_dependents_factor(answer: Any) -> dict[str, str]:
    return {
        "factor": "uncertified_dependents",
        "detail": (
            f"Dependents not fully established "
            f"({answer.certification_reason}); cannot confirm SAFE"
        ),
        "severity": "caution",
    }


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
    certified_rel_path = _context_relative_path(context)
    violations, fixture_inventory, fixture_certified = _constraint_and_fixture_inputs(
        context
    )
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
    # Fail-closed: an uncertified dependents set cannot support a SAFE verdict.
    # The set was derived from the index but completeness was not certified —
    # there may be additional dependents outside the index scope. Escalate so
    # agents do not proceed on a false-safe signal.
    answer = getattr(context.graph, "dependents_answer", None)
    escalated_uncertified = (
        answer is not None and not answer.certified and verdict == "SAFE"
    )
    if escalated_uncertified:
        verdict = "CAUTION"
    risk_factors = list(facts.risk_factors)
    if violations:
        risk_factors.extend(constraint_risk_factor(row) for row in violations)
    if fixture_fact.is_fixture:
        risk_factors.append(_fixture_risk_factor(fixture_fact, context.file_path))
    if escalated_uncertified:
        risk_factors.append(_uncertified_dependents_factor(answer))
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
    causal_envelope = _causal_envelope(
        context, facts, certified_rel_path, verification_command
    )
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
        **_dependents_basis_fields(context.graph),
    }


def _causal_envelope(
    context: SafeToEditContext,
    facts: SafeToEditFacts,
    certified_rel_path: str,
    verification_command: str | None,
) -> dict[str, Any]:
    """Return the trust-bearing causal envelope for the response."""
    causal_inventory = context.certified_inventory
    if context.snapshot_conn is not None and causal_inventory is None:
        causal_inventory = snapshot_inventory(context.snapshot_conn)
    if not (
        context.snapshot_conn is not None
        and facts.test_projection_complete
        and _certified_import_facts_available(
            certified_rel_path,
            conn=context.snapshot_conn,
            inventory=causal_inventory,
        )
    ):
        # The legacy live view and languages without a complete snapshot
        # import resolver cannot prove complete causal facts. Keep legacy
        # top-level hints, but make the trust-bearing envelope unavailable.
        return _unavailable_causal_envelope()
    # Constraint rows are not generation-bound until RFC-0025 P3.  An
    # empty result therefore cannot honestly mean "safe" on a certified
    # read; expose the unavailable fact as first-class ``unknown``.
    return {
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


def _dependents_basis_fields(graph: Any) -> dict[str, Any]:
    """Report how the dependents set was established (RFC-0025 L1).

    A stale or unusable index must not be read as authoritative, and a
    fall-back must not be presented as the derived answer. ``dependents_basis``
    says which path produced the set; ``dependents_certified`` and
    ``dependents_certification_reason`` say whether it can be trusted as
    complete.

    These are deliberately **flat scalars** rather than a nested block: a
    dict-valued key is a "bulk" value that compact output strips, so the label
    would vanish on exactly the surface (MCP) whose callers most need it.

    ``dependents_basis="unavailable"`` is the hand-built or snapshot-certified
    view, which reports its completeness through ``causal_envelope`` instead.
    """
    answer = getattr(graph, "dependents_answer", None)
    if answer is None:
        return {
            "dependents_basis": "unavailable",
            "dependents_certified": False,
            "dependents_certification_reason": "NOT_DERIVED",
            "dependents_delta_files": 0,
        }
    return {
        "dependents_basis": answer.basis,
        "dependents_certified": answer.certified,
        "dependents_certification_reason": answer.certification_reason,
        "dependents_delta_files": answer.delta_files,
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


def _related_import_languages(language: str) -> set[str]:
    """Return the languages whose importers can reach a *language* target."""
    if language in {"javascript", "typescript"}:
        return {"javascript", "typescript"}
    if language in {"c", "cpp"}:
        return {"c", "cpp"}
    return {language}


def _certified_import_facts_available(
    rel_path: str,
    *,
    conn: Any | None = None,
    inventory: frozenset[str] | None = None,
) -> bool:
    """Return whether every possible snapshot importer is covered."""

    language = _target_language(rel_path)
    if language not in _CERTIFIED_IMPORT_LANGUAGES:
        return False
    if inventory is None:
        inventory = frozenset()
    if conn is not None and not _symbol_walk_projections_complete(
        conn, inventory, _related_import_languages(language)
    ):
        return False
    if language == "java" and not _java_projections_complete(conn, rel_path, inventory):
        return False
    if conn is None:
        return True
    if language in {"javascript", "typescript"}:
        return _jsts_import_projection_complete(conn, inventory)
    if language == "python":
        return _python_import_projection_complete(conn, inventory)
    if language in {"c", "cpp"}:
        return _quoted_include_projection_complete(conn, rel_path, inventory)
    return True


def _java_projections_complete(
    conn: Any | None, rel_path: str, inventory: frozenset[str]
) -> bool:
    """Java-specific completeness: no JVM siblings, packages and reflection.

    Other supported JVM languages can reference Java without a Java
    import projection. Until their resolvers exist, even one indexed
    Kotlin or Scala source makes Java's incoming direction incomplete.
    """
    if any(
        Path(path).suffix.lower() in {".kt", ".kts", ".scala"} for path in inventory
    ):
        return False
    if conn is None:
        return True
    if not _java_same_package_projection_complete(conn, rel_path, inventory):
        return False
    return _java_reflection_projection_complete(conn, inventory)


def build_snapshot_syntax_causal_envelope(
    conn: Any,
    rel_path: str,
    file_path: str,
    *,
    inventory: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Build certified causal facts when live syntax blocks health analysis."""
    if inventory is None:
        inventory = snapshot_inventory(conn)
    if not _certified_import_facts_available(rel_path, conn=conn, inventory=inventory):
        return _unavailable_causal_envelope()
    graph = build_snapshot_file_dependency_view(conn, rel_path, inventory=inventory)
    dependents = safe_dependents(graph, rel_path)
    dependencies = safe_dependencies(graph, rel_path)
    reverse_dependencies = _snapshot_reverse_dependencies(conn, inventory)
    if not _pytest_exercising_projection_complete(
        rel_path,
        dependents,
        inventory,
        reverse_dependencies=reverse_dependencies,
    ):
        return _unavailable_causal_envelope()
    tests = _certified_exercising_tests(
        conn,
        rel_path,
        dependents,
        inventory=inventory,
        reverse_dependencies=reverse_dependencies,
    )

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
