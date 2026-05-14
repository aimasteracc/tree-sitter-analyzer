"""
File-level code health scoring.

Computes a 0-100 health score for source files based on five weighted dimensions:
- Lines (20%): Penalizes overly large files
- Complexity (25%): AST node count and nesting depth
- Dependencies (20%): Number of internal project dependencies
- Comments (15%): Comment-to-code ratio
- Coverage (20%): Test coverage placeholder (default: 50 for unknown)
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .core.parser import Parser

# Dimension weights (must sum to 100)
DIMENSION_WEIGHTS = {
    "lines": 20,
    "complexity": 25,
    "dependencies": 20,
    "comments": 15,
    "coverage": 20,
}

# Thresholds for scoring
LINE_SCORE_IDEAL = 200  # Files under 200 lines get full line score
LINE_SCORE_MAX = 2000  # Files over 2000 lines get 0 line score
COMPLEXITY_IDEAL = 500  # Under 500 AST nodes → full complexity score
COMPLEXITY_MAX = 20000  # Over 20000 AST nodes → 0 complexity score
NESTING_MAX_DEPTH = 15  # AST nesting depth of 15+ → penalty starts
COMMENT_RATIO_IDEAL = 0.20  # 20% comment ratio → full score
DEP_IDEAL = 3  # ≤ 3 deps → full score
DEP_MAX = 100  # ≥ 100 deps → 0 score


@dataclass
class HealthScore:
    """
    Health score for a single source file.

    Attributes:
        file_path: Path to the analyzed file
        total: Overall health score (0-100)
        dimensions: Per-dimension scores (0-100 each)
        grade: Letter grade (A-F)
    """

    file_path: str
    total: float
    dimensions: dict[str, float] = field(default_factory=dict)

    @property
    def grade(self) -> str:
        """Letter grade based on total score."""
        if self.total >= 90:
            return "A"
        elif self.total >= 80:
            return "B"
        elif self.total >= 70:
            return "C"
        elif self.total >= 50:
            return "D"
        return "F"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "file": self.file_path,
            "total": self.total,
            "grade": self.grade,
            "dimensions": self.dimensions,
        }


class HealthScorer:
    """
    Compute health scores for source files.

    Usage:
        scorer = HealthScorer()
        result = scorer.score_file("src/main.py")
        print(f"Health: {result.total}/100 ({result.grade})")

        # Score entire project
        results = scorer.score_project("src/")
        for r in results:
            print(f"{r.file_path}: {r.grade}")
    """

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        """
        Initialize the scorer.

        Args:
            weights: Optional custom dimension weights (must sum to 100).
                    Default: lines=20, complexity=25, dependencies=20, comments=15, coverage=20
        """
        self.weights = weights or dict(DIMENSION_WEIGHTS)

    def score_file(self, file_path: str) -> HealthScore:
        """
        Score a single file.

        Args:
            file_path: Path to the source file

        Returns:
            HealthScore with total and per-dimension scores
        """
        # Check if file exists
        path = Path(file_path)
        if not path.exists():
            return HealthScore(file_path=file_path, total=0.0, dimensions={})

        # Read the file
        try:
            source = path.read_text()
        except Exception:
            return HealthScore(file_path=file_path, total=0.0, dimensions={})

        lines = source.splitlines()
        line_count = len(lines)

        # Dimension scores
        dims: dict[str, float] = {}

        # 1. Lines score (20%): smaller files score higher
        dims["lines"] = self._score_lines(line_count)

        # 2. Complexity score (25%): based on AST node count and nesting depth
        dims["complexity"] = self._score_complexity(file_path, source)

        # 3. Dependencies score (20%): placeholder (would need project graph)
        dims["dependencies"] = self._score_dependencies(file_path)

        # 4. Comments score (15%): ratio of comment lines to code lines
        dims["comments"] = self._score_comments(lines, source)

        # 5. Coverage score (20%): placeholder (would need coverage data)
        dims["coverage"] = 50.0

        # Weighted total
        total = 0.0
        for dim, score in dims.items():
            weight = self.weights.get(dim, 20) / 100.0
            total += score * weight

        return HealthScore(
            file_path=file_path,
            total=round(total, 1),
            dimensions={k: round(v, 1) for k, v in dims.items()},
        )

    _EXCLUDE_DIRS = {
        "node_modules",
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        "htmlcov",
        ".cache",
        ".eggs",
        ".idea",
        ".vscode",
        ".claude",
    }

    def score_project(self, project_root: str) -> list[HealthScore]:
        """
        Score all source files in a project directory.

        Args:
            project_root: Root directory of the project

        Returns:
            List of HealthScore objects, sorted by total descending
        """
        root = Path(project_root)
        supported_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".java"}

        results: list[HealthScore] = []
        for ext in supported_exts:
            for f in root.rglob(f"*{ext}"):
                if any(part in self._EXCLUDE_DIRS for part in f.parts):
                    continue
                try:
                    results.append(self.score_file(str(f)))
                except Exception:  # nosec B112
                    continue

        results.sort(key=lambda r: r.total, reverse=True)
        return results

    # ---- Dimension scoring helpers ----

    def _score_lines(self, line_count: int) -> float:
        """Score based on file length. Smaller files get higher scores."""
        if line_count <= 0:
            return 0.0
        if line_count <= LINE_SCORE_IDEAL:
            return 100.0
        if line_count >= LINE_SCORE_MAX:
            return 0.0

        # Linear interpolation between ideal and max
        ratio = (line_count - LINE_SCORE_IDEAL) / (LINE_SCORE_MAX - LINE_SCORE_IDEAL)
        return max(0.0, 100.0 * (1.0 - ratio))

    def _score_complexity(self, file_path: str, source: str) -> float:
        """Score based on AST node count and nesting depth."""
        try:
            ext = Path(file_path).suffix.lower()
            lang_map = {
                ".py": "python",
                ".js": "javascript",
                ".ts": "typescript",
                ".jsx": "javascript",
                ".tsx": "typescript",
                ".java": "java",
            }
            language = lang_map.get(ext)
            if language is None:
                return 50.0

            parser = Parser()
            result = parser.parse_file(file_path, language)

            if not result.success or result.tree is None:
                return 50.0

            # Count total nodes and find max depth
            node_count = 0
            max_depth = 0

            def walk(node: Any, depth: int) -> None:
                nonlocal node_count, max_depth
                node_count += 1
                max_depth = max(max_depth, depth)
                if hasattr(node, "children"):
                    for child in node.children:
                        walk(child, depth + 1)

            walk(result.tree.root_node, 0)

            # Node count score
            if node_count <= COMPLEXITY_IDEAL:
                node_score = 100.0
            elif node_count >= COMPLEXITY_MAX:
                node_score = 0.0
            else:
                ratio = (node_count - COMPLEXITY_IDEAL) / (
                    COMPLEXITY_MAX - COMPLEXITY_IDEAL
                )
                node_score = max(0.0, 100.0 * (1.0 - ratio))

            # Depth penalty (proportional, capped at 40%)
            depth_penalty_pct = 0.0
            if max_depth > NESTING_MAX_DEPTH:
                depth_penalty_pct = min(40.0, (max_depth - NESTING_MAX_DEPTH) * 5.0)

            return max(0.0, node_score * (1.0 - depth_penalty_pct / 100.0))

        except Exception:
            return 50.0

    def _score_dependencies(self, file_path: str) -> float:
        """Score based on import count (uses project_graph if available)."""
        try:
            from .project_graph import extract_imports_from_file

            imports = extract_imports_from_file(file_path)
            # Count only non-stdlib imports
            stdlib = {
                "os",
                "sys",
                "re",
                "json",
                "math",
                "time",
                "datetime",
                "collections",
                "itertools",
                "functools",
                "typing",
                "io",
                "pathlib",
                "hashlib",
                "random",
                "string",
                "textwrap",
            }
            internal_imports = [
                i
                for i in imports
                if i.get("module_name", "")
                and i["module_name"].split(".")[0] not in stdlib
            ]
            dep_count = len(internal_imports)

            if dep_count <= DEP_IDEAL:
                return 100.0
            if dep_count >= DEP_MAX:
                return 0.0

            ratio = (dep_count - DEP_IDEAL) / (DEP_MAX - DEP_IDEAL)
            return max(0.0, 100.0 * (1.0 - ratio))
        except ImportError:
            return 50.0
        except Exception:
            return 50.0

    def _score_comments(self, lines: list[str], source: str) -> float:
        """Score based on comment-to-code ratio."""
        if len(lines) == 0:
            return 0.0

        comment_lines = 0
        code_lines = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if (
                stripped.startswith("#")
                or stripped.startswith("//")
                or stripped.startswith("/*")
            ):
                comment_lines += 1
            elif stripped.startswith('"""') or stripped.startswith("'''"):
                comment_lines += 1
            else:
                code_lines += 1

        total = comment_lines + code_lines
        if total == 0:
            return 0.0

        ratio = comment_lines / total

        if ratio >= COMMENT_RATIO_IDEAL:
            return 100.0
        elif ratio <= 0.0:
            return 0.0
        else:
            return (ratio / COMMENT_RATIO_IDEAL) * 100.0
