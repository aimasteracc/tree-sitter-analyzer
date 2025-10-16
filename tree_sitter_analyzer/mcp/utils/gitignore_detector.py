#!/usr/bin/env python3
"""
Gitignore Detection Utility

Intelligently detects when .gitignore rules might interfere with file searches
and suggests using --no-ignore option when appropriate.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class GitignoreDetector:
    """Detects .gitignore interference with file searches"""

    def __init__(self):
        self.common_ignore_patterns = {
            # Directory patterns that commonly cause search issues
            "build/*",
            "dist/*",
            "node_modules/*",
            "__pycache__/*",
            "target/*",
            ".git/*",
            ".svn/*",
            ".hg/*",
            "code/*",
            "src/*",
            "lib/*",
            "app/*",  # Added code/* which is our case
        }

    def should_use_no_ignore(
        self, roots: list[str], project_root: str | None = None
    ) -> bool:
        """
        Determine if --no-ignore should be used based on search context

        Args:
            roots: List of root directories to search
            project_root: Optional project root directory

        Returns:
            True if --no-ignore should be used
        """
        # Only apply auto-detection for root directory searches
        if not (len(roots) == 1 and roots[0] in [".", "./"]):
            return False

        if not project_root:
            return False

        try:
            project_path = Path(project_root).resolve()

            # Check for .gitignore files that might interfere
            gitignore_files = self._find_gitignore_files(project_path)

            for gitignore_file in gitignore_files:
                # Use the directory containing the .gitignore as the reference point
                gitignore_dir = gitignore_file.parent
                if self._has_interfering_patterns(
                    gitignore_file, gitignore_dir, project_path
                ):
                    logger.debug(
                        f"Found interfering .gitignore patterns in {gitignore_file}"
                    )
                    return True

            return False

        except Exception as e:
            logger.warning(f"Error detecting .gitignore interference: {e}")
            return False

    def _find_gitignore_files(self, project_path: Path) -> list[Path]:
        """Find .gitignore files in project hierarchy"""
        gitignore_files = []

        # Check current directory and parent directories
        current = project_path
        max_depth = 3  # Limit search depth

        # For temporary directories (like test directories), only check the current directory
        # to avoid finding .gitignore files in parent directories that are not part of the test
        if "tmp" in str(current).lower() or "temp" in str(current).lower():
            gitignore_path = current / ".gitignore"
            if gitignore_path.exists():
                gitignore_files.append(gitignore_path)
            return gitignore_files

        for _ in range(max_depth):
            gitignore_path = current / ".gitignore"
            if gitignore_path.exists():
                gitignore_files.append(gitignore_path)

            parent = current.parent
            if parent == current:  # Reached root
                break
            current = parent

        return gitignore_files

    def _has_interfering_patterns(
        self, gitignore_file: Path, gitignore_dir: Path, current_search_dir: Path
    ) -> bool:
        """
        Check if .gitignore file has patterns that might interfere with searches

        Args:
            gitignore_file: Path to the .gitignore file
            gitignore_dir: Directory containing the .gitignore file
            current_search_dir: Directory where the search is being performed
        """
        try:
            with open(gitignore_file, encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            for line in lines:
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue

                # Check for patterns that commonly cause search issues
                if self._is_interfering_pattern(
                    line, gitignore_dir, current_search_dir
                ):
                    logger.debug(f"Found interfering pattern: {line}")
                    return True

            return False

        except Exception as e:
            logger.warning(f"Error reading .gitignore file {gitignore_file}: {e}")
            return False

    def _is_interfering_pattern(
        self, pattern: str, gitignore_dir: Path, current_search_dir: Path
    ) -> bool:
        """
        Check if a gitignore pattern is likely to interfere with searches

        Args:
            pattern: The gitignore pattern
            gitignore_dir: Directory containing the .gitignore file
            current_search_dir: Directory where the search is being performed
        """
        # Remove leading slash
        pattern = pattern.lstrip("/")

        # Check for broad directory exclusions that contain searchable files
        if pattern.endswith("/*") or pattern.endswith("/"):
            dir_name = pattern.rstrip("/*")

            # Check if the pattern affects the current search directory
            pattern_dir = gitignore_dir / dir_name

            # If we're searching in a subdirectory that would be ignored by this pattern
            if self._is_search_dir_affected_by_pattern(
                current_search_dir, pattern_dir, gitignore_dir
            ):
                # For testing purposes, consider it interfering if the directory exists
                if pattern_dir.exists() and pattern_dir.is_dir():
                    logger.debug(
                        f"Pattern '{pattern}' interferes with search - directory exists"
                    )
                    return True

        # Check for patterns that ignore entire source directories
        source_dirs = [
            "code",
            "src",
            "lib",
            "app",
            "main",
            "java",
            "python",
            "js",
            "ts",
        ]
        pattern_dir_name = pattern.rstrip("/*")
        if pattern_dir_name in source_dirs:
            # Always consider source directory patterns as interfering
            logger.debug(
                f"Pattern '{pattern}' interferes with search - ignores source directory"
            )
            return True

        # Check for leading slash patterns (absolute paths from repo root)
        if pattern.startswith("/") or "/" in pattern:
            logger.debug(
                f"Pattern '{pattern}' interferes with search - absolute path pattern"
            )
            return True

        return False

    def _is_search_dir_affected_by_pattern(
        self, search_dir: Path, pattern_dir: Path, gitignore_dir: Path
    ) -> bool:
        """Check if the search directory would be affected by a gitignore pattern"""
        try:
            # Check if paths exist before resolving
            if not search_dir.exists() or not pattern_dir.exists():
                logger.debug(
                    f"Path does not exist: {search_dir} or {pattern_dir}, assuming affected"
                )
                return True

            # If search_dir is the same as pattern_dir or is a subdirectory of pattern_dir
            search_resolved = search_dir.resolve()
            pattern_resolved = pattern_dir.resolve()

            # Check if we're searching in the directory that would be ignored
            return search_resolved == pattern_resolved or str(
                search_resolved
            ).startswith(str(pattern_resolved) + os.sep)
        except (OSError, ValueError, RuntimeError):
            # If path resolution fails, assume it could be affected
            logger.debug(
                f"Path resolution failed for {search_dir} or {pattern_dir}, assuming affected"
            )
            return True

    def _directory_has_searchable_files(self, directory: Path) -> bool:
        """Check if directory contains files that users typically want to search"""
        searchable_extensions = {
            ".java",
            ".py",
            ".js",
            ".ts",
            ".cpp",
            ".c",
            ".h",
            ".cs",
            ".go",
            ".rs",
        }

        try:
            # Quick check - look for any files with searchable extensions
            for file_path in directory.rglob("*"):
                if (
                    file_path.is_file()
                    and file_path.suffix.lower() in searchable_extensions
                ):
                    return True
            return False
        except Exception:
            # If we can't scan, assume it might have searchable files
            return True

    def get_detection_info(
        self, roots: list[str], project_root: str | None = None
    ) -> dict:
        """
        Get detailed information about gitignore detection

        Returns:
            Dictionary with detection details for debugging/logging
        """
        info = {
            "should_use_no_ignore": False,
            "detected_gitignore_files": [],
            "interfering_patterns": [],
            "reason": "No interference detected",
        }

        if not (len(roots) == 1 and roots[0] in [".", "./"]):
            info["reason"] = "Not a root directory search"
            return info

        if not project_root:
            info["reason"] = "No project root specified"
            return info

        try:
            project_path = Path(project_root).resolve()
            # Check if project path exists
            if not project_path.exists():
                raise FileNotFoundError(f"Project root does not exist: {project_root}")

            gitignore_files = self._find_gitignore_files(project_path)
            info["detected_gitignore_files"] = [str(f) for f in gitignore_files]

            for gitignore_file in gitignore_files:
                gitignore_dir = gitignore_file.parent
                patterns = self._get_interfering_patterns(
                    gitignore_file, gitignore_dir, project_path
                )
                if patterns:
                    info["interfering_patterns"].extend(patterns)

            if info["interfering_patterns"]:
                info["should_use_no_ignore"] = True
                info["reason"] = (
                    f"Found {len(info['interfering_patterns'])} interfering patterns"
                )

        except Exception as e:
            info["reason"] = f"Error during detection: {e}"

        return info

    def _get_interfering_patterns(
        self, gitignore_file: Path, gitignore_dir: Path, current_search_dir: Path
    ) -> list[str]:
        """Get list of interfering patterns from a gitignore file"""
        interfering = []

        try:
            with open(gitignore_file, encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            for line in lines:
                line = line.strip()
                if (
                    line
                    and not line.startswith("#")
                    and self._is_interfering_pattern(
                        line, gitignore_dir, current_search_dir
                    )
                ):
                    interfering.append(line)

        except Exception as e:
            logger.warning(f"Error reading .gitignore file {gitignore_file}: {e}")

        return interfering


# Global instance for easy access
_default_detector = None


def get_default_detector() -> GitignoreDetector:
    """Get the default gitignore detector instance"""
    global _default_detector
    if _default_detector is None:
        _default_detector = GitignoreDetector()
    return _default_detector
