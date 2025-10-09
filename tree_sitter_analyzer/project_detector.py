#!/usr/bin/env python3
"""
Project Root Detection

Intelligent detection of project root directories based on common project markers.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

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
        """
        current_dir = str(Path(start_dir).resolve())
        candidates = []

        for _depth in range(self.max_depth):
            # Check for project markers in current directory
            markers_found = self._find_markers_in_dir(current_dir)

            if markers_found:
                # Calculate score based on marker priority and count
                score = self._calculate_score(markers_found)
                candidates.append((current_dir, score, markers_found))

                # If we find high-priority markers, we can stop early
                if any(
                    marker
                    in [
                        ".git",
                        "pyproject.toml",
                        "package.json",
                        "pom.xml",
                        "Cargo.toml",
                        "go.mod",
                    ]
                    for marker in markers_found
                ):
                    logger.debug(
                        f"Found high-priority project root: {current_dir} (markers: {markers_found})"
                    )
                    return current_dir

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
            return best_candidate[0]

        logger.debug(f"No project root detected from {start_dir}")
        return None

    def _find_markers_in_dir(self, directory: str) -> list[str]:
        """
        Find project markers in a directory.

        Args:
            directory: Directory to search in

        Returns:
            List of found marker names
        """
        found_markers = []

        try:
            dir_path = Path(directory)

            for marker in PROJECT_MARKERS:
                if "*" in marker:
                    # Handle glob patterns using pathlib
                    if list(dir_path.glob(marker)):
                        found_markers.append(marker)
                else:
                    # Handle exact matches
                    if (dir_path / marker).exists():
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
        """
        try:
            if file_path:
                path = Path(file_path)
                if path.exists():
                    if path.is_file():
                        return str(path.resolve().parent)
                    else:
                        return str(path.resolve())
            return str(Path.cwd())
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
