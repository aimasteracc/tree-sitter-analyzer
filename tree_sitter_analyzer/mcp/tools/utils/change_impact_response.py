"""Response assembly helpers for change-impact analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

LARGE_DIRTY_DIFF_THRESHOLD = 25

# Pol3 (round-21): the in-response preview lists (``changed_preview``,
# ``scoped_changed_preview``, ``out_of_scope_changed_preview``) are
# capped so the JSON envelope stays small. Hidden truncation is a
# documented footgun (see H2/H3) — every consumer that capped a
# preview must also surface ``preview_limit`` + ``preview_truncated``
# so an agent can decide whether to re-query for the rest. Keep the
# magic number here so all three call sites stay aligned.
CHANGE_IMPACT_PREVIEW_LIMIT = 5

# H8 / J11: ``verdict`` values exposed by change-impact.
#
# Before J11 (round-22) the tool emitted ``CLEAN`` whenever the analysis
# ran without an invalid-scope warning, even when ``changed_count > 0``.
# That collided with the safety-tool vocabulary (safe_to_edit /
# code_patterns) where ``CLEAN`` means "no issues, ship it" — agents that
# chained the two tools shipped pending work because change-impact's
# ``CLEAN`` meant "the scope filter applied" not "no work to verify".
#
# Post J11 the verdict is content-aware:
#   * ``SAFE``    — analysis succeeded AND ``changed_count == 0`` (no
#                   pending work to verify, equivalent to the legacy
#                   ``CLEAN`` semantics).
#   * ``REVIEW``  — analysis succeeded but ``changed_count > 0``; the
#                   caller still has verification work to do before the
#                   queue is closed.
#   * ``WARN``    — soft-failure (e.g. scope paths that don't exist on
#                   disk) — analysis ran but the caller's input was
#                   partly ignored.
#
# We deliberately don't escalate to ``UNSAFE`` here because the tool
# answers a different question (impact) than the safety tools.
#
# F1 (round-37f7): ``CHANGE_IMPACT_VERDICT_CLEAN`` was previously
# ``"CLEAN"`` — a value outside the shared cross-tool legal vocabulary
# (:data:`tree_sitter_analyzer.mcp.tools.base_tool._LEGAL_VERDICTS`).
# It now maps to ``"SAFE"`` so chained agents that branch on a single
# string (Claude Code, Cursor, the queue-ledger CLI) don't have to
# special-case change_impact. The constant *name* keeps the legacy
# ``_CLEAN`` suffix for backward compatibility with call sites that
# import it by name; the *value* is what changed.
CHANGE_IMPACT_VERDICT_CLEAN = "SAFE"
CHANGE_IMPACT_VERDICT_REVIEW = "REVIEW"
CHANGE_IMPACT_VERDICT_WARN = "WARN"


@dataclass(frozen=True)
class AgentSummaryContext:
    """Inputs needed for the compact agent decision summary."""

    risk: str
    changed_files: list[str]
    scope_paths: list[str] | None
    verification: dict[str, Any]
    strategy: dict[str, Any]
    affected_count: int
    tests_to_run_count: int


@dataclass(frozen=True)
class ChangeImpactResponseContext:
    """Computed parts for assembling a change-impact response."""

    request: Any
    risk: str
    affected: set[str]
    file_impacts: list[dict[str, Any]]
    visible_tests: list[str]
    all_tests: list[str]
    verification: dict[str, Any]
    strategy: dict[str, Any]
    test_mapping: dict[str, list[str]]
    agent_summary: dict[str, Any]


def build_no_changes_result(
    mode: str, scope_paths: list[str] | None = None
) -> dict[str, Any]:
    """Build a stable empty-diff response."""
    # M5 (round-26 dogfood): the no-changes path also went through
    # ``summary_line=None`` on both surfaces. Build a stable one-liner
    # so chained tools see ``changed=0 risk=none`` instead of nothing.
    summary_line = "change_impact changed=0 risk=none pytest_required=False"
    return {
        "success": True,
        "mode": mode,
        "changed_files": [],
        "summary": "No changes detected",
        "summary_line": summary_line,
        "agent_summary": {
            "summary_line": summary_line,
            "risk": "none",
            "scope": "scoped" if scope_paths else "workspace",
            "changed_count": 0,
            "affected_count": 0,
            "tests_to_run_count": 0,
            "next_step": "No changes detected; no verification needed.",
            "verification_command": "",
            "stop_condition": "Working tree remains unchanged for the selected mode and scope.",
        },
    }


def build_agent_summary_only_response(result: dict[str, Any]) -> dict[str, Any]:
    """Return a compact change-impact response for agent decision loops."""
    summary = result.get("agent_summary", {})
    return {
        "success": result.get("success", False),
        "mode": result.get("mode", "diff"),
        "scope_paths": result.get("scope_paths", []),
        "scope_filtered": result.get("scope_filtered", False),
        "agent_summary_only": True,
        "agent_summary": summary,
        "risk_level": result.get("risk_level", summary.get("risk", "none")),
        "changed_count": result.get("changed_count", summary.get("changed_count", 0)),
        "affected_count": result.get(
            "affected_count", summary.get("affected_count", 0)
        ),
        "tests_to_run_count": result.get(
            "tests_to_run_count", summary.get("tests_to_run_count", 0)
        ),
        "next_step": summary.get("next_step", ""),
        "verification_command": result.get(
            "verification_command", summary.get("verification_command", "")
        ),
        "focused_test_command": result.get(
            "focused_test_command", summary.get("focused_test_command", "")
        ),
        "queue_ledger": result.get("queue_ledger", summary.get("queue_ledger", {})),
        "verification_strategy": result.get(
            "verification_strategy", summary.get("verification_strategy", "")
        ),
        "verification_steps": result.get("verification_steps", []),
        "stop_condition": summary.get("stop_condition", ""),
    }


def build_agent_summary(context: AgentSummaryContext) -> dict[str, Any]:
    """Build the compact decision surface agents need from change-impact."""
    verification = context.verification
    strategy = context.strategy
    summary: dict[str, Any] = {
        "risk": context.risk,
        "scope": "scoped" if context.scope_paths else "workspace",
        "changed_count": len(context.changed_files),
        "affected_count": context.affected_count,
        "tests_to_run_count": context.tests_to_run_count,
        "next_step": _agent_next_step(verification, strategy),
        "verification_command": verification["verification_command"],
        "verification_strategy": strategy["verification_strategy"],
        "stop_condition": _agent_stop_condition(context.risk, verification, strategy),
    }

    focused = strategy.get("focused_test_command")
    if focused:
        summary["focused_test_command"] = focused

    if context.changed_files:
        # Pol3 (round-21): expose the cap + truncation flag whenever the
        # preview is shorter than the underlying list. Hidden truncation
        # bit chained agents in H2/H3 — the same precedent applies here.
        summary["changed_preview"] = context.changed_files[:CHANGE_IMPACT_PREVIEW_LIMIT]
        summary["preview_limit"] = CHANGE_IMPACT_PREVIEW_LIMIT
        summary["preview_truncated"] = (
            len(context.changed_files) > CHANGE_IMPACT_PREVIEW_LIMIT
        )

    if (
        len(context.changed_files) > LARGE_DIRTY_DIFF_THRESHOLD
        and not context.scope_paths
    ):
        summary["scope_hint"] = (
            "Large dirty worktree detected; pass scope_paths or "
            "--change-impact-scope for the current queue."
        )

    return summary


def attach_queue_ledger(
    result: dict[str, Any],
    *,
    mode: str,
    scope_paths: list[str] | None,
    scoped_changed_files: list[str],
    workspace_changed_files: list[str],
) -> dict[str, Any]:
    """Attach a lightweight scoped dirty-worktree ledger for agent handoffs."""
    if not scope_paths:
        return result

    out_of_scope = [
        path
        for path in workspace_changed_files
        if path not in set(scoped_changed_files)
    ]
    verification_command = result.get("verification_command") or result.get(
        "agent_summary", {}
    ).get("verification_command", "")
    # Pol3 (round-21): a cap on either preview without a transparency flag
    # would let an agent think it had the full picture. Surface
    # ``preview_limit`` + ``preview_truncated`` whenever the underlying
    # count exceeds what we expose.
    preview_truncated = (
        len(scoped_changed_files) > CHANGE_IMPACT_PREVIEW_LIMIT
        or len(out_of_scope) > CHANGE_IMPACT_PREVIEW_LIMIT
    )
    ledger = {
        "mode": mode,
        "scope_paths": scope_paths,
        "scoped_changed_count": len(scoped_changed_files),
        "out_of_scope_changed_count": len(out_of_scope),
        "scoped_changed_preview": scoped_changed_files[:CHANGE_IMPACT_PREVIEW_LIMIT],
        "out_of_scope_changed_preview": out_of_scope[:CHANGE_IMPACT_PREVIEW_LIMIT],
        "preview_limit": CHANGE_IMPACT_PREVIEW_LIMIT,
        "preview_truncated": preview_truncated,
        "handoff": _queue_ledger_handoff(
            scope_paths, scoped_changed_files, out_of_scope, verification_command
        ),
    }
    result["queue_ledger"] = ledger
    summary = result.setdefault("agent_summary", {})
    summary["queue_ledger"] = ledger
    summary["scope_hint"] = (
        f"Scoped queue has {len(scoped_changed_files)} changed file(s); "
        f"{len(out_of_scope)} out-of-scope dirty file(s) remain untouched."
    )
    return result


def _queue_ledger_handoff(
    scope_paths: list[str],
    scoped_changed_files: list[str],
    out_of_scope: list[str],
    verification_command: str,
) -> str:
    """Build one compact queue handoff sentence."""
    scope = ", ".join(scope_paths)
    verification = verification_command or "none"
    return (
        f"scope={scope}; scoped_changed={len(scoped_changed_files)}; "
        f"out_of_scope_dirty={len(out_of_scope)}; verification={verification}"
    )


def build_change_impact_response(
    context: ChangeImpactResponseContext,
) -> dict[str, Any]:
    """Assemble the final response without mixing computation and formatting."""
    request = context.request
    verification = context.verification
    strategy = context.strategy
    # M5 (round-26 dogfood): the previous build emitted ``summary_line=None``
    # at both surfaces even on successful analysis with ``changed_count > 0``.
    # F6's post-hook only fires when the tool returns a populated string
    # at the top level OR inside ``agent_summary`` — neither was set here,
    # so chained agents lost the one-liner they grep for. Build the
    # canonical headline here (``change_impact changed=N risk=R
    # pytest_required=...``) and mirror it into ``agent_summary`` so both
    # surfaces agree, matching the modification_guard / safe_to_edit
    # convention.
    changed_count = len(request.changed_files)
    summary_line = (
        f"change_impact changed={changed_count} risk={context.risk} "
        f"pytest_required={verification['pytest_required']}"
    )
    agent_summary = dict(context.agent_summary)
    agent_summary.setdefault("summary_line", summary_line)
    return {
        "success": True,
        "mode": request.mode,
        "scope_paths": request.scope_paths or [],
        "scope_filtered": bool(request.scope_paths),
        "summary_line": summary_line,
        "agent_summary": agent_summary,
        "changed_count": changed_count,
        "changed_files": request.changed_files[:50],
        "affected_count": len(context.affected),
        "affected_files": sorted(context.affected)[:50] if context.affected else [],
        "risk_level": context.risk,
        "file_impacts": context.file_impacts[:20],
        "tests_to_run": context.visible_tests,
        "tests_to_run_count": len(context.all_tests),
        "tests_to_run_omitted_count": max(
            0, len(context.all_tests) - len(context.visible_tests)
        ),
        "test_required": verification["test_required"],
        "test_runner": verification["test_runner"],
        "default_test_command": verification["default_test_command"],
        "pytest_required": verification["pytest_required"],
        "pytest_command": verification["pytest_command"],
        "test_command": verification["test_command"],
        "verification_command": verification["verification_command"],
        "verification_reason": verification["verification_reason"],
        "focused_test_command": strategy["focused_test_command"],
        "verification_strategy": strategy["verification_strategy"],
        "verification_steps": strategy["verification_steps"],
        "verification_hint": strategy["verification_hint"],
        "test_mapping": context.test_mapping if context.test_mapping else {},
        "diff_stat": request.diff_stat[:500] if request.diff_stat else "",
    }


def _agent_next_step(verification: dict[str, Any], strategy: dict[str, Any]) -> str:
    """Return one concise next action for agent decision-making."""
    if not verification["test_required"]:
        return "Run git diff --check; pytest is not required for docs-only changes."
    focused = strategy.get("focused_test_command")
    if focused and focused != verification["verification_command"]:
        return f"Run focused verification first: {focused}"
    return f"Run verification: {verification['verification_command']}"


def _agent_stop_condition(
    risk: str,
    verification: dict[str, Any],
    strategy: dict[str, Any],
) -> str:
    """Describe when the current edit queue can be considered closed."""
    if not verification["test_required"]:
        # docs-only / config-only edits: no test run required. Keep the
        # ``docs-only`` token lowercase — agent UIs grep for it as a
        # machine-readable signal.
        return (
            "docs-only change: git diff --check passes and no runtime files are added."
        )
    if (
        risk == "high"
        and verification["verification_command"] != verification["default_test_command"]
    ):
        return (
            f"{verification['verification_command']} passes; run "
            f"{verification['default_test_command']} at the queue boundary."
        )
    steps = strategy.get("verification_steps") or [verification["verification_command"]]
    return f"{steps[-1]} exits successfully."


def apply_scope_validation(
    result: dict[str, Any], scope_paths_invalid: list[str]
) -> dict[str, Any]:
    """H8 / J11: surface nonexistent scope paths and a content-aware verdict.

    Behaviour:
      - ``scope_paths_invalid`` always lands in the response (even empty),
        so consumers can branch on a single key without first checking
        existence. The default value keeps round-trip JSON stable.
      - ``agent_summary["verdict"]`` is content-aware (F1: legacy
        ``CLEAN`` was rebound to ``SAFE`` so the value lives inside
        the cross-tool legal vocabulary):
          * ``WARN``   — any invalid scope path was supplied.
          * ``SAFE``   — analysis ran cleanly AND ``changed_count == 0``.
          * ``REVIEW`` — analysis ran cleanly but ``changed_count > 0``;
                         the queue still has verification work pending.
        Pre-J11 the response emitted ``CLEAN`` even with 14 changed files,
        which collided with the safety-tool vocabulary (where ``CLEAN``
        means "ship it"). Agents chaining the two ended up shipping pending
        work.
      - ``agent_summary["next_step"]`` is rewritten with a concrete
        "did you typo?" hint when any scope is invalid so the agent's
        decision loop catches it before re-running.
      - ``summary_line`` (top-level and inside ``agent_summary``) gains a
        ``scope_invalid=N`` token so chained tools can grep one line.
      - We never flip ``success`` to False. The analysis still has value;
        the verdict escalation is what tells agents "you ignored part of
        the input".
    """
    result.setdefault("scope_paths_invalid", scope_paths_invalid)
    agent_summary = result.setdefault("agent_summary", {})

    if scope_paths_invalid:
        agent_summary["verdict"] = CHANGE_IMPACT_VERDICT_WARN
        agent_summary["next_step"] = (
            f"scope path(s) do not exist: {scope_paths_invalid} — did you typo?"
        )
        agent_summary["scope_paths_invalid"] = list(scope_paths_invalid)
        _augment_summary_line(result, agent_summary, scope_paths_invalid)
    else:
        # J11 (round-22): pick CLEAN vs REVIEW based on whether the
        # analysis still has pending work to verify. Use setdefault on
        # whichever value we compute so we don't stomp a richer verdict
        # another helper may have set first.
        changed_count = _resolve_changed_count(result, agent_summary)
        default_verdict = (
            CHANGE_IMPACT_VERDICT_CLEAN
            if changed_count == 0
            else CHANGE_IMPACT_VERDICT_REVIEW
        )
        agent_summary.setdefault("verdict", default_verdict)

    return result


def _resolve_changed_count(
    result: dict[str, Any], agent_summary: dict[str, Any]
) -> int:
    """Best-effort lookup of ``changed_count`` across response shapes.

    The full change-impact response stores ``changed_count`` at the top
    level, the no-changes shortcut returns it inside ``agent_summary``,
    and the agent-summary-only collapse keeps it at the top level too.
    Try both and fall back to counting ``changed_files``. Returning 0
    when nothing is found is safe — it preserves the legacy CLEAN
    default for ambiguous callers.
    """
    for source in (result, agent_summary):
        value = source.get("changed_count")
        if isinstance(value, int):
            return value
    files = result.get("changed_files")
    if isinstance(files, list):
        return len(files)
    return 0


def _augment_summary_line(
    result: dict[str, Any],
    agent_summary: dict[str, Any],
    scope_paths_invalid: list[str],
) -> None:
    """Append a ``scope_invalid=N`` token to both summary_line surfaces.

    Keeps the original line content if one already exists; only appends
    once per call. Bare absence is also handled — a minimal headline is
    synthesized so chained agents always see the warning.
    """
    token = f"scope_invalid={len(scope_paths_invalid)}"

    existing_top = result.get("summary_line")
    if isinstance(existing_top, str) and existing_top:
        if token not in existing_top:
            result["summary_line"] = f"{existing_top} {token}"
    else:
        result["summary_line"] = f"change_impact: {token}"

    existing_agent = agent_summary.get("summary_line")
    if isinstance(existing_agent, str) and existing_agent:
        if token not in existing_agent:
            agent_summary["summary_line"] = f"{existing_agent} {token}"
    else:
        agent_summary["summary_line"] = result["summary_line"]
