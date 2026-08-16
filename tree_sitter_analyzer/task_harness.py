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
import json
import sys
from typing import Any, Literal, cast

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
    # Exact one-of contract per operation: forbidden fields are rejected,
    # never silently ignored (Codex review #1290 P2).
    if operation == "understand":
        if diff_payload is not None:
            raise ValueError("understand rejects diff")
        return UnderstandRequest(task=task or "", budget=budget)
    if operation == "plan_change":
        if diff_payload is not None and (task or "").strip():
            raise ValueError("plan_change accepts exactly one of task or diff")
        if diff_payload is not None:
            return PlanChangeRequest(diff=_diff_from_dict(diff_payload), budget=budget)
        return PlanChangeRequest(task=task or "", budget=budget)
    if operation == "assess_change":
        if diff_payload is None:
            raise ValueError("assess_change requires exactly one diff")
        if (task or "").strip():
            raise ValueError("assess_change rejects task")
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


def load_corpus(path: str) -> list[tuple[Operation, dict[str, Any]]]:
    """Load a JSONL experiment corpus (one request mapping per line).

    Each line is ``{"operation": "understand|plan_change|assess_change",
    **request fields}``. Malformed lines raise ValueError with the line
    number so the corpus manifest stays exact (RFC-0022 experiment
    discipline).
    """
    entries: list[tuple[Operation, dict[str, Any]]] = []
    if path == "-":
        import io

        lines = io.StringIO(sys.stdin.read()).readlines()
    else:
        with open(path, encoding="utf-8") as handle:
            lines = handle.readlines()
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"corpus line {index}: invalid JSON: {exc}") from exc
        if type(payload) is not dict:
            raise ValueError(f"corpus line {index}: not an object")
        operation = payload.get("operation")
        if operation not in ("understand", "plan_change", "assess_change"):
            raise ValueError(f"corpus line {index}: unknown operation {operation!r}")
        request_payload = dict(payload)
        request_payload.pop("operation", None)
        entries.append((cast(Operation, operation), request_payload))
    if not entries:
        raise ValueError("corpus is empty")
    return entries


def run_corpus(
    corpus_path: str,
    project_root: str | None = None,
) -> str:
    """Run a JSONL corpus and emit one JSON report.

    Every outcome is serialized into ``{"results": [...]}`` so experiments
    can be diffed across runs; all fields except the per-execution timing
    measurements (``consumed.routing_wall_ms``/``cleanup_wall_ms``/
    ``deadline_overrun_ms``) are deterministic for the same source state.
    A failed request mapping is a hard corpus error (exact manifest
    discipline), never a skipped case.
    """
    entries = load_corpus(corpus_path)
    serialized: list[str] = []
    for operation, payload in entries:
        request = request_from_dict(operation, payload)
        serialized.append(
            asyncio.run(run_operation(operation, request, project_root=project_root))
        )
    results = [json.loads(text) for text in serialized]
    return json.dumps(
        {"results": results},
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    )


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
        default=None,
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
    parser.add_argument(
        "--request-json",
        default=None,
        help=(
            "Read one strict request mapping from this path ('-' = stdin); "
            "mutually exclusive with --task/--diff."
        ),
    )
    parser.add_argument(
        "--corpus",
        default=None,
        help=(
            "JSONL experiment corpus ('-' = stdin); each line is "
            '{"operation": ..., ...request fields}. Emits one JSON report.'
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    request: Any
    if args.operation is None and args.corpus is None:
        print("--operation is required (or use --corpus)", file=sys.stderr)
        return 2
    if args.task and args.diff:
        print("task and diff are mutually exclusive", file=sys.stderr)
        return 2
    if args.corpus is not None and (args.task or args.diff or args.request_json):
        print(
            "--corpus is exclusive with --task/--diff/--request-json",
            file=sys.stderr,
        )
        return 2
    if args.request_json is not None and (args.task or args.diff):
        print(
            "--request-json is exclusive with --task/--diff",
            file=sys.stderr,
        )
        return 2
    if args.corpus is not None:
        try:
            report = run_corpus(args.corpus, project_root=args.project_root)
        except ValueError as exc:
            print(f"invalid corpus: {exc}", file=sys.stderr)
            return 2
        except Exception as exc:  # pragma: no cover - CLI crash path
            print(f"harness failure: {exc}", file=sys.stderr)
            return 1
        print(report)
        return 0
    if args.request_json is not None:
        try:
            if args.request_json == "-":
                import io

                payload = json.loads(io.StringIO(sys.stdin.read()).read())
            else:
                with open(args.request_json, encoding="utf-8") as handle:
                    payload = json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"invalid request JSON: {exc}", file=sys.stderr)
            return 2
        if type(payload) is not dict:
            print("invalid request JSON: not an object", file=sys.stderr)
            return 2
        try:
            request = request_from_dict(args.operation, payload)
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
    budget = Budget(
        profile=args.profile,
        max_primitive_calls=args.max_primitive_calls,
        max_evidence_items=args.max_evidence_items,
        routing_deadline_ms=args.routing_deadline_ms,
    )
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
