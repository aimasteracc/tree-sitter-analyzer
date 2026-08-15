"""RFC-0022 task-outcome/v1 deterministic serializers (Phase A).

One execution creates one immutable/frozen ``TaskOutcome``; the parity oracle
serializes that same object through JSON and TOON, decodes both, and requires
exact model equality (RFC-0022 §Determinism and serializer parity). It never
compares two live executions. Transport metadata is outside the semantic
model.

Cost invariants (RFC-0022 §Executable value and cost invariants):
- compact model bytes/tokens are strictly less than standard;
- TOON bytes do not exceed JSON bytes for the same frozen model;
- decoding JSON and TOON yields exactly the same frozen model.
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


def serialize_toon(outcome: TaskOutcome) -> str:
    """Deterministic TOON line format for one frozen outcome.

    Line-oriented ``key: value`` with two-space indentation, lists as
    ``- item`` lines — the same shape MCP ``toon_content`` blobs use, so
    agents already familiar with TOON can read task outcomes without a new
    format.
    """
    return _toon_lines(_outcome_to_dict(outcome), depth=0)


def decode_json(text: str) -> TaskOutcome:
    """Decode serializer JSON back to the exact frozen model."""
    payload = json.loads(text)
    return _dict_to_outcome(payload)


def decode_toon(text: str) -> TaskOutcome:
    """Decode serializer TOON back to the exact frozen model."""
    return _dict_to_outcome(_parse_toon(text))


def parity_roundtrip(outcome: TaskOutcome) -> None:
    """Assert JSON/TOON decode to the exact same frozen model.

    Raises AssertionError when the two serializers disagree — the parity
    oracle contract.
    """
    from_json = decode_json(serialize_json(outcome))
    from_toon = decode_toon(serialize_toon(outcome))
    assert from_json == from_toon, "JSON/TOON parity violated"
    assert from_json == outcome, "JSON roundtrip not identity"
    assert from_toon == outcome, "TOON roundtrip not identity"


def json_vs_toon_bytes(outcome: TaskOutcome) -> tuple[int, int]:
    """Return (json_bytes, toon_bytes) for the same frozen model."""
    return (
        len(serialize_json(outcome).encode("utf-8")),
        len(serialize_toon(outcome).encode("utf-8")),
    )


def _outcome_to_dict(outcome: TaskOutcome) -> dict[str, Any]:
    return {
        "schema": "task-outcome/v1",
        "task": outcome.task,
        "verdict": outcome.verdict,
        "status": outcome.status,
        "error": outcome.error,
        "evidence": list(outcome.evidence),
        "consumed": asdict(outcome.consumed) if outcome.consumed else None,
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


def _toon_lines(value: Any, *, depth: int) -> str:
    lines: list[str] = []
    if isinstance(value, dict):
        if not value:
            return "{}" + "\n"  # pragma: no cover - empty dicts are scalarized upstream
        for key in sorted(value):
            prefix = "  " * depth
            item = value[key]
            if isinstance(item, dict) and item:
                lines.append(f"{prefix}{key}:")
                lines.append(_toon_lines(item, depth=depth + 1))
            elif isinstance(item, list) and item:
                lines.append(f"{prefix}{key}:")
                lines.append(_toon_lines(item, depth=depth + 1))
            else:
                lines.append(f"{prefix}{key}: {_toon_scalar(item)}")
    elif isinstance(value, list):
        if not value:
            return "[]" + "\n"  # pragma: no cover - empty lists are scalarized upstream
        for item in value:
            prefix = "  " * depth
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{prefix}-")
                lines.append(_toon_lines(item, depth=depth + 1))
            else:
                lines.append(f"{prefix}- {_toon_scalar(item)}")
    return "\n".join(lines) + "\n"


def _toon_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        # Symmetric JSON-style quoting: newlines, quotes, backslashes and
        # surrounding whitespace survive the roundtrip losslessly.
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (dict, list)) and not value:
        return "{}" if isinstance(value, dict) else "[]"
    return str(value)


def _parse_toon(text: str) -> dict[str, Any]:
    """Parse the TOON line format back into nested dict/list structure.

    A ``key:`` line with no value opens a child whose kind (dict or list) is
    decided by the first following line: a ``- `` item makes it a list.
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any] | list[Any]]] = [(0, root)]
    pending_child: tuple[dict[str, Any], str] | None = None
    pending_item: list[Any] | None = None
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        is_item = line.startswith("-")
        if is_item:
            line = line[1:].strip()
        target_depth = indent // 2
        while len(stack) > 1 and target_depth < stack[-1][0]:
            stack.pop()
        _parent_depth, parent = stack[-1]
        if pending_item is not None:
            # A bare ``-`` opened an item whose kind (dict or list) is
            # decided by this first content line.
            list_parent = pending_item
            pending_item = None
            if is_item:
                nested_item: dict[str, Any] | list[Any] = []
            else:
                nested_item = {}
            list_parent.append(nested_item)
            stack.append((target_depth, nested_item))
            parent = nested_item
        if pending_child is not None:
            # The previous bare key decides its kind now.
            container_parent, container_key = pending_child
            pending_child = None
            if is_item:
                opened: dict[str, Any] | list[Any] = []
            else:
                opened = {}
            container_parent[container_key] = opened
            stack.append((target_depth, opened))
            parent = opened
        if not is_item and isinstance(parent, list):
            # A continuation line after a list item belongs to that item.
            if not parent or not isinstance(parent[-1], dict):
                raise ValueError(  # pragma: no cover - pytest.raises verifies
                    "TOON continuation outside a list item"
                )
            parent = parent[-1]
        if is_item:
            if not isinstance(parent, list):
                raise ValueError(  # pragma: no cover - pytest.raises verifies
                    "TOON item outside a list"
                )
            if not line:
                # A bare ``-`` opens an item whose kind is decided by the
                # next line (dict for keys, list for nested ``-`` items).
                pending_item = parent
                continue
            if line.startswith('"'):
                # Quoted string item first: a colon inside it is data.
                parent.append(_parse_toon_scalar(line))
            elif ":" in line:
                key, _, value = line.partition(":")
                value = value.strip()
                item: dict[str, Any] = {}
                parent.append(item)
                if value:
                    item[key.strip()] = _parse_toon_scalar(value)
                else:
                    pending_child = (item, key.strip())
                stack.append((target_depth + 1, item))
            else:
                # Scalar item: must be a quoted string or exact literal.
                parent.append(_parse_toon_scalar(line))
            continue
        if ":" not in line:
            raise ValueError(f"TOON line lacks a key: {raw_line!r}")
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if isinstance(parent, list):
            raise ValueError(
                "TOON key line inside a list"
            )  # pragma: no cover - continuation handles list parents
        if value:
            parent[key] = _parse_toon_scalar(value)
            continue
        pending_child = (parent, key)
    if pending_child is not None:
        parent, key = pending_child
        parent[key] = {}
    if pending_item is not None:
        pending_item.append({})
    return root


def _parse_toon_scalar(value: str) -> Any:
    if value == "null":
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    if value == "[]":
        return []
    if value == "{}":
        return {}
    if value.startswith('"'):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid quoted TOON string: {value!r}") from exc
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"unquoted TOON value must be a literal: {value!r}") from None


_OUTCOME_KEYS = frozenset(
    {"schema", "task", "verdict", "status", "error", "evidence", "consumed", "request"}
)
_REQUEST_KEYS = frozenset({"kind", "task", "diff", "budget"})
_BUDGET_KEYS = frozenset(
    {"profile", "max_primitive_calls", "max_evidence_items", "routing_deadline_ms"}
)
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
    return TaskOutcome(
        task=payload["task"],
        request=request,
        verdict=payload["verdict"],
        status=payload.get("status", "unknown"),
        evidence=tuple(payload.get("evidence", [])),
        consumed=consumed,
        error=payload.get("error"),
    )


def _dict_to_diff(payload: dict[str, Any] | None) -> DiffInput | None:
    if payload is None:
        return None
    return DiffInput(
        source=payload["source"],
        scope_paths=tuple(payload.get("scope_paths", [])),
    )
