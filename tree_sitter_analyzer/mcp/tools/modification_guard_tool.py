#!/usr/bin/env python3
"""
Modification Guard Tool

Pre-modification safety check: run this BEFORE editing any public symbol.
Internally calls trace_impact and returns a structured "modification safety report".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool, format_summary_line, mirror_summary_line
from .trace_impact_tool import TraceImpactTool, _get_impact_level

# Set up logging
logger = setup_logger(__name__)

# Mapping from impact level to safety verdict
_VERDICT_MAP: dict[str, str] = {
    "none": "SAFE",
    "low": "CAUTION",
    "medium": "REVIEW",
    "high": "UNSAFE",
}

# Verdict boost order (used when architecture rank escalates severity)
_VERDICT_BOOST: dict[str, str] = {
    "SAFE": "CAUTION",
    "CAUTION": "REVIEW",
    "REVIEW": "UNSAFE",
    "UNSAFE": "UNSAFE",  # already max
}

# Map this tool's verdict vocabulary to the cross-tool ``risk`` field
# (low / medium / high) so agents can compare risk across safety tools
# without learning each tool's local enum.
_VERDICT_TO_RISK: dict[str, str] = {
    "SAFE": "low",
    "CAUTION": "low",
    "REVIEW": "medium",
    "UNSAFE": "high",
}

CRITICAL_NODES_FILE = ".tree-sitter-cache/critical_nodes.json"


def _build_agent_summary(
    *,
    symbol: str,
    modification_type: str,
    safety_verdict: str,
    total_callers: int,
    summary_line: str,
    proceed_recommendation: str,
    architecture_rank: int | None,
) -> dict[str, Any]:
    """Compose the agent_summary block for modification_guard responses.

    F10 fix: previously this tool emitted ``agent_summary={}`` because no
    one populated it. Every safety tool (safe_to_edit, file_health,
    modification_guard) ships the same shape — ``summary_line``,
    ``verdict``, ``risk``, ``next_step`` — so agents can branch on a
    single field regardless of which safety tool ran.
    """
    risk = _VERDICT_TO_RISK.get(safety_verdict, "medium")
    next_step = _next_step_for_verdict(
        safety_verdict=safety_verdict,
        symbol=symbol,
        modification_type=modification_type,
        total_callers=total_callers,
        architecture_rank=architecture_rank,
    )
    return {
        "summary_line": summary_line,
        "verdict": safety_verdict,
        "risk": risk,
        "next_step": next_step,
        "symbol": symbol,
        "modification_type": modification_type,
        "total_callers": total_callers,
        "recommendation": proceed_recommendation,
        "stop_condition": (
            f"safety_verdict resolves to SAFE or all {total_callers} caller(s) "
            "have been reviewed/updated."
        ),
    }


def _next_step_for_verdict(
    *,
    safety_verdict: str,
    symbol: str,
    modification_type: str,
    total_callers: int,
    architecture_rank: int | None,
) -> str:
    """Return one concrete next action keyed by the safety verdict."""
    if architecture_rank is not None and architecture_rank <= 10:
        return (
            f"{symbol} is rank #{architecture_rank} in the architecture — "
            "plan a staged migration and run batch_search before editing."
        )
    if safety_verdict == "SAFE":
        return f"Proceed with {modification_type} for '{symbol}'."
    if safety_verdict == "CAUTION":
        return (
            f"Run batch_search(['{symbol}']) to review {total_callers} caller(s), "
            "then proceed with the edit."
        )
    if safety_verdict == "REVIEW":
        return (
            f"Audit all {total_callers} call sites via batch_search(['{symbol}']) "
            "before changing the signature."
        )
    # UNSAFE / anything else: highest caution
    return (
        f"Do NOT modify '{symbol}' yet — plan a deprecation strategy and "
        f"update all {total_callers} call sites atomically."
    )


def _load_critical_nodes(project_root: str | None) -> list[dict[str, Any]]:
    """Load critical_nodes.json from the project cache, if it exists."""
    if not project_root:
        return []
    path = Path(project_root) / CRITICAL_NODES_FILE
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as fh:
            data: list[dict[str, Any]] = json.load(fh)
        return data
    except (OSError, json.JSONDecodeError, TypeError):
        return []


def _build_required_actions(
    symbol: str,
    modification_type: str,
    impact_level: str,
    total_callers: int,
) -> list[str]:
    """
    Build a list of required actions based on impact level and modification type.

    Args:
        symbol: The symbol being modified
        modification_type: Type of planned modification
        impact_level: Severity level (none / low / medium / high)
        total_callers: Total number of callers found

    Returns:
        List of action strings
    """
    actions: list[str] = []

    if impact_level == "none":
        actions.append("No callers found — safe to proceed.")
        return actions

    actions.append(f"Review all {total_callers} call site(s) before modifying.")
    actions.append(f"Use batch_search to find callers: ['{symbol}']")

    if modification_type in ("rename", "signature_change"):
        actions.append(
            "Update all call sites to match the new name / signature after the change."
        )
    if modification_type == "delete":
        actions.append(
            "Confirm every caller can be safely removed or refactored before deleting."
        )
    if modification_type == "behavior_change":
        actions.append(
            "Audit each caller to verify they tolerate the changed behavior."
        )

    if impact_level == "high":
        actions.append(
            "Consider creating a new method and deprecating the old one "
            "to allow a staged migration."
        )
        actions.append(
            "Update all call sites atomically or use feature flags to reduce risk."
        )

    return actions


class ModificationGuardTool(BaseMCPTool):
    """
    MCP tool for pre-modification safety checks.

    Runs trace_impact internally and returns a structured safety report with
    a safety_verdict (SAFE / CAUTION / REVIEW / UNSAFE) and required actions.
    """

    def __init__(self, project_root: str | None = None) -> None:
        """
        Initialize the modification guard tool.

        Args:
            project_root: Optional project root directory
        """
        # Create the inner trace_impact_tool BEFORE ``super().__init__`` so
        # the project-root hook that fires inside the parent constructor
        # can find the attribute. Otherwise it logs a noisy warning on
        # every construction.
        self._trace_impact_tool = TraceImpactTool(project_root)
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        """Propagate the project-root change to the inner trace_impact tool.

        ARCH-A4: tools react via this hook; ``BaseMCPTool.set_project_path``
        stays the single entrypoint. Forwarding to the inner tool uses its
        public ``set_project_path`` so its own hook fires too. Guard with
        ``hasattr`` because the hook may fire during ``super().__init__``
        before the inner tool is set (defence-in-depth).
        """
        if project_root is None:
            return
        inner = getattr(self, "_trace_impact_tool", None)
        if inner is not None:
            inner.set_project_path(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        """
        Get the MCP tool definition for modification_guard.

        Returns:
            Tool definition with name, description, and input schema
        """
        return {
            "name": "modification_guard",
            "description": (
                "Pre-modification safety check: run this BEFORE editing any public symbol.\n\n"
                "Returns a structured safety report showing how many places in the codebase\n"
                "depend on the symbol you are about to modify.\n\n"
                "WHEN TO USE:\n"
                "- ALWAYS before renaming a public function, class, or variable\n"
                "- ALWAYS before changing a method signature "
                "(adding/removing/reordering parameters)\n"
                "- ALWAYS before deleting a public symbol\n"
                "- When you want a structured 'proceed / review / stop' recommendation\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For private methods (underscore prefix) — "
                "use trace_impact instead if needed\n"
                "- For purely additive changes "
                "(adding a new method that doesn't replace anything)\n"
                "- For comment or docstring edits only\n"
                "\n"
                "IMPORTANT: This tool calls trace_impact internally. Do not call both — call\n"
                "modification_guard for pre-modification checks, "
                "trace_impact for general usage lookup.\n"
                "\n"
                "safety_verdict values:\n"
                "  SAFE     — 0 callers, proceed freely\n"
                "  CAUTION  — 1-5 callers, review before modifying\n"
                "  REVIEW   — 6-20 callers, check all call sites\n"
                "  UNSAFE   — 21+ callers, requires careful planning"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": (
                            "The symbol you are about to modify "
                            "(function/class/variable name). "
                            "Example: 'processPayment', 'UserService'"
                        ),
                    },
                    "modification_type": {
                        "type": "string",
                        "enum": [
                            "rename",
                            "signature_change",
                            "delete",
                            "behavior_change",
                            "refactor",
                        ],
                        "description": "Type of modification you plan to make.",
                    },
                    "file_path": {
                        "type": "string",
                        "description": (
                            "File where the symbol is defined (optional, improves accuracy). "
                            "Example: 'src/services/PaymentService.java'"
                        ),
                    },
                },
                "required": ["symbol", "modification_type"],
                # F5: refuse unknown keys; central enforcement is in
                # BaseMCPTool.__init_subclass__.
                "additionalProperties": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """
        Validate input arguments.

        Args:
            arguments: Tool arguments to validate

        Returns:
            True if arguments are valid

        Raises:
            ValueError: If arguments are invalid
        """
        symbol = arguments.get("symbol")
        if not symbol or not isinstance(symbol, str) or not symbol.strip():
            raise ValueError(
                "symbol parameter is required and must be a non-empty string"
            )

        modification_type = arguments.get("modification_type")
        valid_types = {
            "rename",
            "signature_change",
            "delete",
            "behavior_change",
            "refactor",
        }
        if not modification_type or modification_type not in valid_types:
            raise ValueError(
                f"modification_type must be one of: {', '.join(sorted(valid_types))}"
            )

        file_path = arguments.get("file_path")
        if file_path is not None and not isinstance(file_path, str):
            raise ValueError("file_path must be a string")

        return True

    @handle_mcp_errors("modification_guard")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the modification guard tool.

        Args:
            arguments: Tool arguments containing symbol, modification_type, and optional file_path

        Returns:
            Structured safety report with safety_verdict and required_actions
        """
        self.validate_arguments(arguments)

        symbol = arguments["symbol"].strip()
        modification_type = arguments["modification_type"]
        file_path = arguments.get("file_path")

        # Build arguments for trace_impact — pass through project_root if set
        trace_args: dict[str, Any] = {"symbol": symbol}
        if file_path:
            trace_args["file_path"] = file_path
        if self.project_root:
            trace_args["project_root"] = self.project_root

        # Delegate to trace_impact
        trace_result = await self._trace_impact_tool.execute(trace_args)

        # If trace_impact itself failed, surface the error
        if not trace_result.get("success", False):
            return {
                "success": False,
                "symbol": symbol,
                "modification_type": modification_type,
                "error": trace_result.get("error", "trace_impact failed"),
            }

        total_callers: int = trace_result.get("call_count", 0)
        impact = _get_impact_level(total_callers)
        impact_level = impact["level"]
        safety_verdict = _VERDICT_MAP.get(impact_level, "REVIEW")

        # Build callers_by_file breakdown
        usages: list[dict[str, Any]] = trace_result.get("usages", [])
        callers_by_file: dict[str, int] = {}
        for usage in usages:
            file_key: str = usage.get("file", "unknown")
            callers_by_file[file_key] = callers_by_file.get(file_key, 0) + 1

        required_actions = _build_required_actions(
            symbol=symbol,
            modification_type=modification_type,
            impact_level=impact_level,
            total_callers=total_callers,
        )

        proceed_recommendation: str
        if safety_verdict == "SAFE":
            proceed_recommendation = (
                f"No callers found for '{symbol}'. Safe to {modification_type}."
            )
        elif safety_verdict == "CAUTION":
            proceed_recommendation = (
                f"Review {total_callers} caller(s) before proceeding. "
                f"Use batch_search(['{symbol}']) to inspect usage patterns."
            )
        elif safety_verdict == "REVIEW":
            proceed_recommendation = (
                f"Check all {total_callers} call sites before modifying. "
                f"Use batch_search(['{symbol}']) to see all usage patterns."
            )
        else:
            proceed_recommendation = (
                f"Review all {total_callers} callers first. "
                f"Use batch_search(['{symbol}']) to see all usage patterns."
            )

        result: dict[str, Any] = {
            "success": True,
            "symbol": symbol,
            "modification_type": modification_type,
            "impact_level": impact_level,
            "impact_badge": impact["badge"],
            "impact_guidance": impact["guidance"],
            "total_callers": total_callers,
            # ``count`` is the cross-tool canonical alias (every search/
            # scan tool exposes a top-level ``count`` integer).
            "count": total_callers,
            "callers_by_file": callers_by_file,
            "safety_verdict": safety_verdict,
            # ``verdict`` is a canonical alias used across all safety tools
            # (safe_to_edit, modification_guard). Same value, shorter key
            # — discoverable by callers that don't know our exact name.
            "verdict": safety_verdict,
            "required_actions": required_actions,
            "proceed_recommendation": proceed_recommendation,
            # ``recommendation`` mirrors ``proceed_recommendation`` so this
            # tool's response carries the same field name every other
            # safety tool exposes (safe_to_edit, file_health). One key,
            # one source of truth.
            "recommendation": proceed_recommendation,
        }

        # --- PageRank architecture check ---
        critical_nodes = _load_critical_nodes(self.project_root)
        for rank, node in enumerate(critical_nodes, start=1):
            if node.get("name") == symbol:
                pr_score = node.get("pagerank", 0)
                subtypes = node.get("inbound_refs", 0)
                result["architecture_rank"] = rank
                result["architecture_score"] = pr_score
                result["architecture_warning"] = (
                    f"{symbol} is #{rank} in the project's architectural "
                    f"hierarchy (PageRank {pr_score:.4f}, "
                    f"{subtypes} direct subtypes). "
                    f"Modifying it affects the project's foundation."
                )
                # Boost verdict for top-10 architecture nodes
                if rank <= 10:
                    boosted = _VERDICT_BOOST.get(safety_verdict, safety_verdict)
                    result["safety_verdict"] = boosted
                    # Keep the ``verdict`` alias in sync with the boosted value.
                    result["verdict"] = boosted
                break

        # Unified summary line: one line to see everything
        final_verdict = result["safety_verdict"]
        rank_str = (
            f"rank=#{result['architecture_rank']}"
            if "architecture_rank" in result
            else "rank=-"
        )
        pr_str = (
            f"pr={result['architecture_score']:.4f}"
            if "architecture_score" in result
            else ""
        )
        parts = [
            symbol,
            rank_str,
            f"callers={total_callers}",
            f"verdict={final_verdict}",
        ]
        if pr_str:
            parts.insert(2, pr_str)
        # J5 (round-22): single-space join via helper — was ``"  ".join``
        # (literal double space) which produced ``"foo rank=#1  pr=...."``.
        result["summary_line"] = format_summary_line(*parts)

        # F10: populate agent_summary with the canonical safety-tool
        # shape (summary_line / verdict / risk / next_step). Prior to
        # this fix the field was synthesised as ``{}`` downstream by
        # ensure_canonical_success_envelope, which gave agents no useful
        # decision signal.
        result["agent_summary"] = _build_agent_summary(
            symbol=symbol,
            modification_type=modification_type,
            safety_verdict=final_verdict,
            total_callers=total_callers,
            summary_line=result["summary_line"],
            proceed_recommendation=proceed_recommendation,
            architecture_rank=result.get("architecture_rank"),
        )

        # Mirror agent_summary.summary_line to the top-level envelope
        # (idempotent — keeps the value we just set above) so direct
        # callers that bypass the MCP dispatch hook still see it.
        return mirror_summary_line(result)
