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
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._health_scorer_helpers import (
    calculate_git_hotspot,
    calculate_weighted_total,
    read_source_file,
    round_available_scores,
)
from ._lang_extension_map import EXT_TO_LANG as _EXT_TO_LANG
from .constants import EXCLUDE_DIRS
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

PROJECT_HEALTH_SOURCE_EXTS = frozenset(
    # Code-only. r34 Q4 narrowed this set to extensions that have a real
    # language plugin in ``_EXT_TO_LANG`` so the scorer never falls back
    # to ``language=None`` (which would grade docs/markup as if they were
    # code and inflate the C-grade bucket). Markdown smell-detection is
    # intentionally OFF here — see CLAUDE.md "Deliberate design
    # decisions" §4. If you want to score markdown structure, build a
    # separate ``markdown_health`` tool.
    #
    # Bug #785 fix: derive directly from the canonical EXT_TO_LANG map so
    # this set never drifts when new language plugins are added. Extensions
    # intentionally excluded from the indexer (e.g. .css, .html, .md, .sql,
    # .yaml, .yml — see _lang_extension_map.py) are also excluded here since
    # they are not wired into EXT_TO_LANG.
    _EXT_TO_LANG.keys()
)

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

# _EXT_TO_LANG is imported from _lang_extension_map at the top of this module.
# Bug #785 fix: using the canonical map eliminates the drift that caused bash,
# scala, swiftinterface, and hxx files to be silently skipped by the scorer.

# Languages whose imports ``DependencyGraph`` can actually resolve into
# file-level edges (mirrors ``project_graph._IMPORT_RESOLVERS``). Files in
# any OTHER language produce an empty graph result (fan_out == fan_in == 0),
# which the fan-out/fan-in scoring would read as a *perfect* 100 — a false
# green for newly-scanned extensions (.sh / .scala / .swift, etc.). For those
# we return a NEUTRAL score instead of pretending dependencies are clean.
_DEPENDENCY_ANALYZABLE_LANGS: set[str] = {
    "python",
    "javascript",
    "typescript",
    "go",
    "rust",
    "c",
    "cpp",
    "java",
}
_NEUTRAL_DEP_SCORE = 50.0


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

    def score_file(
        self, file_path: str, *, fast_dependencies: bool = False
    ) -> HealthScore:
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
        dims = self._score_dimensions(
            file_path, source, language, fast_dependencies=fast_dependencies
        )
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
        *,
        fast_dependencies: bool = False,
    ) -> dict[str, float | None]:
        """Score each health dimension for a source file."""
        dependency_score = (
            _score_deps_fallback(file_path)
            if fast_dependencies
            else score_dependencies(file_path)
        )
        return {
            "size": score_size(len(source.splitlines())),
            "complexity": score_complexity(file_path, source, language),
            "dependencies": dependency_score,
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
    # path *relative to the scanned root* (see ``_is_excluded``) so a
    # unit test that explicitly scores a fixture sub-tree
    # (e.g. ``score_project(tests/fixtures/project_graph/health_project)``)
    # is not broken by the broader project-level filter.
    # Shared build/cache excludes (constants.EXCLUDE_DIRS — incl. C#/Java/Rust
    # bin/obj/packages/target) PLUS health-scoring-specific excludes (test data
    # / fixtures must not count toward a project's code-quality grade).
    _EXCLUDE_DIRS = EXCLUDE_DIRS | {
        "golden_masters",
        "golden",
        "fixtures",
        "test_data",
        "examples",
    }

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
        return any(
            part in self._EXCLUDE_DIRS or part.startswith(".") for part in rel_parts
        )

    def _iter_source_files(self, root: Path) -> tuple[list[Path], int]:
        """Return source files and a count of pruned generated/hidden dirs."""
        files: list[Path] = []
        pruned_dirs = 0
        for dirpath, dirnames, filenames in os.walk(root):
            kept_dirs: list[str] = []
            for name in dirnames:
                if name in self._EXCLUDE_DIRS or name.startswith("."):
                    pruned_dirs += 1
                else:
                    kept_dirs.append(name)
            dirnames[:] = kept_dirs
            for filename in filenames:
                if filename.startswith("."):
                    continue
                if Path(filename).suffix.lower() in self.source_extensions:
                    files.append(Path(dirpath) / filename)
        return files, pruned_dirs

    def score_project(
        self,
        project_root: str,
        *,
        use_cache: bool = True,
    ) -> list[HealthScore]:
        """Score all source files; returns just the score list.

        This is the legacy API. Prefer ``score_project_with_stats``
        when you need to surface coverage metrics (how many files were
        scanned vs scored vs skipped, and why) — agents asking "did you
        really index my whole project?" need those numbers, not the
        list alone.
        """
        scores, _stats = self.score_project_with_stats(
            project_root, use_cache=use_cache
        )
        return scores

    def score_project_with_stats(
        self,
        project_root: str,
        *,
        use_cache: bool = True,
    ) -> tuple[list[HealthScore], dict[str, Any]]:
        """
        Score all source files AND return walker coverage statistics.

        Coverage stats let an agent answer "how many files did you
        actually look at?" honestly — the difference between scanned
        and scored files (excluded directories, parse failures) is the
        kind of information that used to be silently dropped before
        ``TRUST_BUT_VERIFY_2026-05-23.md``.

        Args:
            project_root: Root directory of the project
            use_cache: When True (default), use the persistent
                :class:`HealthScoreCache` so unchanged files reuse their
                previous score. The first warm-up still scores every file;
                subsequent runs are near-instant for unchanged files.

        Returns:
            Tuple of (scores, stats) where stats has shape::

                {
                    "total_files_scanned":   int,  # rglob hits, pre-filter
                    "total_files_scored":    int,  # actually scored
                    "total_files_skipped":   int,  # scanned but not scored
                    "skip_reasons": {
                        "excluded_dir":   int,  # in self._EXCLUDE_DIRS
                        "scoring_failed": int,  # score_file raised
                    },
                }
        """
        # Import locally to avoid a circular import at module load time —
        # _health_score_cache pulls in nothing heavy but keeps the import
        # graph one-directional.
        from ._health_score_cache import HealthScoreCache

        root = Path(project_root)
        cache = HealthScoreCache(str(root)) if use_cache else None
        results: list[HealthScore] = []
        scanned = 0
        excluded_dir = 0
        scoring_failed = 0
        try:
            files, excluded_dir = self._iter_source_files(root)
            for f in files:
                scanned += 1
                if self._is_excluded(f, root):
                    excluded_dir += 1
                    continue
                score = self._score_file_with_cache(str(f), cache)
                if score is None:
                    scoring_failed += 1
                    continue
                results.append(score)
        finally:
            if cache is not None:
                cache.close()

        results.sort(key=lambda r: r.total, reverse=True)
        stats: dict[str, Any] = {
            "total_files_scanned": scanned,
            "total_files_scored": len(results),
            "total_files_skipped": excluded_dir + scoring_failed,
            "skip_reasons": {
                "excluded_dir": excluded_dir,
                "scoring_failed": scoring_failed,
            },
        }
        return results, stats

    def _score_file_with_cache(
        self,
        file_path: str,
        cache: Any,
    ) -> HealthScore | None:
        """Look up a cached score, fall back to fresh scoring on miss/error.

        Returns None when scoring raises; the outer loop just skips the
        file (mirrors the original ``except Exception: continue`` flow).
        """
        if cache is not None:
            cached = cache.lookup(file_path)
            if cached is not None:
                return HealthScore(
                    file_path=cached["file_path"],
                    total=cached["total"],
                    dimensions=cached.get("dimensions", {}),
                )

        try:
            score = self.score_file(file_path)
        except Exception:  # nosec B112
            return None
        if cache is not None:
            cache.store(score)
        return score

    # ---- Dimension scoring helpers ----

    # Coverage uses instance state (self._coverage_cache), stays as method
    # All others are pure functions delegated to module-level

    def _load_coverage_data(self) -> dict[str, float]:
        """Load coverage data from coverage.json in current or parent directories."""
        if self._coverage_cache is not None:
            return self._coverage_cache

        self._coverage_cache = {}

        search_paths = [Path.cwd()]
        for parent in Path.cwd().parents[:3]:
            search_paths.append(parent)

        for search_dir in search_paths:
            cov_file = search_dir / "coverage.json"
            if cov_file.exists():
                coverage_db = search_dir / ".coverage"
                if _coverage_json_is_stale(cov_file, coverage_db):
                    logger.info(
                        "Ignoring stale coverage.json because .coverage is newer: "
                        f"{cov_file}"
                    )
                    continue
                try:
                    data = json.loads(cov_file.read_text(encoding="utf-8"))
                    files = data.get("files", {})
                    for file_path, file_data in files.items():
                        summary = file_data.get("summary", {})
                        pct = summary.get("percent_covered", 0.0)
                        self._coverage_cache[file_path] = float(pct)

                    total = data.get("totals", {}).get("percent_covered", 0)
                    logger.info(
                        f"Loaded coverage data for {len(self._coverage_cache)} files "
                        f"from {cov_file} (total: {total:.1f}%)"
                    )
                    return self._coverage_cache
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    logger.warning(f"Failed to parse coverage.json: {e}")
                    continue

        logger.debug("No coverage.json found")
        return self._coverage_cache

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
    """Score based on McCabe Cyclomatic Complexity.

    Derives CC from the language plugin extractor (single source of truth,
    RFC-0019 / #1094). The extractor uses per-language AST walkers with the
    correct node-type names; the old DECISION_NODE_TYPES table was stale for
    Java (switch_expression/ternary_expression/do_statement all missed) and
    JavaScript/TypeScript (ternary_expression was mapped as
    conditional_expression).

    For files with ≥3 functions, scores the **average CC per function**
    against industry-standard thresholds (≤5 simple, 5-10 moderate,
    10-15 complex). This stops penalizing well-factored modules that
    contain many small functions.

    For files with <3 functions (utility scripts, single-function
    modules), the total CC from all functions is scored against CC_IDEAL/
    CC_MODERATE/CC_COMPLEX thresholds.
    """
    try:
        if language is None:
            return 50.0

        from .complexity_heatmap import analyze_file_complexity

        funcs = analyze_file_complexity(file_path, language)
        n_funcs = len(funcs)

        if n_funcs == 0:
            # No functions found (empty file, language with no plugin, or
            # parse failure inside analyze_file_complexity). Fall back to
            # base CC = 1 — same as the old path for files with no decision
            # nodes and no function defs.
            cc = 1
        else:
            cc = sum(f.complexity for f in funcs)

        # Multi-function file: score the average CC per function
        # against industry-standard thresholds.
        if n_funcs >= 3:
            avg_cc = cc / n_funcs
            if avg_cc <= 5.0:
                return 100.0
            if avg_cc <= 10.0:
                ratio = (avg_cc - 5.0) / 5.0
                return max(30.0, 100.0 - 70.0 * ratio)
            if avg_cc <= 15.0:
                ratio = (avg_cc - 10.0) / 5.0
                return max(5.0, 30.0 - 25.0 * ratio)
            return 5.0

        # Few-function file: score total CC against absolute thresholds.
        if cc <= CC_IDEAL:
            return 100.0
        if cc <= CC_MODERATE:
            ratio = (cc - CC_IDEAL) / (CC_MODERATE - CC_IDEAL)
            return max(30.0, 100.0 - 70.0 * ratio)
        if cc <= CC_COMPLEX:
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
    """Fallback: score based on raw import count.

    Applies the same neutral-language guard as ``score_dependencies``: a
    file in a language ``DependencyGraph`` cannot analyze (bash / scala /
    swift / ...) would otherwise resolve to zero imports and a false-perfect
    100 here too. Returning the neutral score keeps the ``fast_dependencies``
    fast path consistent with the full-graph path.
    """
    language = _EXT_TO_LANG.get(Path(file_path).suffix.lower())
    if language is not None and language not in _DEPENDENCY_ANALYZABLE_LANGS:
        return _NEUTRAL_DEP_SCORE
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
    """Score based on real dependency graph (fan-out + fan-in).

    Returns a neutral score for files in a language ``DependencyGraph``
    cannot analyze (bash / scala / swift / ruby / ...). Those produce an
    empty graph result, and the fan-out/fan-in branches below would map
    ``0`` dependencies to a perfect 100 — a false green. A neutral score
    avoids rewarding "no dependencies we could even detect".
    """
    language = _EXT_TO_LANG.get(Path(file_path).suffix.lower())
    if language is not None and language not in _DEPENDENCY_ANALYZABLE_LANGS:
        return _NEUTRAL_DEP_SCORE
    try:
        from .project_graph import DependencyGraph

        path = Path(file_path).resolve()
        project_root = find_project_root(path)

        graph = DependencyGraph(str(project_root))
        rel = str(path.relative_to(project_root)).replace("\\", "/")

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
