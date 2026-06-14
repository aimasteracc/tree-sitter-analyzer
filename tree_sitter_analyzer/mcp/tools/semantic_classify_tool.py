#!/usr/bin/env python3
"""
Semantic Classify MCP Tool — Standalone semantic change classification.

Classifies code changes into semantic categories (api_change, refactor,
feature_addition, etc.) with risk assessment and confidence scores.

Can operate in two modes:
- classify_strings: Compare two code strings
- classify_git: Compare a file between two git refs
"""

from typing import Any

from ...ast_diff import ASTDiffer
from ...project_graph import _language_from_ext
from ...semantic_change_classifier import SemanticChangeClassifier
from ...utils import setup_logger
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

# Default cap on classification entries returned.
_DEFAULT_HUNK_CAP = 50


def _strip_children(node_dict: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a serialised ASTNodeInfo without the recursive children list."""
    return {k: v for k, v in node_dict.items() if k != "children"}


def _compact_hunk(hunk_dict: dict[str, Any]) -> dict[str, Any]:
    """Strip children from hunk.old / hunk.new so only the top-level node is kept."""
    result: dict[str, Any] = {}
    for key, val in hunk_dict.items():
        if key in ("old", "new") and isinstance(val, dict):
            result[key] = _strip_children(val)
        else:
            result[key] = val
    return result


def _compact_classification(
    entry: dict[str, Any],
    *,
    include_ast_nodes: bool,
) -> dict[str, Any]:
    """Return a compact version of a ClassifiedHunk dict.

    By default (include_ast_nodes=False):
      - ``hunk`` is present but hunk.old/new have their ``children`` stripped.
    With include_ast_nodes=True:
      - Full hunk dict is preserved (children included).
    """
    if include_ast_nodes:
        return entry
    hunk = entry.get("hunk")
    if not isinstance(hunk, dict):
        return entry
    compact: dict[str, Any] = {k: v for k, v in entry.items() if k != "hunk"}
    compact["hunk"] = _compact_hunk(hunk)
    return compact


class SemanticClassifyTool(BaseMCPTool):
    """MCP Tool for semantic change classification."""

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
            "name": "semantic_classify",
            "description": (
                "Classify code changes into semantic categories with risk assessment. "
                "Modes: classify_string (two code strings), classify_file (file between git refs). "
                "Returns dominant category, risk level, confidence, and per-hunk classification. "
                "No other tool provides semantic change understanding."
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
                    # pain #11 (dogfood pass 2): the tests pinned a contract
                    # with singular ``classify_string`` and ``classify_file``;
                    # the tool had previously drifted to plural / "_git" names.
                    # Rename for parity, the tested names are also more intuitive.
                    "enum": ["classify_string", "classify_file"],
                    "description": "Classification mode",
                    "default": "classify_string",
                },
                "old_source": {
                    "type": "string",
                    "description": "Old source code string (for classify_string mode)",
                },
                "new_source": {
                    "type": "string",
                    "description": "New source code string (for classify_string mode)",
                },
                "language": {
                    "type": "string",
                    "description": "Language for classify_string mode (auto-detected for classify_file)",
                },
                "file_path": {
                    "type": "string",
                    "description": "File path (for classify_file mode or as context for classify_string)",
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
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format",
                    "default": "toon",
                },
                # #528 — byte-budget params (opt-in, never required)
                "include_ast_nodes": {
                    "type": "boolean",
                    "description": (
                        "Include full AST node details (hunk.old/new) in each classification. "
                        "Off by default to keep response ≤ raw diff size. "
                        "Enable only when you need to inspect exact AST change structure."
                    ),
                    "default": False,
                },
                "hunk_cap": {
                    "type": "integer",
                    "description": (
                        "Maximum number of classification entries to return. "
                        "Default 50. When the limit is hit, truncated/listed_cap/next_step "
                        "honesty fields are added to the response."
                    ),
                    "default": 50,
                },
            },
            # Wave 1b (audit edit-10): ``mode`` is resolved at runtime
            # (_resolve_mode defaults to classify_file when a file_path is
            # given), so it is NOT required. Declaring it required made strict
            # MCP clients reject a valid ``{file_path: X}`` call before dispatch.
            "required": [],
            "additionalProperties": False,
        }

    @staticmethod
    def _resolve_mode(arguments: dict[str, Any]) -> str:
        """Effective mode.

        Wave 1b (audit edit-10): the facade advertises ``classify`` as taking a
        ``file_path``, but the default mode was ``classify_string`` (which needs
        ``old_source``/``new_source``), so ``classify file_path=X`` failed with
        "old_source and new_source are required". When no mode is given, default
        to ``classify_file`` if a ``file_path`` was supplied (and not an explicit
        old/new string pair), else the string-diff default.
        """
        mode = arguments.get("mode")
        if mode:
            return str(mode)
        has_string_pair = bool(arguments.get("old_source")) and bool(
            arguments.get("new_source")
        )
        if arguments.get("file_path") and not has_string_pair:
            return "classify_file"
        return "classify_string"

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = self._resolve_mode(arguments)
        if mode == "classify_string":
            if (
                arguments.get("old_source") is None
                or arguments.get("new_source") is None
            ):
                raise ValueError(
                    "old_source and new_source are required for classify_string mode"
                )
            if not arguments.get("language"):
                raise ValueError("language is required for classify_string mode")
        elif mode == "classify_file":
            if not arguments.get("file_path"):
                raise ValueError("file_path is required for classify_file mode")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        mode = self._resolve_mode(arguments)
        output_format = arguments.get("output_format", "toon")
        differ = self._get_differ()

        if mode == "classify_string":
            diff_result = differ.diff_strings(
                old_source=arguments["old_source"],
                new_source=arguments["new_source"],
                language=arguments["language"],
            )
            file_path = arguments.get("file_path")
        elif mode == "classify_file":
            file_path = arguments["file_path"]
            diff_result = self._diff_git(differ, arguments)
        else:
            raise ValueError(f"Unknown mode: {mode}")

        classifier = SemanticChangeClassifier(file_path=file_path)
        classification = classifier.classify(diff_result)
        # Always deserialize with children so _compact_classification can
        # strip them (default) or keep them (include_ast_nodes=True).
        class_dict = classification.to_dict(include_children=True)

        # Map risk_level to canonical verdict vocabulary (pain-01 tsa-landing
        # contract). NOT_FOUND when there are zero classifications (identical
        # sources) so agents skip downstream change-impact tools.
        classifications = class_dict.get("classifications") or []
        risk_level = class_dict.get("risk_level", "medium")
        if not classifications:
            verdict = "NOT_FOUND"
        elif risk_level == "high":
            verdict = "CAUTION"
        elif risk_level == "medium":
            verdict = "REVIEW"
        else:
            verdict = "INFO"

        include_ast_nodes = bool(arguments.get("include_ast_nodes", False))
        hunk_cap = int(arguments.get("hunk_cap", 50))

        # #528 — build a compact summary list by default; full AST nodes opt-in.
        # ClassifiedHunk.to_dict() inlines the full ASTDiffHunk which carries
        # recursive ASTNodeInfo children — up to 267 nodes per hunk on large files.
        # Strip children (and optionally the entire hunk) unless opted in.
        all_classifications = class_dict.get("classifications", [])
        compact_classifications = [
            _compact_classification(c, include_ast_nodes=include_ast_nodes)
            for c in all_classifications
        ]

        truncated = len(compact_classifications) > hunk_cap
        listed = compact_classifications[:hunk_cap]

        # change_count is part of the agent-contract shape: a scalar that
        # downstream tools can branch on without walking the classifications
        # list. Tests pin this name (pain pass 2).
        response: dict[str, Any] = {
            "success": True,
            "file_path": file_path,
            "diff_hunks": len(diff_result.hunks),
            "change_count": len(all_classifications),
            "verdict": verdict,
            # Scalar summary fields from SemanticClassification (no bulk lists)
            "dominant_category": class_dict.get("dominant_category"),
            "dominant_label": class_dict.get("dominant_label"),
            "risk_level": class_dict.get("risk_level"),
            "change_summary": class_dict.get("change_summary"),
            "category_counts": class_dict.get("category_counts"),
            "classifications": listed,
        }

        if truncated:
            response["truncated"] = True
            response["listed_cap"] = hunk_cap
            response["next_step"] = (
                f"Response capped at {hunk_cap} classifications. "
                f"Use hunk_cap={hunk_cap * 2} to see more, or filter by category."
            )

        return apply_toon_format_to_response(response, output_format)

    def _diff_git(self, differ: ASTDiffer, arguments: dict[str, Any]) -> Any:
        import subprocess

        file_path = arguments["file_path"]
        old_ref = arguments.get("old_ref", "HEAD~1")
        new_ref = arguments.get("new_ref", "HEAD")

        language = arguments.get("language") or _language_from_ext(file_path) or ""

        try:
            old_result = subprocess.run(  # nosec B603,B607
                ["git", "show", f"{old_ref}:{file_path}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
            old_source = old_result.stdout if old_result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            old_source = ""

        try:
            new_result = subprocess.run(  # nosec B603,B607
                ["git", "show", f"{new_ref}:{file_path}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
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
