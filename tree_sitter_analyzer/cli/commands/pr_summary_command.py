#!/usr/bin/env python3
"""
Pull Request Summary CLI

Generates structured PR descriptions from git diff and code analysis.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from ...output_manager import output_data, output_error, output_info, set_output_mode
from ...pr_summary import (
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
from ...project_detector import detect_project_root
from ...utils import setup_logger

logger = setup_logger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    """Build argument parser for PR summary CLI."""
    parser = argparse.ArgumentParser(
        description="Generate pull request summaries from git diff.",
        epilog="""
Examples:
  # Generate PR summary comparing to main branch
  %(prog)s --base main

  # Generate PR summary with custom branches
  %(prog)s --base develop --head feature/new-auth

  # Generate summary from existing diff file
  %(prog)s --diff-file changes.diff

  # Output in different formats
  %(prog)s --base main --format json
  %(prog)s --base main --format toon

  # Disable semantic analysis (faster)
  %(prog)s --base main --no-semantic-analysis
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--base",
        default="main",
        help="Base branch to compare against (default: main)",
    )

    parser.add_argument(
        "--head",
        help="Head branch (default: current branch)",
    )

    parser.add_argument(
        "--diff-file",
        help="Read diff from file instead of git",
    )

    parser.add_argument(
        "--diff-input",
        help="Raw git diff output (use instead of base/head/diff-file)",
    )

    parser.add_argument(
        "--format",
        choices=["markdown", "json", "toon"],
        default="markdown",
        help="Output format (default: markdown)",
    )

    parser.add_argument(
        "--project-root",
        help="Project root directory (auto-detected if omitted)",
    )

    parser.add_argument(
        "--no-semantic-analysis",
        action="store_true",
        help="Disable semantic code analysis (faster, less detailed)",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress non-essential output",
    )

    return parser


def _get_git_diff(base: str, head: str | None, project_root: str) -> str:
    """Get git diff between branches."""
    from subprocess import CalledProcessError, check_output

    try:
        if head:
            cmd = ["git", "diff", f"{base}...{head}"]
        else:
            cmd = ["git", "diff", f"{base}..."]

        result = check_output(cmd, cwd=project_root, text=True)
        return result
    except CalledProcessError as e:
        output_error(f"Failed to get git diff: {e}")
        sys.exit(1)
    except FileNotFoundError:
        output_error("Git not found. Please install git or use --diff-file option.")
        sys.exit(1)


def _get_current_branch(project_root: str) -> str:
    """Get current git branch name."""
    from subprocess import CalledProcessError, check_output

    try:
        result = check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=project_root,
            text=True,
        ).strip()
        return result
    except CalledProcessError:
        return "HEAD"


def _categorize_changes(
    diff_summary: DiffSummary,
) -> list[tuple[FileChange, ChangeCategory]]:
    """Categorize file changes by type."""
    classifier = ChangeClassifier()
    categorized = classifier.classify_changes(diff_summary)

    # Map back to file changes for output
    return [(cat.file_change, cat.category) for cat in categorized]


def _analyze_semantic_changes(
    file_changes: list[FileChange], project_root: str
) -> list[SemanticChange]:
    """Analyze semantic changes in code."""
    analyzer = SemanticAnalyzer()
    semantic_changes: list[SemanticChange] = []

    for file_change in file_changes:
        if file_change.change_type not in (ChangeType.ADDED, ChangeType.MODIFIED):
            continue

        try:
            result = analyzer.analyze_diff(file_change)
            semantic_changes.extend(result.changes)
        except Exception as e:
            if not getattr(_analyze_semantic_changes, "quiet", False):
                output_info(f"Semantic analysis failed for {file_change.path}: {e}")

    return semantic_changes


def _detect_breaking_changes(
    semantic_changes: list[SemanticChange],
) -> list[SemanticChange]:
    """Filter breaking changes from semantic analysis."""
    return [c for c in semantic_changes if c.is_breaking]


def _format_markdown(
    diff_summary: DiffSummary,
    categorized: list[tuple[FileChange, ChangeCategory]],
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

    # Group by category
    category_map: dict[ChangeCategory, list[tuple[FileChange, ChangeCategory]]] = {
        cat: [] for cat in ChangeCategory
    }
    for item in categorized:
        category_map[item[1]].append(item)

    # Categorized changes
    for category in ChangeCategory:
        items = category_map[category]
        if items:
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
            for file_change, _ in items:
                change_icon = {
                    "added": "➕",
                    "modified": "📝",
                    "deleted": "➖",
                }.get(file_change.change_type.value, "•")
                lines.append(f"- {change_icon} `{file_change.path}`")
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

    # Semantic changes (non-breaking, limited)
    other_semantic = [c for c in semantic_changes if not c.is_breaking]
    if other_semantic:
        lines.append("### 🔍 Semantic Changes")
        lines.append("")
        for change in other_semantic[:20]:
            lines.append(f"- {change.change_type.value}: `{change.name}`")
        if len(other_semantic) > 20:
            lines.append(f"- ... and {len(other_semantic) - 20} more")
        lines.append("")

    return "\n".join(lines)


def _format_json(
    diff_summary: DiffSummary,
    categorized: list[tuple[FileChange, ChangeCategory]],
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
                "category": cat.value,
                "file_path": fc.path,
                "change_type": fc.change_type.value,
            }
            for fc, cat in categorized
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
    diff_summary: DiffSummary,
    categorized: list[tuple[FileChange, ChangeCategory]],
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
    category_counts: dict[ChangeCategory, int] = dict.fromkeys(ChangeCategory, 0)
    for _, cat in categorized:
        category_counts[cat] += 1

    for category in ChangeCategory:
        count = category_counts[category]
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


async def _run(args: argparse.Namespace) -> int:
    """Run the PR summary generation."""
    set_output_mode(quiet=bool(args.quiet), json_output=(args.format == "json"))

    project_root = str(detect_project_root(None, args.project_root))

    # Get diff input
    if args.diff_input:
        diff_input = args.diff_input
    elif args.diff_file:
        try:
            with open(args.diff_file) as f:
                diff_input = f.read()
        except FileNotFoundError:
            output_error(f"Diff file not found: {args.diff_file}")
            return 1
    else:
        head = args.head or _get_current_branch(project_root)
        if not args.quiet:
            output_info(f"Comparing {args.base}...{head}")

        diff_input = _get_git_diff(args.base, head, project_root)

    if not diff_input.strip():
        output_error("No diff found. Branches may be identical.")
        return 1

    # Parse diff
    parser = DiffParser()
    diff_summary = parser.parse_diff(diff_input)

    if not diff_summary.files:
        output_error("No file changes found in diff.")
        return 1

    # Categorize changes
    categorized = _categorize_changes(diff_summary)

    # Determine PR type
    classifier = ChangeClassifier()
    # Convert to CategorizedChange objects
    from tree_sitter_analyzer.pr_summary.change_classifier import (
        CategorizedChange as CC,
    )

    categorized_changes = [
        CC(
            file_change=fc,
            category=cat,
            confidence=0.8,
            reason=f"File in {cat.value} category",
        )
        for fc, cat in categorized
    ]
    pr_type = classifier.determine_pr_type(categorized_changes)

    # Semantic analysis
    semantic_changes: list[SemanticChange] = []
    breaking: list[SemanticChange] = []

    if not args.no_semantic_analysis:
        if not args.quiet:
            output_info("Running semantic analysis...")

        # Store quiet flag for the nested function
        _analyze_semantic_changes.quiet = args.quiet  # type: ignore[attr-defined]

        try:
            semantic_changes = _analyze_semantic_changes(diff_summary.files, project_root)
            breaking = _detect_breaking_changes(semantic_changes)
        except Exception as e:
            if not args.quiet:
                output_info(f"Semantic analysis failed: {e}")

    # Format output
    output: dict[str, Any] | str
    if args.format == "json":
        output = _format_json(
            diff_summary, categorized, semantic_changes, breaking, pr_type
        )
    elif args.format == "toon":
        output = _format_toon(
            diff_summary, categorized, semantic_changes, breaking, pr_type
        )
    else:  # markdown
        output = _format_markdown(
            diff_summary, categorized, semantic_changes, breaking, pr_type
        )

    output_data(output)
    return 0


def main() -> int:
    """Entry point for PR summary CLI."""
    parser = _build_parser()
    args = parser.parse_args()

    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
