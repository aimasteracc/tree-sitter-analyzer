#!/usr/bin/env python3
"""
Project Root Detection

Intelligent detection of project root directories based on common project markers.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


# r37dd (dogfood): module-level constant + helper extracted from
# ``ProjectRootDetector._traverse_upward`` so the loop body stays at
# ≤3 levels of nesting. These markers short-circuit the upward walk —
# any project that has one of them is unambiguously a project root.
_HIGH_PRIORITY_PROJECT_MARKERS: frozenset[str] = frozenset(
    {
        ".git",
        "pyproject.toml",
        "package.json",
        "pom.xml",
        "Cargo.toml",
        "go.mod",
    }
)


def _has_high_priority_marker(markers_found: list[str]) -> bool:
    """Return True iff any high-priority marker is in ``markers_found``."""
    for marker in markers_found:
        if marker in _HIGH_PRIORITY_PROJECT_MARKERS:
            return True
    return False


def _marker_exists_in_dir(dir_path: Path, marker: str) -> bool:
    """Return True iff ``marker`` exists in ``dir_path``.

    Glob patterns (markers containing ``*``) are matched via
    ``Path.glob``; exact names use ``Path.exists()``.
    """
    if "*" in marker:
        return bool(list(dir_path.glob(marker)))
    return (dir_path / marker).exists()


# Common project root indicators (in priority order)
PROJECT_MARKERS = [
    # Version control
    ".git",
    ".hg",
    ".svn",
    # Python projects
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "Pipfile",
    "poetry.lock",
    "conda.yaml",
    "environment.yml",
    # JavaScript/Node.js projects
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "node_modules",
    # Java projects
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "gradlew",
    "mvnw",
    # C/C++ projects
    "CMakeLists.txt",
    "Makefile",
    "configure.ac",
    "configure.in",
    # Rust projects
    "Cargo.toml",
    "Cargo.lock",
    # Go projects
    "go.mod",
    "go.sum",
    # .NET projects
    "*.sln",
    "*.csproj",
    "*.vbproj",
    "*.fsproj",
    # Other common markers
    "README.md",
    "README.rst",
    "README.txt",
    "LICENSE",
    "CHANGELOG.md",
    ".dockerignore",
    "Dockerfile",
    "docker-compose.yml",
    ".editorconfig",
]


class ProjectRootDetector:
    """Intelligent project root directory detection."""

    def __init__(self, max_depth: int = 10):
        """
        Initialize project root detector.

        Args:
            max_depth: Maximum directory levels to traverse upward
        """
        self.max_depth = max_depth

    def detect_from_file(self, file_path: str) -> str | None:
        """
        Detect project root from a file path.

        Args:
            file_path: Path to a file within the project

        Returns:
            Project root directory path, or None if not detected
        """
        if not file_path:
            return None

        try:
            # Convert to absolute path and get directory
            abs_path = Path(file_path).resolve()
            if abs_path.is_file():
                start_dir = abs_path.parent
            else:
                start_dir = abs_path

            return self._traverse_upward(str(start_dir))

        except Exception as e:
            logger.warning(f"Error detecting project root from {file_path}: {e}")
            return None

    def detect_from_cwd(self) -> str | None:
        """
        Detect project root from current working directory.

        Returns:
            Project root directory path, or None if not detected
        """
        try:
            return self._traverse_upward(str(Path.cwd()))
        except Exception as e:
            logger.warning(f"Error detecting project root from cwd: {e}")
            return None

    def _traverse_upward(self, start_dir: str) -> str | None:
        """
        Traverse upward from start directory looking for project markers.

        Args:
            start_dir: Directory to start traversal from

        Returns:
            Project root directory path, or None if not found

        r37dd (dogfood): flattened nesting 6 → 3 by promoting the inline
        high-priority marker check to a module helper
        (``_has_high_priority_marker``) and the early-return list to a
        module constant (``_HIGH_PRIORITY_PROJECT_MARKERS``).
        """
        current_dir = str(Path(start_dir).resolve())
        candidates: list[tuple[str, int, list[str]]] = []

        for _depth in range(self.max_depth):
            early = self._record_dir_candidates(current_dir, candidates)
            if early is not None:
                return early
            # Move up one directory
            current_path = Path(current_dir)
            parent_path = current_path.parent
            if parent_path == current_path:  # Reached filesystem root
                break
            current_dir = str(parent_path)

        # Return the best candidate if any found
        if candidates:
            # Sort by score (descending) and return the best
            candidates.sort(key=lambda x: x[1], reverse=True)
            best_candidate = candidates[0]
            logger.debug(
                f"Selected project root: {best_candidate[0]} (score: {best_candidate[1]}, markers: {best_candidate[2]})"
            )
            best_root: str = best_candidate[0]
            return best_root

        logger.debug(f"No project root detected from {start_dir}")
        return None

    def _record_dir_candidates(
        self,
        current_dir: str,
        candidates: list[tuple[str, int, list[str]]],
    ) -> str | None:
        """Score the markers in ``current_dir``; short-circuit on high priority.

        Mutates ``candidates`` with ``(dir, score, markers)`` when markers
        exist. Returns the directory immediately if it carries any
        high-priority marker (``.git`` / ``pyproject.toml`` etc.) so the
        caller can break the upward walk.
        """
        markers_found = self._find_markers_in_dir(current_dir)
        if not markers_found:
            return None
        score = self._calculate_score(markers_found)
        candidates.append((current_dir, score, markers_found))
        if not _has_high_priority_marker(markers_found):
            return None
        logger.debug(
            f"Found high-priority project root: {current_dir} (markers: {markers_found})"
        )
        return current_dir

    def _find_markers_in_dir(self, directory: str) -> list[str]:
        """
        Find project markers in a directory.

        Args:
            directory: Directory to search in

        Returns:
            List of found marker names
        """
        # r37dd: flattened nesting 6 → 3 via per-marker helper.
        found_markers: list[str] = []
        try:
            dir_path = Path(directory)
            for marker in PROJECT_MARKERS:
                if _marker_exists_in_dir(dir_path, marker):
                    found_markers.append(marker)
        except (OSError, PermissionError) as e:
            logger.debug(f"Cannot access directory {directory}: {e}")
        return found_markers

    def _calculate_score(self, markers: list[str]) -> int:
        """
        Calculate a score for project root candidates based on markers found.

        Args:
            markers: List of found markers

        Returns:
            Score (higher is better)
        """
        score = 0

        # High-priority markers
        high_priority = [
            ".git",
            "pyproject.toml",
            "package.json",
            "pom.xml",
            "Cargo.toml",
            "go.mod",
        ]
        medium_priority = ["setup.py", "requirements.txt", "CMakeLists.txt", "Makefile"]

        for marker in markers:
            if marker in high_priority:
                score += 100
            elif marker in medium_priority:
                score += 50
            else:
                score += 10

        # Bonus for multiple markers
        if len(markers) > 1:
            score += len(markers) * 5

        return score

    def get_fallback_root(self, file_path: str) -> str:
        """
        Get fallback project root when detection fails.

        Args:
            file_path: Original file path

        Returns:
            Fallback directory (file's directory or cwd)

        r37dd: flattened nesting 6 → 3 via early-return guards.
        """
        try:
            if not file_path:
                return str(Path.cwd())
            path = Path(file_path)
            if not path.exists():
                return str(Path.cwd())
            if path.is_file():
                return str(path.resolve().parent)
            return str(path.resolve())
        except Exception:
            return str(Path.cwd())


def detect_project_root(
    file_path: str | None = None, explicit_root: str | None = None
) -> str | None:
    """
    Unified project root detection with priority handling.

    Priority order:
    1. explicit_root parameter (highest priority)
    2. Auto-detection from file_path
    3. Auto-detection from current working directory
    4. Return None if no markers found

    Args:
        file_path: Path to a file within the project
        explicit_root: Explicitly specified project root

    Returns:
        Project root directory path, or None if no markers found
    """
    detector = ProjectRootDetector()

    # Priority 1: Explicit root
    if explicit_root:
        explicit_path = Path(explicit_root)
        if explicit_path.exists() and explicit_path.is_dir():
            logger.debug(f"Using explicit project root: {explicit_root}")
            return str(explicit_path.resolve())
        else:
            logger.warning(f"Explicit project root does not exist: {explicit_root}")

    # Priority 2: Auto-detection from file path
    if file_path:
        detected_root = detector.detect_from_file(file_path)
        if detected_root:
            logger.debug(f"Auto-detected project root from file: {detected_root}")
            return detected_root

    # Priority 3: Auto-detection from cwd
    detected_root = detector.detect_from_cwd()
    if detected_root:
        logger.debug(f"Auto-detected project root from cwd: {detected_root}")
        return detected_root

    # Priority 4: Return None if no markers found
    logger.debug("No project markers found, returning None")
    return None


if __name__ == "__main__":
    # Test the detector
    import sys

    if len(sys.argv) > 1:
        test_path = sys.argv[1]
        result = detect_project_root(test_path)
        print(f"Project root for '{test_path}': {result}")
    else:
        result = detect_project_root()
        print(f"Project root from cwd: {result}")
