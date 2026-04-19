"""MCP tool for change impact analysis — answers 'what breaks if I change X?'."""
from __future__ import annotations

from typing import Any

from tree_sitter_analyzer.analysis.change_impact import ChangeImpactAnalyzer
from tree_sitter_analyzer.mcp.tools.base_tool import BaseMCPTool
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)


class ChangeImpactTool(BaseMCPTool):
    """Analyze the blast radius of file changes — impacted files, tools, and tests."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "change_impact",
            "description": (
                "Analyze the blast radius of file changes across the project.\n\n"
                "Given a list of changed files, reports:\n"
                "- Direct and transitive import dependents\n"
                "- MCP tools that depend on the changed code\n"
                "- Test files that cover the affected code\n\n"
                "WHEN TO USE:\n"
                "- Before refactoring: understand what will be affected\n"
                "- Before deleting code: check if anything depends on it\n"
                "- After CI failure: trace which changes caused the break\n\n"
                "WHEN NOT TO USE:\n"
                "- Simple grep/search — use search_content instead\n"
                "- Single-file analysis — use individual code quality tools"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of project-relative file paths to analyze",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["text", "json"],
                        "default": "text",
                        "description": "Output format",
                    },
                },
                "required": ["files"],
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        files: list[str] = arguments.get("files", [])
        fmt: str = arguments.get("format", "text")

        if not files:
            return {"type": "text", "text": "No files specified."}

        if not self.project_root:
            return {"type": "text", "text": "Error: project_root not set."}

        analyzer = ChangeImpactAnalyzer(self.project_root)
        result = analyzer.analyze(list(files))

        if fmt == "json":
            return {"type": "text", "text": self._format_json(result)}

        return {"type": "text", "text": self._format_text(result)}

    def _format_text(self, result: Any) -> str:
        lines: list[str] = []
        lines.append(f"Change Impact Analysis: {len(result.changed_files)} file(s)")
        lines.append("=" * 50)

        for f in result.changed_files:
            lines.append(f"  Changed: {f}")

        if result.impacted:
            lines.append(f"\nImpacted files ({result.total_impact_count} total):")
            direct = [i for i in result.impacted if i.distance == 1]
            transitive = [i for i in result.impacted if i.distance > 1]
            if direct:
                lines.append(f"  Direct ({len(direct)}):")
                for item in direct:
                    lines.append(f"    - {item.path}")
            if transitive:
                lines.append(f"  Transitive ({len(transitive)}):")
                for item in transitive:
                    lines.append(f"    - {item.path} (distance={item.distance})")
        else:
            lines.append("\nNo impacted files.")

        if result.affected_tools:
            lines.append(f"\nAffected MCP tools ({len(result.affected_tools)}):")
            for tool in result.affected_tools:
                lines.append(f"  - {tool}")

        if result.affected_tests:
            lines.append(f"\nAffected tests ({len(result.affected_tests)}):")
            for test in result.affected_tests:
                lines.append(f"  - {test}")

        lines.append(f"\nTotal blast radius: {result.total_impact_count}")
        return "\n".join(lines)

    def _format_json(self, result: Any) -> str:
        import json

        data = {
            "changed_files": list(result.changed_files),
            "impacted": [
                {"path": i.path, "relation": i.relation, "distance": i.distance}
                for i in result.impacted
            ],
            "affected_tools": list(result.affected_tools),
            "affected_tests": list(result.affected_tests),
            "total_impact_count": result.total_impact_count,
        }
        return json.dumps(data, indent=2, ensure_ascii=False)
