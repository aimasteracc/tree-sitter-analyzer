"""Doc-Sync MCP Tool — detect stale file-path references in documentation."""

from typing import Any

from ...doc_sync import run_doc_sync
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class DocSyncTool(BaseMCPTool):
    """MCP Tool: check documentation files for stale file-path references."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "doc_sync",
            "description": (
                "Scan markdown documentation for stale file-path references — "
                "backtick spans and link targets that point to files that no "
                "longer exist in the project. Returns each stale reference with "
                "the doc file path, line number, and missing target path. "
                "Unique to TSA: uses the live project tree to validate every "
                "documentation pointer, surfacing doc drift before it misleads "
                "users or AI agents."
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
                "doc_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Glob patterns (relative to project root) for markdown "
                        "files to scan. Defaults to "
                        '["docs/**/*.md", "README.md", "CHANGELOG.md"].'
                    ),
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json"],
                    "default": "json",
                    "description": "Output format: JSON.",
                },
            },
            "required": [],
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        patterns = arguments.get("doc_patterns")
        if patterns is not None and not isinstance(patterns, list):
            raise ValueError("doc_patterns must be a list of strings")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        project_root = str(self.project_root)
        doc_patterns = arguments.get("doc_patterns") or None

        result = run_doc_sync(project_root, doc_patterns=doc_patterns)

        # #577: inject verdict + agent_summary so the envelope is uniform.
        # verdict=SAFE when no stale refs; REVIEW when stale refs found
        # (agent should fix broken doc pointers before confusing future readers).
        stale_count: int = result.get("stale_count", 0)
        verdict = "SAFE" if stale_count == 0 else "REVIEW"
        docs_scanned: int = result.get("docs_scanned", 0)
        total_refs: int = result.get("total_refs_checked", 0)
        summary_line = (
            f"doc_sync: {docs_scanned} doc(s) scanned, "
            f"{total_refs} ref(s) checked, {stale_count} stale"
        )
        if stale_count == 0:
            next_step = "Documentation is in sync — no stale file references found."
        else:
            next_step = (
                f"{stale_count} stale reference(s) found. "
                "Update or remove the broken links listed in stale_refs."
            )
        agent_summary = {
            "summary_line": summary_line,
            "verdict": verdict,
            "next_step": next_step,
        }

        # Build the canonical envelope that both paths share.
        envelope: dict[str, Any] = {
            **result,
            "verdict": verdict,
            "agent_summary": agent_summary,
        }

        return envelope
