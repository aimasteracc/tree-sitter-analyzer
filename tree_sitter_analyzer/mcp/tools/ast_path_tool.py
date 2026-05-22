#!/usr/bin/env python3
"""
CodeGraph AST Path MCP Tool — "What's at line X of file Y?"

Answers scope-enclosing queries by walking the Tree-sitter AST:
- path: Full AST path from root to the node at a given line
- scope: Innermost enclosing named scope (function/class/method) at a line
- outline: Hierarchical file outline (top-level declarations)
- siblings: Sibling declarations at the same scope level as a given line

CodeGraph parity: equivalent to CodeGraph's "enclosing scope" and
"go-to-definition context" queries. No other built-in tool provides
line-level AST scope navigation.
"""

from typing import Any

from ...ast_path import ASTPathNavigator
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CodeGraphASTPathTool(BaseMCPTool):
    """MCP Tool for AST path/scope navigation (CodeGraph parity)."""

    def __init__(self, project_root: str | None = None) -> None:
        self._navigator: ASTPathNavigator | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._navigator = None

    def _get_navigator(self) -> ASTPathNavigator:
        if self._navigator is None:
            self._navigator = ASTPathNavigator()
        return self._navigator

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_ast_path",
            "description": (
                "AST path/scope navigation — answer 'what is at line X of file Y?' (CodeGraph parity). "
                "Modes: "
                "path (full AST path from root to node at line), "
                "scope (innermost enclosing function/class + siblings), "
                "outline (hierarchical file outline), "
                "siblings (declarations at same scope level). "
                "No other built-in tool provides line-level AST scope navigation."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["path", "scope", "outline", "siblings"],
                    "description": "Query mode (default: scope)",
                    "default": "scope",
                },
                "file_path": {
                    "type": "string",
                    "description": "Source file path to analyze",
                },
                "line": {
                    "type": "integer",
                    "description": "Target line number (required for path, scope, siblings modes)",
                },
                "language": {
                    "type": "string",
                    "description": "Override language detection (optional)",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Max outline depth for outline mode (default: 3)",
                    "default": 3,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format: 'toon' (default, token-efficient) or 'json'",
                    "default": "toon",
                },
            },
            "required": ["file_path"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "scope")
        if mode in ("path", "scope", "siblings") and "line" not in arguments:
            raise ValueError(f"line is required for mode '{mode}'")
        if not arguments.get("file_path"):
            raise ValueError("file_path is required")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        mode = arguments.get("mode", "scope")
        file_path = arguments["file_path"]
        line = arguments.get("line")
        language = arguments.get("language")
        max_depth = arguments.get("max_depth", 3)
        output_format = arguments.get("output_format", "toon")

        resolved = self.resolve_and_validate_file_path(file_path)
        nav = self._get_navigator()

        # validate_arguments guarantees line is int for path/scope/siblings modes.
        line_int: int = int(line) if line is not None else 0

        if mode == "path":
            result = nav.path_at_line(resolved, line_int, language)
        elif mode == "scope":
            result = nav.scope_at(resolved, line_int, language)
        elif mode == "outline":
            result = nav.outline(resolved, language, max_depth=max_depth)
        elif mode == "siblings":
            path_result = nav.path_at_line(resolved, line_int, language)
            result = path_result
        else:
            raise ValueError(f"Unknown mode: {mode}")

        # Pain #24 (dogfood pass 3): ast_path emitted no verdict. NOT_FOUND
        # when the result is effectively empty (no nodes/path), INFO when
        # there is structural data for the agent to act on.
        result_dict = result.to_dict()
        # Treat any non-empty list field or non-empty ``path`` as "found".
        has_data = any(
            bool(result_dict.get(k))
            for k in ("path", "nodes", "siblings", "outline", "scope")
        )
        response: dict[str, Any] = {
            "success": True,
            "mode": mode,
            "verdict": "INFO" if has_data else "NOT_FOUND",
            **result_dict,
        }

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(response, output_format)
