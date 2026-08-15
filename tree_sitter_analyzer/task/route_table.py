"""RFC-0022 task-outcome/v1 fixed route table (Phase A).

The route decision table is pinned row by row from RFC-0022 §Complete V1
route decision table. There is no task-layer keyword, regex, identifier,
intent, or LLM router: free text passes unchanged to ``nav.context``, the
sole owner of natural-language symbol inference. Parameters not shown are
not sent; primitive output format is JSON internally. The compact/standard
values in a cell are selected only by ``Budget.profile``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RouteRow:
    """One pinned route row: condition -> primitive call + stop/degrade rule.

    ``parameters`` pins the static parameter set; ``dynamic_parameters``
    names the runtime-supplied parameters (file_path, mode, scope_paths,
    snapshot/generation tokens) that the executor must attach per RFC-0022
    §Complete V1 route decision table.
    """

    operation: str
    condition: str
    facade: str
    action: str
    parameters: tuple[tuple[str, str], ...]
    stop_rule: str
    dynamic_parameters: tuple[str, ...] = ()


#: Row order is significant: calls run in displayed order, fan-out lists are
#: de-duplicated and sorted by (path, symbol) before their pinned cap.
ROUTE_TABLE: tuple[RouteRow, ...] = (
    RouteRow(
        operation="all",
        condition="always",
        facade="index",
        action="status",
        parameters=(
            ("access_mode", "read_existing"),
            ("output_format", "json"),
        ),
        stop_rule="missing oracle => freshness unknown; continue, at most "
        "partial if graph evidence is used",
    ),
    RouteRow(
        operation="understand(task)",
        condition="valid task and certified index tokens",
        facade="nav",
        action="context",
        parameters=(
            ("max_nodes", "12/30"),
            ("max_code_blocks", "3/5"),
            ("include_graph", "false"),
            ("access_mode", "read_existing"),
            ("output_format", "json"),
        ),
        dynamic_parameters=("task", "snapshot_id", "source_generation"),
        stop_rule="failure => unknown; success ends route",
    ),
    RouteRow(
        operation="plan_change(task)",
        condition="valid task and certified index tokens",
        facade="nav",
        action="context",
        parameters=(
            ("max_nodes", "12/30"),
            ("max_code_blocks", "3/5"),
            ("include_graph", "false"),
            ("access_mode", "read_existing"),
            ("output_format", "json"),
        ),
        dynamic_parameters=("task", "snapshot_id", "source_generation"),
        stop_rule="failure => unknown and stop",
    ),
    RouteRow(
        operation="plan_change(task)",
        condition="each distinct generation-matched existing path explicitly "
        "returned in code_blocks, max 2/5",
        facade="edit",
        action="safe",
        parameters=(
            ("edit_type", "refactor"),
            ("access_mode", "read_existing"),
            ("output_format", "json"),
        ),
        dynamic_parameters=("file_path", "snapshot_id", "source_generation"),
        stop_rule="missing path is not inferred; token mismatch stops route; "
        "other per-call failure is partial",
    ),
    RouteRow(
        operation="diff operation",
        condition="valid diff",
        facade="edit",
        action="impact",
        parameters=(
            ("include_tests", "true"),
            ("resource_profile", "local_low_impact"),
            ("access_mode", "read_existing"),
            ("output_format", "json"),
        ),
        dynamic_parameters=("mode", "scope_paths"),
        stop_rule="missing/failing diff_snapshot_id => unknown and stop",
    ),
    RouteRow(
        operation="diff operation",
        condition="successful generation-matched impact; reserved before fan-out",
        facade="edit",
        action="constraints",
        parameters=(
            ("persist", "false"),
            ("access_mode", "read_existing"),
            ("output_format", "json"),
        ),
        dynamic_parameters=(
            "diff_snapshot_id",
            "snapshot_id",
            "source_generation",
            "scope_paths",
        ),
        stop_rule="not_applicable:NO_CONFIG satisfies the row; invocation "
        "failure degrades per the truth table",
    ),
    RouteRow(
        operation="diff operation",
        condition="each non-binary changed record with old/new material available",
        facade="edit",
        action="ast_diff",
        parameters=(
            ("access_mode", "read_existing"),
            ("output_format", "json"),
        ),
        dynamic_parameters=("diff_snapshot_id", "file_path"),
        stop_rule="unsupported add/delete/rename is explicit not_run, never "
        "locally reconstructed",
    ),
    RouteRow(
        operation="diff operation",
        condition="same eligible records",
        facade="edit",
        action="classify",
        parameters=(
            ("access_mode", "read_existing"),
            ("output_format", "json"),
        ),
        dynamic_parameters=("diff_snapshot_id", "file_path"),
        stop_rule="per-file failure => partial",
    ),
)

#: edit.safe fan-out caps per profile (RFC-0022 §Complete V1 route table).
SAFE_FANOUT_CAPS: dict[str, int] = {"compact": 2, "standard": 5}
