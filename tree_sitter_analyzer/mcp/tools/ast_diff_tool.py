#!/usr/bin/env python3
"""
AST Structured Diff MCP Tool — Tree-level code change understanding.

Compares two versions of source code at the AST node level, producing
semantically meaningful diff results (signature vs body changes, renamed
functions, added/removed classes, etc.).

Unlike text diffs, understands code structure.
"""

from typing import Any

from ...ast_diff import ASTDiffer
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# Byte-budget constant for include_node_bodies opt-in (Issue #552)
#
# When include_node_bodies=True the full children subtree is inlined.
# This cap prevents any single large added/removed node (e.g. a big schema
# dict literal) from dumping megabytes into the response.  When the budget
# is exceeded children_truncated=True and bytes_omitted=<int> are added
# to the response for transparency.  Patched to 1 in tests to force
# truncation.  Default matches the sibling get_code_outline tool's spirit
# (~32 KB is enough for any practical per-diff inspection need).
# ---------------------------------------------------------------------------
NODE_BODIES_BUDGET: int = 32_768  # 32 KB


class ASTDiffTool(BaseMCPTool):
    """MCP Tool for structural AST diffing."""

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
                "Structural AST diff — tree-level code change understanding. "
                "Compares two code versions at the AST level: detects signature changes, "
                "body changes, renamed functions, added/removed classes/imports. "
                "Modes: diff_files (two file paths), diff_strings (two code strings), "
                "diff_git (file between two git refs). "
                "No other tool provides tree-level structural diffing."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["diff_files", "diff_strings", "diff_git"],
                    # mode is runtime-resolved from arg shape (issue #529) —
                    # NOT in required; an absent mode is inferred from the args.
                    "description": "Diff mode — inferred when omitted: "
                    "old_ref/new_ref → diff_git; "
                    "old_source/new_source → diff_strings; "
                    "old_file/new_file → diff_files. "
                    "Explicit value always wins.",
                    "default": "diff_files",
                },
                "old_file": {
                    "type": "string",
                    "description": "Path to the old version of the file (for diff_files mode)",
                },
                "new_file": {
                    "type": "string",
                    "description": "Path to the new version of the file (for diff_files mode)",
                },
                "old_source": {
                    "type": "string",
                    "description": "Old source code string (for diff_strings mode)",
                },
                "new_source": {
                    "type": "string",
                    "description": "New source code string (for diff_strings mode)",
                },
                "file_path": {
                    "type": "string",
                    "description": "File path to diff between git refs (for diff_git mode)",
                },
                "old_ref": {
                    "type": "string",
                    "description": "Old git ref (default: HEAD~1)",
                    "default": "HEAD~1",
                },
                "new_ref": {
                    "type": "string",
                    "description": "New git ref (default: HEAD)",
                    "default": "HEAD",
                },
                "language": {
                    "type": "string",
                    "description": "Language override (auto-detected from file extension if omitted)",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format: 'toon' (default, token-efficient) or 'json'",
                    "default": "toon",
                },
                # Issue #552 — opt-in full node body (default: compact summaries only)
                "include_node_bodies": {
                    "type": "boolean",
                    "description": (
                        "Include the full recursive children subtree in each hunk's "
                        "old/new node. Off by default — the default response keeps only "
                        "the compact node summary (type, kind, name, line, end_line, "
                        "text_hash, preview, child_count) which is 70-99% smaller. "
                        "Enable only when you need to inspect exact AST sub-structure. "
                        "A 32 KB byte budget is enforced; when exceeded, "
                        "children_truncated=true and bytes_omitted=<int> are set. "
                        "NEVER mark this required — runtime-resolved param."
                    ),
                    "default": False,
                },
            },
            # mode is runtime-resolved from arg shape (issue #529 / the 6×-recurred
            # facade trap) — it is NOT required. Declaring it required causes strict
            # MCP clients to reject valid calls like {old_ref, new_ref, file_path}.
            "required": [],
            "additionalProperties": False,
        }

    @staticmethod
    def _resolve_mode(arguments: dict[str, Any]) -> str:
        """Effective mode — inferred from argument shape when omitted.

        Issue #529 (schema honesty / mode inference):
        - Explicit ``mode`` always wins.
        - old_source/new_source present → diff_strings
        - old_file/new_file present → diff_files
        - old_ref/new_ref + file_path → diff_git
        - None of the above → returns empty string (validate_arguments will raise)

        Source/file signatures are checked BEFORE refs because callers that
        materialize schema defaults (the CLI bridge fills old_ref/new_ref
        with HEAD~1/HEAD) carry ref fields on every call — refs alone must
        not steal the inference from an explicit string/file diff. The git
        signature additionally requires its file_path discriminator
        (Codex P2 on #551).
        """
        mode = arguments.get("mode")
        if mode:
            return str(mode)
        if (
            arguments.get("old_source") is not None
            or arguments.get("new_source") is not None
        ):
            return "diff_strings"
        if arguments.get("old_file") or arguments.get("new_file"):
            return "diff_files"
        if (arguments.get("old_ref") or arguments.get("new_ref")) and arguments.get(
            "file_path"
        ):
            return "diff_git"
        return ""

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = self._resolve_mode(arguments)
        if mode == "diff_files":
            if not arguments.get("old_file") or not arguments.get("new_file"):
                raise ValueError(
                    "old_file and new_file are required for diff_files mode"
                )
        elif mode == "diff_strings":
            if (
                arguments.get("old_source") is None
                or arguments.get("new_source") is None
            ):
                raise ValueError(
                    "old_source and new_source are required for diff_strings mode"
                )
            if not arguments.get("language"):
                raise ValueError("language is required for diff_strings mode")
        elif mode == "diff_git":
            if not arguments.get("file_path"):
                raise ValueError("file_path is required for diff_git mode")
        else:
            raise ValueError(
                "Cannot infer mode from arguments. "
                "Provide one of the following mode signatures:\n"
                "  diff_files:   old_file + new_file\n"
                "  diff_strings: old_source + new_source + language\n"
                "  diff_git:     old_ref + new_ref + file_path\n"
                "Or pass mode= explicitly."
            )
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        mode = self._resolve_mode(arguments)
        output_format = arguments.get("output_format", "toon")
        include_node_bodies = bool(arguments.get("include_node_bodies", False))
        differ = self._get_differ()

        if mode == "diff_files":
            result = differ.diff_files(
                old_path=arguments["old_file"],
                new_path=arguments["new_file"],
                language=arguments.get("language"),
            )
        elif mode == "diff_strings":
            result = differ.diff_strings(
                old_source=arguments["old_source"],
                new_source=arguments["new_source"],
                language=arguments["language"],
            )
        elif mode == "diff_git":
            result = self._diff_git(differ, arguments)
        else:
            raise ValueError(f"Unknown mode: {mode}")

        result_dict = result.to_dict(
            include_children=include_node_bodies, with_child_count=True
        )
        # pain #5 (dogfood): ast-diff had no verdict. NOT_FOUND when the two
        # sides are identical (zero hunks), INFO when there are real changes.
        # We deliberately don't escalate to REVIEW/CAUTION here — diff
        # severity is the semantic_classify tool's job.
        verdict = "NOT_FOUND" if not result_dict.get("hunks") else "INFO"
        hunk_count = len(result_dict.get("hunks", []))
        lang_str = result_dict.get("language", "unknown")
        agent_summary_line = (
            f"{hunk_count} AST change(s) in {lang_str}"
            if hunk_count
            else f"No AST changes in {lang_str}"
        )
        response: dict[str, Any] = {
            "success": True,
            "verdict": verdict,
            "summary_line": agent_summary_line,
            "agent_summary": agent_summary_line,
            **result_dict,
        }

        # Issue #552 — apply byte budget when include_node_bodies=True.
        # When the hunks serialise to more than NODE_BODIES_BUDGET bytes,
        # stop inlining children and set transparency flags.
        if include_node_bodies:
            import json

            hunks_bytes = len(json.dumps(response.get("hunks", [])))
            if hunks_bytes > NODE_BODIES_BUDGET:
                # Rebuild without children and record how many bytes were saved
                compact_dict = result.to_dict(
                    include_children=False, with_child_count=True
                )
                compact_hunks_bytes = len(json.dumps(compact_dict.get("hunks", [])))
                response["hunks"] = compact_dict["hunks"]
                response["children_truncated"] = True
                response["bytes_omitted"] = hunks_bytes - compact_hunks_bytes

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(response, output_format)

    def _diff_git(self, differ: ASTDiffer, arguments: dict[str, Any]) -> Any:
        import subprocess

        from ...project_graph import _language_from_ext

        file_path = arguments["file_path"]
        old_ref = arguments.get("old_ref", "HEAD~1")
        new_ref = arguments.get("new_ref", "HEAD")

        language = arguments.get("language") or _language_from_ext(file_path) or ""

        try:
            old_result = subprocess.run(
                ["git", "show", f"{old_ref}:{file_path}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            old_source = old_result.stdout if old_result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            old_source = ""

        try:
            new_result = subprocess.run(
                ["git", "show", f"{new_ref}:{file_path}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            new_source = new_result.stdout if new_result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            new_source = ""

        return differ.diff_strings(
            old_source=old_source,
            new_source=new_source,
            language=language,
            old_file=f"{old_ref}:{file_path}",
            new_file=f"{new_ref}:{file_path}",
        )
