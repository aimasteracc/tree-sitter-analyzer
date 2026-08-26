"""RFC-0022 task-outcome/v1 deterministic serializers (Phase A).

One execution creates one immutable/frozen ``TaskOutcome``; the serializer
encodes that object to JSON and decodes it back, requiring exact model equality
(RFC-0022 §Determinism). It never compares two live executions. Transport
metadata is outside the semantic model.

Cost invariants (RFC-0022 §Executable value and cost invariants):
- compact model bytes/tokens are strictly less than standard.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from .models import (
    AssessChangeRequest,
    Budget,
    ConsumedBudget,
    DiffInput,
    PlanChangeRequest,
    TaskOutcome,
    TaskRequest,
    UnderstandRequest,
)

_JSON_INDENT = 2


def serialize_json(outcome: TaskOutcome) -> str:
    """Deterministic JSON for one frozen outcome (indent=2, sorted keys)."""
    return json.dumps(
        _outcome_to_dict(outcome),
        indent=_JSON_INDENT,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    )


def decode_json(text: str) -> TaskOutcome:
    """Decode serializer JSON back to the exact frozen model."""
    payload = json.loads(text)
    return _dict_to_outcome(payload)


def _outcome_to_dict(outcome: TaskOutcome) -> dict[str, Any]:
    return {
        "schema": "task-outcome/v1",
        "success": outcome.success,
        "operation": outcome.task,
        "status": outcome.status,
        "verdict": outcome.verdict,
        "subject": outcome.subject,
        "claims": list(outcome.claims),
        "artifacts": outcome.artifacts,
        "evidence": list(outcome.evidence),
        "provenance": list(outcome.provenance),
        "freshness": list(outcome.freshness),
        "unknowns": list(outcome.unknowns),
        "errors": list(outcome.errors),
        "budget": outcome.budget,
        "truncation": outcome.truncation,
        "next_step": outcome.next_step,
        "agent_summary": outcome.agent_summary,
        "consumed": asdict(outcome.consumed) if outcome.consumed else None,
        "error": outcome.error,
        "request": _request_to_dict(outcome.request),
    }


def _request_to_dict(request: TaskRequest) -> dict[str, Any]:
    base: dict[str, Any] = {"budget": asdict(request.budget)}
    if isinstance(request, UnderstandRequest):
        base["kind"] = "understand"
        base["task"] = request.task
    elif isinstance(request, PlanChangeRequest):
        base["kind"] = "plan_change"
        base["task"] = request.task
        base["diff"] = _diff_to_dict(request.diff)
    elif isinstance(request, AssessChangeRequest):
        base["kind"] = "assess_change"
        base["diff"] = _diff_to_dict(request.diff)
    else:  # pragma: no cover - guarded by models
        raise ValueError(f"unknown request type {type(request).__name__}")
    return base


def _diff_to_dict(diff: DiffInput | None) -> dict[str, Any] | None:
    if diff is None:
        return None
    return {
        "source": diff.source,
        "scope_paths": list(diff.scope_paths),
    }


_OUTCOME_KEYS = frozenset(
    {
        "schema",
        "success",
        "operation",
        "status",
        "verdict",
        "subject",
        "claims",
        "artifacts",
        "evidence",
        "provenance",
        "freshness",
        "unknowns",
        "errors",
        "budget",
        "truncation",
        "next_step",
        "agent_summary",
        "consumed",
        "error",
        "request",
    }
)
_SUBJECT_KEYS = frozenset({"task", "diff"})
_ARTIFACT_KEYS = frozenset(
    {
        "relevant_symbols",
        "relevant_paths",
        "plan_steps",
        "verification",
        "edge_collections",
    }
)
_PLAN_STEP_KEYS = frozenset({"ordinal", "kind", "path", "symbol", "evidence_ids"})
_REQUEST_KEYS = frozenset({"kind", "task", "diff", "budget"})
_BUDGET_KEYS = frozenset(
    {"profile", "max_primitive_calls", "max_evidence_items", "routing_deadline_ms"}
)
_BUDGET_RECORD_KEYS = frozenset(
    {
        "profile",
        "max_primitive_calls",
        "max_evidence_items",
        "routing_deadline_ms",
        "effective_calls",
        "effective_evidence",
        "effective_deadline_ms",
    }
)
_TRUNCATION_KEYS = frozenset({"truncated", "reason", "omitted_rows"})
_CONSUMED_KEYS = frozenset(
    {
        "primitive_calls",
        "evidence_items",
        "routing_wall_ms",
        "deadline_overrun_ms",
        "cleanup_calls",
        "cleanup_wall_ms",
        "cleanup_status",
        "cleanup_error_code",
    }
)


def _require_exact_keys(
    payload: dict[str, Any], allowed: frozenset[str], name: str
) -> None:
    """Reject unknown fields (RFC-0022 L398: strict clients reject unknown values)."""
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"{name} carries unknown fields: {sorted(unknown)}")


def _dict_to_outcome(payload: dict[str, Any]) -> TaskOutcome:
    _require_exact_keys(payload, _OUTCOME_KEYS, "outcome")
    request_payload = payload["request"]
    _require_exact_keys(request_payload, _REQUEST_KEYS, "request")
    budget_payload = request_payload["budget"]
    _require_exact_keys(budget_payload, _BUDGET_KEYS, "budget")
    budget = Budget(
        profile=budget_payload["profile"],
        max_primitive_calls=budget_payload.get("max_primitive_calls"),
        max_evidence_items=budget_payload.get("max_evidence_items"),
        routing_deadline_ms=budget_payload.get("routing_deadline_ms"),
    )
    kind = request_payload["kind"]
    if kind == "understand":
        request: TaskRequest = UnderstandRequest(
            task=request_payload["task"], budget=budget
        )
    elif kind == "plan_change":
        request = PlanChangeRequest(
            task=request_payload["task"],
            diff=_dict_to_diff(request_payload.get("diff")),
            budget=budget,
        )
    elif kind == "assess_change":
        request = AssessChangeRequest(
            diff=_dict_to_diff(request_payload["diff"]),
            budget=budget,
        )
    else:  # pragma: no cover - guarded by serializers
        raise ValueError(f"unknown request kind {kind!r}")
    consumed_payload = payload.get("consumed")
    if consumed_payload is not None:
        _require_exact_keys(consumed_payload, _CONSUMED_KEYS, "consumed")
    consumed = (
        ConsumedBudget(
            primitive_calls=consumed_payload["primitive_calls"],
            evidence_items=consumed_payload["evidence_items"],
            routing_wall_ms=consumed_payload["routing_wall_ms"],
            deadline_overrun_ms=consumed_payload.get("deadline_overrun_ms", 0),
            cleanup_calls=consumed_payload.get("cleanup_calls", 0),
            cleanup_wall_ms=consumed_payload.get("cleanup_wall_ms", 0),
            cleanup_status=consumed_payload.get("cleanup_status", "not_required"),
            cleanup_error_code=consumed_payload.get("cleanup_error_code"),
        )
        if consumed_payload is not None
        else None
    )
    # The V1 fixed fields are required (RFC-0022: arrays stay present when
    # empty); a truncated or incompatible wire payload must be rejected, not
    # silently defaulted (Codex review #1290 P2).
    _REQUIRED_OUTCOME_FIELDS = (
        "schema",
        "success",
        "operation",
        "status",
        "verdict",
        "subject",
        "claims",
        "artifacts",
        "evidence",
        "provenance",
        "freshness",
        "unknowns",
        "errors",
        "budget",
        "truncation",
        "next_step",
        "agent_summary",
        "consumed",
        "error",
        "request",
    )
    missing_fields = [name for name in _REQUIRED_OUTCOME_FIELDS if name not in payload]
    if missing_fields:
        raise ValueError(
            f"outcome is missing required fields: {sorted(missing_fields)}"
        )
    subject = payload["subject"]
    _require_exact_keys(subject, _SUBJECT_KEYS, "subject")
    artifacts = payload["artifacts"]
    _require_exact_keys(artifacts, _ARTIFACT_KEYS, "artifacts")
    for step in artifacts.get("plan_steps", []):
        _require_exact_keys(step, _PLAN_STEP_KEYS, "plan_step")
    budget_record = payload["budget"]
    _require_exact_keys(budget_record, _BUDGET_RECORD_KEYS, "budget record")
    truncation = payload["truncation"]
    _require_exact_keys(truncation, _TRUNCATION_KEYS, "truncation")
    return TaskOutcome(
        task=payload["operation"],
        request=request,
        verdict=payload["verdict"],
        status=payload["status"],
        success=payload["success"],
        subject=subject,
        claims=tuple(payload["claims"]),
        artifacts=artifacts,
        evidence=tuple(payload["evidence"]),
        provenance=tuple(payload["provenance"]),
        freshness=tuple(payload["freshness"]),
        unknowns=tuple(payload["unknowns"]),
        errors=tuple(payload["errors"]),
        budget=budget_record,
        truncation=truncation,
        next_step=payload["next_step"],
        agent_summary=payload["agent_summary"],
        consumed=consumed,
        error=payload["error"],
    )


def _dict_to_diff(payload: dict[str, Any] | None) -> DiffInput | None:
    if payload is None:
        return None
    return DiffInput(
        source=payload["source"],
        scope_paths=tuple(payload.get("scope_paths", [])),
    )
