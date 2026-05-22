#!/usr/bin/env python3
"""
CodeGraph Call Graph MCP Tool

Exposes bidirectional function-level call tracking via MCP protocol.
Provides callers_of, callees_of, call_chain, and summary queries.
CodeGraph parity: equivalent to codegraph_callers / codegraph_callees.
"""

from typing import Any

from ...call_graph import CallGraph
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CodeGraphCallTool(BaseMCPTool):
    """MCP Tool for function-level call graph analysis."""

    def __init__(self, project_root: str | None = None) -> None:
        self._call_graph: CallGraph | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._call_graph = None

    def _get_call_graph(self) -> CallGraph:
        if self._call_graph is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            self._call_graph = CallGraph(self.project_root)
        return self._call_graph

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_call_graph",
            "description": (
                "Function-level call graph (CodeGraph parity). Modes: "
                "callers (who calls X), callees (what does X call), "
                "chain (transitive call chain), summary (stats), "
                "all_functions (list all discovered functions), "
                "file_impact (upstream/downstream impact of changing a file), "
                "functions_in_file (list functions defined in a file). "
                "No other built-in tool provides function-level call tracking."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": [
                        "callers",
                        "callees",
                        "chain",
                        "summary",
                        "all_functions",
                        "file_impact",
                        "functions_in_file",
                    ],
                    "description": "Query mode (default: summary)",
                    "default": "summary",
                },
                "function_name": {
                    "type": "string",
                    "description": "Target function name (required for callers, callees, chain modes)",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to disambiguate overloaded functions, or required for file_impact/functions_in_file modes",
                },
                "depth": {
                    "type": "integer",
                    "description": "Max traversal depth for chain mode (default: 5)",
                    "default": 5,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format: 'toon' (default, token-efficient) or 'json'",
                    "default": "toon",
                },
            },
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "summary")
        if mode in ("callers", "callees", "chain") and "function_name" not in arguments:
            raise ValueError(f"function_name is required for mode '{mode}'")
        if mode in ("file_impact", "functions_in_file") and "file_path" not in arguments:
            raise ValueError(f"file_path is required for mode '{mode}'")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        mode = arguments.get("mode", "summary")
        output_format = arguments.get("output_format", "toon")
        graph = self._get_call_graph()

        # pain #6 (dogfood): call_graph emitted verdict=null in every mode.
        # For function lookups, NOT_FOUND when the function isn't anywhere
        # tells the agent to stop chasing — INFO otherwise.
        if mode == "summary":
            summary = graph.summary()
            verdict = "INFO" if summary.get("function_count", 0) > 0 else "NOT_FOUND"
            result = {
                "success": True,
                "mode": "summary",
                "verdict": verdict,
                **summary,
            }
        elif mode == "all_functions":
            funcs = graph.all_functions()
            result = {
                "success": True,
                "mode": "all_functions",
                "verdict": "INFO" if funcs else "NOT_FOUND",
                "count": len(funcs),
                "functions": funcs,
            }
        elif mode == "callers":
            func_name = arguments["function_name"]
            file_path = arguments.get("file_path")
            callers = graph.callers_of(func_name, file_path)
            result = {
                "success": True,
                "mode": "callers",
                "verdict": "INFO" if callers else "NOT_FOUND",
                "function": func_name,
                "caller_count": len(callers),
                "callers": callers,
            }
        elif mode == "callees":
            func_name = arguments["function_name"]
            file_path = arguments.get("file_path")
            callees = graph.callees_of(func_name, file_path)
            result = {
                "success": True,
                "mode": "callees",
                "verdict": "INFO" if callees else "NOT_FOUND",
                "function": func_name,
                "callee_count": len(callees),
                "callees": callees,
            }
        elif mode == "chain":
            func_name = arguments["function_name"]
            file_path = arguments.get("file_path")
            depth = arguments.get("depth", 5)
            chain = graph.call_chain(func_name, file_path, depth)
            result = {
                "success": True,
                "mode": "chain",
                "verdict": "INFO" if chain else "NOT_FOUND",
                "function": func_name,
                "depth": depth,
                "edge_count": len(chain),
                "chain": chain,
            }
        elif mode == "file_impact":
            file_path = arguments["file_path"]
            impact = graph.file_impact(file_path)
            result = {
                "success": True,
                "mode": "file_impact",
                "verdict": "INFO" if impact["function_count"] > 0 else "NOT_FOUND",
                **impact,
            }
        elif mode == "functions_in_file":
            file_path = arguments["file_path"]
            funcs = graph.functions_in_file(file_path)
            result = {
                "success": True,
                "mode": "functions_in_file",
                "verdict": "INFO" if funcs else "NOT_FOUND",
                "file": file_path,
                "function_count": len(funcs),
                "functions": funcs,
            }
        else:
            raise ValueError(f"Unknown mode: {mode}")

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)
