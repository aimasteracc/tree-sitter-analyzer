"""
File-level code health scoring.

Computes a 0-100 health score for source files based on weighted dimensions:
- Size (10%): Penalizes overly large files
- Complexity (25%): McCabe Cyclomatic Complexity (decision-path count)
- Dependencies (20%): Number of internal project dependencies
- Coverage (10%): Test coverage from coverage.json (None if unknown)
- Duplication (10%): Repeated line-level code blocks
- Structure (15%): Nesting depth ratio vs total nodes
- Git hotspot (10%): Recent change frequency
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._health_scorer_helpers import (
    calculate_git_hotspot,
    calculate_weighted_total,
    read_source_file,
    round_available_scores,
)
from .core.parser import Parser

logger = logging.getLogger(__name__)

# Dimension weights (must sum to 100)
DIMENSION_WEIGHTS = {
    "size": 10,
    "complexity": 25,
    "dependencies": 20,
    "coverage": 10,
    "duplication": 10,
    "structure": 15,
    "git_hotspot": 10,
}

# Q4 (round-33 dogfood): keep PROJECT_HEALTH_SOURCE_EXTS narrowed to
# extensions that map to a real language in ``_EXT_TO_LANG`` further down
# this module. Markdown / YAML / HTML / CSS / SQL have no language plugin
# wired into the scorer — including them inflates total_files by ~3x and
# floods the C-grade bucket with golden-master docs that don't represent
# the project's code health.
PROJECT_HEALTH_SOURCE_EXTS = {
    ".py",
    ".java",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".go",
    ".rs",
    ".kt",
    ".cs",
    ".rb",
    ".php",
    ".c",
    ".cpp",
    ".h",
    ".cc",
    ".cxx",
    ".hpp",
}

# Thresholds for scoring
SIZE_IDEAL = 200  # Files under 200 lines get full size score
SIZE_MAX = 2000  # Files over 2000 lines get 0 size score
DEP_IDEAL = 3  # ≤ 3 deps → full score
DEP_MAX = 100  # ≥ 100 deps → 0 score
CC_IDEAL = 15  # File-level CC ≤ 15 → full complexity score (aggregate of functions)
CC_MODERATE = 40  # CC ≤ 40 → moderate penalty
CC_COMPLEX = 100  # CC ≤ 100 → heavy penalty, CC > 100 → near-zero
NESTING_MAX_DEPTH = 15  # Depth > 15 → penalty starts
STRUCTURE_DEPTH_IDEAL = (
    10  # Ideal max AST depth (tree-sitter trees are inherently deep)
)
STRUCTURE_DEPTH_MAX = 30  # Max AST depth for scoring
HOTSPOT_COMMITS_LOW = 5  # ≤ 5 commits in 90 days → full score (stable)
HOTSPOT_COMMITS_HIGH = 50  # ≥ 50 commits in 90 days → 0 score (volatile)

# Per-language decision node types for McCabe Cyclomatic Complexity
# CC = 1 + count(decision_nodes)
DECISION_NODE_TYPES: dict[str, set[str]] = {
    "python": {
        "if_statement",
        "elif_clause",
        "for_statement",
        "while_statement",
        "except_clause",
        "conditional_expression",
        "boolean_operator",
        "case_clause",
    },
    "javascript": {
        "if_statement",
        "for_statement",
        "for_in_statement",
        "while_statement",
        "do_statement",
        "switch_statement",
        "case_clause",
        "catch_clause",
        "conditional_expression",
        "logical_expression",
        "try_statement",
    },
    "typescript": {
        "if_statement",
        "for_statement",
        "for_in_statement",
        "while_statement",
        "do_statement",
        "switch_statement",
        "case_clause",
        "catch_clause",
        "conditional_expression",
        "logical_expression",
        "try_statement",
    },
    "java": {
        "if_statement",
        "while_statement",
        "for_statement",
        "enhanced_for_statement",
        "switch_statement",
        "case_clause",
        "catch_clause",
        "conditional_expression",
    },
    "c": {
        "if_statement",
        "while_statement",
        "for_statement",
        "switch_statement",
        "case_clause",
        "conditional_expression",
        "do_statement",
        "labeled_statement",
    },
    "cpp": {
        "if_statement",
        "while_statement",
        "for_statement",
        "switch_statement",
        "case_clause",
        "conditional_expression",
        "do_statement",
        "catch_clause",
        "try_statement",
        "range_based_for_statement",
    },
    "go": {
        "if_statement",
        "for_statement",
        "case_clause",
        "type_switch_statement",
        "select_statement",
        "communication_case",
    },
    "rust": {
        "if_statement",
        "if_let_expression",
        "while_expression",
        "while_let_expression",
        "for_expression",
        "loop_expression",
        "match_expression",
        "try_expression",
    },
    "ruby": {
        "if",
        "elsif",
        "unless",
        "while",
        "until",
        "for",
        "case",
        "when",
        "rescue",
        "and",
        "or",
        "ternary",
    },
    "php": {
        "if_statement",
        "while_statement",
        "for_statement",
        "foreach_statement",
        "switch_statement",
        "case_statement",
        "catch_clause",
        "conditional_expression",
        "try_statement",
    },
    "kotlin": {
        "if_statement",
        "when_expression",
        "when_entry",
        "for_statement",
        "while_statement",
        "do_statement",
        "try_expression",
        "catch_block",
        "conditional_expression",
    },
    "swift": {
        "if_statement",
        "while_statement",
        "for_statement",
        "switch_statement",
        "case_statement",
        "catch_clause",
        "guard_statement",
        "conditional_expression",
    },
    "csharp": {
        "if_statement",
        "while_statement",
        "for_statement",
        "foreach_statement",
        "switch_statement",
        "case_switch_label",
        "catch_clause",
        "conditional_expression",
        "try_statement",
        "do_statement",
    },
}

# Extension → language mapping
_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".kt": "kotlin",
    ".swift": "swift",
    ".cs": "csharp",
}


@dataclass
class HealthScore:
    """
    Health score for a single source file.

    Attributes:
        file_path: Path to the analyzed file
        total: Overall health score (0-100)
        dimensions: Per-dimension scores (0-100 each)
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

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        source_extensions: set[str] | None = None,
    ) -> None:
        """
        Initialize the scorer.

        Args:
            weights: Optional custom dimension weights (must sum to 100).
                    Default: size=10, complexity=25, dependencies=20,
                             coverage=10, duplication=10, structure=15,
                             git_hotspot=10
            source_extensions: Optional override for file extensions to scan.
                Defaults to project-health supported source extensions.
        """
        self.weights = weights or dict(DIMENSION_WEIGHTS)
        self.source_extensions = set(source_extensions or PROJECT_HEALTH_SOURCE_EXTS)
        self._coverage_cache: dict[str, float] | None = None

    def score_file(self, file_path: str) -> HealthScore:
        """
        Score a single file.

        Args:
            file_path: Path to the source file

        Returns:
            HealthScore with total and per-dimension scores
        """
        path = Path(file_path)
        source = read_source_file(path)
        if source is None:
            return HealthScore(file_path=file_path, total=0.0, dimensions={})

        language = _EXT_TO_LANG.get(path.suffix.lower())
        dims = self._score_dimensions(file_path, source, language)
        total = calculate_weighted_total(dims, self.weights)

        return HealthScore(
            file_path=file_path,
            total=round(total, 1),
            dimensions=round_available_scores(dims),
        )

    def _score_dimensions(
        self,
        file_path: str,
        source: str,
        language: str | None,
    ) -> dict[str, float | None]:
        """Score each health dimension for a source file."""
        return {
            "size": score_size(len(source.splitlines())),
            "complexity": score_complexity(file_path, source, language),
            "dependencies": score_dependencies(file_path),
            "coverage": self._score_coverage(file_path),
            "duplication": score_duplication(source, language),
            "structure": score_structure(file_path, source, language),
            "git_hotspot": score_git_hotspot(file_path),
        }

    # Q4 (round-33 dogfood): ``golden_masters`` is a snapshot of expected
    # MCP output stored under tests/ — it is not source code and must be
    # skipped by the walker. ``fixtures`` and ``test_data`` are tested
    # sample trees; excluding them at the walker level keeps project_health
    # focused on the actual codebase. The exclusion is matched against the
    # path *relative to the scanned root* so the existing test that scores
    # ``tests/fixtures/project_graph/health_project`` directly still works.
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
        "golden_masters",
        "golden",
        "fixtures",
        "test_data",
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
        results: list[HealthScore] = []
        for ext in self.source_extensions:
            for f in root.rglob(f"*{ext}"):
                if self._is_excluded(f, root):
                    continue
                try:
                    results.append(self.score_file(str(f)))
                except Exception:  # nosec B112
                    continue

        results.sort(key=lambda r: r.total, reverse=True)
        return results

    def _is_excluded(self, file_path: Path, root: Path) -> bool:
        """Return True when the file lives under an excluded directory.

        The exclusion is matched against the path *relative to the scanned
        root* so a unit test that explicitly scores a fixture sub-tree
        (e.g. ``score_project(tests/fixtures/project_graph/health_project)``)
        is not broken by the broader project-level filter. When the file
        is not under ``root`` (defensive fallback) we fall back to absolute
        parts.
        """
        try:
            rel_parts = file_path.relative_to(root).parts
        except ValueError:
            rel_parts = file_path.parts
        return any(part in self._EXCLUDE_DIRS for part in rel_parts)

    # ---- Dimension scoring helpers ----

    # Coverage uses instance state (self._coverage_cache), stays as method
    # All others are pure functions delegated to module-level

    def _load_coverage_data(self) -> dict[str, float]:
        """Load coverage data from coverage.json in current or parent directories.

        r37di (dogfood): flattened nesting 6 → 3 by extracting the
        per-directory probe into ``_try_load_coverage_from_dir`` and
        the dict-population step into ``_populate_coverage_cache``.
        """
        if self._coverage_cache is not None:
            return self._coverage_cache

        cache: dict[str, float] = {}
        self._coverage_cache = cache
        search_paths = [Path.cwd(), *Path.cwd().parents[:3]]
        for search_dir in search_paths:
            if self._try_load_coverage_from_dir(search_dir, cache):
                return cache
        logger.debug("No coverage.json found")
        return cache

    @staticmethod
    def _try_load_coverage_from_dir(search_dir: Path, cache: dict[str, float]) -> bool:
        """Probe ``search_dir`` for a fresh ``coverage.json``; populate cache.

        Returns ``True`` when the cache is populated (caller stops walking
        parents), ``False`` when no usable coverage.json was found. Stale
        files (older than ``.coverage``) and parse errors both yield
        ``False`` so the caller can keep looking.
        """
        cov_file = search_dir / "coverage.json"
        if not cov_file.exists():
            return False
        coverage_db = search_dir / ".coverage"
        if _coverage_json_is_stale(cov_file, coverage_db):
            logger.info(
                f"Ignoring stale coverage.json because .coverage is newer: {cov_file}"
            )
            return False
        try:
            data = json.loads(cov_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse coverage.json: {e}")
            return False
        HealthScorer._populate_coverage_cache(data, cov_file, cache)
        return True

    @staticmethod
    def _populate_coverage_cache(
        data: dict, cov_file: Path, cache: dict[str, float]
    ) -> None:
        """Fill ``cache`` from a parsed coverage.json payload (in place)."""
        files = data.get("files", {})
        for file_path, file_data in files.items():
            summary = file_data.get("summary", {})
            pct = summary.get("percent_covered", 0.0)
            cache[file_path] = float(pct)
        total = data.get("totals", {}).get("percent_covered", 0)
        logger.info(
            f"Loaded coverage data for {len(cache)} files "
            f"from {cov_file} (total: {total:.1f}%)"
        )

    def _score_coverage(self, file_path: str) -> float | None:
        """Score based on test coverage. Returns None if no coverage data available."""
        coverage_data = self._load_coverage_data()
        if not coverage_data:
            return None

        path = Path(file_path)
        candidates = [str(path), path.name]

        try:
            candidates.append(str(path.relative_to(Path.cwd())))
        except ValueError:
            pass

        for parent in [Path.cwd()] + list(Path.cwd().parents[:3]):
            try:
                candidates.append(str(path.relative_to(parent)))
            except ValueError:
                continue

        for candidate in candidates:
            if candidate in coverage_data:
                return coverage_data[candidate]

        path_str = str(path)
        for cov_path, pct in coverage_data.items():
            if path_str.endswith(cov_path) or cov_path.endswith(path_str):
                return pct

        return None


def _coverage_json_is_stale(cov_file: Path, coverage_db: Path) -> bool:
    """Return True when pytest-cov data is newer than the JSON report."""
    if not coverage_db.exists():
        return False
    try:
        return coverage_db.stat().st_mtime > cov_file.stat().st_mtime
    except OSError:
        return False


# ---- Module-level dimension scoring functions ----


def score_size(line_count: int) -> float:
    """Score based on file length. Smaller files get higher scores."""
    if line_count <= 0:
        return 0.0
    if line_count <= SIZE_IDEAL:
        return 100.0
    if line_count >= SIZE_MAX:
        return 0.0
    ratio = (line_count - SIZE_IDEAL) / (SIZE_MAX - SIZE_IDEAL)
    return max(0.0, 100.0 * (1.0 - ratio))


def score_complexity(file_path: str, source: str, language: str | None) -> float:
    """Score based on McCabe Cyclomatic Complexity (CC = 1 + decision nodes)."""
    try:
        if language is None:
            return 50.0

        parser = Parser()
        result = parser.parse_file(file_path, language)

        if not result.success or result.tree is None:
            return 50.0

        decision_types = DECISION_NODE_TYPES.get(language, set())
        cc = 1

        def walk(node: Any, depth: int) -> None:
            nonlocal cc
            if hasattr(node, "type") and node.type in decision_types:
                cc += 1
            if hasattr(node, "children"):
                for child in node.children:
                    walk(child, depth + 1)

        walk(result.tree.root_node, 0)

        if cc <= CC_IDEAL:
            return 100.0
        elif cc <= CC_MODERATE:
            ratio = (cc - CC_IDEAL) / (CC_MODERATE - CC_IDEAL)
            return max(30.0, 100.0 - 70.0 * ratio)
        elif cc <= CC_COMPLEX:
            ratio = (cc - CC_MODERATE) / (CC_COMPLEX - CC_MODERATE)
            return max(5.0, 30.0 - 25.0 * ratio)
        return 5.0

    except Exception:
        return 50.0


def find_project_root(path: Path) -> Path:
    """Walk up from file path to find project root."""
    markers = {
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "package.json",
        "Cargo.toml",
        "go.mod",
    }
    current = path.parent if path.is_file() else path
    for _ in range(10):
        if any((current / m).exists() for m in markers):
            return current
        if current.parent == current:
            break
        current = current.parent
    return path.parent if path.is_file() else path


def _score_deps_fallback(file_path: str) -> float:
    """Fallback: score based on raw import count."""
    try:
        from .project_graph import extract_imports_from_file

        imports = extract_imports_from_file(file_path)
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
            if i.get("module_name", "") and i["module_name"].split(".")[0] not in stdlib
        ]
        dep_count = len(internal_imports)

        if dep_count <= DEP_IDEAL:
            return 100.0
        if dep_count >= DEP_MAX:
            return 0.0

        ratio = (dep_count - DEP_IDEAL) / (DEP_MAX - DEP_IDEAL)
        return max(0.0, 100.0 * (1.0 - ratio))
    except Exception:
        return 50.0


def score_dependencies(file_path: str) -> float:
    """Score based on real dependency graph (fan-out + fan-in)."""
    try:
        from .project_graph import DependencyGraph

        path = Path(file_path).resolve()
        project_root = find_project_root(path)

        graph = DependencyGraph(str(project_root))
        rel = str(path.relative_to(project_root))

        fan_out = len(graph.dependencies_of(rel))
        fan_in = len(graph.dependents_of(rel))

        if fan_out <= DEP_IDEAL:
            out_score = 100.0
        elif fan_out >= DEP_MAX:
            out_score = 0.0
        else:
            ratio = (fan_out - DEP_IDEAL) / (DEP_MAX - DEP_IDEAL)
            out_score = max(0.0, 100.0 * (1.0 - ratio))

        if fan_in <= 5:
            in_score = 100.0
        elif fan_in >= 50:
            in_score = 0.0
        else:
            ratio = (fan_in - 5) / 45.0
            in_score = max(0.0, 100.0 * (1.0 - ratio))

        return 0.6 * out_score + 0.4 * in_score

    except Exception:
        return _score_deps_fallback(file_path)


def score_duplication(source: str, language: str | None) -> float:
    """Score based on repeated code blocks (line-level hashing)."""
    lines = source.splitlines()
    if len(lines) < 10:
        return 100.0

    block_hashes: dict[int, int] = {}
    for i in range(len(lines) - 2):
        block = (lines[i].strip(), lines[i + 1].strip(), lines[i + 2].strip())
        if all(not b for b in block):
            continue
        h = hash(block)
        block_hashes[h] = block_hashes.get(h, 0) + 1

    total_blocks = len(block_hashes)
    if total_blocks == 0:
        return 100.0

    duplicate_blocks = sum(1 for count in block_hashes.values() if count > 1)
    dup_ratio = duplicate_blocks / total_blocks

    if dup_ratio <= 0.05:
        return 100.0
    if dup_ratio >= 0.30:
        return 0.0
    return max(0.0, 100.0 * (1.0 - (dup_ratio - 0.05) / 0.25))


def score_structure(file_path: str, source: str, language: str | None) -> float:
    """Score based on AST nesting depth relative to file size."""
    try:
        if language is None:
            return 50.0

        parser = Parser()
        result = parser.parse_file(file_path, language)

        if not result.success or result.tree is None:
            return 50.0

        max_depth = 0

        def walk(node: Any, depth: int) -> None:
            nonlocal max_depth
            max_depth = max(max_depth, depth)
            if hasattr(node, "children"):
                for child in node.children:
                    walk(child, depth + 1)

        walk(result.tree.root_node, 0)

        if max_depth <= STRUCTURE_DEPTH_IDEAL:
            return 100.0
        if max_depth >= STRUCTURE_DEPTH_MAX:
            return 0.0
        ratio = (max_depth - STRUCTURE_DEPTH_IDEAL) / (
            STRUCTURE_DEPTH_MAX - STRUCTURE_DEPTH_IDEAL
        )
        return max(0.0, 100.0 * (1.0 - ratio))

    except Exception:
        return 50.0


def score_git_hotspot(file_path: str) -> float | None:
    """Score based on git commit frequency (Tornhill's hotspot analysis)."""
    try:
        return calculate_git_hotspot(
            file_path,
            HOTSPOT_COMMITS_LOW,
            HOTSPOT_COMMITS_HIGH,
        )
    except Exception:
        return None
