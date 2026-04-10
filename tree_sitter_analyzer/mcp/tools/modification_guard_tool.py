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
from .base_tool import BaseMCPTool
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

CRITICAL_NODES_FILE = ".tree-sitter-cache/critical_nodes.json"


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
        super().__init__(project_root)
        self._trace_impact_tool = TraceImpactTool(project_root)

    def set_project_path(self, project_path: str) -> None:
        """
        Update project path for this tool and the inner trace_impact tool.

        Args:
            project_path: New project root directory
        """
        super().set_project_path(project_path)
        self._trace_impact_tool.set_project_path(project_path)

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
            raise ValueError("symbol parameter is required and must be a non-empty string")

        modification_type = arguments.get("modification_type")
        valid_types = {"rename", "signature_change", "delete", "behavior_change", "refactor"}
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
            "callers_by_file": callers_by_file,
            "safety_verdict": safety_verdict,
            "required_actions": required_actions,
            "proceed_recommendation": proceed_recommendation,
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
                    result["safety_verdict"] = _VERDICT_BOOST.get(
                        safety_verdict, safety_verdict
                    )
                break

        # Unified summary line: one line to see everything
        final_verdict = result["safety_verdict"]
        rank_str = f"rank=#{result['architecture_rank']}" if "architecture_rank" in result else "rank=-"
        pr_str = f"pr={result['architecture_score']:.4f}" if "architecture_score" in result else ""
        parts = [
            symbol,
            rank_str,
            f"callers={total_callers}",
            f"verdict={final_verdict}",
        ]
        if pr_str:
            parts.insert(2, pr_str)
        result["summary_line"] = "  ".join(parts)

        return result
