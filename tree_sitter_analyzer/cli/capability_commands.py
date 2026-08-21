"""Handlers for the RFC-0027 §L7/§L8 capability flags.

Three capabilities that were built, tested, and reachable from nothing:

===================  ==================  =============================
CLI flag             MCP twin            what it answers
===================  ==================  =============================
``--project-card``   project action=card  "what is this project?"
``--plan-rename``    edit action=plan_rename  "what would this rename touch?"
``--refactor-queue`` health action=refactor_queue  "what do I clean up first?"
===================  ==================  =============================

Each handler routes through the *same facade* the MCP surface uses, so parity
is structural rather than duplicated. ``--plan-rename`` therefore inherits the
facade's ``PLAN_RENAME_IS_PREVIEW_ONLY`` guard for free: the CLI has no way to
express an apply because there is no flag for it and the facade would reject
the argument anyway.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid a circular import; only needed for annotations
    from tree_sitter_analyzer.cli.special_commands import SpecialCommandContext


def _execute_facade(
    facade: Any,
    tool_args: dict[str, Any],
    output_format: str,
    label: str,
    context: SpecialCommandContext,
) -> int:
    """Run one facade action and emit its payload. Same shape as nav's helper."""
    import asyncio

    try:
        result: dict[str, Any] = asyncio.run(facade.execute(tool_args))
    except Exception as exc:  # noqa: BLE001 — CLI boundary: never traceback
        context.output_error(f"{label} failed: {exc}")
        return 1
    if output_format == "toon":
        import sys

        print(result.get("toon_content", ""), file=sys.stdout)
    else:
        context.output_json(result)
    return 0 if result.get("success", False) else 1


def _handle_project_card(
    args: Any, context: SpecialCommandContext, output_format: str
) -> int:
    from tree_sitter_analyzer.mcp.tools.project_facade import build_project_facade

    project_root = getattr(args, "project_root", None) or os.getcwd()
    facade = build_project_facade(project_root=project_root)
    return _execute_facade(
        facade,
        {"action": "card", "output_format": output_format},
        output_format,
        "--project-card",
        context,
    )


def _handle_plan_rename(
    args: Any, context: SpecialCommandContext, output_format: str
) -> int:
    new_name = getattr(args, "plan_rename_to", None)
    if not new_name:
        context.output_error("--plan-rename requires --plan-rename-to NEW_NAME")
        return 1

    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    project_root = getattr(args, "project_root", None) or os.getcwd()
    facade = build_edit_facade(project_root=project_root)
    return _execute_facade(
        facade,
        {
            "action": "plan_rename",
            "symbol": getattr(args, "plan_rename", None),
            "new_name": new_name,
            "output_format": output_format,
        },
        output_format,
        "--plan-rename",
        context,
    )


def _handle_refactor_queue(
    args: Any, context: SpecialCommandContext, output_format: str
) -> int:
    from tree_sitter_analyzer.mcp.tools.health_facade import build_health_facade

    project_root = getattr(args, "project_root", None) or os.getcwd()
    facade = build_health_facade(project_root=project_root)
    return _execute_facade(
        facade,
        {
            "action": "refactor_queue",
            "top_n": getattr(args, "refactor_queue_top_n", 5),
            "output_format": output_format,
        },
        output_format,
        "--refactor-queue",
        context,
    )


def handle_capability_actions(
    args: Any,
    context: SpecialCommandContext,
) -> int | None:
    """Dispatch ``--project-card`` / ``--plan-rename`` / ``--refactor-queue``."""
    output_format = getattr(args, "output_format", "json") or "json"

    if getattr(args, "project_card", False):
        return _handle_project_card(args, context, output_format)
    if getattr(args, "plan_rename", None):
        return _handle_plan_rename(args, context, output_format)
    if getattr(args, "refactor_queue", False):
        return _handle_refactor_queue(args, context, output_format)
    return None
