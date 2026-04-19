"""
Code Complexity Heatmap Analysis

Provides line-level cyclomatic complexity visualization for source code files.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

# Complexity level thresholds
LEVEL_LOW = (1, 5)      # Low complexity (1-5)
LEVEL_MEDIUM = (6, 10)  # Medium complexity (6-10)
LEVEL_HIGH = (11, 20)   # High complexity (11-20)
LEVEL_CRITICAL = (21, 9999)  # Critical complexity (20+)

# ASCII characters for heatmap (ordered by complexity)
ASCII_CHARS = {
    "low": "\u2591",      # light shade
    "medium": "\u2592",   # medium shade
    "high": "\u2593",     # dark shade
    "critical": "\u2588",  # full block
}

# ANSI color codes
ANSI_COLORS = {
    "low": "\033[32m",      # green
    "medium": "\033[33m",   # yellow
    "high": "\033[38;5;208m",  # orange
    "critical": "\033[31m", # red
    "reset": "\033[0m",
}

@dataclass(frozen=True)
class LineComplexity:
    """Complexity score for a single line."""
    line_number: int
    complexity: int
    level: str  # low, medium, high, critical
    ascii_char: str
    nodes: tuple[str, ...] = ()  # AST node types contributing to complexity

@dataclass(frozen=True)
class FileComplexityHeatmap:
    """Complexity heatmap for an entire file."""
    file_path: str
    total_lines: int
    total_complexity: int
    avg_complexity: float
    max_complexity: int
    overall_level: str
    lines: tuple[LineComplexity, ...]
    source_lines: tuple[str, ...] = ()

@dataclass
class ComplexityAnalyzer(BaseAnalyzer):
    """Analyzes code complexity and generates heatmaps."""

    def __init__(self, project_root: str) -> None:
        super().__init__()
        self.project_root = Path(project_root)

    def analyze_file(self, file_path: str) -> FileComplexityHeatmap:
        """Analyze a single file and generate complexity heatmap."""
        full_path = self.project_root / file_path
        try:
            text = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.warning(f"Could not read file {file_path}: {e}")
            return FileComplexityHeatmap(
                file_path=file_path,
                total_lines=0,
                total_complexity=0,
                avg_complexity=0.0,
                max_complexity=0,
                overall_level="low",
                lines=(),
                source_lines=(),
            )

        source_lines = text.split("\n")
        total_lines = len(source_lines)

        # Calculate line-by-line complexity
        lines: list[LineComplexity] = []
        total_complexity = 0
        max_complexity = 0

        for line_num, line_text in enumerate(source_lines, start=1):
            complexity = self._calculate_line_complexity(line_text)
            level = self._get_complexity_level(complexity)
            ascii_char = ASCII_CHARS[level]

            lines.append(
                LineComplexity(
                    line_number=line_num,
                    complexity=complexity,
                    level=level,
                    ascii_char=ascii_char,
                    nodes=(),
                )
            )

            total_complexity += complexity
            if complexity > max_complexity:
                max_complexity = complexity

        avg_complexity = total_complexity / total_lines if total_lines > 0 else 0.0
        overall_level = self._get_overall_level(avg_complexity, max_complexity)

        return FileComplexityHeatmap(
            file_path=file_path,
            total_lines=total_lines,
            total_complexity=total_complexity,
            avg_complexity=round(avg_complexity, 1),
            max_complexity=max_complexity,
            overall_level=overall_level,
            lines=tuple(lines),
            source_lines=tuple(source_lines),
        )

    def _calculate_line_complexity(self, line: str) -> int:
        """Calculate cyclomatic complexity for a single line."""
        import re

        complexity = 1  # Base complexity

        # Branch keywords that increase complexity
        branch_keywords = [
            r"\bif\b",
            r"\belif\b",
            r"\belse\s+if\b",
            r"\bfor\b",
            r"\bwhile\b",
            r"\bcatch\b",
            r"\bexcept\b",
            r"\bcase\b",
            r"\bdefault\b",
            r"\?\s",  # ternary operator
            r"&&",
            r"\|\|",
        ]

        line_lower = line.lower().strip()

        # Count branch keywords
        for pattern in branch_keywords:
            matches = re.findall(pattern, line_lower)
            complexity += len(matches)

        # Count nested parentheses (rough indicator of nesting)
        open_parens = line.count("(")
        close_parens = line.count(")")
        nesting_depth = min(open_parens, close_parens)
        complexity += nesting_depth // 2  # Penalize deep nesting

        return min(complexity, 50)  # Cap at 50 for very complex lines

    def _get_complexity_level(self, complexity: int) -> str:
        """Get complexity level category."""
        if LEVEL_LOW[0] <= complexity <= LEVEL_LOW[1]:
            return "low"
        elif LEVEL_MEDIUM[0] <= complexity <= LEVEL_MEDIUM[1]:
            return "medium"
        elif LEVEL_HIGH[0] <= complexity <= LEVEL_HIGH[1]:
            return "high"
        else:
            return "critical"

    def _get_overall_level(self, avg: float, max_val: int) -> str:
        """Get overall file complexity level."""
        if max_val >= LEVEL_CRITICAL[0]:
            return "critical"
        elif avg >= LEVEL_HIGH[0] or max_val >= LEVEL_HIGH[1]:
            return "high"
        elif avg >= LEVEL_MEDIUM[0]:
            return "medium"
        else:
            return "low"

@dataclass
class HeatmapFormatter:
    """Format complexity heatmap for display."""

    use_ansi: bool = False
    show_line_numbers: bool = True
    show_source: bool = True

    def format(self, heatmap: FileComplexityHeatmap) -> str:
        """Format heatmap as string."""
        lines: list[str] = []

        # Header
        level_emoji = {
            "low": "🟢",
            "medium": "🟡",
            "high": "🟠",
            "critical": "🔴",
        }
        emoji = level_emoji.get(heatmap.overall_level, "⚪")

        lines.append(
            f"{heatmap.file_path} ({heatmap.total_lines} lines, "
            f"avg: {heatmap.avg_complexity}, max: {heatmap.max_complexity}) {emoji}"
        )
        lines.append("─" * 60)

        # Heatmap rows
        for line_cmplx in heatmap.lines:
            line_num = line_cmplx.line_number
            complexity = line_cmplx.complexity
            level = line_cmplx.level
            char = line_cmplx.ascii_char

            # Get color if ANSI is enabled
            if self.use_ansi:
                color = ANSI_COLORS[level]
                reset = ANSI_COLORS["reset"]
                char = f"{color}{char}{reset}"

            # Build row
            if self.show_line_numbers and self.show_source and heatmap.source_lines:
                source = heatmap.source_lines[line_num - 1][:60]
                lines.append(
                    f"{line_num:4d} {char * 30} [{complexity:2d}] {source}"
                )
            elif self.show_line_numbers:
                lines.append(f"{line_num:4d} {char * 40} [{complexity:2d}]")
            else:
                lines.append(f"{char * 50} [{complexity:2d}]")

        return "\n".join(lines)

    def format_summary(self, heatmap: FileComplexityHeatmap) -> dict[str, Any]:
        """Format heatmap as JSON summary."""
        level_counts: dict[str, int] = {"low": 0, "medium": 0, "high": 0, "critical": 0}

        for line in heatmap.lines:
            level_counts[line.level] += 1

        return {
            "file": heatmap.file_path,
            "total_lines": heatmap.total_lines,
            "avg_complexity": heatmap.avg_complexity,
            "max_complexity": heatmap.max_complexity,
            "overall_level": heatmap.overall_level,
            "level_distribution": level_counts,
            "complex_lines": level_counts["high"] + level_counts["critical"],
        }

def create_heatmap(
    project_root: str,
    file_path: str,
    use_ansi: bool = False,
) -> FileComplexityHeatmap:
    """Create a complexity heatmap for a file."""
    analyzer = ComplexityAnalyzer(project_root)
    return analyzer.analyze_file(file_path)

def format_heatmap(
    heatmap: FileComplexityHeatmap,
    use_ansi: bool = False,
) -> str:
    """Format a heatmap for display."""
    formatter = HeatmapFormatter(use_ansi=use_ansi)
    return formatter.format(heatmap)
