"""RFC-0022 Phase A experiment harness (internal; NOT a public surface).

The harness wires the fixed router (``tree_sitter_analyzer.task.router``) to
the real same-process MCP primitive adapters, so the three task outcomes can
be exercised end-to-end without registering any facade, CLI flag, or codemap
surface (RFC-0022 §Public surface: Phase A — internal experiment only).

Usage (real CLI smoke; index the repository first with ``tsa index``)::

    python -m tree_sitter_analyzer.task_harness --project-root . \\
        --operation understand --task "how does dispatch work"
    python -m tree_sitter_analyzer.task_harness --project-root . \\
        --operation assess_change --diff workspace --profile compact

The harness never builds an index, runs a command, or mutates the
repository: ``index.status``, ``nav.context``, ``edit.safe``,
``edit.impact``, ``edit.constraints``, ``edit.ast_diff``,
``edit.classify`` and ``edit.release_snapshot`` are invoked exactly as the
route table pins them, all with ``access_mode="read_existing"``.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any, Literal

from .mcp.tools.change_impact_tool import ChangeImpactTool
from .mcp.tools.codegraph_context_tool import CodeGraphContextTool
from .mcp.tools.codegraph_status_tool import CodeGraphStatusTool
from .mcp.tools.edit_facade import build_edit_facade
from .task.models import (
    AssessChangeRequest,
    Budget,
    DiffInput,
    PlanChangeRequest,
    UnderstandRequest,
)
from .task.serializers import serialize_json, serialize_toon

Operation = Literal["understand", "plan_change", "assess_change"]


class McpPrimitiveExecutor:
    """PrimitiveExecutor over the real same-process MCP adapters.

    ``edit.*`` actions route through the strict edit facade (exact argument
    projection); ``index.status`` and ``nav.context`` use their tools
    directly. All calls use ``output_format="json"`` (internal routing
    format, RFC-0022 §Complete V1 route decision table).
    """

    def __init__(self, project_root: str | None = None) -> None:
        self._project_root = project_root
        self._index_status = CodeGraphStatusTool(project_root)
        self._nav_context = CodeGraphContextTool(project_root)
        self._edit = build_edit_facade(project_root)
        self._change_impact = ChangeImpactTool(project_root)

    async def call(
        self, facade: str, action: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        if facade == "index" and action == "status":
            return await self._index_status.execute(dict(arguments))
        if facade == "nav" and action == "context":
            return await self._nav_context.execute(dict(arguments))
        if facade == "edit":
            result: dict[str, Any] = await self._edit.execute(
                {"action": action, **arguments}
            )
            return result
        raise ValueError(f"unknown primitive {facade}.{action}")


def request_from_dict(operation: Operation, payload: dict[str, Any]) -> Any:
    """Build one request from a decoded mapping (strict: no unknown fields).

    Raises ``ValueError`` on unknown or malformed fields — the caller maps
    this to ``INVALID_REQUEST`` (RFC-0022: decoded mappings reject unknown
    fields rather than ignoring them).
    """
    allowed = {
        "task",
        "diff",
        "budget",
        "profile",
        "max_primitive_calls",
        "max_evidence_items",
        "routing_deadline_ms",
    }
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"unknown request fields: {sorted(unknown)}")
    budget = _budget_from_dict(payload)
    task = payload.get("task")
    diff_payload = payload.get("diff")
    if operation == "understand":
        return UnderstandRequest(task=task or "", budget=budget)
    if operation == "plan_change":
        if diff_payload is not None:
            return PlanChangeRequest(diff=_diff_from_dict(diff_payload), budget=budget)
        return PlanChangeRequest(task=task or "", budget=budget)
    if operation == "assess_change":
        if diff_payload is None:
            raise ValueError("assess_change requires exactly one diff")
        return AssessChangeRequest(diff=_diff_from_dict(diff_payload), budget=budget)
    raise ValueError(f"unknown operation {operation!r}")


def _budget_from_dict(payload: dict[str, Any]) -> Budget:
    budget_payload = payload.get("budget")
    if budget_payload is None:
        return Budget(profile=payload.get("profile", "standard"))
    if type(budget_payload) is not dict:
        raise ValueError("budget must be a dict")
    known = {
        "profile",
        "max_primitive_calls",
        "max_evidence_items",
        "routing_deadline_ms",
    }
    unknown = set(budget_payload) - known
    if unknown:
        raise ValueError(f"unknown budget fields: {sorted(unknown)}")
    return Budget(
        profile=budget_payload.get("profile", "standard"),
        max_primitive_calls=budget_payload.get("max_primitive_calls"),
        max_evidence_items=budget_payload.get("max_evidence_items"),
        routing_deadline_ms=budget_payload.get("routing_deadline_ms"),
    )


def _diff_from_dict(payload: dict[str, Any]) -> DiffInput:
    if type(payload) is not dict:
        raise ValueError("diff must be a dict")
    known = {"source", "scope_paths"}
    unknown = set(payload) - known
    if unknown:
        raise ValueError(f"unknown diff fields: {sorted(unknown)}")
    source = payload.get("source", "workspace")
    scope_paths = payload.get("scope_paths") or []
    if type(scope_paths) is not list or any(
        type(path) is not str for path in scope_paths
    ):
        raise ValueError("scope_paths must be a list of strings")
    return DiffInput(source=source, scope_paths=tuple(scope_paths))


async def run_operation(
    operation: Operation,
    request: Any,
    project_root: str | None = None,
    output_format: str = "json",
) -> str:
    """Execute one task outcome and serialize it (JSON or TOON)."""
    from .task.router import assess_change, plan_change, understand

    executor = McpPrimitiveExecutor(project_root)
    if operation == "understand":
        outcome = await understand(request, executor)
    elif operation == "plan_change":
        outcome = await plan_change(request, executor)
    else:
        outcome = await assess_change(request, executor)
    if output_format == "toon":
        return serialize_toon(outcome)
    return serialize_json(outcome)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tree_sitter_analyzer.task_harness",
        description=(
            "RFC-0022 Phase A experiment harness (internal-only; not a public "
            "TSA command). Index the repository first with `tsa index`."
        ),
    )
    parser.add_argument(
        "--project-root", default=".", help="Repository root (default: cwd)."
    )
    parser.add_argument(
        "--operation",
        choices=("understand", "plan_change", "assess_change"),
        required=True,
    )
    parser.add_argument("--task", default="", help="Task text (task routes).")
    parser.add_argument(
        "--diff",
        choices=("workspace", "staged"),
        default=None,
        help="Diff source (diff routes; requires a frozen index + workspace diff).",
    )
    parser.add_argument(
        "--scope-path",
        action="append",
        default=[],
        help="Diff scope path (repeatable; default: project scope).",
    )
    parser.add_argument(
        "--profile", choices=("compact", "standard"), default="standard"
    )
    parser.add_argument(
        "--max-primitive-calls",
        type=int,
        default=None,
        help="Explicit lower ceiling on routed primitive calls.",
    )
    parser.add_argument(
        "--max-evidence-items",
        type=int,
        default=None,
        help="Explicit lower ceiling on minted evidence items.",
    )
    parser.add_argument(
        "--routing-deadline-ms",
        type=int,
        default=None,
        help="Explicit lower ceiling on the routing deadline.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "toon"),
        default="json",
        help="Output format (harness-local; no default is flipped).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.task and args.diff:
        print("task and diff are mutually exclusive", file=sys.stderr)
        return 2
    budget = Budget(
        profile=args.profile,
        max_primitive_calls=args.max_primitive_calls,
        max_evidence_items=args.max_evidence_items,
        routing_deadline_ms=args.routing_deadline_ms,
    )
    request: Any
    try:
        if args.diff:
            request = (
                PlanChangeRequest(
                    diff=DiffInput(
                        source=args.diff, scope_paths=tuple(args.scope_path)
                    ),
                    budget=budget,
                )
                if args.operation == "plan_change"
                else AssessChangeRequest(
                    diff=DiffInput(
                        source=args.diff, scope_paths=tuple(args.scope_path)
                    ),
                    budget=budget,
                )
            )
        else:
            if args.operation == "understand":
                request = UnderstandRequest(task=args.task, budget=budget)
            else:
                request = PlanChangeRequest(task=args.task, budget=budget)
    except ValueError as exc:
        print(f"invalid request: {exc}", file=sys.stderr)
        return 2
    try:
        serialized = asyncio.run(
            run_operation(
                args.operation,
                request,
                project_root=args.project_root,
                output_format=args.format,
            )
        )
    except Exception as exc:  # pragma: no cover - CLI crash path
        print(f"harness failure: {exc}", file=sys.stderr)
        return 1
    print(serialized)
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry
    sys.exit(main())
