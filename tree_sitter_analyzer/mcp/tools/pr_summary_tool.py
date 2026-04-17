#!/usr/bin/env python3
"""
Pull Request Summary Tool

Generates structured PR descriptions from git diff and code analysis.
"""

from subprocess import CalledProcessError, check_output
from typing import Any

from ...pr_summary import (
    CategorizedChange,
    ChangeCategory,
    ChangeClassifier,
    ChangeType,
    DiffParser,
    DiffSummary,
    FileChange,
    PRType,
    SemanticAnalyzer,
    SemanticChange,
)
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class PRSummaryTool(BaseMCPTool):
    """MCP tool for generating pull request summaries."""

    def __init__(self, project_root: str | None = None):
        """
        Initialize the PR summary tool.

        Args:
            project_root: Optional project root directory
        """
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        """Get MCP tool definition."""
        return {
            "name": "pr_summary",
            "description": (
                "Generate structured PR descriptions from git diff.\n\n"
                "WHEN TO USE:\n"
                "- Create PR descriptions from code changes\n"
                "- Summarize pull request impact\n"
                "- Detect breaking changes automatically\n"
                "- Categorize changes by type (feature, bugfix, refactor, etc.)\n\n"
                "RETURNS:\n"
                "- PR type (feature, bugfix, refactor, docs, test, chore)\n"
                "- File changes summary (added, modified, deleted)\n"
                "- Change categories with file lists\n"
                "- Breaking change detection\n"
                "- Semantic analysis results\n\n"
                "EXAMPLE:\n"
                '  Generate PR summary: {"base": "main", "format": "markdown"}'
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "base": {
                        "type": "string",
                        "description": "Base branch to compare against (e.g., 'main', 'develop')",
                        "default": "main",
                    },
                    "head": {
                        "type": "string",
                        "description": "Head branch (default: current branch)",
                    },
                    "diff_input": {
                        "type": "string",
                        "description": "Raw git diff output (use instead of base/head)",
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["markdown", "json", "toon"],
                        "description": "Output format (default: markdown)",
                    },
                    "semantic_analysis": {
                        "type": "boolean",
                        "description": "Enable semantic code analysis (default: true)",
                        "default": True,
                    },
                },
            },
        }

    def _get_git_diff(self, base: str, head: str | None = None) -> str:
        """
        Get git diff between branches.

        Args:
            base: Base branch
            head: Head branch (None for current branch)

        Returns:
            Git diff output
        """
        try:
            if head:
                cmd = ["git", "diff", f"{base}...{head}"]
            else:
                # Diff against base branch
                cmd = ["git", "diff", f"{base}..."]

            result = check_output(cmd, cwd=self.project_root, text=True)
            return result
        except CalledProcessError as e:
            logger.error(f"Git diff failed: {e}")
            raise ValueError(f"Failed to get git diff: {e}") from e

    def _get_current_branch(self) -> str:
        """Get current git branch name."""
        try:
            result = check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.project_root,
                text=True,
            ).strip()
            return result
        except CalledProcessError as e:
            logger.warning(f"Failed to get current branch: {e}")
            return "HEAD"

    def _categorize_changes(
        self, diff_summary: DiffSummary
    ) -> list[CategorizedChange]:
        """
        Categorize file changes by type.

        Args:
            diff_summary: DiffSummary with file changes

        Returns:
            List of categorized changes
        """
        classifier = ChangeClassifier()
        return classifier.classify_changes(diff_summary)

    def _analyze_semantic_changes(
        self, file_changes: list[FileChange]
    ) -> list[SemanticChange]:
        """
        Analyze semantic changes in code.

        Args:
            file_changes: List of file changes

        Returns:
            List of semantic changes
        """
        analyzer = SemanticAnalyzer()
        semantic_changes: list[SemanticChange] = []

        for file_change in file_changes:
            if file_change.change_type not in (ChangeType.ADDED, ChangeType.MODIFIED):
                continue

            try:
                result = analyzer.analyze_diff(file_change)
                semantic_changes.extend(result.changes)
            except Exception as e:
                logger.debug(f"Semantic analysis failed for {file_change.path}: {e}")

        return semantic_changes

    def _detect_breaking_changes(
        self, semantic_changes: list[SemanticChange]
    ) -> list[SemanticChange]:
        """
        Filter breaking changes from semantic analysis.

        Args:
            semantic_changes: List of semantic changes

        Returns:
            List of breaking changes
        """
        return [c for c in semantic_changes if c.is_breaking]

    def _format_markdown(
        self,
        diff_summary: DiffSummary,
        categorized: list[CategorizedChange],
        semantic_changes: list[SemanticChange],
        breaking: list[SemanticChange],
        pr_type: PRType,
    ) -> str:
        """Format PR summary as markdown."""
        lines = [
            "## Pull Request Summary",
            "",
            f"**Type:** {pr_type.primary_category.value}",
            "",
            "### 📊 Changes Overview",
            f"- **Files changed:** {diff_summary.total_files_changed}",
            f"- **Lines added:** {diff_summary.total_additions}",
            f"- **Lines deleted:** {diff_summary.total_deletions}",
            f"- **Net change:** {diff_summary.net_lines:+} lines",
            "",
        ]

        # Categorized changes
        if categorized:
            lines.append("### 📁 Changes by Category")
            lines.append("")

            for category in ChangeCategory:
                category_files = [
                    c.file_change.path for c in categorized if c.category == category
                ]
                if category_files:
                    emoji = {
                        ChangeCategory.FEATURE: "✨",
                        ChangeCategory.BUGFIX: "🐛",
                        ChangeCategory.REFACTOR: "♻️",
                        ChangeCategory.DOCS: "📝",
                        ChangeCategory.TEST: "🧪",
                        ChangeCategory.CHORE: "🔧",
                        ChangeCategory.PERF: "⚡",
                        ChangeCategory.STYLE: "🎨",
                        ChangeCategory.CI: "🔧",
                        ChangeCategory.BUILD: "🏗️",
                    }.get(category, "•")

                    lines.append(f"#### {emoji} {category.value.title()}")
                    for file_path in category_files:
                        # Find the corresponding categorized change
                        cat = next(
                            (c for c in categorized if c.file_change.path == file_path),
                            None,
                        )
                        if cat:
                            change_icon = {
                                "added": "➕",
                                "modified": "📝",
                                "deleted": "➖",
                            }.get(cat.file_change.change_type.value, "•")
                            lines.append(f"- {change_icon} `{file_path}`")
                    lines.append("")

        # Breaking changes
        if breaking:
            lines.append("### ⚠️ Breaking Changes")
            lines.append("")
            for change in breaking:
                lines.append(f"- `{change.change_type.value}` `{change.name}`")
                if change.description:
                    lines.append(f"  - {change.description}")
            lines.append("")

        # Semantic changes (non-breaking)
        other_semantic = [c for c in semantic_changes if not c.is_breaking]
        if other_semantic:
            lines.append("### 🔍 Semantic Changes")
            lines.append("")
            for change in other_semantic[:20]:  # Limit to 20
                lines.append(f"- {change.change_type.value}: `{change.name}`")
            if len(other_semantic) > 20:
                lines.append(f"- ... and {len(other_semantic) - 20} more")
            lines.append("")

        return "\n".join(lines)

    def _format_json(
        self,
        diff_summary: DiffSummary,
        categorized: list[CategorizedChange],
        semantic_changes: list[SemanticChange],
        breaking: list[SemanticChange],
        pr_type: PRType,
    ) -> dict[str, Any]:
        """Format PR summary as JSON."""
        return {
            "pr_type": pr_type.primary_category.value,
            "summary": {
                "files_changed": diff_summary.total_files_changed,
                "lines_added": diff_summary.total_additions,
                "lines_deleted": diff_summary.total_deletions,
                "net_lines": diff_summary.net_lines,
            },
            "categories": [
                {
                    "category": cat.category.value,
                    "file_path": cat.file_change.path,
                    "change_type": cat.file_change.change_type.value,
                    "confidence": cat.confidence,
                }
                for cat in categorized
            ],
            "semantic_changes": [
                {
                    "change_type": sc.change_type.value,
                    "name": sc.name,
                    "file_path": sc.file_path,
                    "is_breaking": sc.is_breaking,
                    "description": sc.description,
                }
                for sc in semantic_changes
            ],
            "breaking_changes": [
                {
                    "change_type": bc.change_type.value,
                    "name": bc.name,
                    "file_path": bc.file_path,
                    "description": bc.description,
                }
                for bc in breaking
            ],
        }

    def _format_toon(
        self,
        diff_summary: DiffSummary,
        categorized: list[CategorizedChange],
        semantic_changes: list[SemanticChange],
        breaking: list[SemanticChange],
        pr_type: PRType,
    ) -> str:
        """Format PR summary as TOON."""
        lines = [
            "📋 Pull Request Summary",
            f"   Type: {pr_type.primary_category.value}",
            "",
            "📊 Changes Overview:",
            f"   Files changed: {diff_summary.total_files_changed}",
            f"   Lines added: {diff_summary.total_additions}",
            f"   Lines deleted: {diff_summary.total_deletions}",
            f"   Net change: {diff_summary.net_lines:+}",
            "",
        ]

        # Category summary
        for category in ChangeCategory:
            count = sum(1 for c in categorized if c.category == category)
            if count:
                emoji = {
                    ChangeCategory.FEATURE: "✨",
                    ChangeCategory.BUGFIX: "🐛",
                    ChangeCategory.REFACTOR: "♻️",
                    ChangeCategory.DOCS: "📝",
                    ChangeCategory.TEST: "🧪",
                    ChangeCategory.CHORE: "🔧",
                    ChangeCategory.PERF: "⚡",
                    ChangeCategory.STYLE: "🎨",
                    ChangeCategory.CI: "🔧",
                    ChangeCategory.BUILD: "🏗️",
                }.get(category, "•")
                lines.append(f"   {emoji} {category.value.title()}: {count}")

        lines.append("")

        # Breaking changes
        if breaking:
            lines.append(f"⚠️ Breaking Changes: {len(breaking)}")
            for change in breaking[:5]:
                lines.append(f"   - {change.change_type.value} '{change.name}'")

        return "\n".join(lines)

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the PR summary tool.

        Args:
            arguments: Tool arguments

        Returns:
            Dictionary with PR summary
        """
        # Get diff input
        diff_input = arguments.get("diff_input", "")
        base = arguments.get("base", "main")
        head = arguments.get("head")
        output_format = arguments.get("output_format", "markdown")
        semantic_analysis = arguments.get("semantic_analysis", True)

        # Get git diff if not provided
        if not diff_input:
            if head is None:
                head = self._get_current_branch()
            diff_input = self._get_git_diff(base, head)

        # Parse diff
        parser = DiffParser()
        diff_summary = parser.parse_diff(diff_input)

        # Categorize changes
        categorized = self._categorize_changes(diff_summary)

        # Determine PR type
        classifier = ChangeClassifier()
        pr_type = classifier.determine_pr_type(categorized)

        # Semantic analysis
        semantic_changes: list[SemanticChange] = []
        breaking: list[SemanticChange] = []

        if semantic_analysis:
            try:
                semantic_changes = self._analyze_semantic_changes(diff_summary.files)
                breaking = self._detect_breaking_changes(semantic_changes)
            except Exception as e:
                logger.warning(f"Semantic analysis failed: {e}")

        # Format output
        if output_format == "json":
            return {"result": self._format_json(
                diff_summary, categorized, semantic_changes, breaking, pr_type
            )}

        if output_format == "toon":
            return {
                "content": [
                    {
                        "type": "text",
                        "text": self._format_toon(
                            diff_summary, categorized, semantic_changes, breaking, pr_type
                        ),
                    }
                ]
            }

        # Default: markdown
        return {
            "content": [
                {
                    "type": "text",
                    "text": self._format_markdown(
                        diff_summary, categorized, semantic_changes, breaking, pr_type
                    ),
                }
            ]
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """
        Validate tool arguments.

        Args:
            arguments: Arguments to validate

        Returns:
            True if valid

        Raises:
            ValueError: If arguments are invalid
        """
        output_format = arguments.get("output_format", "markdown")
        if output_format not in ("markdown", "json", "toon"):
            raise ValueError(
                f"Invalid output_format: {output_format}. "
                "Must be 'markdown', 'json', or 'toon'"
            )

        return True
