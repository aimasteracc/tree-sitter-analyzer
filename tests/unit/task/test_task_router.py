"""RFC-0022 fixed router contract tests (Phase A, NO1-010A).

Exact pins for route execution (RFC-0022 RED-first acceptance items 3-8):
route order and exact parameters, fan-out order/caps, constraints-slot
reservation, generation stop (including zero constraints calls), cleanup in
an outer finally with fixed accounting, budget/deadline admission and exact
overrun, task-text omission, and the fail-closed rules.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from tree_sitter_analyzer.task import (
    AssessChangeRequest,
    Budget,
    DiffInput,
    PlanChangeRequest,
    UnderstandRequest,
)
from tree_sitter_analyzer.task.router import (
    assess_change,
    plan_change,
    understand,
)
from tree_sitter_analyzer.task.serializers import serialize_json, serialize_toon

INDEX_OK = {
    "success": True,
    "snapshot_id": "idx_snap_1",
    "source_generation": "gen_1",
    "completeness": "complete",
    "action_version": "index.status/v1",
    "source_snapshots": [
        {"kind": "index", "snapshot_id": "idx_snap_1", "source_generation": "gen_1"}
    ],
}

NAV_OK = {
    "success": True,
    "verdict": "INFO",
    "action_version": "nav.context/v1",
    "snapshot_id": "idx_snap_1",
    "source_generation": "gen_1",
    "code_blocks": [
        {"path": "src/z.py", "symbol": "zulu"},
        {"path": "src/a.py", "symbol": "alpha"},
        {"path": "src/m.py", "symbol": "mike"},
    ],
}

SAFE_OK = {
    "success": True,
    "verdict": "SAFE",
    "action_version": "edit.safe/v1",
    "snapshot_id": "idx_snap_1",
    "source_generation": "gen_1",
}

IMPACT_OK = {
    "success": True,
    "verdict": "SAFE",
    "action_version": "edit.impact/v1",
    "diff_snapshot_id": "ds_1",
    "route_lease_id": "lease_1",
    "source_generation": "gen_1",
    "changed_records": [
        {"path": "src/b.py", "status": "modified"},
        {"path": "src/a.py", "status": "modified"},
        {"path": "src/del.py", "status": "deleted"},
    ],
    "assessed_scope_paths": ["src/a.py", "src/b.py", "src/del.py"],
    "source_snapshots": [
        {"kind": "index", "snapshot_id": "idx_snap_1", "source_generation": "gen_1"}
    ],
}

CONSTRAINTS_NO_CONFIG = {
    "success": True,
    "verdict": "SAFE",
    "state": "not_applicable",
    "reason": "NO_CONFIG",
    "violations": [],
    "action_version": "edit.constraints/v1",
    "source_snapshots": [
        {"kind": "index", "snapshot_id": "idx_snap_1", "source_generation": "gen_1"},
        {"kind": "diff", "snapshot_id": "ds_1", "source_generation": "gen_1"},
    ],
}

AST_DIFF_OK = {
    "success": True,
    "verdict": "INFO",
    "action_version": "edit.ast_diff/v1",
}
CLASSIFY_OK = {
    "success": True,
    "verdict": "INFO",
    "action_version": "edit.classify/v1",
}
RELEASE_OK = {"success": True, "action_version": "edit.release_snapshot/v1"}


class FakeExecutor:
    """Scripted PrimitiveExecutor with a call log and a blocking hook."""

    def __init__(self, responses: dict[tuple[str, str], dict[str, Any]] | None = None):
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.responses: dict[tuple[str, str], dict[str, Any]] = dict(responses or {})
        self.block_after: int | None = None  # call index whose await advances clock
        self.clock: list[int] = [0]

    async def call(self, facade, action, arguments):
        self.calls.append((facade, action, dict(arguments)))
        if self.block_after is not None and len(self.calls) == self.block_after:
            self.clock.append(self.clock[-1] + 60_000)
        key = (facade, action)
        if key in self.responses:
            return dict(self.responses[key])
        if key == ("index", "status"):
            return dict(INDEX_OK)
        if key == ("nav", "context"):
            return dict(NAV_OK)
        if key == ("edit", "safe"):
            return dict(SAFE_OK)
        if key == ("edit", "impact"):
            return dict(IMPACT_OK)
        if key == ("edit", "constraints"):
            return dict(CONSTRAINTS_NO_CONFIG)
        if key == ("edit", "ast_diff"):
            return dict(AST_DIFF_OK)
        if key == ("edit", "classify"):
            return dict(CLASSIFY_OK)
        if key == ("edit", "release_snapshot"):
            return dict(RELEASE_OK)
        raise AssertionError(f"unexpected call {facade}.{action}")


def _clock(executor: FakeExecutor):
    return lambda: executor.clock[-1]


def _run(coro):
    return asyncio.run(coro)


# --- Route order and exact parameters ------------------------------------


def test_understand_runs_exact_route_and_parameters() -> None:
    executor = FakeExecutor()
    outcome = _run(
        understand(UnderstandRequest(task="how does dispatch work"), executor)
    )
    assert outcome.verdict == "INFO"
    assert outcome.status == "complete"
    assert [(f, a) for f, a, _ in executor.calls] == [
        ("index", "status"),
        ("nav", "context"),
    ]
    _, _, index_args = executor.calls[0]
    assert index_args == {
        "access_mode": "read_existing",
        "output_format": "json",
    }
    _, _, nav_args = executor.calls[1]
    assert nav_args == {
        "task": "how does dispatch work",
        "max_nodes": 30,
        "max_code_blocks": 5,
        "include_graph": False,
        "access_mode": "read_existing",
        "snapshot_id": "idx_snap_1",
        "source_generation": "gen_1",
        "output_format": "json",
    }


def test_understand_compact_profile_lowers_cell_values() -> None:
    executor = FakeExecutor()
    outcome = _run(
        understand(
            UnderstandRequest(task="x", budget=Budget(profile="compact")),
            executor,
        )
    )
    assert outcome.verdict == "INFO"
    _, _, nav_args = executor.calls[1]
    assert nav_args["max_nodes"] == 12
    assert nav_args["max_code_blocks"] == 3


def test_plan_change_task_fanout_is_sorted_and_capped() -> None:
    executor = FakeExecutor()
    outcome = _run(
        plan_change(
            PlanChangeRequest(
                task="refactor dispatch", budget=Budget(profile="compact")
            ),
            executor,
        )
    )
    safe_calls = [args for f, a, args in executor.calls if (f, a) == ("edit", "safe")]
    assert [args["file_path"] for args in safe_calls] == ["src/a.py", "src/m.py"]
    for args in safe_calls:
        assert args["edit_type"] == "refactor"
        assert args["snapshot_id"] == "idx_snap_1"
        assert args["source_generation"] == "gen_1"
        assert args["access_mode"] == "read_existing"
    assert outcome.status == "complete"
    assert [s["kind"] for s in outcome.artifacts["plan_steps"]] == [
        "inspect_context",
        "inspect_context",
        "inspect_context",
        "check_file_safety",
        "check_file_safety",
    ]
    # Cap is 2 for compact even though three code blocks exist.
    assert len(safe_calls) == 2


def test_plan_change_standard_profile_caps_at_five() -> None:
    executor = FakeExecutor()
    nav = dict(NAV_OK)
    nav["code_blocks"] = [{"path": f"src/p{i}.py", "symbol": f"s{i}"} for i in range(6)]
    executor.responses[("nav", "context")] = nav
    _run(plan_change(PlanChangeRequest(task="refactor many"), executor))
    safe_calls = [args for f, a, args in executor.calls if (f, a) == ("edit", "safe")]
    assert len(safe_calls) == 5


def test_understand_plan_steps_and_artifacts() -> None:
    executor = FakeExecutor()
    outcome = _run(
        understand(UnderstandRequest(task="how does dispatch work"), executor)
    )
    assert outcome.artifacts["relevant_symbols"] == ["alpha", "mike", "zulu"]
    assert outcome.artifacts["relevant_paths"] == [
        "src/a.py",
        "src/m.py",
        "src/z.py",
    ]
    step = outcome.artifacts["plan_steps"][0]
    assert step["kind"] == "inspect_context"
    assert step["ordinal"] == 1
    assert len(step["evidence_ids"]) == 1
    assert step["evidence_ids"][0].startswith("evidence:")


# --- Stop rules -----------------------------------------------------------


def test_missing_oracle_stops_task_rows() -> None:
    executor = FakeExecutor(
        responses={
            ("index", "status"): {
                "success": True,
                "snapshot_id": None,
                "source_generation": None,
                "completeness": "unknown",
                "action_version": "index.status/v1",
                "access_state": "missing",
                "access_reason": "MISSING_INDEX",
            }
        }
    )
    outcome = _run(understand(UnderstandRequest(task="x"), executor))
    assert [(f, a) for f, a, _ in executor.calls] == [("index", "status")]
    assert outcome.status == "unknown"
    assert outcome.verdict == "WARN"
    assert outcome.freshness[0]["freshness"] == "missing"
    assert outcome.freshness[0]["reason"] == "AUTHORITATIVE_SNAPSHOT_UNAVAILABLE"


def test_incomplete_oracle_yields_partial_status() -> None:
    executor = FakeExecutor(
        responses={
            ("index", "status"): {
                "success": True,
                "snapshot_id": "idx_snap_1",
                "source_generation": "gen_1",
                "completeness": "partial",
                "action_version": "index.status/v1",
            }
        }
    )
    outcome = _run(understand(UnderstandRequest(task="x"), executor))
    assert outcome.status == "partial"
    # Freshness unknown degrades the INFO verdict to WARN (fail closed).
    assert outcome.verdict == "WARN"


def test_nav_token_mismatch_stops_route() -> None:
    executor = FakeExecutor(
        responses={
            ("nav", "context"): {
                "success": True,
                "verdict": "INFO",
                "action_version": "nav.context/v1",
                "snapshot_id": "idx_snap_OTHER",
                "source_generation": "gen_1",
                "code_blocks": [{"path": "src/a.py", "symbol": "alpha"}],
            }
        }
    )
    outcome = _run(plan_change(PlanChangeRequest(task="refactor dispatch"), executor))
    safe_calls = [a for f, a, _ in executor.calls if (f, a) == ("edit", "safe")]
    assert safe_calls == []
    # index complete + nav unknown -> partial (RFC aggregate status).
    assert outcome.status == "partial"
    assert any(u["reason"] == "SOURCE_GENERATION_MISMATCH" for u in outcome.unknowns)


def test_diff_route_order_and_reserved_constraints_slot() -> None:
    executor = FakeExecutor()
    outcome = _run(
        assess_change(AssessChangeRequest(diff=DiffInput("workspace")), executor)
    )
    assert [(f, a) for f, a, _ in executor.calls] == [
        ("index", "status"),
        ("edit", "impact"),
        ("edit", "constraints"),
        ("edit", "ast_diff"),
        ("edit", "classify"),
        ("edit", "ast_diff"),
        ("edit", "classify"),
        ("edit", "release_snapshot"),
    ]
    _, _, impact_args = executor.calls[1]
    assert impact_args["mode"] == "diff"
    assert impact_args["include_tests"] is True
    assert impact_args["resource_profile"] == "local_low_impact"
    _, _, constraints_args = executor.calls[2]
    assert constraints_args == {
        "diff_snapshot_id": "ds_1",
        "snapshot_id": "idx_snap_1",
        "source_generation": "gen_1",
        "scope_paths": ["src/a.py", "src/b.py", "src/del.py"],
        "persist": False,
        "access_mode": "read_existing",
        "output_format": "json",
    }
    # Deleted records are explicit not_run, never locally reconstructed.
    assert any(
        u["reason"] == "not_run:UNSUPPORTED_DIFF_RECORD" for u in outcome.unknowns
    )
    # Fan-out sorted by path; only modified records get ast_diff/classify.
    ast_diff_paths = [
        args["file_path"]
        for f, a, args in executor.calls
        if (f, a) == ("edit", "ast_diff")
    ]
    assert ast_diff_paths == ["src/a.py", "src/b.py"]
    assert outcome.status == "complete"
    assert outcome.verdict == "SAFE"
    assert outcome.artifacts["plan_steps"] == []  # assess_change leaves empty
    assert outcome.subject == {
        "diff": {
            "source": "workspace",
            "snapshot_id": "ds_1",
            "changed_paths": ["src/a.py", "src/b.py", "src/del.py"],
        }
    }


def test_diff_budget_three_runs_impact_constraints_but_no_fanout() -> None:
    executor = FakeExecutor()
    outcome = _run(
        assess_change(
            AssessChangeRequest(
                diff=DiffInput("workspace"),
                budget=Budget(profile="compact", max_primitive_calls=3),
            ),
            executor,
        )
    )
    assert [(f, a) for f, a, _ in executor.calls] == [
        ("index", "status"),
        ("edit", "impact"),
        ("edit", "constraints"),
        ("edit", "release_snapshot"),
    ]
    assert outcome.status == "partial"
    assert "BUDGET_EXHAUSTED" in outcome.errors
    assert outcome.truncation["truncated"] is True


def test_diff_impact_generation_mismatch_stops_and_cleans_up() -> None:
    impact = dict(IMPACT_OK)
    impact["source_generation"] = "gen_OTHER"
    executor = FakeExecutor(responses={("edit", "impact"): impact})
    outcome = _run(
        assess_change(AssessChangeRequest(diff=DiffInput("workspace")), executor)
    )
    actions = [(f, a) for f, a, _ in executor.calls]
    assert ("edit", "constraints") not in actions
    assert ("edit", "ast_diff") not in actions
    assert actions[-1] == ("edit", "release_snapshot")  # cleanup still runs
    assert any(u["reason"] == "SOURCE_GENERATION_MISMATCH" for u in outcome.unknowns)
    assert outcome.consumed.cleanup_status == "succeeded"
    assert outcome.consumed.cleanup_calls == 1


def test_diff_missing_oracle_stops_before_constraints_and_fanout() -> None:
    executor = FakeExecutor(
        responses={
            ("index", "status"): {
                "success": True,
                "snapshot_id": None,
                "source_generation": None,
                "completeness": "unknown",
                "action_version": "index.status/v1",
                "access_state": "missing",
                "access_reason": "MISSING_INDEX",
            }
        }
    )
    outcome = _run(
        assess_change(AssessChangeRequest(diff=DiffInput("workspace")), executor)
    )
    actions = [(f, a) for f, a, _ in executor.calls]
    # A diff may call impact, but stops before constraints/fan-out.
    assert ("edit", "impact") in actions
    assert ("edit", "constraints") not in actions
    assert ("edit", "ast_diff") not in actions
    assert any(
        u["row"] == "diff:edit.constraints"
        and u["reason"] == "AUTHORITATIVE_SNAPSHOT_UNAVAILABLE"
        for u in outcome.unknowns
    )
    # impact succeeded (partial freshness) + unknown rows -> partial.
    assert outcome.status == "partial"


def test_constraints_echo_mismatch_stops_fanout() -> None:
    constraints = dict(CONSTRAINTS_NO_CONFIG)
    constraints["source_snapshots"] = [
        {
            "kind": "index",
            "snapshot_id": "idx_snap_OTHER",
            "source_generation": "gen_1",
        },
        {"kind": "diff", "snapshot_id": "ds_1", "source_generation": "gen_1"},
    ]
    executor = FakeExecutor(responses={("edit", "constraints"): constraints})
    outcome = _run(
        assess_change(AssessChangeRequest(diff=DiffInput("workspace")), executor)
    )
    actions = [(f, a) for f, a, _ in executor.calls]
    assert ("edit", "ast_diff") not in actions
    assert any(
        u["row"] == "diff:edit.constraints"
        and u["reason"] == "SOURCE_GENERATION_MISMATCH"
        for u in outcome.unknowns
    )


def test_constraints_no_config_is_a_completed_row() -> None:
    executor = FakeExecutor()
    outcome = _run(
        assess_change(AssessChangeRequest(diff=DiffInput("workspace")), executor)
    )
    verification = outcome.artifacts["verification"]
    constraints_row = next(
        v for v in verification if v["row"] == "diff:edit.constraints"
    )
    assert constraints_row["status_contribution"] == "complete"
    assert constraints_row["verdict_contribution"] is None
    assert constraints_row["finding"] == "no_config"


def test_constraints_violation_preserves_primitive_verdict() -> None:
    constraints = {
        "success": True,
        "verdict": "UNSAFE",
        "state": "applicable",
        "violations": [
            {"severity": "error", "path": "src/a.py", "message": "no direct dep"},
            {"severity": "warning", "path": "src/b.py", "message": "layering"},
        ],
        "action_version": "edit.constraints/v1",
        "source_snapshots": [
            {
                "kind": "index",
                "snapshot_id": "idx_snap_1",
                "source_generation": "gen_1",
            },
            {"kind": "diff", "snapshot_id": "ds_1", "source_generation": "gen_1"},
        ],
    }
    executor = FakeExecutor(responses={("edit", "constraints"): constraints})
    outcome = _run(
        plan_change(PlanChangeRequest(diff=DiffInput("workspace")), executor)
    )
    assert outcome.verdict == "UNSAFE"
    assert outcome.status == "complete"
    kinds = [s["kind"] for s in outcome.artifacts["plan_steps"]]
    assert "check_constraint" in kinds
    # Each violation step cites only its own fragment's evidence ID.
    constraint_steps = [
        s for s in outcome.artifacts["plan_steps"] if s["kind"] == "check_constraint"
    ]
    assert len(constraint_steps) == 2
    assert constraint_steps[0]["evidence_ids"] != constraint_steps[1]["evidence_ids"]


# --- Cleanup accounting ---------------------------------------------------


def test_cleanup_failure_forces_error_outcome() -> None:
    executor = FakeExecutor(
        responses={("edit", "release_snapshot"): {"success": False}}
    )
    outcome = _run(
        assess_change(AssessChangeRequest(diff=DiffInput("workspace")), executor)
    )
    assert outcome.success is False
    assert outcome.verdict == "ERROR"
    assert outcome.status == "unknown"
    assert "DIFF_SNAPSHOT_CLEANUP_FAILED" in outcome.errors
    assert outcome.error == "ERROR"
    assert outcome.consumed.cleanup_status == "failed"
    assert outcome.consumed.cleanup_error_code == "DIFF_SNAPSHOT_CLEANUP_FAILED"


def test_no_cleanup_when_no_diff_snapshot() -> None:
    executor = FakeExecutor()
    outcome = _run(understand(UnderstandRequest(task="x"), executor))
    assert outcome.consumed.cleanup_calls == 0
    assert outcome.consumed.cleanup_status == "not_required"


# --- Budget / deadline ----------------------------------------------------


def test_deadline_blocks_later_calls_and_reports_exact_overrun() -> None:
    executor = FakeExecutor()
    executor.block_after = 2  # nav.context blocks past the deadline
    outcome = _run(
        plan_change(
            PlanChangeRequest(
                task="refactor dispatch", budget=Budget(profile="compact")
            ),
            executor,
            clock=_clock(executor),
        )
    )
    safe_calls = [a for f, a, _ in executor.calls if (f, a) == ("edit", "safe")]
    assert safe_calls == []
    assert outcome.consumed.primitive_calls == 2
    assert outcome.consumed.deadline_overrun_ms == 55_000
    assert "TRUNCATED" in outcome.errors
    assert outcome.truncation["truncated"] is True
    assert any("edit.safe" in row for row in outcome.truncation["omitted_rows"])


def test_budget_exhaustion_stops_before_call() -> None:
    executor = FakeExecutor()
    outcome = _run(
        plan_change(
            PlanChangeRequest(
                task="refactor dispatch",
                budget=Budget(profile="standard", max_primitive_calls=3),
            ),
            executor,
        )
    )
    actions = [(f, a) for f, a, _ in executor.calls]
    assert actions == [("index", "status"), ("nav", "context"), ("edit", "safe")]
    assert "BUDGET_EXHAUSTED" in outcome.errors
    assert outcome.consumed.primitive_calls == 3


def test_failed_calls_consume_budget() -> None:
    executor = FakeExecutor(
        responses={("nav", "context"): {"success": False, "verdict": "ERROR"}}
    )
    outcome = _run(understand(UnderstandRequest(task="x"), executor))
    assert outcome.consumed.primitive_calls == 2
    assert outcome.status == "partial"


# --- Security -------------------------------------------------------------


def test_task_text_never_appears_in_frozen_model() -> None:
    secret_task = "explain the SECRET_TOKEN=abc123 in private/path/key.pem"  # pragma: allowlist secret -- canary bytes must never reach the model
    executor = FakeExecutor()
    outcome = _run(understand(UnderstandRequest(task=secret_task), executor))
    assert outcome.request.task == "TASK_TEXT_OMITTED"
    for text in (serialize_json(outcome), serialize_toon(outcome)):
        assert "SECRET_TOKEN" not in text
        assert "abc123" not in text
        assert "key.pem" not in text
        assert "explain the" not in text
    for record in outcome.provenance:
        assert "SECRET_TOKEN" not in record["request_hash"]


def test_executor_exception_is_redacted_failure() -> None:
    class ExplodingExecutor(FakeExecutor):
        async def call(self, facade, action, arguments):
            self.calls.append((facade, action, dict(arguments)))
            raise RuntimeError("secret traceback detail /home/me/file.py")

    executor = ExplodingExecutor()
    outcome = _run(understand(UnderstandRequest(task="x"), executor))
    # Index failed -> unknown; nav not called -> unknown: all unknown.
    assert outcome.status == "unknown"
    for text in (serialize_json(outcome), serialize_toon(outcome)):
        assert "secret traceback" not in text
        assert "/home/me" not in text


def test_only_pinned_actions_are_ever_called() -> None:
    pinned = {
        ("index", "status"),
        ("nav", "context"),
        ("edit", "safe"),
        ("edit", "impact"),
        ("edit", "constraints"),
        ("edit", "ast_diff"),
        ("edit", "classify"),
        ("edit", "release_snapshot"),
    }
    executor = FakeExecutor()
    _run(assess_change(AssessChangeRequest(diff=DiffInput("staged")), executor))
    _run(understand(UnderstandRequest(task="x"), executor))
    _run(plan_change(PlanChangeRequest(task="y"), executor))
    assert {(f, a) for f, a, _ in executor.calls} <= pinned


def test_router_never_imports_analyzer_internals() -> None:
    import pathlib

    source = (
        pathlib.Path(__file__).parent.parent.parent.parent
        / "tree_sitter_analyzer"
        / "task"
        / "router.py"
    )
    text = source.read_text()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            assert "tree_sitter_analyzer" not in stripped or stripped.startswith(
                "from ."
            ), f"router imports analyzer internals: {stripped}"
    # The retired umbrella prototype is globally guarded by
    # test_tsa_explore_prototype_is_retired_with_zero_references; the router
    # must not import analyzer internals or run commands.
    assert "subprocess" not in text
    assert "os.system" not in text


def test_plan_change_diff_uses_staged_mode() -> None:
    executor = FakeExecutor()
    outcome = _run(
        plan_change(
            PlanChangeRequest(
                diff=DiffInput(source="staged", scope_paths=("src/",)),
            ),
            executor,
        )
    )
    _, _, impact_args = executor.calls[1]
    assert impact_args["mode"] == "staged"
    assert impact_args["scope_paths"] == ["src/"]
    assert outcome.status == "complete"
    kinds = [s["kind"] for s in outcome.artifacts["plan_steps"]]
    assert "review_changed_file" in kinds
    assert "review_structure" in kinds
    assert "review_classification" in kinds


def test_compact_diff_budget_omits_fanout_as_partial() -> None:
    # Compact = 4 primitive calls: index + impact + constraints fill three,
    # so the first fan-out call is admitted and the rest are omitted
    # (BUDGET_EXHAUSTED, partial — RFC: budget omission makes it partial).
    executor = FakeExecutor()
    outcome = _run(
        plan_change(
            PlanChangeRequest(
                diff=DiffInput(source="workspace"),
                budget=Budget(profile="compact"),
            ),
            executor,
        )
    )
    assert outcome.status == "partial"
    assert "BUDGET_EXHAUSTED" in outcome.errors
    assert outcome.truncation["truncated"] is True
    assert any("edit.classify" in row for row in outcome.truncation["omitted_rows"])


def test_nav_access_unavailable_is_fail_closed_not_token_mismatch() -> None:
    # P0.4 (RFC-0022): a primitive may classify an unavailable capability
    # with success=true; Phase A branches on access_state/access_reason.
    executor = FakeExecutor(
        responses={
            ("nav", "context"): {
                "success": True,
                "verdict": "INFO",
                "action_version": "nav.context/v1",
                "access_state": "unknown",
                "access_reason": "READ_EXISTING_AUTHORITY_UNCERTIFIED",
                "code_blocks": [],
            }
        }
    )
    outcome = _run(understand(UnderstandRequest(task="x"), executor))
    assert outcome.status == "partial"
    assert any(
        u["reason"] == "ACCESS_UNAVAILABLE:READ_EXISTING_AUTHORITY_UNCERTIFIED"
        for u in outcome.unknowns
    )
    assert not any(
        u["reason"] == "SOURCE_GENERATION_MISMATCH" for u in outcome.unknowns
    )


def test_diff_impact_access_unavailable_stops_route() -> None:
    impact = dict(IMPACT_OK)
    impact["access_state"] = "unknown"
    impact["access_reason"] = "DIFF_SNAPSHOT_READ_EXISTING_UNSUPPORTED"
    executor = FakeExecutor(responses={("edit", "impact"): impact})
    outcome = _run(
        assess_change(AssessChangeRequest(diff=DiffInput("workspace")), executor)
    )
    actions = [(f, a) for f, a, _ in executor.calls]
    assert ("edit", "constraints") not in actions
    assert ("edit", "ast_diff") not in actions
    assert any(
        u["reason"] == "ACCESS_UNAVAILABLE:DIFF_SNAPSHOT_READ_EXISTING_UNSUPPORTED"
        for u in outcome.unknowns
    )
    # index complete + impact unknown -> partial (RFC aggregate status).
    assert outcome.status == "partial"


def test_serialized_wire_roundtrips_router_outcome() -> None:
    from tree_sitter_analyzer.task.serializers import (
        decode_json,
        decode_toon,
        parity_roundtrip,
    )

    executor = FakeExecutor()
    outcome = _run(
        assess_change(AssessChangeRequest(diff=DiffInput("workspace")), executor)
    )
    parity_roundtrip(outcome)
    assert decode_json(serialize_json(outcome)) == outcome
    assert decode_toon(serialize_toon(outcome)) == outcome
    wire = json.loads(serialize_json(outcome))
    assert wire["schema"] == "task-outcome/v1"
    assert wire["operation"] == "assess_change"
    assert wire["success"] is True
    assert wire["subject"]["diff"]["source"] == "workspace"
    assert wire["artifacts"]["edge_collections"] == []
    assert wire["next_step"] is None
    assert wire["agent_summary"] == {}


# --- Fail-closed branch coverage (codecov patch gate, NO1-010A) -----------


def test_impact_missing_snapshot_fields_is_unknown_and_stops() -> None:
    impact = dict(IMPACT_OK)
    del impact["diff_snapshot_id"]
    executor = FakeExecutor(responses={("edit", "impact"): impact})
    outcome = _run(
        assess_change(AssessChangeRequest(diff=DiffInput("workspace")), executor)
    )
    assert ("edit", "constraints") not in [(f, a) for f, a, _ in executor.calls]
    assert any(
        u["row"] == "diff:edit.impact" and u["reason"] == "MISSING_SNAPSHOT_FIELDS"
        for u in outcome.unknowns
    )
    assert outcome.consumed.cleanup_calls == 0


def test_deadline_stop_before_impact_records_not_called() -> None:
    executor = FakeExecutor()
    executor.block_after = 1  # index.status blocks past the deadline
    outcome = _run(
        assess_change(
            AssessChangeRequest(diff=DiffInput("workspace")),
            executor,
            clock=_clock(executor),
        )
    )
    actions = [(f, a) for f, a, _ in executor.calls]
    assert actions == [("index", "status")]
    # Not-called rows are recorded as contributions and truncation rows.
    assert "diff:edit.impact" in outcome.truncation["omitted_rows"]
    impact_row = next(
        v for v in outcome.artifacts["verification"] if v["row"] == "diff:edit.impact"
    )
    assert impact_row["status_contribution"] == "unknown"
    assert "TRUNCATED" in outcome.errors


def test_budget_floor_rejects_below_three_for_diff() -> None:
    # The diff route requires >= 3 calls at the boundary (RFC-0022); the
    # request model rejects lower explicit budgets before any primitive work.
    with pytest.raises(ValueError, match="BUDGET_INVALID"):
        AssessChangeRequest(
            diff=DiffInput("workspace"),
            budget=Budget(profile="standard", max_primitive_calls=2),
        )


def test_constraints_access_unavailable_stops_fanout() -> None:
    constraints = dict(CONSTRAINTS_NO_CONFIG)
    constraints["access_state"] = "unknown"
    constraints["access_reason"] = "READ_EXISTING_AUTHORITY_UNCERTIFIED"
    executor = FakeExecutor(responses={("edit", "constraints"): constraints})
    outcome = _run(
        assess_change(AssessChangeRequest(diff=DiffInput("workspace")), executor)
    )
    assert ("edit", "ast_diff") not in [(f, a) for f, a, _ in executor.calls]
    assert any(
        u["row"] == "diff:edit.constraints"
        and u["reason"] == "ACCESS_UNAVAILABLE:READ_EXISTING_AUTHORITY_UNCERTIFIED"
        for u in outcome.unknowns
    )


def test_ast_diff_failure_is_partial_and_classify_still_runs() -> None:
    executor = FakeExecutor(
        responses={("edit", "ast_diff"): {"success": False, "verdict": "ERROR"}}
    )
    outcome = _run(
        plan_change(PlanChangeRequest(diff=DiffInput("workspace")), executor)
    )
    actions = [(f, a) for f, a, _ in executor.calls]
    assert ("edit", "classify") in actions  # per-file failure, route continues
    assert any(
        u["row"] == "diff:edit.ast_diff:src/a.py" and u["reason"] == "PRIMITIVE_FAILURE"
        for u in outcome.unknowns
    )
    assert outcome.status == "partial"


def test_ast_diff_access_unavailable_is_per_file_failure() -> None:
    ast_diff = {
        "success": True,
        "verdict": "INFO",
        "access_state": "unknown",
        "access_reason": "UNCERTIFIED_X",
    }
    executor = FakeExecutor(responses={("edit", "ast_diff"): ast_diff})
    outcome = _run(
        assess_change(AssessChangeRequest(diff=DiffInput("workspace")), executor)
    )
    assert any(
        u["reason"] == "ACCESS_UNAVAILABLE:UNCERTIFIED_X" for u in outcome.unknowns
    )


def test_classify_failure_is_partial() -> None:
    executor = FakeExecutor(
        responses={("edit", "classify"): {"success": False, "verdict": "ERROR"}}
    )
    outcome = _run(
        assess_change(AssessChangeRequest(diff=DiffInput("workspace")), executor)
    )
    assert outcome.status == "partial"
    assert any(
        u["row"] == "diff:edit.classify:src/a.py" and u["reason"] == "PRIMITIVE_FAILURE"
        for u in outcome.unknowns
    )


def test_safe_access_unavailable_is_per_call_failure() -> None:
    safe = dict(SAFE_OK)
    safe["access_state"] = "unknown"
    safe["access_reason"] = "READ_EXISTING_AUTHORITY_UNCERTIFIED"
    executor = FakeExecutor(responses={("edit", "safe"): safe})
    outcome = _run(plan_change(PlanChangeRequest(task="refactor dispatch"), executor))
    assert outcome.status == "partial"
    assert any(
        u["row"].startswith("plan_change:edit.safe:")
        and u["reason"] == "ACCESS_UNAVAILABLE:READ_EXISTING_AUTHORITY_UNCERTIFIED"
        for u in outcome.unknowns
    )


def test_error_verdict_on_success_is_malformed_unknown() -> None:
    impact = dict(IMPACT_OK)
    impact["verdict"] = "ERROR"
    executor = FakeExecutor(responses={("edit", "impact"): impact})
    outcome = _run(
        assess_change(AssessChangeRequest(diff=DiffInput("workspace")), executor)
    )
    impact_row = next(
        v for v in outcome.artifacts["verification"] if v["row"] == "diff:edit.impact"
    )
    assert impact_row["finding"] == "malformed"
    assert impact_row["status_contribution"] == "unknown"


def test_success_without_verdict_is_malformed_unknown() -> None:
    impact = dict(IMPACT_OK)
    del impact["verdict"]
    executor = FakeExecutor(responses={("edit", "impact"): impact})
    outcome = _run(
        assess_change(AssessChangeRequest(diff=DiffInput("workspace")), executor)
    )
    impact_row = next(
        v for v in outcome.artifacts["verification"] if v["row"] == "diff:edit.impact"
    )
    assert impact_row["finding"] == "malformed"


def test_echo_records_skips_malformed_entries_then_falls_back() -> None:
    nav = dict(NAV_OK)
    nav["source_snapshots"] = [
        {"kind": "index"},  # missing ids -> skipped
        "junk",  # not a dict -> skipped
    ]
    nav["snapshot_id"] = "idx_snap_1"
    nav["source_generation"] = "gen_1"
    executor = FakeExecutor(responses={("nav", "context"): nav})
    outcome = _run(understand(UnderstandRequest(task="x"), executor))
    # All entries malformed -> empty list -> top-level echo fallback matches.
    assert outcome.status == "complete"
    assert outcome.verdict == "INFO"


def test_nonmatching_source_snapshots_never_fallback_to_top_level() -> None:
    nav = dict(NAV_OK)
    nav["source_snapshots"] = [
        {"kind": "diff", "snapshot_id": "ds_1", "source_generation": "g1"}
    ]
    nav["snapshot_id"] = "idx_snap_1"
    nav["source_generation"] = "gen_1"
    executor = FakeExecutor(responses={("nav", "context"): nav})
    outcome = _run(understand(UnderstandRequest(task="x"), executor))
    # A valid but non-matching record list is a real echo mismatch (fail
    # closed), never silently replaced by the top-level echo.
    assert any(
        u["row"] == "understand:nav.context"
        and u["reason"] == "SOURCE_GENERATION_MISMATCH"
        for u in outcome.unknowns
    )


def test_violation_without_path_mints_no_evidence() -> None:
    constraints = {
        "success": True,
        "verdict": "CAUTION",
        "state": "applicable",
        "violations": [
            {"severity": "warning"},  # no path -> no step/evidence
        ],
        "action_version": "edit.constraints/v1",
        "source_snapshots": [
            {
                "kind": "index",
                "snapshot_id": "idx_snap_1",
                "source_generation": "gen_1",
            },
            {"kind": "diff", "snapshot_id": "ds_1", "source_generation": "gen_1"},
        ],
    }
    executor = FakeExecutor(responses={("edit", "constraints"): constraints})
    outcome = _run(
        plan_change(PlanChangeRequest(diff=DiffInput("workspace")), executor)
    )
    assert not any(
        s["kind"] == "check_constraint" for s in outcome.artifacts["plan_steps"]
    )


def test_internal_error_guard_freezes_internal_error_outcome(monkeypatch) -> None:
    import tree_sitter_analyzer.task.router as router_module

    def boom(fragments):
        raise RuntimeError("router bug")

    monkeypatch.setattr(router_module, "project_plan_steps", boom)
    executor = FakeExecutor()
    outcome = _run(
        plan_change(PlanChangeRequest(diff=DiffInput("workspace")), executor)
    )
    assert outcome.success is False
    assert outcome.verdict == "ERROR"
    assert "INTERNAL_ERROR" in outcome.errors


# --- Remaining branch coverage (codecov patch gate round 2) ---------------


def test_impact_failure_is_unknown_and_stops() -> None:
    executor = FakeExecutor(
        responses={("edit", "impact"): {"success": False, "verdict": "ERROR"}}
    )
    outcome = _run(
        assess_change(AssessChangeRequest(diff=DiffInput("workspace")), executor)
    )
    assert ("edit", "constraints") not in [(f, a) for f, a, _ in executor.calls]
    assert any(
        u["row"] == "diff:edit.impact" and u["reason"] == "PRIMITIVE_FAILURE"
        for u in outcome.unknowns
    )
    assert outcome.consumed.cleanup_calls == 0  # no ids -> no cleanup


def test_impact_missing_lease_id_is_unknown() -> None:
    impact = dict(IMPACT_OK)
    del impact["route_lease_id"]
    executor = FakeExecutor(responses={("edit", "impact"): impact})
    outcome = _run(
        assess_change(AssessChangeRequest(diff=DiffInput("workspace")), executor)
    )
    assert any(
        u["row"] == "diff:edit.impact" and u["reason"] == "MISSING_SNAPSHOT_FIELDS"
        for u in outcome.unknowns
    )
    assert outcome.consumed.cleanup_calls == 0


def test_changed_records_junk_entries_are_skipped() -> None:
    impact = dict(IMPACT_OK)
    impact["changed_records"] = [
        "junk",  # not a dict
        {"status": "modified"},  # no path
        {"path": 42, "status": "modified"},  # non-str path
        {"path": "src/bin.dat", "status": "modified", "binary": True},
        {"path": "src/ok.py", "status": "modified"},
    ]
    executor = FakeExecutor(responses={("edit", "impact"): impact})
    outcome = _run(
        assess_change(AssessChangeRequest(diff=DiffInput("workspace")), executor)
    )
    # Only the valid record is fanned out; junk entries never crash or step.
    ast_diff_paths = [
        args["file_path"]
        for f, a, args in executor.calls
        if (f, a) == ("edit", "ast_diff")
    ]
    assert ast_diff_paths == ["src/ok.py"]
    # Binary records are still changed paths in the subject; only the
    # structural/classification fan-out skips them.
    assert outcome.subject["diff"]["changed_paths"] == ["src/bin.dat", "src/ok.py"]


def test_constraints_deadline_not_called_records_unknown() -> None:
    executor = FakeExecutor()
    executor.block_after = 2  # impact blocks past the deadline
    outcome = _run(
        assess_change(
            AssessChangeRequest(diff=DiffInput("workspace")),
            executor,
            clock=_clock(executor),
        )
    )
    # The deadline is checked before each call: constraints is never started.
    assert "diff:edit.constraints" in outcome.truncation["omitted_rows"]
    assert "TRUNCATED" in outcome.errors
    assert ("edit", "constraints") not in [(f, a) for f, a, _ in executor.calls]


def test_constraints_violations_without_action_version_mint_no_evidence() -> None:
    constraints = {
        "success": True,
        "verdict": "CAUTION",
        "state": "applicable",
        "violations": [{"severity": "warning", "path": "src/a.py"}],
        "source_snapshots": [
            {
                "kind": "index",
                "snapshot_id": "idx_snap_1",
                "source_generation": "gen_1",
            },
            {"kind": "diff", "snapshot_id": "ds_1", "source_generation": "gen_1"},
        ],
        # no action_version -> evidence ownership missing
    }
    executor = FakeExecutor(responses={("edit", "constraints"): constraints})
    outcome = _run(
        plan_change(PlanChangeRequest(diff=DiffInput("workspace")), executor)
    )
    assert any(
        u["row"] == "diff:edit.constraints" and u["reason"] == "ACTION_VERSION_MISSING"
        for u in outcome.unknowns
    )
    assert not any(
        s["kind"] == "check_constraint" for s in outcome.artifacts["plan_steps"]
    )


def test_classify_access_unavailable_is_per_file_failure() -> None:
    classify = {
        "success": True,
        "verdict": "INFO",
        "access_state": "unknown",
        "access_reason": "UNCERTIFIED_Y",
    }
    executor = FakeExecutor(responses={("edit", "classify"): classify})
    outcome = _run(
        assess_change(AssessChangeRequest(diff=DiffInput("workspace")), executor)
    )
    assert any(
        u["reason"] == "ACCESS_UNAVAILABLE:UNCERTIFIED_Y" for u in outcome.unknowns
    )


def test_nav_deadline_not_called_records_unknown() -> None:
    executor = FakeExecutor()
    executor.block_after = 1  # index.status blocks past the deadline
    outcome = _run(
        plan_change(
            PlanChangeRequest(task="refactor dispatch"),
            executor,
            clock=_clock(executor),
        )
    )
    # nav.context is never started after the deadline passes.
    assert "plan_change:nav.context" in outcome.truncation["omitted_rows"]
    assert ("nav", "context") not in [(f, a) for f, a, _ in executor.calls]
    assert ("edit", "safe") not in [(f, a) for f, a, _ in executor.calls]


def test_code_blocks_junk_entries_are_skipped() -> None:
    nav = dict(NAV_OK)
    nav["code_blocks"] = [
        "junk",
        {"path": 42, "symbol": "x"},
        {"path": "src/empty.py", "symbol": ""},
        {"path": "src/real.py", "symbol": "real"},
    ]
    executor = FakeExecutor(responses={("nav", "context"): nav})
    outcome = _run(plan_change(PlanChangeRequest(task="refactor dispatch"), executor))
    safe_calls = [args for f, a, args in executor.calls if (f, a) == ("edit", "safe")]
    # The empty-symbol block has a valid path, so it participates in the
    # fan-out; its symbol is only optional metadata.
    assert [args["file_path"] for args in safe_calls] == ["src/empty.py", "src/real.py"]
    assert outcome.artifacts["relevant_paths"] == ["src/empty.py", "src/real.py"]


def test_safe_echo_mismatch_stops_route() -> None:
    safe = dict(SAFE_OK)
    safe["source_generation"] = "gen_OTHER"
    executor = FakeExecutor(responses={("edit", "safe"): safe})
    outcome = _run(plan_change(PlanChangeRequest(task="refactor dispatch"), executor))
    safe_calls = [args for f, a, args in executor.calls if (f, a) == ("edit", "safe")]
    assert len(safe_calls) == 1  # first mismatch stops the fan-out
    assert any(
        u["row"] == "plan_change:edit.safe:src/a.py"
        and u["reason"] == "SOURCE_GENERATION_MISMATCH"
        for u in outcome.unknowns
    )


def test_safe_failure_is_partial_and_fanout_continues() -> None:
    executor = FakeExecutor(
        responses={("edit", "safe"): {"success": False, "verdict": "ERROR"}}
    )
    outcome = _run(plan_change(PlanChangeRequest(task="refactor dispatch"), executor))
    safe_calls = [args for f, a, args in executor.calls if (f, a) == ("edit", "safe")]
    # All three fan-out paths still run; per-call failure is partial, not a stop.
    assert [args["file_path"] for args in safe_calls] == [
        "src/a.py",
        "src/m.py",
        "src/z.py",
    ]
    assert outcome.status == "partial"
    assert any(
        u["row"].startswith("plan_change:edit.safe:")
        and u["reason"] == "PRIMITIVE_FAILURE"
        for u in outcome.unknowns
    )


def test_release_snapshot_raising_degrades_cleanup_to_failed() -> None:
    class RaisingReleaseExecutor(FakeExecutor):
        async def call(self, facade, action, arguments):
            if action == "release_snapshot":
                raise RuntimeError("cleanup boom")
            return await super().call(facade, action, arguments)

    executor = RaisingReleaseExecutor()
    outcome = _run(
        assess_change(AssessChangeRequest(diff=DiffInput("workspace")), executor)
    )
    assert outcome.success is False
    assert outcome.verdict == "ERROR"
    assert outcome.consumed.cleanup_status == "failed"
    assert outcome.consumed.cleanup_error_code == "DIFF_SNAPSHOT_CLEANUP_FAILED"
    for text in (serialize_json(outcome), serialize_toon(outcome)):
        assert "cleanup boom" not in text


def test_safe_without_action_version_mints_no_evidence() -> None:
    safe = dict(SAFE_OK)
    del safe["action_version"]
    executor = FakeExecutor(responses={("edit", "safe"): safe})
    outcome = _run(plan_change(PlanChangeRequest(task="refactor dispatch"), executor))
    assert any(
        u["row"].startswith("plan_change:edit.safe:")
        and u["reason"] == "ACTION_VERSION_MISSING"
        for u in outcome.unknowns
    )
    safe_steps = [
        s for s in outcome.artifacts["plan_steps"] if s["kind"] == "check_file_safety"
    ]
    assert safe_steps == []  # no evidence -> no step


def test_access_state_without_reason_uses_stable_fallback() -> None:
    nav = dict(NAV_OK)
    nav["access_state"] = "unknown"
    nav.pop("source_snapshots", None)
    executor = FakeExecutor(responses={("nav", "context"): nav})
    outcome = _run(understand(UnderstandRequest(task="x"), executor))
    assert any(
        u["reason"] == "ACCESS_UNAVAILABLE:READ_EXISTING_UNAVAILABLE"
        for u in outcome.unknowns
    )


def test_risk_verdict_on_success_is_complete_risk_finding() -> None:
    safe = dict(SAFE_OK)
    safe["verdict"] = "WARN"
    executor = FakeExecutor(responses={("edit", "safe"): safe})
    outcome = _run(plan_change(PlanChangeRequest(task="refactor dispatch"), executor))
    safe_row = next(
        v
        for v in outcome.artifacts["verification"]
        if v["row"] == "plan_change:edit.safe:src/a.py"
    )
    assert safe_row["finding"] == "risk"
    assert safe_row["status_contribution"] == "complete"
    assert safe_row["verdict_contribution"] == "WARN"
