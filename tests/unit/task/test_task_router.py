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
