"""RFC-0022 fixed router (Phase A, internal experiment only).

The fixed router executes the pinned route decision table
(``route_table.ROUTE_TABLE``) for the three task outcomes
``understand`` / ``plan_change`` / ``assess_change``. The non-negotiable
boundary holds: this module validates, routes, and normalizes primitive
results only; it never parses a patch or source, resolves a symbol, builds a
graph, evaluates a constraint, or runs a command, and it MUST NOT import
analyzer internals. Primitive calls go through the injected
``PrimitiveExecutor``; the harness outside this package wires the real
same-process MCP adapters (RFC-0022 §Phase A).

Executable contract highlights (RFC-0022):
- boundary validation precedes primitive work; invalid requests make zero
  calls and freeze ``INVALID_REQUEST``;
- sequential calls only; the deadline is checked before each call and an
  overrunning primitive reports ``deadline_overrun_ms`` exactly;
- diff routes reserve the constraints slot before impact and run
  impact -> constraints -> fan-out;
- only primitive-issued tokens are compared; a generation/snapshot mismatch
  stops graph-, source-, and snapshot-dependent routing;
- the validated ``edit.release_snapshot`` pair is released in an outer
  ``finally`` as unconditional, separately-accounted cleanup;
- task text never enters the frozen model: requests are projected with the
  fixed ``TASK_TEXT_OMITTED`` scalar and provenance request hashes omit it;
- the static verification truth table and plan-steps projection are the
  sole aggregation engines (``truth_table`` / ``projection``).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Protocol

from . import (
    _router_constraints,
    _router_impact,
    _router_index,
    _router_task,
    _router_wire,
)
from ._router_session import (
    RouteSession,
    degraded_unknown,
    with_evidence,
)
from ._router_session import (
    request_hash as _request_hash,
)
from .models import (
    TASK_TEXT_OMITTED,
    AssessChangeRequest,
    ConsumedBudget,
    PlanChangeRequest,
    Status,
    TaskOutcome,
    TaskRequest,
    UnderstandRequest,
    Verdict,
    build_artifacts,
    build_budget_record,
    build_subject_diff,
    build_subject_task,
)
from .projection import StepFragment, project_plan_steps
from .truth_table import (
    FRESH,
    UNKNOWN,
    aggregate_status_and_verdict,
    contribute,
)

#: Stable error codes (RFC-0022 §Fixed task-outcome/v1 semantics).
INTERNAL_ERROR = "INTERNAL_ERROR"
UNSUPPORTED_DIFF_SOURCE = "UNSUPPORTED_DIFF_SOURCE"
DIFF_SNAPSHOT_CLEANUP_FAILED = "DIFF_SNAPSHOT_CLEANUP_FAILED"
BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
TRUNCATED = "TRUNCATED"
SOURCE_GENERATION_MISMATCH = "SOURCE_GENERATION_MISMATCH"

_UNSUPPORTED_RECORD_STATUSES = frozenset(
    {"added", "deleted", "renamed", "A", "D", "R", "C"}
)
_STRUCTURAL_INVALID_VERDICTS = frozenset({"REVIEW", "UNSAFE"})

Clock = Callable[[], int]


class PrimitiveExecutor(Protocol):
    """Injected primitive-call seam (implemented by the harness bridge).

    The task layer never imports analyzer internals; the harness wires this
    protocol to the same-process MCP adapters (RFC-0022 §Phase A).
    """

    async def call(
        self, facade: str, action: str, arguments: dict[str, Any]
    ) -> dict[str, Any]: ...


def _default_clock() -> int:
    return int(time.monotonic() * 1000)


def _project_request(request: TaskRequest) -> TaskRequest:
    """Project the frozen request: task text is never frozen (RFC-0022)."""
    budget = request.budget
    if isinstance(request, UnderstandRequest):
        return UnderstandRequest(task=TASK_TEXT_OMITTED, budget=budget)
    if isinstance(request, PlanChangeRequest):
        if request.task:
            return PlanChangeRequest(task=TASK_TEXT_OMITTED, budget=budget)
        return PlanChangeRequest(diff=request.diff, budget=budget)
    if isinstance(request, AssessChangeRequest):
        return AssessChangeRequest(diff=request.diff, budget=budget)
    raise ValueError(
        f"unknown request type {type(request).__name__}"
    )  # pragma: no cover


def _error_outcome(operation: str, request: TaskRequest, code: str) -> TaskOutcome:
    """Freeze a failed outcome: success=false, verdict=ERROR (zero calls)."""
    try:
        projected = _project_request(request)
    except ValueError:  # pragma: no cover - defensive projection fallback
        projected = request
    return TaskOutcome(
        task=operation,  # type: ignore[arg-type]
        request=projected,
        verdict="ERROR",
        status="unknown",
        subject=build_subject_task(),
        errors=(code,),
        budget=build_budget_record(request.budget),
        truncation={"truncated": False, "reason": None, "omitted_rows": []},
        consumed=ConsumedBudget(primitive_calls=0, evidence_items=0, routing_wall_ms=0),
        error=code,
    )


async def understand(
    request: UnderstandRequest,
    executor: PrimitiveExecutor,
    clock: Clock | None = None,
) -> TaskOutcome:
    """Understand: context for task-understanding (RFC-0022 route table)."""
    return await _run_route_guarded(request, "understand", executor, clock)


async def plan_change(
    request: PlanChangeRequest,
    executor: PrimitiveExecutor,
    clock: Clock | None = None,
) -> TaskOutcome:
    """Plan change: task mode (context + file-safety) or diff mode."""
    return await _run_route_guarded(request, "plan_change", executor, clock)


async def assess_change(
    request: AssessChangeRequest,
    executor: PrimitiveExecutor,
    clock: Clock | None = None,
) -> TaskOutcome:
    """Assess change: diff mode only; ``plan_steps`` stays empty."""
    return await _run_route_guarded(request, "assess_change", executor, clock)


async def _run_route_guarded(
    request: TaskRequest,
    operation: str,
    executor: PrimitiveExecutor,
    clock: Clock | None,
) -> TaskOutcome:
    """Boundary guard: internal failures stay inside task-outcome/v1.

    Requests are validated at construction (models raise ValueError), so any
    exception escaping the route body is an internal failure: freeze
    ``INTERNAL_ERROR`` with ``success=false`` / ``verdict=ERROR``
    (RFC-0022 §Fixed task-outcome/v1 semantics).
    """
    try:
        return await _run_route(request, operation, executor, clock)
    except Exception:
        return _error_outcome(operation, request, INTERNAL_ERROR)


async def _run_route(
    request: TaskRequest,
    operation: str,
    executor: PrimitiveExecutor,
    clock: Clock | None,
) -> TaskOutcome:
    clock_fn = clock or _default_clock
    session = RouteSession.from_request(request, executor, clock_fn)
    budget = session.budget
    start_ms = session.start_ms
    snapshot_state = session.snapshots
    ledger = session.ledger
    cleanup = session.cleanup

    contributions = ledger.contributions
    evidence = ledger.evidence
    provenance = ledger.provenance
    freshness_records = ledger.freshness_records
    unknowns = ledger.unknowns
    errors = ledger.errors
    step_fragments = ledger.step_fragments
    relevant_symbols = ledger.relevant_symbols
    relevant_paths = ledger.relevant_paths
    verification = ledger.verification
    claims = ledger.claims
    truncated_rows = ledger.truncated_rows
    truncated_reason: str | None = None
    changed_paths: list[str] = []
    assessed_scope_paths: list[str] = []
    diff_source = "workspace"
    request_diff = getattr(request, "diff", None)
    diff_request = request_diff is not None and isinstance(
        request, (PlanChangeRequest, AssessChangeRequest)
    )
    if diff_request and request_diff is not None:
        diff_source = request_diff.source
    add_unknown = session.add_unknown
    current_snapshots = session.current_snapshots
    mint_evidence = session.mint_evidence
    record_contribution = session.record_contribution
    record_not_called = session.record_not_called
    call = session.call

    try:
        await _router_index.run_index_oracle(session)

        if not session.stopped and diff_request:
            # --- Diff route: impact -> constraints -> fan-out. ---
            assert request_diff is not None
            impact_result = await _router_impact.run_impact_stage(
                session=session, diff=request_diff
            )
            diff_source = impact_result.diff_source
            changed_paths = list(impact_result.changed_paths)
            assessed_scope_paths = list(impact_result.assessed_scope_paths)
            changed_records = list(impact_result.changed_records)
            if not session.stopped:
                await _router_constraints.run_constraints_stage(
                    session=session,
                    assessed_scope_paths=tuple(assessed_scope_paths),
                )

                # Fan-out ast_diff + classify over eligible records.
                if snapshot_state.diff_snapshot_id and not session.stopped:
                    eligible: list[str] = []
                    for record in changed_records or []:
                        if not isinstance(record, dict):
                            continue
                        path = record.get("path")
                        if not isinstance(path, str):
                            continue
                        # Frozen ChangedFile records use Git status codes
                        # (A/D/R/C) plus old/new availability and
                        # unsupported_kind (Codex review #1290); the fan-out
                        # requires both materialized sides.
                        unsupported = (
                            record.get("binary") is True
                            or record.get("status") in _UNSUPPORTED_RECORD_STATUSES
                            or record.get("unsupported_kind") is not None
                            or record.get("old_available") is False
                            or record.get("new_available") is False
                            or record.get("old_kind") not in (None, "file", "missing")
                            or record.get("new_kind") not in (None, "file", "missing")
                        )
                        if unsupported:
                            add_unknown(
                                f"diff:edit.ast_diff:{path}",
                                "not_run:UNSUPPORTED_DIFF_RECORD",
                            )
                            add_unknown(
                                f"diff:edit.classify:{path}",
                                "not_run:UNSUPPORTED_DIFF_RECORD",
                            )
                            continue
                        eligible.append(path)
                    sorted_eligible = sorted(set(eligible))
                    for path_index, path in enumerate(sorted_eligible):  # noqa: C901
                        ast_diff_arguments = {
                            "diff_snapshot_id": snapshot_state.diff_snapshot_id,
                            "file_path": path,
                            "access_mode": "read_existing",
                            "output_format": "json",
                        }
                        ast_diff_response = await call(
                            f"diff:edit.ast_diff:{path}",
                            "edit",
                            "ast_diff",
                            ast_diff_arguments,
                        )
                        if ast_diff_response is None:
                            for remaining in sorted_eligible[path_index:]:
                                record_not_called(
                                    f"diff:edit.ast_diff:{remaining}",
                                    "edit",
                                    "ast_diff",
                                    kind="structural",
                                )
                                record_not_called(
                                    f"diff:edit.classify:{remaining}",
                                    "edit",
                                    "classify",
                                )
                            session.stopped = True
                            break
                        ast_diff_success = ast_diff_response.get("success") is True
                        ast_diff_verdict = ast_diff_response.get("verdict")
                        ast_diff_access_unavailable = _router_wire.access_unavailable(
                            ast_diff_response
                        )
                        if ast_diff_access_unavailable is not None:
                            contribution = contribute(
                                row=f"diff:edit.ast_diff:{path}",
                                state="failed",
                                kind="structural",
                                finding="malformed",
                                freshness=UNKNOWN,
                                truncated=False,
                            )
                            record_contribution(
                                contribution,
                                facade="edit",
                                action="ast_diff",
                                response=ast_diff_response,
                                request_hash=_request_hash(ast_diff_arguments),
                                evidence_ids=[],
                                snapshots=current_snapshots(),
                                success=True,
                            )
                            add_unknown(
                                f"diff:edit.ast_diff:{path}",
                                f"ACCESS_UNAVAILABLE:{ast_diff_access_unavailable}",
                            )
                        elif ast_diff_success:
                            ast_diff_records = _router_wire.echo_records(
                                ast_diff_response
                            )
                            ast_diff_echo_ok = any(
                                record.kind == "diff"
                                and record.snapshot_id
                                == snapshot_state.diff_snapshot_id
                                and record.source_generation
                                == snapshot_state.impact_source_generation
                                for record in ast_diff_records
                            )
                            if not ast_diff_echo_ok:
                                contribution = contribute(
                                    row=f"diff:edit.ast_diff:{path}",
                                    state="failed",
                                    kind="structural",
                                    finding="malformed",
                                    freshness=UNKNOWN,
                                    truncated=False,
                                )
                                record_contribution(
                                    contribution,
                                    facade="edit",
                                    action="ast_diff",
                                    response=ast_diff_response,
                                    request_hash=_request_hash(ast_diff_arguments),
                                    evidence_ids=[],
                                    snapshots=ast_diff_records,
                                    success=True,
                                )
                                add_unknown(
                                    f"diff:edit.ast_diff:{path}",
                                    SOURCE_GENERATION_MISMATCH,
                                )
                                session.stopped = True
                                break
                            finding = (
                                "invalid"
                                if ast_diff_verdict in _STRUCTURAL_INVALID_VERDICTS
                                else _router_wire.finding_from_verdict(ast_diff_verdict)
                            )
                            ast_diff_truncated = (
                                ast_diff_response.get("truncated") is True
                            )
                            contribution = contribute(
                                row=f"diff:edit.ast_diff:{path}",
                                state="succeeded",
                                kind="structural",
                                finding=finding,
                                freshness=FRESH,
                                truncated=ast_diff_truncated,
                                primitive_verdict=_router_wire.primitive_verdict(
                                    ast_diff_verdict
                                ),
                            )
                            evidence_id, evidence_code = mint_evidence(
                                f"diff:edit.ast_diff:{path}",
                                "edit",
                                "ast_diff",
                                ast_diff_response,
                                path,
                                snapshots=ast_diff_records,
                            )
                            if evidence_code == "action_version_missing":
                                contribution = degraded_unknown(contribution)
                            else:
                                contribution = with_evidence(
                                    contribution, evidence_id, locator=path
                                )
                            record_contribution(
                                contribution,
                                facade="edit",
                                action="ast_diff",
                                response=ast_diff_response,
                                request_hash=_request_hash(ast_diff_arguments),
                                evidence_ids=([evidence_id] if evidence_id else []),
                                snapshots=current_snapshots(),
                                success=True,
                            )
                            step_fragments.append(
                                StepFragment(
                                    route="edit.ast_diff",
                                    path=path,
                                    symbol=None,
                                    locator=path,
                                    evidence_id=evidence_id,
                                )
                            )
                        else:
                            contribution = contribute(
                                row=f"diff:edit.ast_diff:{path}",
                                state="failed",
                                kind="structural",
                                finding="malformed",
                                freshness=UNKNOWN,
                                truncated=False,
                            )
                            record_contribution(
                                contribution,
                                facade="edit",
                                action="ast_diff",
                                response=ast_diff_response,
                                request_hash=_request_hash(ast_diff_arguments),
                                evidence_ids=[],
                                snapshots=current_snapshots(),
                                success=False,
                            )
                            add_unknown(
                                f"diff:edit.ast_diff:{path}", "PRIMITIVE_FAILURE"
                            )
                        classify_arguments = {
                            "diff_snapshot_id": snapshot_state.diff_snapshot_id,
                            "file_path": path,
                            "access_mode": "read_existing",
                            "output_format": "json",
                        }
                        classify_response = await call(
                            f"diff:edit.classify:{path}",
                            "edit",
                            "classify",
                            classify_arguments,
                        )
                        if classify_response is None:
                            record_not_called(
                                f"diff:edit.classify:{path}",
                                "edit",
                                "classify",
                            )
                            for remaining in sorted_eligible[path_index + 1 :]:
                                record_not_called(
                                    f"diff:edit.ast_diff:{remaining}",
                                    "edit",
                                    "ast_diff",
                                    kind="structural",
                                )
                                record_not_called(
                                    f"diff:edit.classify:{remaining}",
                                    "edit",
                                    "classify",
                                )
                            session.stopped = True
                            break
                        classify_success = classify_response.get("success") is True
                        classify_verdict = classify_response.get("verdict")
                        classify_access_unavailable = _router_wire.access_unavailable(
                            classify_response
                        )
                        if classify_access_unavailable is not None:
                            contribution = contribute(
                                row=f"diff:edit.classify:{path}",
                                state="failed",
                                kind="generic",
                                finding="malformed",
                                freshness=UNKNOWN,
                                truncated=False,
                            )
                            record_contribution(
                                contribution,
                                facade="edit",
                                action="classify",
                                response=classify_response,
                                request_hash=_request_hash(classify_arguments),
                                evidence_ids=[],
                                snapshots=current_snapshots(),
                                success=True,
                            )
                            add_unknown(
                                f"diff:edit.classify:{path}",
                                f"ACCESS_UNAVAILABLE:{classify_access_unavailable}",
                            )
                        elif classify_success:
                            classify_records = _router_wire.echo_records(
                                classify_response
                            )
                            classify_echo_ok = any(
                                record.kind == "diff"
                                and record.snapshot_id
                                == snapshot_state.diff_snapshot_id
                                and record.source_generation
                                == snapshot_state.impact_source_generation
                                for record in classify_records
                            )
                            if not classify_echo_ok:
                                contribution = contribute(
                                    row=f"diff:edit.classify:{path}",
                                    state="failed",
                                    kind="generic",
                                    finding="malformed",
                                    freshness=UNKNOWN,
                                    truncated=False,
                                )
                                record_contribution(
                                    contribution,
                                    facade="edit",
                                    action="classify",
                                    response=classify_response,
                                    request_hash=_request_hash(classify_arguments),
                                    evidence_ids=[],
                                    snapshots=classify_records,
                                    success=True,
                                )
                                add_unknown(
                                    f"diff:edit.classify:{path}",
                                    SOURCE_GENERATION_MISMATCH,
                                )
                                session.stopped = True
                                break
                            classify_truncated = (
                                classify_response.get("truncated") is True
                            )
                            contribution = contribute(
                                row=f"diff:edit.classify:{path}",
                                state="succeeded",
                                kind="generic",
                                finding=_router_wire.finding_from_verdict(
                                    classify_verdict
                                ),
                                freshness=FRESH,
                                truncated=classify_truncated,
                                primitive_verdict=_router_wire.primitive_verdict(
                                    classify_verdict
                                ),
                            )
                            evidence_id, evidence_code = mint_evidence(
                                f"diff:edit.classify:{path}",
                                "edit",
                                "classify",
                                classify_response,
                                path,
                                snapshots=classify_records,
                            )
                            if evidence_code == "action_version_missing":
                                contribution = degraded_unknown(contribution)
                            else:
                                contribution = with_evidence(
                                    contribution, evidence_id, locator=path
                                )
                            record_contribution(
                                contribution,
                                facade="edit",
                                action="classify",
                                response=classify_response,
                                request_hash=_request_hash(classify_arguments),
                                evidence_ids=([evidence_id] if evidence_id else []),
                                snapshots=current_snapshots(),
                                success=True,
                            )
                            step_fragments.append(
                                StepFragment(
                                    route="edit.classify",
                                    path=path,
                                    symbol=None,
                                    locator=path,
                                    evidence_id=evidence_id,
                                )
                            )
                        else:
                            contribution = contribute(
                                row=f"diff:edit.classify:{path}",
                                state="failed",
                                kind="generic",
                                finding="malformed",
                                freshness=UNKNOWN,
                                truncated=False,
                            )
                            record_contribution(
                                contribution,
                                facade="edit",
                                action="classify",
                                response=classify_response,
                                request_hash=_request_hash(classify_arguments),
                                evidence_ids=[],
                                snapshots=current_snapshots(),
                                success=False,
                            )
                            add_unknown(
                                f"diff:edit.classify:{path}", "PRIMITIVE_FAILURE"
                            )
        elif (
            not session.stopped and not diff_request
        ):  # pragma: no cover - 路由停止状态只会在分支内部设置
            await _router_task.run_task_route(
                session=session,
                operation=operation,
                task=getattr(request, "task", "") or "",
            )
        session.routed_end_ms = clock_fn()
    finally:
        if snapshot_state.diff_snapshot_id and snapshot_state.route_lease_id:
            cleanup.calls = 1
            cleanup_start = clock_fn()
            try:
                cleanup_response = await executor.call(
                    "edit",
                    "release_snapshot",
                    {
                        "diff_snapshot_id": snapshot_state.diff_snapshot_id,
                        "route_lease_id": snapshot_state.route_lease_id,
                    },
                )
            except Exception:
                cleanup_response = {"success": False}
            cleanup.wall_ms = int(clock_fn() - cleanup_start)
            if cleanup_response.get("success") is True:
                cleanup.status = "succeeded"
            else:
                cleanup.status = "failed"
                cleanup.error_code = DIFF_SNAPSHOT_CLEANUP_FAILED

    # --- Freeze one TaskOutcome value. ---
    if truncated_rows:
        truncated_reason = (
            BUDGET_EXHAUSTED
            if session.consumed_calls >= budget.effective_calls
            else TRUNCATED
        )
        errors.append(truncated_reason)
    status, verdict = aggregate_status_and_verdict(contributions)
    # routing wall time excludes the separately-accounted cleanup interval
    # (Codex #1290 P2: cleanup bypasses route admission).
    routing_wall_ms = int(session.routed_end_ms - start_ms)
    if truncated_rows and status == "complete":
        # Omitted decision-relevant evidence forces partial (RFC-0022).
        status = "partial"
    if cleanup.status == "failed":
        errors.append(DIFF_SNAPSHOT_CLEANUP_FAILED)
        status = "unknown"
        verdict = "ERROR"
    if diff_request:
        subject = build_subject_diff(
            diff_source,
            snapshot_state.diff_snapshot_id or "",
            sorted(set(changed_paths)),
        )
    else:
        subject = build_subject_task()
    plan_steps = (
        [] if operation == "assess_change" else project_plan_steps(step_fragments)
    )
    artifacts = build_artifacts(
        relevant_symbols=sorted(set(relevant_symbols)),
        relevant_paths=sorted(set(relevant_paths)),
        plan_steps=plan_steps,
        verification=verification,
    )
    for contribution in contributions:
        if contribution.ignored:  # pragma: no cover - router never emits ignored rows
            continue
        if contribution.evidence_id is not None:
            claims.append(
                {
                    "assertion": "supported",
                    "evidence_id": contribution.evidence_id,
                    "locator": contribution.locator,
                }
            )
        elif contribution.status_contribution == "unknown":
            claims.append(
                {
                    "assertion": "unknown",
                    "evidence_id": None,
                    "locator": contribution.locator,
                }
            )
    next_step = build_next_step(
        operation=operation,
        status=status,
        verdict=verdict,
        unknowns=unknowns,
        freshness=freshness_records,
        plan_steps=plan_steps,
        truncated=bool(truncated_rows),
    )
    agent_summary = build_agent_summary(
        operation=operation,
        status=status,
        verdict=verdict,
        next_step=next_step,
        primitive_calls=session.consumed_calls,
        evidence_items=len(evidence),
        cleanup_status=cleanup.status,
        plan_steps_count=len(plan_steps),
    )
    return TaskOutcome(
        task=operation,  # type: ignore[arg-type]
        request=_project_request(request),
        verdict=verdict,
        status=status,
        subject=subject,
        claims=tuple(claims),
        artifacts=artifacts,
        evidence=tuple(evidence),
        provenance=tuple(provenance),
        freshness=tuple(freshness_records),
        unknowns=tuple(unknowns),
        errors=tuple(errors),
        budget=build_budget_record(budget),
        next_step=next_step,
        agent_summary=agent_summary,
        truncation={
            "truncated": bool(truncated_rows),
            "reason": truncated_reason,
            "omitted_rows": truncated_rows,
        },
        consumed=ConsumedBudget(
            primitive_calls=session.consumed_calls,
            evidence_items=len(evidence),
            routing_wall_ms=routing_wall_ms,
            deadline_overrun_ms=max(0, routing_wall_ms - budget.effective_deadline_ms),
            cleanup_calls=cleanup.calls,
            cleanup_wall_ms=cleanup.wall_ms,
            cleanup_status=cleanup.status,  # type: ignore[arg-type]
            cleanup_error_code=cleanup.error_code,
        ),
        error="ERROR" if verdict == "ERROR" else None,
    )


def build_next_step(
    *,
    operation: str,
    status: Status,
    verdict: Verdict,
    unknowns: list[dict[str, Any]],
    freshness: list[dict[str, Any]],
    plan_steps: list[dict[str, Any]],
    truncated: bool,
) -> str | None:
    """Deterministic, table-driven next-step hint (never evidence).

    RFC-0022: a primitive-provided suggestion is inert suggested text; this
    is the task's own projection of the frozen outcome into one actionable
    sentence. Priority: unlock path (access authority) > oracle freshness >
    budget/deadline > review steps > done state > None.
    """
    for unknown in unknowns:
        reason = str(unknown.get("reason", ""))
        if reason.startswith("ACCESS_UNAVAILABLE:"):
            authority = reason.split(":", 1)[1]
            return (
                f"Read-existing authority unavailable ({authority}): the "
                "zero-write backend is not certified on this platform. "
                "Certify the P0.4 authority or run on a certified OS, then "
                "retry this route."
            )
    for record in freshness:
        reason = str(record.get("reason") or "")
        if record.get("freshness") in {"missing", "unknown"} and (
            reason == "AUTHORITATIVE_SNAPSHOT_UNAVAILABLE"
            or reason.startswith("INCOMPLETE_ORACLE:")
        ):
            return (
                "The index oracle is unavailable or incomplete: run a full "
                "re-index (--full-index), then retry this route."
            )
    if truncated:
        return (
            "Budget or deadline limited the route: raise the profile or "
            "narrow the scope, then retry."
        )
    if operation == "plan_change" and plan_steps:
        paths = sorted({step["path"] for step in plan_steps if step["path"]})
        listed = ", ".join(paths[:5])
        if len(paths) > 5:
            listed += f", \u2026 (+{len(paths) - 5} more)"
        return f"Review the planned change across {len(paths)} file(s): {listed}."
    if (
        operation == "assess_change"
        and status == "complete"
        and verdict
        in {
            "SAFE",
            "INFO",
            "NOT_FOUND",
        }
    ):
        return "No static issues found in the assessed change."
    if status == "unknown":
        return (
            "The route could not establish evidence: check the unknowns "
            "list for the blocking reason."
        )
    return None


def build_agent_summary(
    *,
    operation: str,
    status: Status,
    verdict: Verdict,
    next_step: str | None,
    primitive_calls: int,
    evidence_items: int,
    cleanup_status: str,
    plan_steps_count: int,
) -> dict[str, Any]:
    """Deterministic compact summary for agent branching (never evidence)."""
    return {
        "summary_line": (
            f"task {operation} {status} verdict={verdict} "
            f"calls={primitive_calls} evidence={evidence_items}"
        ),
        "operation": operation,
        "status": status,
        "verdict": verdict,
        "primitive_calls": primitive_calls,
        "evidence_items": evidence_items,
        "cleanup_status": cleanup_status,
        "plan_steps": plan_steps_count,
        "next_step": next_step,
    }
