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
                    "enum": ["toon", "json"],
                    "default": "toon",
                    "description": "Output format (default: toon for token efficiency).",
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
        output_format = arguments.get("output_format", "toon")

        result = run_doc_sync(project_root, doc_patterns=doc_patterns)

        if output_format == "toon":
            return {"format": "toon", "toon_content": self._to_toon(result)}
        return result

    @staticmethod
    def _to_toon(result: dict[str, Any]) -> str:
        lines: list[str] = []
        lines.append("doc_sync:")
        lines.append(f"  success: {result['success']}")
        lines.append(f"  docs_scanned: {result['docs_scanned']}")
        lines.append(f"  total_refs_checked: {result['total_refs_checked']}")
        lines.append(f"  stale_count: {result['stale_count']}")
        stale = result.get("stale_refs", [])
        if stale:
            lines.append("  stale_refs:")
            for s in stale:
                lines.append(f"    - doc_file: {s['doc_file']}")
                lines.append(f"      line: {s['line']}")
                lines.append(f"      missing_path: {s['path']}")
                lines.append(f"      reason: {s['reason']}")
        else:
            lines.append("  stale_refs: []")
        return "\n".join(lines)
