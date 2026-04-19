#!/usr/bin/env python3
"""
Semantic Impact Analysis MCP Tool

Provides semantic-level code impact analysis that goes beyond textual
occurrence counting. Considers type hierarchy, visibility, call chain depth,
and API surface area to assess change risk.

Risk Levels: SAFE, LOW, MODERATE, HIGH, CRITICAL
"""

from __future__ import annotations

from typing import Any

from ...analysis.semantic_impact import (
    SymbolProfile,
    Visibility,
    _compute_risk_score,
    _determine_risk_level,
    analyze_semantic_impact,
    report_to_dict,
)
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class SemanticImpactTool(BaseMCPTool):
    """
    Semantic Impact Analysis Tool

    Analyzes the semantic impact of code changes considering:
    - Type hierarchy (base class changes propagate to all subclasses)
    - Visibility (public API changes have wider impact than private ones)
    - Call chain depth (deeper call chains amplify blast radius)
    - API surface (methods in interfaces/abstract classes affect all implementations)
    """

    def get_tool_definition(self) -> dict[str, Any]:
        """Get the MCP tool definition."""
        return {
            "name": "semantic_impact",
            "description": (
                "Analyze the semantic impact of a code change. "
                "Goes beyond textual occurrence counting to assess the *semantic* impact "
                "of code changes. Considers type hierarchy, visibility, call chain depth, "
                "and API surface area. Risk Levels: SAFE, LOW, MODERATE, HIGH, CRITICAL. "
                "Returns a risk score (0-100) with contributing factors and actionable suggestions. "
                "Use mode='quick' for fast assessment based on visibility and caller count only."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Symbol name being analyzed",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Source file path (optional, used for language detection)",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["full", "quick"],
                        "description": "Analysis mode: 'full' for detailed analysis, 'quick' for fast risk assessment",
                        "default": "full",
                    },
                    "caller_count": {
                        "type": "integer",
                        "description": "Number of callers found (from trace_impact)",
                        "default": 0,
                    },
                    "call_chain_depth": {
                        "type": "integer",
                        "description": "Max call chain depth (from dependency graph)",
                        "default": 0,
                    },
                    "visibility": {
                        "type": "string",
                        "enum": ["public", "protected", "private", "package", "internal"],
                        "description": "Symbol visibility",
                        "default": "public",
                    },
                    "is_abstract": {
                        "type": "boolean",
                        "description": "Whether the symbol is abstract",
                        "default": False,
                    },
                    "is_interface_member": {
                        "type": "boolean",
                        "description": "Whether the symbol is an interface member",
                        "default": False,
                    },
                    "is_static": {
                        "type": "boolean",
                        "description": "Whether the symbol is static",
                        "default": False,
                    },
                    "is_type_hierarchy_root": {
                        "type": "boolean",
                        "description": "Whether this is a base class/interface root (quick mode)",
                        "default": False,
                    },
                    "base_classes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of base class names",
                    },
                    "annotations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of annotations on the symbol",
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["json", "tson"],
                        "description": "Output format",
                        "default": "json",
                    },
                },
                "required": ["symbol"],
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate tool arguments."""
        symbol = arguments.get("symbol")
        if not symbol or not isinstance(symbol, str):
            raise ValueError("symbol is required and must be a string")

        caller_count = arguments.get("caller_count", 0)
        if not isinstance(caller_count, int) or caller_count < 0:
            raise ValueError("caller_count must be a non-negative integer")

        call_chain_depth = arguments.get("call_chain_depth", 0)
        if not isinstance(call_chain_depth, int) or call_chain_depth < 0:
            raise ValueError("call_chain_depth must be a non-negative integer")

        visibility = arguments.get("visibility", "public")
        valid_visibilities = {"public", "protected", "private", "package", "internal"}
        if visibility not in valid_visibilities:
            raise ValueError(f"visibility must be one of {valid_visibilities}")

        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute the semantic impact analysis."""
        self.validate_arguments(arguments)

        # Extract common parameters
        symbol = arguments["symbol"]
        mode = arguments.get("mode", "full")
        caller_count = arguments.get("caller_count", 0)
        visibility = arguments.get("visibility", "public")
        is_abstract = arguments.get("is_abstract", False)

        # Map visibility string to enum
        visibility_map: dict[str, Visibility] = {
            "public": Visibility.PUBLIC,
            "protected": Visibility.PROTECTED,
            "private": Visibility.PRIVATE,
            "package": Visibility.PACKAGE,
            "internal": Visibility.PACKAGE,
        }

        if mode == "quick":
            return self._execute_quick(
                symbol=symbol,
                caller_count=caller_count,
                visibility=visibility,
                visibility_map=visibility_map,
                is_abstract=is_abstract,
                is_type_hierarchy_root=arguments.get("is_type_hierarchy_root", False),
            )

        return self._execute_full(arguments, visibility_map)

    def _execute_quick(
        self,
        symbol: str,
        caller_count: int,
        visibility: str,
        visibility_map: dict[str, Visibility],
        is_abstract: bool,
        is_type_hierarchy_root: bool,
    ) -> dict[str, Any]:
        """Quick mode: fast risk assessment based on visibility and caller count."""
        profile = SymbolProfile(
            name=symbol,
            file_path="",
            language="",
            visibility=visibility_map.get(visibility.lower(), Visibility.PUBLIC),
            is_abstract=is_abstract,
        )

        risk_score, factors = _compute_risk_score(
            caller_count=caller_count,
            visibility=profile.visibility,
            call_chain_depth=0,
            is_type_hierarchy_root=is_type_hierarchy_root,
            is_abstract=profile.is_abstract,
            is_interface_member=False,
            is_static=False,
            is_constructor=False,
            annotations=(),
        )

        risk_level = _determine_risk_level(risk_score)

        return {
            "symbol": symbol,
            "risk_level": risk_level.value,
            "risk_score": risk_score,
            "key_factors": list(factors),
        }

    def _execute_full(
        self,
        arguments: dict[str, Any],
        visibility_map: dict[str, Visibility],
    ) -> dict[str, Any]:
        """Full mode: detailed semantic impact analysis."""
        symbol = arguments["symbol"]
        file_path = arguments.get("file_path")
        caller_count = arguments.get("caller_count", 0)
        call_chain_depth = arguments.get("call_chain_depth", 0)
        visibility = arguments.get("visibility", "public")
        is_abstract = arguments.get("is_abstract", False)
        is_interface_member = arguments.get("is_interface_member", False)
        is_static = arguments.get("is_static", False)
        base_classes = arguments.get("base_classes", [])
        annotations = arguments.get("annotations", [])
        output_format = arguments.get("output_format", "json")

        # Build symbol profile
        profile = SymbolProfile(
            name=symbol,
            file_path=file_path or "",
            language="",
            visibility=visibility_map.get(visibility.lower(), Visibility.PUBLIC),
            is_abstract=is_abstract,
            is_interface_member=is_interface_member,
            is_static=is_static,
            base_classes=tuple(base_classes),
            annotations=tuple(annotations),
        )

        # Perform semantic impact analysis
        report = analyze_semantic_impact(
            symbol=symbol,
            file_path=file_path,
            caller_count=caller_count,
            call_chain_depth=call_chain_depth,
            profile=profile,
        )

        # Convert to dict
        result = report_to_dict(report)

        # Format output
        if output_format == "tson":
            from ...formatters.toon_encoder import ToonEncoder

            encoder = ToonEncoder()
            toon_output = encoder.encode(result)
            return {"output": toon_output, "format": "tson"}
        return result
