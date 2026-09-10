"""NO1-010A follow-up: actionable outputs and adapter-boundary wire contract.

Two contracts:

1. ``build_next_step`` / ``build_agent_summary`` — the frozen outcome must
   tell an agent what to do next (unlock path, re-index, budget, review
   list, done) and give a compact deterministic summary to branch on.
   Suggestions are inert text, never evidence (RFC-0022).
2. The router must project the REAL primitive wire shapes, not test-only
   ones: code blocks use ``file``/``name``, constraint violations use
   ``caller_file``/``caller_name``, frozen changed records use Git status
   codes plus old/new availability. These fixtures are copies of the real
   adapter output shapes (codegraph_context_tool ``_build_code_blocks``,
   constraints evaluator rows, ``ChangedFile.to_dict``).
"""

from __future__ import annotations

import asyncio

from tree_sitter_analyzer.task import (
    Budget,
    DiffInput,
    PlanChangeRequest,
    UnderstandRequest,
)
from tree_sitter_analyzer.task.router import (
    build_agent_summary,
    build_next_step,
    plan_change,
    understand,
)
from tree_sitter_analyzer.task.serializers import decode_json, serialize_json

# --- Real-wire fixtures (copied shapes from the live adapters) ---------------

REAL_INDEX_STATUS = {
    "success": True,
    "verdict": "INFO",
    "snapshot_id": "idxsnap_real1",
    "source_generation": "idxsrc-v3:abc123",
    "completeness": "complete",
    "action_version": "index.status/v1",
    "source_snapshots": [
        {
            "kind": "index",
            "snapshot_id": "idxsnap_real1",
            "source_generation": "idxsrc-v3:abc123",
        }
    ],
}

#: Real CodeGraphContextTool code blocks (codegraph_context_tool.py ~L907):
#: {"file", "name", "start_line", "end_line", "content"}.
REAL_NAV_CONTEXT = {
    "success": True,
    "verdict": "INFO",
    "action_version": "nav.context/v1",
    "snapshot_id": "idxsnap_real1",
    "source_generation": "idxsrc-v3:abc123",
    "code_blocks": [
        {
            "file": "src/app.py",
            "name": "dispatch",
            "start_line": 3,
            "end_line": 9,
            "content": "def dispatch(request):\\n    ...\\n",
        },
        {
            "file": "src/app.py",
            "name": "handle_ping",
            "start_line": 11,
            "end_line": 13,
            "content": "def handle_ping(request):\\n    ...\\n",
        },
    ],
}

#: Real frozen impact records (ChangedFile.to_dict): Git status codes +
#: availability fields; assessed scope from the frozen capture.
REAL_IMPACT = {
    "success": True,
    "verdict": "SAFE",
    "action_version": "edit.impact/v1",
    "diff_snapshot_id": "ds_real1",
    "route_lease_id": "lease_real1",
    "source_generation": "idxsrc-v3:abc123",
    "changed_records": [
        {
            "path": "src/app.py",
            "status": "M",
            "old_available": True,
            "new_available": True,
            "binary": False,
            "patch_available": True,
            "old_kind": "file",
            "new_kind": "file",
        },
        {
            "path": "src/gone.py",
            "status": "D",
            "old_available": True,
            "new_available": False,
            "binary": False,
            "patch_available": True,
            "old_kind": "file",
            "new_kind": "missing",
        },
    ],
    "assessed_scope_paths": ["src/app.py", "src/gone.py"],
    "source_snapshots": [
        {
            "kind": "index",
            "snapshot_id": "idxsnap_real1",
            "source_generation": "idxsrc-v3:abc123",
        }
    ],
}

#: Real constraints rows (evaluator SELECT): caller_name, caller_file,
#: caller_line, callee_name, callee_file, severity.
REAL_CONSTRAINTS = {
    "success": True,
    "verdict": "UNSAFE",
    "state": "applicable",
    "action_version": "edit.constraints/v1",
    "violations": [
        {
            "rule_id": "no_direct_dep",
            "caller_name": "dispatch",
            "caller_file": "src/app.py",
            "caller_line": 4,
            "callee_name": "handle_ping",
            "callee_file": "src/app.py",
            "severity": "error",
        }
    ],
    "source_snapshots": [
        {
            "kind": "index",
            "snapshot_id": "idxsnap_real1",
            "source_generation": "idxsrc-v3:abc123",
        },
        {
            "kind": "diff",
            "snapshot_id": "ds_real1",
            "source_generation": "idxsrc-v3:abc123",
        },
    ],
}

REAL_AST_DIFF = {
    "success": True,
    "verdict": "INFO",
    "action_version": "edit.ast_diff/v1",
    "source_snapshots": [
        {
            "kind": "diff",
            "snapshot_id": "ds_real1",
            "source_generation": "idxsrc-v3:abc123",
        }
    ],
}

REAL_CLASSIFY = {
    "success": True,
    "verdict": "INFO",
    "action_version": "edit.classify/v1",
    "truncated": False,
    "source_snapshots": [
        {
            "kind": "diff",
            "snapshot_id": "ds_real1",
            "source_generation": "idxsrc-v3:abc123",
        }
    ],
}


class RealWireExecutor:
    """Serves the real-wire fixtures and records the arguments used."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    async def call(self, facade, action, arguments):
        self.calls.append((facade, action, dict(arguments)))
        fixtures = {
            ("index", "status"): REAL_INDEX_STATUS,
            ("nav", "context"): REAL_NAV_CONTEXT,
            ("edit", "impact"): REAL_IMPACT,
            ("edit", "constraints"): REAL_CONSTRAINTS,
            ("edit", "ast_diff"): REAL_AST_DIFF,
            ("edit", "classify"): REAL_CLASSIFY,
            ("edit", "safe"): {
                "success": True,
                "verdict": "SAFE",
                "action_version": "edit.safe/v1",
                "snapshot_id": "idxsnap_real1",
                "source_generation": "idxsrc-v3:abc123",
            },
            ("edit", "release_snapshot"): {"success": True},
        }
        return dict(fixtures[(facade, action)])


def _run(coro):
    return asyncio.run(coro)


# --- Actionable outputs ------------------------------------------------------


def test_next_step_reports_unlock_path_for_uncertified_authority() -> None:
    hint = build_next_step(
        operation="understand",
        status="partial",
        verdict="WARN",
        unknowns=[
            {
                "row": "understand:nav.context",
                "reason": "ACCESS_UNAVAILABLE:READ_EXISTING_AUTHORITY_UNCERTIFIED",
            }
        ],
        freshness=[],
        plan_steps=[],
        truncated=False,
    )
    assert hint is not None
    assert "READ_EXISTING_AUTHORITY_UNCERTIFIED" in hint
    assert "certif" in hint.lower()


def test_next_step_reports_reindex_for_missing_oracle() -> None:
    hint = build_next_step(
        operation="understand",
        status="unknown",
        verdict="WARN",
        unknowns=[],
        freshness=[
            {"freshness": "missing", "reason": "AUTHORITATIVE_SNAPSHOT_UNAVAILABLE"}
        ],
        plan_steps=[],
        truncated=False,
    )
    assert hint is not None
    assert "re-index" in hint
    hint2 = build_next_step(
        operation="understand",
        status="partial",
        verdict="WARN",
        unknowns=[],
        freshness=[{"freshness": "unknown", "reason": "INCOMPLETE_ORACLE:partial"}],
        plan_steps=[],
        truncated=False,
    )
    assert "re-index" in hint2


def test_next_step_reports_budget_truncation() -> None:
    hint = build_next_step(
        operation="assess_change",
        status="partial",
        verdict="WARN",
        unknowns=[],
        freshness=[],
        plan_steps=[],
        truncated=True,
    )
    assert hint is not None
    assert "Budget" in hint


def test_next_step_lists_review_files_for_plan_change() -> None:
    hint = build_next_step(
        operation="plan_change",
        status="complete",
        verdict="SAFE",
        unknowns=[],
        freshness=[],
        plan_steps=[
            {
                "ordinal": 1,
                "kind": "check_file_safety",
                "path": "src/app.py",
                "symbol": None,
                "evidence_ids": ["evidence:e1"],
            },
            {
                "ordinal": 2,
                "kind": "check_constraint",
                "path": "src/app.py",
                "symbol": None,
                "evidence_ids": ["evidence:e2"],
            },
        ],
        truncated=False,
    )
    assert hint == "Review the planned change across 1 file(s): src/app.py."


def test_next_step_reports_done_for_clean_assess() -> None:
    hint = build_next_step(
        operation="assess_change",
        status="complete",
        verdict="SAFE",
        unknowns=[],
        freshness=[],
        plan_steps=[],
        truncated=False,
    )
    assert hint == "No static issues found in the assessed change."


def test_next_step_none_when_nothing_actionable() -> None:
    assert (
        build_next_step(
            operation="understand",
            status="complete",
            verdict="INFO",
            unknowns=[],
            freshness=[],
            plan_steps=[],
            truncated=False,
        )
        is None
    )


def test_agent_summary_is_compact_and_deterministic() -> None:
    summary = build_agent_summary(
        operation="assess_change",
        status="complete",
        verdict="SAFE",
        next_step="No static issues found in the assessed change.",
        primitive_calls=6,
        evidence_items=4,
        cleanup_status="succeeded",
        plan_steps_count=0,
    )
    assert summary == {
        "summary_line": "task assess_change complete verdict=SAFE calls=6 evidence=4",
        "operation": "assess_change",
        "status": "complete",
        "verdict": "SAFE",
        "primitive_calls": 6,
        "evidence_items": 4,
        "cleanup_status": "succeeded",
        "plan_steps": 0,
        "next_step": "No static issues found in the assessed change.",
    }
    assert (
        build_agent_summary(
            operation="assess_change",
            status="complete",
            verdict="SAFE",
            next_step=None,
            primitive_calls=6,
            evidence_items=4,
            cleanup_status="succeeded",
            plan_steps_count=0,
        )["summary_line"]
        == summary["summary_line"]
    )


# --- Adapter-boundary wire contract ------------------------------------------


def test_understand_projects_real_nav_wire() -> None:
    executor = RealWireExecutor()
    outcome = _run(
        understand(UnderstandRequest(task="how does dispatch work"), executor)
    )
    assert outcome.artifacts["relevant_paths"] == ["src/app.py"]
    assert outcome.artifacts["relevant_symbols"] == ["dispatch", "handle_ping"]
    kinds = [s["kind"] for s in outcome.artifacts["plan_steps"]]
    assert kinds == ["inspect_context", "inspect_context"]
    assert outcome.artifacts["plan_steps"][0]["path"] == "src/app.py"
    assert outcome.artifacts["plan_steps"][0]["symbol"] == "dispatch"
    assert outcome.status == "complete"
    # The outcome now carries an actionable summary + next step.
    assert outcome.next_step is None  # nothing to do after a clean understand
    assert outcome.agent_summary["verdict"] == "INFO"  # type: ignore[index]
    assert decode_json(serialize_json(outcome)) == outcome


def test_plan_change_diff_projects_real_wire_end_to_end() -> None:
    executor = RealWireExecutor()
    outcome = _run(
        plan_change(
            PlanChangeRequest(
                diff=DiffInput("workspace"),
                budget=Budget(profile="standard"),
            ),
            executor,
        )
    )
    # Git status D is explicit not_run, never reconstructed.
    assert any(
        u["row"] == "diff:edit.ast_diff:src/gone.py"
        and u["reason"] == "not_run:UNSUPPORTED_DIFF_RECORD"
        for u in outcome.unknowns
    )
    # Only the modified file enters the structural/classification fan-out.
    ast_diff_paths = [
        args["file_path"]
        for f, a, args in executor.calls
        if (f, a) == ("edit", "ast_diff")
    ]
    assert ast_diff_paths == ["src/app.py"]
    # Real violation wire (caller_file/caller_name) projects a step.
    constraint_steps = [
        s for s in outcome.artifacts["plan_steps"] if s["kind"] == "check_constraint"
    ]
    assert len(constraint_steps) == 1
    assert constraint_steps[0]["path"] == "src/app.py"
    assert constraint_steps[0]["symbol"] == "dispatch"
    assert outcome.verdict == "UNSAFE"
    # The review list covers every changed record (incl. the deletion).
    assert (
        outcome.next_step
        == "Review the planned change across 2 file(s): src/app.py, src/gone.py."
    )
    assert outcome.agent_summary["verdict"] == "UNSAFE"  # type: ignore[index]
    assert decode_json(serialize_json(outcome)) == outcome
