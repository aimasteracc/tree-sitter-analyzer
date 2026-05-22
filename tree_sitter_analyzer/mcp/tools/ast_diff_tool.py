#!/usr/bin/env python3
"""
AST Structured Diff MCP Tool

Exposes tree-level code change understanding via MCP protocol.
Compares two versions of a file at the AST level to identify
added/removed/modified functions, classes, imports, and variables.
"""

import time
from typing import Any

from ...ast_diff import ASTDiffer
from ...utils import setup_logger
from .base_tool import BaseMCPTool, _canonicalize_verdict, mirror_summary_line

logger = setup_logger(__name__)


def _attach_ast_diff_envelope(result: dict[str, Any]) -> None:
    summary = result.get("summary", {})
    added = summary.get("added", 0)
    removed = summary.get("removed", 0)
    modified = summary.get("modified", 0)
    total = added + removed + modified

    if result.get("success") is False:
        verdict = "ERROR"
        summary_line = f"ast_diff error: {result.get('error', 'unknown')}"
        next_step = "Check file_path and refs are valid."
    elif total == 0:
        verdict = _canonicalize_verdict("SAFE")
        summary_line = "ast_diff: no structural changes detected"
        next_step = "File structure is unchanged."
    else:
        verdict = _canonicalize_verdict("CAUTION" if removed > 0 else "INFO")
        summary_line = (
            f"ast_diff: {added} added, {removed} removed, {modified} modified"
        )
        next_step = "Review changes. Use callers/callees to assess impact."

    agent_summary: dict[str, Any] = {
        "summary_line": summary_line,
        "verdict": verdict,
        "next_step": next_step,
        "risk": "low" if total == 0 else ("medium" if removed else "low"),
    }
    result["agent_summary"] = agent_summary
    result.setdefault("summary_line", summary_line)
    result.setdefault("verdict", verdict)
    mirror_summary_line(result)


class ASTDiffTool(BaseMCPTool):
    """MCP Tool for AST-level structured diff of source code changes."""

    def __init__(self, project_root: str | None = None) -> None:
        self._differ: ASTDiffer | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._differ = None

    def _get_differ(self) -> ASTDiffer:
        if self._differ is None:
            self._differ = ASTDiffer()
        return self._differ

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "ast_diff",
            "description": (
                "AST-level structured diff. Compares two versions of a file "
                "at the tree level — identifies added/removed/modified "
                "functions, classes, imports, variables. Modes: "
                "file_revisions (compare two git refs), "
                "working_tree (compare file on disk vs git ref), "
                "strings (compare two source strings). "
                "No other tool provides tree-level semantic diff."
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
                        "file_revisions",
                        "working_tree",
                        "strings",
                    ],
                    "description": (
                        "file_revisions: compare two git refs; "
                        "working_tree: compare disk vs git; "
                        "strings: compare two source strings"
                    ),
                    "default": "file_revisions",
                },
                "file_path": {
                    "type": "string",
                    "description": "File path (required for file_revisions and working_tree modes)",
                },
                "old_ref": {
                    "type": "string",
                    "description": "Git ref for old version (default: HEAD~1)",
                    "default": "HEAD~1",
                },
                "new_ref": {
                    "type": "string",
                    "description": "Git ref for new version (default: HEAD)",
                    "default": "HEAD",
                },
                "old_source": {
                    "type": "string",
                    "description": "Old source code (required for strings mode)",
                },
                "new_source": {
                    "type": "string",
                    "description": "New source code (required for strings mode)",
                },
                "language": {
                    "type": "string",
                    "description": "Programming language (required for strings mode)",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format (default: toon)",
                    "default": "toon",
                },
            },
            "additionalProperties": False,
        }

    _VALID_MODES = ("file_revisions", "working_tree", "strings")

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "file_revisions")
        if mode not in self._VALID_MODES:
            raise ValueError(
                f"Invalid mode '{mode}'; expected one of: "
                f"{', '.join(self._VALID_MODES)}."
            )
        if mode in ("file_revisions", "working_tree") and not arguments.get(
            "file_path"
        ):
            raise ValueError(f"file_path is required for mode '{mode}'")
        if mode == "strings":
            if not arguments.get("old_source") and not arguments.get("new_source"):
                raise ValueError("old_source or new_source required for strings mode")
            if not arguments.get("language"):
                raise ValueError("language is required for strings mode")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        started = time.perf_counter()
        mode = arguments.get("mode", "file_revisions")
        output_format = arguments.get("output_format", "toon")
        differ = self._get_differ()

        if mode == "file_revisions":
            file_path = arguments["file_path"]
            old_ref = arguments.get("old_ref", "HEAD~1")
            new_ref = arguments.get("new_ref", "HEAD")
            diff_result = differ.diff_file_revisions(file_path, old_ref, new_ref)
        elif mode == "working_tree":
            file_path = arguments["file_path"]
            ref = arguments.get("old_ref", "HEAD")
            diff_result = differ.diff_file_against_git(file_path, ref)
        elif mode == "strings":
            old_source = arguments.get("old_source", "")
            new_source = arguments.get("new_source", "")
            language = arguments["language"]
            diff_result = differ.diff_strings(old_source, new_source, language)
        else:
            raise ValueError(f"Invalid mode: {mode}")

        result = diff_result.to_dict()
        result["mode"] = mode
        result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)

        _attach_ast_diff_envelope(result)

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)
