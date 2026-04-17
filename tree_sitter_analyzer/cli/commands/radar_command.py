#!/usr/bin/env python3
"""
Standalone CLI for project radar analysis.

Provides unified project health view showing:
- Riskiest files (complexity × churn × impact)
- Code ownership (top contributor per file)
- File churn metrics (commit frequency)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ...analyzer.git_analyzer import GitAnalyzer
from ...analyzer.risk_scoring import FileRisk, RiskCalculator
from ...output_manager import output_data, output_error, output_info, set_output_mode


def _build_parser() -> argparse.ArgumentParser:
    """Build argument parser for project radar CLI."""
    parser = argparse.ArgumentParser(
        description="Project radar: unified view of risky files, ownership, and churn.",
        epilog="""
Examples:
  # Show top 20 riskiest files
  %(prog)s

  # Show top 10 riskiest files
  %(prog)s --top 10

  # Filter by file extension
  %(prog)s --extension .py

  # Set time window for churn analysis
  %(prog)s --since "3 months ago"

  # Custom output format
  %(prog)s --format json
  %(prog)s --format toon
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Number of riskiest files to show (default: 20)",
    )

    parser.add_argument(
        "--since",
        default="6 months ago",
        help="Time window for churn analysis (default: '6 months ago')",
    )

    parser.add_argument(
        "--extension",
        help="Filter by file extension (e.g., '.py', '.js')",
    )

    parser.add_argument(
        "--format",
        choices=["text", "json", "toon"],
        default="text",
        help="Output format: 'text' (default), 'json', or 'toon'",
    )

    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root directory (default: current directory)",
    )

    parser.add_argument(
        "--weights",
        nargs=3,
        metavar=("COMPLEXITY", "CHURN", "IMPACT"),
        type=float,
        default=None,
        help="Custom weights for risk calculation (default: 0.3 0.3 0.4)",
    )

    return parser


def format_text_output(risks: list[FileRisk], top_n: int) -> str:
    """Format risks as human-readable text table.

    Args:
        risks: List of FileRisk objects (pre-sorted).
        top_n: Number of files to display.

    Returns:
        Formatted text output.
    """
    lines: list[str] = []
    lines.append("=" * 120)
    lines.append(f"PROJECT RADAR — Top {top_n} Riskiest Files")
    lines.append("=" * 120)
    lines.append("")

    for i, risk in enumerate(risks[:top_n], 1):
        lines.append(f"{i}. {risk.path}")
        lines.append(f"   Overall Risk: {risk.overall_risk:.2f} " + _risk_bar(risk.overall_risk))
        lines.append(f"   Complexity:  {risk.complexity_score:.2f} | " +
                     f"Churn: {risk.churn_score:.2f} | " +
                     f"Impact: {risk.impact_score:.2f}")

        if risk.churn:
            churn = risk.churn
            lines.append(f"   Churn: {churn.commit_count} commits")
            if churn.authors:
                top_author, count = churn.authors[0]
                lines.append(f"   Top Author: {top_author} ({count} commits)")

        if risk.ownership:
            owner = risk.ownership
            lines.append(f"   Owner: {owner.top_contributor} " +
                         f"({owner.ownership_percentage:.1f}% ownership)")

        lines.append("")

    return "\n".join(lines)


def _risk_bar(score: float) -> str:
    """Create visual risk bar.

    Args:
        score: Risk score 0-1.

    Returns:
        Visual bar string.
    """
    filled = int(score * 20)
    bar = "█" * filled + "░" * (20 - filled)
    return f"[{bar}]"


def format_json_output(risks: list[FileRisk]) -> str:
    """Format risks as JSON.

    Args:
        risks: List of FileRisk objects.

    Returns:
        JSON string.
    """
    import json

    data: list[dict[str, object]] = []
    for risk in risks:
        item: dict[str, object] = {
            "path": risk.path,
            "overall_risk": risk.overall_risk,
            "complexity_score": risk.complexity_score,
            "churn_score": risk.churn_score,
            "impact_score": risk.impact_score,
        }

        if risk.churn:
            item["churn"] = {
                "commit_count": risk.churn.commit_count,
                "authors": risk.churn.authors,
            }

        if risk.ownership:
            item["ownership"] = {
                "top_contributor": risk.ownership.top_contributor,
                "ownership_percentage": risk.ownership.ownership_percentage,
            }

        data.append(item)

    return json.dumps(data, indent=2)


def format_toon_output(risks: list[FileRisk]) -> str:
    """Format risks as TOON (Tree-sitter Object Notation).

    Args:
        risks: List of FileRisk objects.

    Returns:
        TOON string.
    """
    from ...formatters.toon_encoder import ToonEncoder

    encoder = ToonEncoder()

    data: list[dict[str, object]] = []
    for risk in risks:
        item: dict[str, object] = {
            "path": risk.path,
            "risk": risk.overall_risk,
            "complexity": risk.complexity_score,
            "churn": risk.churn_score,
            "impact": risk.impact_score,
        }
        data.append(item)

    return encoder.encode({"project_radar": data})


def main() -> int:
    """Run the project radar CLI.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    parser = _build_parser()
    args = parser.parse_args()

    # Set output mode
    set_output_mode(json_output=(args.format == "json"))

    # Parse custom weights if provided
    weights: dict[str, float] | None = None
    if args.weights:
        c, ch, i = args.weights
        total = c + ch + i
        if abs(total - 1.0) > 0.01:
            output_error(f"Weights must sum to 1.0, got {total}")
            return 1
        weights = {"complexity": c, "churn": ch, "impact": i}

    project_root = Path(args.project_root).resolve()

    # Initialize git analyzer
    try:
        git_analyzer = GitAnalyzer(project_root)
    except ValueError as e:
        output_error(str(e))
        return 1

    output_info("Analyzing project...")

    # Collect data
    churn_data = git_analyzer.get_file_churn(since=args.since, extension=args.extension)
    ownership_data = git_analyzer.get_file_ownership(since=args.since)

    # For MVP, use placeholder complexity/impact scores
    # In real implementation, these would come from the actual analysis modules
    all_files = set(churn_data.keys()) | set(ownership_data.keys())
    complexity_scores: dict[str, float] = dict.fromkeys(all_files, 50.0)  # Placeholder
    impact_scores: dict[str, float] = dict.fromkeys(all_files, 50.0)  # Placeholder

    # Calculate risk scores
    calculator = RiskCalculator(weights=weights)
    risks = calculator.calculate_batch_risk(
        complexity_scores=complexity_scores,
        churn_data=churn_data,
        impact_scores=impact_scores,
        ownership_data=ownership_data,
    )

    # Format output
    if args.format == "text":
        output = format_text_output(risks, args.top)
    elif args.format == "json":
        output = format_json_output(risks)
    else:  # toon
        output = format_toon_output(risks)

    output_data(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
