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

from .evidence import (
    EvidenceInput,
    SourceSnapshotRecord,
    evidence_identity,
    normalized_result_hash,
)
from .models import (
    TASK_TEXT_OMITTED,
    AssessChangeRequest,
    ConsumedBudget,
    PlanChangeRequest,
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
from .route_table import SAFE_FANOUT_CAPS
from .truth_table import (
    FRESH,
    MISSING,
    NOT_APPLICABLE,
    UNKNOWN,
    Contribution,
    Finding,
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

#: Primitive verdict vocabularies (RFC truth table rows 5-8).
_RISK_VERDICTS = frozenset({"UNSAFE", "WARN", "REVIEW", "CAUTION"})
_NON_RISK_VERDICTS = frozenset({"SAFE", "INFO", "NOT_FOUND"})
_STRUCTURAL_INVALID_VERDICTS = frozenset({"REVIEW", "UNSAFE"})
_UNSUPPORTED_RECORD_STATUSES = frozenset({"added", "deleted", "renamed"})

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


def _finding_from_verdict(verdict: object) -> Finding:
    """Normalize a primitive verdict to a truth-table finding.

    risk verdicts -> ``risk``; non-risk verdicts -> ``none``; anything else
    (missing, unknown, ERROR) -> ``malformed`` so the truth table records
    ``unknown`` (fail closed).
    """
    if isinstance(verdict, str) and verdict in _RISK_VERDICTS:
        return "risk"
    if isinstance(verdict, str) and verdict in _NON_RISK_VERDICTS:
        return "none"
    return "malformed"


def _primitive_verdict(verdict: object) -> Verdict | None:
    if isinstance(verdict, str) and (
        verdict in _RISK_VERDICTS or verdict in _NON_RISK_VERDICTS
    ):
        return verdict  # type: ignore[return-value]  # narrowed by membership
    return None


def _access_unavailable(response: dict[str, Any]) -> str | None:
    """P0.4 access-evidence branch (RFC-0022 §P0.4).

    A primitive may classify an unavailable capability with ``success=true``;
    Phase A branches on ``access_state``/``access_reason``, not on
    ``success``. Returns the stable reason when the capability was not
    available (including ``unknown`` authority), else ``None``.
    """
    state = response.get("access_state")
    if state is not None and state != "available":
        reason = response.get("access_reason")
        if isinstance(reason, str) and reason:
            return reason
        return "READ_EXISTING_UNAVAILABLE"
    return None


def _echo_records(response: dict[str, Any]) -> list[SourceSnapshotRecord]:
    """Extract the stable P0.4 snapshot record list from a primitive result."""
    records: list[SourceSnapshotRecord] = []
    for raw in response.get("source_snapshots") or []:
        if type(raw) is not dict:
            continue
        kind = raw.get("kind")
        snapshot_id = raw.get("snapshot_id")
        source_generation = raw.get("source_generation")
        if (
            kind in {"index", "diff"}
            and isinstance(snapshot_id, str)
            and isinstance(source_generation, str)
        ):
            records.append(
                SourceSnapshotRecord(
                    kind=kind,
                    snapshot_id=snapshot_id,
                    source_generation=source_generation,
                )
            )
    if records:
        return records
    # Fallback: top-level echoes (some adapters echo snapshot_id and
    # source_generation at the top level rather than in access evidence).
    snapshot_id = response.get("snapshot_id")
    source_generation = response.get("source_generation")
    if isinstance(snapshot_id, str) and isinstance(source_generation, str):
        records.append(
            SourceSnapshotRecord(
                kind="index",
                snapshot_id=snapshot_id,
                source_generation=source_generation,
            )
        )
    return records


def _echo_matches(
    records: list[SourceSnapshotRecord], snapshot_id: str, source_generation: str
) -> bool:
    return any(
        record.kind == "index"
        and record.snapshot_id == snapshot_id
        and record.source_generation == source_generation
        for record in records
    )


def _snapshot_wire(records: list[SourceSnapshotRecord]) -> list[dict[str, Any]]:
    return [
        {
            "kind": record.kind,
            "snapshot_id": record.snapshot_id,
            "source_generation": record.source_generation,
        }
        for record in records
    ]


def _request_hash(arguments: dict[str, Any]) -> str:
    """Canonical request hash with task text replaced by the fixed scalar."""
    canonical = dict(arguments)
    if "task" in canonical:
        canonical["task"] = TASK_TEXT_OMITTED
    return normalized_result_hash(canonical)


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
    start_ms = clock_fn()
    budget = request.budget
    deadline_ms = start_ms + budget.effective_deadline_ms

    consumed_calls = 0
    contributions: list[Contribution] = []
    evidence: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    freshness_records: list[dict[str, Any]] = []
    unknowns: list[dict[str, Any]] = []
    errors: list[str] = []
    step_fragments: list[StepFragment] = []
    relevant_symbols: list[str] = []
    relevant_paths: list[str] = []
    verification: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    truncated_rows: list[str] = []
    truncated_reason: str | None = None
    index_snapshot_id: str | None = None
    index_source_generation: str | None = None
    index_complete = False
    oracle_fresh = False
    diff_snapshot_id: str | None = None
    route_lease_id: str | None = None
    impact_source_generation: str | None = None
    changed_paths: list[str] = []
    assessed_scope_paths: list[str] = []
    route_stopped = False
    diff_source = "workspace"
    request_diff = getattr(request, "diff", None)
    diff_request = request_diff is not None and isinstance(
        request, (PlanChangeRequest, AssessChangeRequest)
    )
    if diff_request:
        assert request_diff is not None
        diff_source = request_diff.source
    cleanup_calls = 0
    cleanup_wall_ms = 0
    cleanup_status: str = "not_required"
    cleanup_error_code: str | None = None

    def record_freshness(freshness: str, reason: str | None, tokens: list[str]) -> None:
        freshness_records.append(
            {
                "freshness": freshness,
                "reason": reason,
                "oracle_complete": index_complete,
                "snapshot_id": index_snapshot_id,
                "source_generation": index_source_generation,
                "graph_tokens": tokens,
            }
        )

    def add_unknown(row: str, reason: str) -> None:
        unknowns.append({"row": row, "reason": reason})

    def current_snapshots() -> list[SourceSnapshotRecord]:
        snapshots: list[SourceSnapshotRecord] = []
        if index_snapshot_id and index_source_generation:
            snapshots.append(
                SourceSnapshotRecord(
                    kind="index",
                    snapshot_id=index_snapshot_id,
                    source_generation=index_source_generation,
                )
            )
        if diff_snapshot_id and impact_source_generation:
            snapshots.append(
                SourceSnapshotRecord(
                    kind="diff",
                    snapshot_id=diff_snapshot_id,
                    source_generation=impact_source_generation,
                )
            )
        return snapshots

    def mint_evidence(
        row: str,
        facade: str,
        action: str,
        response: dict[str, Any],
        locator: str | None,
        fragment: dict[str, Any] | None = None,
    ) -> str | None:
        """Mint one evidence ID from the exact wire fragment (RFC-0022).

        Missing/disagreeing ownership mints nothing (``unknown``). The
        fragment defaults to the full response; per-fragment minting (e.g.
        one violation or code block) passes the exact fragment bytes.
        """
        action_version = response.get("action_version")
        if not isinstance(action_version, str) or not action_version:
            add_unknown(row, "ACTION_VERSION_MISSING")
            return None
        canonical_fragment = dict(sorted((fragment or response).items()))
        result_hash = normalized_result_hash(canonical_fragment)
        identity = evidence_identity(
            EvidenceInput(
                primitive_facade=facade,
                action=action,
                action_version=action_version,
                normalized_result_sha256=result_hash,
                source_snapshots=tuple(current_snapshots()),
                locator=locator or "",
            )
        )
        evidence.append(
            {
                "evidence_id": identity,
                "primitive_facade": facade,
                "action": action,
                "action_version": action_version,
                "normalized_result_sha256": result_hash,
                "source_snapshots": _snapshot_wire(current_snapshots()),
                "locator": locator,
            }
        )
        return identity

    def record_contribution(
        contribution: Contribution,
        *,
        facade: str,
        action: str,
        response: dict[str, Any] | None,
        request_hash: str,
        evidence_ids: list[str],
        snapshots: list[SourceSnapshotRecord],
        success: bool,
    ) -> None:
        contributions.append(contribution)
        verification.append(
            {
                "row": contribution.row,
                "facade": facade,
                "action": action,
                "finding": contribution.finding,
                "freshness": contribution.freshness,
                "truncated": contribution.truncated,
                "status_contribution": contribution.status_contribution,
                "verdict_contribution": contribution.verdict_contribution,
                "evidence_id": contribution.evidence_id,
                "locator": contribution.locator,
            }
        )
        provenance.append(
            {
                "row": contribution.row,
                "primitive_facade": facade,
                "action": action,
                "action_version": (
                    response.get("action_version") if response else None
                ),
                "request_hash": request_hash,
                "result_hash": (
                    normalized_result_hash(dict(sorted(response.items())))
                    if response
                    else None
                ),
                "source_snapshots": _snapshot_wire(snapshots),
                "success": success,
                "verdict": response.get("verdict") if response else None,
                "truncated": contribution.truncated,
                "evidence_ids": list(evidence_ids),
            }
        )

    def record_not_called(
        row: str, facade: str, action: str, kind: str = "generic"
    ) -> None:
        """Record an omitted required row (budget/deadline) as not_called."""
        contribution = contribute(
            row=row,
            state="not_called",
            kind=kind,  # type: ignore[arg-type]
            finding="malformed",
            freshness=UNKNOWN,
            truncated=None,
        )
        record_contribution(
            contribution,
            facade=facade,
            action=action,
            response=None,
            request_hash=_request_hash({}),
            evidence_ids=[],
            snapshots=[],
            success=True,
        )

    async def call(
        row: str,
        facade: str,
        action: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any] | None:
        """One routed call: budget/deadline admission, then execute.

        Returns ``None`` when budget or deadline stopped the call before
        admission; a raised executor error degrades to a failed response.
        """
        nonlocal consumed_calls
        if consumed_calls >= budget.effective_calls:
            truncated_rows.append(row)
            return None
        if clock_fn() > deadline_ms:
            truncated_rows.append(row)
            return None
        consumed_calls += 1
        try:
            return await executor.call(facade, action, arguments)
        except Exception:
            return {"success": False, "verdict": "ERROR"}

    def with_evidence(
        contribution: Contribution,
        evidence_id: str | None,
        locator: str | None = None,
    ) -> Contribution:
        return Contribution(
            row=contribution.row,
            kind=contribution.kind,
            state=contribution.state,
            finding=contribution.finding,
            freshness=contribution.freshness,
            truncated=contribution.truncated,
            status_contribution=contribution.status_contribution,
            verdict_contribution=contribution.verdict_contribution,
            locator=(locator if locator is not None else contribution.locator),
            evidence_id=evidence_id,
            primitive_verdict=contribution.primitive_verdict,
        )

    try:
        # --- Row 1: authoritative index snapshot oracle (all routes). ---
        index_response = await call(
            "all:index.status",
            "index",
            "status",
            {"access_mode": "read_existing", "output_format": "json"},
        )
        if index_response is None:  # pragma: no cover - first call is always admitted
            record_freshness(UNKNOWN, "BUDGET_EXHAUSTED", [])
            record_not_called("all:index.status", "index", "status")
        else:
            index_success = index_response.get("success") is True
            index_snapshot_id = index_response.get("snapshot_id")
            index_source_generation = index_response.get("source_generation")
            index_completeness = index_response.get("completeness")
            if not isinstance(index_snapshot_id, str) or not index_snapshot_id:
                index_snapshot_id = None
            if (
                not isinstance(index_source_generation, str)
                or not index_source_generation
            ):
                index_source_generation = None
            index_complete = index_completeness == "complete"
            oracle_fresh = (
                index_success
                and index_snapshot_id is not None
                and index_source_generation is not None
                and index_complete
            )
            if not index_success:
                record_freshness(
                    UNKNOWN,
                    str(
                        index_response.get("access_reason")
                        or "AUTHORITATIVE_SNAPSHOT_UNAVAILABLE"
                    ),
                    [],
                )
                contribution = contribute(
                    row="all:index.status",
                    state="failed",
                    kind="generic",
                    finding="malformed",
                    freshness=UNKNOWN,
                    truncated=False,
                )
                record_contribution(
                    contribution,
                    facade="index",
                    action="status",
                    response=index_response,
                    request_hash=_request_hash({"access_mode": "read_existing"}),
                    evidence_ids=[],
                    snapshots=[],
                    success=False,
                )
                add_unknown("all:index.status", "PRIMITIVE_FAILURE")
            elif index_snapshot_id is None or index_source_generation is None:
                record_freshness(MISSING, "AUTHORITATIVE_SNAPSHOT_UNAVAILABLE", [])
                contribution = contribute(
                    row="all:index.status",
                    state="succeeded",
                    kind="generic",
                    finding="malformed",
                    freshness=MISSING,
                    truncated=False,
                )
                record_contribution(
                    contribution,
                    facade="index",
                    action="status",
                    response=index_response,
                    request_hash=_request_hash({"access_mode": "read_existing"}),
                    evidence_ids=[],
                    snapshots=[],
                    success=True,
                )
                add_unknown("all:index.status", "AUTHORITATIVE_SNAPSHOT_UNAVAILABLE")
            else:
                record_freshness(
                    FRESH if index_complete else UNKNOWN,
                    None
                    if index_complete
                    else f"INCOMPLETE_ORACLE:{index_completeness}",
                    [index_snapshot_id],
                )
                contribution = contribute(
                    row="all:index.status",
                    state="succeeded",
                    kind="generic",
                    finding="none",
                    freshness=FRESH if index_complete else UNKNOWN,
                    truncated=False,
                    primitive_verdict="INFO",
                )
                record_contribution(
                    contribution,
                    facade="index",
                    action="status",
                    response=index_response,
                    request_hash=_request_hash({"access_mode": "read_existing"}),
                    evidence_ids=[],
                    snapshots=current_snapshots(),
                    success=True,
                )

        if not route_stopped and diff_request:
            # --- Diff route: impact -> constraints -> fan-out. ---
            assert request_diff is not None
            impact_arguments = {
                "mode": "diff" if diff_source == "workspace" else "staged",
                "scope_paths": list(request_diff.scope_paths),
                "include_tests": True,
                "resource_profile": "local_low_impact",
                "access_mode": "read_existing",
                "output_format": "json",
            }
            impact_response = await call(
                "diff:edit.impact", "edit", "impact", impact_arguments
            )
            if impact_response is None:
                record_not_called("diff:edit.impact", "edit", "impact")
                route_stopped = True
            else:
                impact_success = impact_response.get("success") is True
                diff_snapshot_id = impact_response.get("diff_snapshot_id")
                route_lease_id = impact_response.get("route_lease_id")
                impact_source_generation = impact_response.get("source_generation")
                changed_records = impact_response.get("changed_records") or []
                assessed_scope_paths = impact_response.get("assessed_scope_paths") or []
                if not isinstance(diff_snapshot_id, str) or not diff_snapshot_id:
                    diff_snapshot_id = None
                if not isinstance(route_lease_id, str) or not route_lease_id:
                    route_lease_id = None
                if (
                    not isinstance(impact_source_generation, str)
                    or not impact_source_generation
                ):
                    impact_source_generation = None
                for record in changed_records:
                    if isinstance(record, dict) and isinstance(record.get("path"), str):
                        changed_paths.append(record["path"])
                snapshots = current_snapshots()
                missing_fields = (
                    diff_snapshot_id is None
                    or route_lease_id is None
                    or impact_source_generation is None
                )
                access_unavailable = _access_unavailable(impact_response)
                if access_unavailable is not None:
                    contribution = contribute(
                        row="diff:edit.impact",
                        state="failed",
                        kind="generic",
                        finding="malformed",
                        freshness=UNKNOWN,
                        truncated=False,
                    )
                    record_contribution(
                        contribution,
                        facade="edit",
                        action="impact",
                        response=impact_response,
                        request_hash=_request_hash(impact_arguments),
                        evidence_ids=[],
                        snapshots=snapshots,
                        success=True,
                    )
                    add_unknown(
                        "diff:edit.impact", f"ACCESS_UNAVAILABLE:{access_unavailable}"
                    )
                    route_stopped = True
                elif not impact_success:
                    contribution = contribute(
                        row="diff:edit.impact",
                        state="failed",
                        kind="generic",
                        finding="malformed",
                        freshness=UNKNOWN,
                        truncated=False,
                    )
                    record_contribution(
                        contribution,
                        facade="edit",
                        action="impact",
                        response=impact_response,
                        request_hash=_request_hash(impact_arguments),
                        evidence_ids=[],
                        snapshots=snapshots,
                        success=False,
                    )
                    add_unknown("diff:edit.impact", "PRIMITIVE_FAILURE")
                    route_stopped = True
                elif missing_fields:
                    contribution = contribute(
                        row="diff:edit.impact",
                        state="failed",
                        kind="generic",
                        finding="malformed",
                        freshness=UNKNOWN,
                        truncated=False,
                    )
                    record_contribution(
                        contribution,
                        facade="edit",
                        action="impact",
                        response=impact_response,
                        request_hash=_request_hash(impact_arguments),
                        evidence_ids=[],
                        snapshots=snapshots,
                        success=True,
                    )
                    add_unknown("diff:edit.impact", "MISSING_SNAPSHOT_FIELDS")
                    route_stopped = True
                elif (
                    index_source_generation is not None
                    and impact_source_generation != index_source_generation
                ):
                    contribution = contribute(
                        row="diff:edit.impact",
                        state="failed",
                        kind="generic",
                        finding="malformed",
                        freshness=UNKNOWN,
                        truncated=False,
                    )
                    record_contribution(
                        contribution,
                        facade="edit",
                        action="impact",
                        response=impact_response,
                        request_hash=_request_hash(impact_arguments),
                        evidence_ids=[],
                        snapshots=snapshots,
                        success=True,
                    )
                    add_unknown("diff:edit.impact", SOURCE_GENERATION_MISMATCH)
                    route_stopped = True
                else:
                    freshness = FRESH if oracle_fresh else UNKNOWN
                    impact_verdict = impact_response.get("verdict")
                    contribution = contribute(
                        row="diff:edit.impact",
                        state="succeeded",
                        kind="generic",
                        finding=_finding_from_verdict(impact_verdict),
                        freshness=freshness,
                        truncated=False,
                        primitive_verdict=_primitive_verdict(impact_verdict),
                    )
                    impact_evidence_id = mint_evidence(
                        "diff:edit.impact",
                        "edit",
                        "impact",
                        impact_response,
                        None,
                    )
                    contribution = with_evidence(contribution, impact_evidence_id)
                    record_contribution(
                        contribution,
                        facade="edit",
                        action="impact",
                        response=impact_response,
                        request_hash=_request_hash(impact_arguments),
                        evidence_ids=(
                            [impact_evidence_id] if impact_evidence_id else []
                        ),
                        snapshots=snapshots,
                        success=True,
                    )
                    for record in changed_records:
                        if isinstance(record, dict) and isinstance(
                            record.get("path"), str
                        ):
                            step_fragments.append(
                                StepFragment(
                                    route="edit.impact",
                                    path=record["path"],
                                    symbol=None,
                                    locator=record["path"],
                                    evidence_id=impact_evidence_id,
                                )
                            )
                if (
                    diff_snapshot_id
                    and route_lease_id
                    and not route_stopped
                    and (index_snapshot_id is None or index_source_generation is None)
                ):
                    # Missing oracle tokens stop before constraints/fan-out.
                    contribution = contribute(
                        row="diff:edit.constraints",
                        state="not_called",
                        kind="constraints",
                        finding="malformed",
                        freshness=UNKNOWN,
                        truncated=None,
                    )
                    record_contribution(
                        contribution,
                        facade="edit",
                        action="constraints",
                        response=None,
                        request_hash=_request_hash({}),
                        evidence_ids=[],
                        snapshots=[],
                        success=True,
                    )
                    add_unknown(
                        "diff:edit.constraints",
                        "AUTHORITATIVE_SNAPSHOT_UNAVAILABLE",
                    )
                    route_stopped = True
                if diff_snapshot_id and route_lease_id and not route_stopped:
                    # Reserved constraints slot, immediately after impact.
                    assert index_snapshot_id is not None
                    assert index_source_generation is not None
                    constraints_arguments = {
                        "diff_snapshot_id": diff_snapshot_id,
                        "snapshot_id": index_snapshot_id,
                        "source_generation": index_source_generation,
                        "scope_paths": list(assessed_scope_paths),
                        "persist": False,
                        "access_mode": "read_existing",
                        "output_format": "json",
                    }
                    constraints_response = await call(
                        "diff:edit.constraints",
                        "edit",
                        "constraints",
                        constraints_arguments,
                    )
                    if constraints_response is None:
                        record_not_called(
                            "diff:edit.constraints",
                            "edit",
                            "constraints",
                            kind="constraints",
                        )
                        route_stopped = True
                    else:
                        constraints_access_unavailable = _access_unavailable(
                            constraints_response
                        )
                        if constraints_access_unavailable is not None:
                            contribution = contribute(
                                row="diff:edit.constraints",
                                state="failed",
                                kind="constraints",
                                finding="malformed",
                                freshness=UNKNOWN,
                                truncated=False,
                            )
                            record_contribution(
                                contribution,
                                facade="edit",
                                action="constraints",
                                response=constraints_response,
                                request_hash=_request_hash(constraints_arguments),
                                evidence_ids=[],
                                snapshots=_echo_records(constraints_response),
                                success=True,
                            )
                            add_unknown(
                                "diff:edit.constraints",
                                f"ACCESS_UNAVAILABLE:{constraints_access_unavailable}",
                            )
                            route_stopped = True
                        else:
                            records = _echo_records(constraints_response)
                            diff_echo_ok = any(
                                record.kind == "diff"
                                and record.snapshot_id == diff_snapshot_id
                                and record.source_generation == impact_source_generation
                                for record in records
                            )
                            index_echo_ok = _echo_matches(
                                records, index_snapshot_id, index_source_generation
                            )
                            state = constraints_response.get("state")
                            reason = constraints_response.get("reason")
                            violations = [
                                dict(item)
                                for item in constraints_response.get("violations") or []
                                if isinstance(item, dict)
                            ]
                            if not diff_echo_ok or not index_echo_ok:
                                contribution = contribute(
                                    row="diff:edit.constraints",
                                    state="failed",
                                    kind="constraints",
                                    finding="malformed",
                                    freshness=UNKNOWN,
                                    truncated=False,
                                )
                                record_contribution(
                                    contribution,
                                    facade="edit",
                                    action="constraints",
                                    response=constraints_response,
                                    request_hash=_request_hash(constraints_arguments),
                                    evidence_ids=[],
                                    snapshots=records,
                                    success=True,
                                )
                                add_unknown(
                                    "diff:edit.constraints",
                                    SOURCE_GENERATION_MISMATCH,
                                )
                                route_stopped = True
                            elif state == "not_applicable" and reason == "NO_CONFIG":
                                contribution = contribute(
                                    row="diff:edit.constraints",
                                    state="succeeded",
                                    kind="constraints",
                                    finding="no_config",
                                    freshness=NOT_APPLICABLE,
                                    truncated=False,
                                )
                                record_contribution(
                                    contribution,
                                    facade="edit",
                                    action="constraints",
                                    response=constraints_response,
                                    request_hash=_request_hash(constraints_arguments),
                                    evidence_ids=[],
                                    snapshots=records,
                                    success=True,
                                )
                            else:
                                constraints_verdict = constraints_response.get(
                                    "verdict"
                                )
                                finding: Finding = (
                                    "violation"
                                    if state == "applicable" and violations
                                    else "none"
                                )
                                contribution = contribute(
                                    row="diff:edit.constraints",
                                    state="succeeded",
                                    kind="constraints",
                                    finding=finding,
                                    freshness=FRESH if oracle_fresh else UNKNOWN,
                                    truncated=False,
                                    primitive_verdict=_primitive_verdict(
                                        constraints_verdict
                                    ),
                                    violations=violations,
                                )
                                violation_evidence_ids: list[str] = []
                                for item in violations:
                                    if not isinstance(item.get("path"), str):
                                        continue
                                    violation_evidence_id = mint_evidence(
                                        "diff:edit.constraints",
                                        "edit",
                                        "constraints",
                                        constraints_response,
                                        item["path"],
                                        fragment=item,
                                    )
                                    if violation_evidence_id is not None:
                                        violation_evidence_ids.append(
                                            violation_evidence_id
                                        )
                                    step_fragments.append(
                                        StepFragment(
                                            route="edit.constraints",
                                            path=item["path"],
                                            symbol=None,
                                            locator=item["path"],
                                            evidence_id=violation_evidence_id,
                                        )
                                    )
                                contribution = with_evidence(
                                    contribution,
                                    violation_evidence_ids[0]
                                    if violation_evidence_ids
                                    else None,
                                )
                                record_contribution(
                                    contribution,
                                    facade="edit",
                                    action="constraints",
                                    response=constraints_response,
                                    request_hash=_request_hash(constraints_arguments),
                                    evidence_ids=violation_evidence_ids,
                                    snapshots=records,
                                    success=True,
                                )

                # Fan-out ast_diff + classify over eligible records.
                if diff_snapshot_id and not route_stopped:
                    eligible: list[str] = []
                    for record in changed_records:
                        if not isinstance(record, dict):
                            continue
                        path = record.get("path")
                        if not isinstance(path, str):
                            continue
                        if record.get("binary") is True:
                            continue
                        if record.get("status") in _UNSUPPORTED_RECORD_STATUSES:
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
                    for path_index, path in enumerate(sorted_eligible):
                        ast_diff_arguments = {
                            "diff_snapshot_id": diff_snapshot_id,
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
                            route_stopped = True
                            break
                        ast_diff_success = ast_diff_response.get("success") is True
                        ast_diff_verdict = ast_diff_response.get("verdict")
                        ast_diff_access_unavailable = _access_unavailable(
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
                            finding = (
                                "invalid"
                                if ast_diff_verdict in _STRUCTURAL_INVALID_VERDICTS
                                else _finding_from_verdict(ast_diff_verdict)
                            )
                            contribution = contribute(
                                row=f"diff:edit.ast_diff:{path}",
                                state="succeeded",
                                kind="structural",
                                finding=finding,
                                freshness=FRESH,
                                truncated=False,
                                primitive_verdict=_primitive_verdict(ast_diff_verdict),
                            )
                            evidence_id = mint_evidence(
                                f"diff:edit.ast_diff:{path}",
                                "edit",
                                "ast_diff",
                                ast_diff_response,
                                path,
                            )
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
                            "diff_snapshot_id": diff_snapshot_id,
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
                            route_stopped = True
                            break
                        classify_success = classify_response.get("success") is True
                        classify_verdict = classify_response.get("verdict")
                        classify_access_unavailable = _access_unavailable(
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
                            contribution = contribute(
                                row=f"diff:edit.classify:{path}",
                                state="succeeded",
                                kind="generic",
                                finding=_finding_from_verdict(classify_verdict),
                                freshness=FRESH,
                                truncated=False,
                                primitive_verdict=_primitive_verdict(classify_verdict),
                            )
                            evidence_id = mint_evidence(
                                f"diff:edit.classify:{path}",
                                "edit",
                                "classify",
                                classify_response,
                                path,
                            )
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
            not route_stopped and not diff_request
        ):  # pragma: no cover - route_stopped is only set inside the branches
            # --- Task route: nav.context (+ edit.safe fan-out for plan). ---
            task_text = getattr(request, "task", "") or ""
            if index_snapshot_id is None or index_source_generation is None:
                contribution = contribute(
                    row=f"{operation}:nav.context",
                    state="not_called",
                    kind="generic",
                    finding="malformed",
                    freshness=UNKNOWN,
                    truncated=None,
                )
                record_contribution(
                    contribution,
                    facade="nav",
                    action="context",
                    response=None,
                    request_hash=_request_hash({}),
                    evidence_ids=[],
                    snapshots=[],
                    success=True,
                )
                add_unknown(
                    f"{operation}:nav.context",
                    "AUTHORITATIVE_SNAPSHOT_UNAVAILABLE",
                )
            else:
                nav_arguments = {
                    "task": task_text,
                    "max_nodes": 12 if budget.profile == "compact" else 30,
                    "max_code_blocks": 3 if budget.profile == "compact" else 5,
                    "include_graph": False,
                    "access_mode": "read_existing",
                    "snapshot_id": index_snapshot_id,
                    "source_generation": index_source_generation,
                    "output_format": "json",
                }
                nav_response = await call(
                    f"{operation}:nav.context",
                    "nav",
                    "context",
                    nav_arguments,
                )
                if nav_response is None:
                    record_not_called(f"{operation}:nav.context", "nav", "context")
                    route_stopped = True
                else:
                    records = _echo_records(nav_response)
                    echo_ok = _echo_matches(
                        records, index_snapshot_id, index_source_generation
                    )
                    nav_success = nav_response.get("success") is True
                    nav_access_unavailable = _access_unavailable(nav_response)
                    if nav_access_unavailable is not None:
                        contribution = contribute(
                            row=f"{operation}:nav.context",
                            state="failed",
                            kind="generic",
                            finding="malformed",
                            freshness=UNKNOWN,
                            truncated=False,
                        )
                        record_contribution(
                            contribution,
                            facade="nav",
                            action="context",
                            response=nav_response,
                            request_hash=_request_hash(nav_arguments),
                            evidence_ids=[],
                            snapshots=records,
                            success=True,
                        )
                        add_unknown(
                            f"{operation}:nav.context",
                            f"ACCESS_UNAVAILABLE:{nav_access_unavailable}",
                        )
                        route_stopped = True
                    elif not nav_success:
                        contribution = contribute(
                            row=f"{operation}:nav.context",
                            state="failed",
                            kind="generic",
                            finding="malformed",
                            freshness=UNKNOWN,
                            truncated=False,
                        )
                        record_contribution(
                            contribution,
                            facade="nav",
                            action="context",
                            response=nav_response,
                            request_hash=_request_hash(nav_arguments),
                            evidence_ids=[],
                            snapshots=records,
                            success=False,
                        )
                        add_unknown(f"{operation}:nav.context", "PRIMITIVE_FAILURE")
                        route_stopped = True
                    elif not echo_ok:
                        contribution = contribute(
                            row=f"{operation}:nav.context",
                            state="failed",
                            kind="generic",
                            finding="malformed",
                            freshness=UNKNOWN,
                            truncated=False,
                        )
                        record_contribution(
                            contribution,
                            facade="nav",
                            action="context",
                            response=nav_response,
                            request_hash=_request_hash(nav_arguments),
                            evidence_ids=[],
                            snapshots=records,
                            success=True,
                        )
                        add_unknown(
                            f"{operation}:nav.context", SOURCE_GENERATION_MISMATCH
                        )
                        route_stopped = True
                    else:
                        nav_verdict = nav_response.get("verdict")
                        contribution = contribute(
                            row=f"{operation}:nav.context",
                            state="succeeded",
                            kind="generic",
                            finding=_finding_from_verdict(nav_verdict),
                            freshness=FRESH if oracle_fresh else UNKNOWN,
                            truncated=False,
                            primitive_verdict=_primitive_verdict(nav_verdict),
                        )
                        record_contribution(
                            contribution,
                            facade="nav",
                            action="context",
                            response=nav_response,
                            request_hash=_request_hash(nav_arguments),
                            evidence_ids=[],
                            snapshots=records,
                            success=True,
                        )
                        code_blocks = nav_response.get("code_blocks") or []
                        block_paths: list[str] = []
                        for block in code_blocks:
                            if not isinstance(block, dict):
                                continue
                            path = block.get("path")
                            symbol = block.get("symbol")
                            if isinstance(path, str):
                                block_paths.append(path)
                                if isinstance(symbol, str) and symbol:
                                    relevant_symbols.append(symbol)
                            evidence_id = mint_evidence(
                                f"{operation}:nav.context",
                                "nav",
                                "context",
                                nav_response,
                                path if isinstance(path, str) else None,
                            )
                            step_fragments.append(
                                StepFragment(
                                    route="nav.context",
                                    path=path if isinstance(path, str) else None,
                                    symbol=(
                                        symbol if isinstance(symbol, str) else None
                                    ),
                                    locator=(path if isinstance(path, str) else None),
                                    evidence_id=evidence_id,
                                )
                            )
                        relevant_paths.extend(block_paths)
                        if operation == "plan_change":
                            safe_paths = sorted(set(block_paths))
                            cap = SAFE_FANOUT_CAPS[budget.profile]
                            for safe_index, path in enumerate(safe_paths[:cap]):
                                safe_arguments = {
                                    "file_path": path,
                                    "edit_type": "refactor",
                                    "snapshot_id": index_snapshot_id,
                                    "source_generation": index_source_generation,
                                    "access_mode": "read_existing",
                                    "output_format": "json",
                                }
                                safe_response = await call(
                                    f"plan_change:edit.safe:{path}",
                                    "edit",
                                    "safe",
                                    safe_arguments,
                                )
                                if safe_response is None:
                                    for remaining in safe_paths[safe_index:]:
                                        record_not_called(
                                            f"plan_change:edit.safe:{remaining}",
                                            "edit",
                                            "safe",
                                        )
                                    route_stopped = True
                                    break
                                safe_records = _echo_records(safe_response)
                                safe_echo_ok = _echo_matches(
                                    safe_records,
                                    index_snapshot_id,
                                    index_source_generation,
                                )
                                safe_success = safe_response.get("success") is True
                                safe_access_unavailable = _access_unavailable(
                                    safe_response
                                )
                                if safe_access_unavailable is not None:
                                    contribution = contribute(
                                        row=f"plan_change:edit.safe:{path}",
                                        state="failed",
                                        kind="generic",
                                        finding="malformed",
                                        freshness=UNKNOWN,
                                        truncated=False,
                                    )
                                    record_contribution(
                                        contribution,
                                        facade="edit",
                                        action="safe",
                                        response=safe_response,
                                        request_hash=_request_hash(safe_arguments),
                                        evidence_ids=[],
                                        snapshots=safe_records,
                                        success=True,
                                    )
                                    add_unknown(
                                        f"plan_change:edit.safe:{path}",
                                        f"ACCESS_UNAVAILABLE:{safe_access_unavailable}",
                                    )
                                    continue
                                if not safe_success:
                                    contribution = contribute(
                                        row=f"plan_change:edit.safe:{path}",
                                        state="failed",
                                        kind="generic",
                                        finding="malformed",
                                        freshness=UNKNOWN,
                                        truncated=False,
                                    )
                                    record_contribution(
                                        contribution,
                                        facade="edit",
                                        action="safe",
                                        response=safe_response,
                                        request_hash=_request_hash(safe_arguments),
                                        evidence_ids=[],
                                        snapshots=safe_records,
                                        success=False,
                                    )
                                    add_unknown(
                                        f"plan_change:edit.safe:{path}",
                                        "PRIMITIVE_FAILURE",
                                    )
                                    continue
                                if not safe_echo_ok:
                                    contribution = contribute(
                                        row=f"plan_change:edit.safe:{path}",
                                        state="failed",
                                        kind="generic",
                                        finding="malformed",
                                        freshness=UNKNOWN,
                                        truncated=False,
                                    )
                                    record_contribution(
                                        contribution,
                                        facade="edit",
                                        action="safe",
                                        response=safe_response,
                                        request_hash=_request_hash(safe_arguments),
                                        evidence_ids=[],
                                        snapshots=safe_records,
                                        success=True,
                                    )
                                    add_unknown(
                                        f"plan_change:edit.safe:{path}",
                                        SOURCE_GENERATION_MISMATCH,
                                    )
                                    route_stopped = True
                                    break
                                safe_verdict = safe_response.get("verdict")
                                contribution = contribute(
                                    row=f"plan_change:edit.safe:{path}",
                                    state="succeeded",
                                    kind="generic",
                                    finding=_finding_from_verdict(safe_verdict),
                                    freshness=FRESH if oracle_fresh else UNKNOWN,
                                    truncated=False,
                                    primitive_verdict=_primitive_verdict(safe_verdict),
                                )
                                evidence_id = mint_evidence(
                                    f"plan_change:edit.safe:{path}",
                                    "edit",
                                    "safe",
                                    safe_response,
                                    path,
                                )
                                contribution = with_evidence(
                                    contribution, evidence_id, locator=path
                                )
                                record_contribution(
                                    contribution,
                                    facade="edit",
                                    action="safe",
                                    response=safe_response,
                                    request_hash=_request_hash(safe_arguments),
                                    evidence_ids=([evidence_id] if evidence_id else []),
                                    snapshots=safe_records,
                                    success=True,
                                )
                                relevant_paths.append(path)
                                step_fragments.append(
                                    StepFragment(
                                        route="edit.safe",
                                        path=path,
                                        symbol=None,
                                        locator=path,
                                        evidence_id=evidence_id,
                                    )
                                )
    finally:
        if diff_snapshot_id and route_lease_id:
            cleanup_calls = 1
            cleanup_start = clock_fn()
            try:
                cleanup_response = await executor.call(
                    "edit",
                    "release_snapshot",
                    {
                        "diff_snapshot_id": diff_snapshot_id,
                        "route_lease_id": route_lease_id,
                    },
                )
            except Exception:
                cleanup_response = {"success": False}
            cleanup_wall_ms = int(clock_fn() - cleanup_start)
            if cleanup_response.get("success") is True:
                cleanup_status = "succeeded"
            else:
                cleanup_status = "failed"
                cleanup_error_code = DIFF_SNAPSHOT_CLEANUP_FAILED

    # --- Freeze one TaskOutcome value. ---
    if truncated_rows:
        truncated_reason = (
            BUDGET_EXHAUSTED if consumed_calls >= budget.effective_calls else TRUNCATED
        )
        errors.append(truncated_reason)
    status, verdict = aggregate_status_and_verdict(contributions)
    routing_wall_ms = int(clock_fn() - start_ms)
    if cleanup_status == "failed":
        errors.append(DIFF_SNAPSHOT_CLEANUP_FAILED)
        status = "unknown"
        verdict = "ERROR"
    if diff_request:
        subject = build_subject_diff(
            diff_source,
            diff_snapshot_id or "",
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
        truncation={
            "truncated": bool(truncated_rows),
            "reason": truncated_reason,
            "omitted_rows": truncated_rows,
        },
        consumed=ConsumedBudget(
            primitive_calls=consumed_calls,
            evidence_items=len(evidence),
            routing_wall_ms=routing_wall_ms,
            deadline_overrun_ms=max(0, routing_wall_ms - budget.effective_deadline_ms),
            cleanup_calls=cleanup_calls,
            cleanup_wall_ms=cleanup_wall_ms,
            cleanup_status=cleanup_status,  # type: ignore[arg-type]
            cleanup_error_code=cleanup_error_code,
        ),
        error="ERROR" if verdict == "ERROR" else None,
    )
