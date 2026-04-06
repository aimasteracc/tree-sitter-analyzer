#!/usr/bin/env python3
"""
Project Index Module — Persistent cross-session codebase memory.

Stores a lightweight snapshot of project structure to disk so Claude can
instantly recall architecture on the next session without re-scanning.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Map file extensions to canonical language names
_EXT_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".m": "objc",
    ".mm": "objc",
    ".scala": "scala",
    ".hs": "haskell",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".clj": "clojure",
    ".lua": "lua",
    ".r": "r",
    ".R": "r",
    ".jl": "julia",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".fish": "shell",
    ".ps1": "powershell",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".xml": "xml",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".md": "markdown",
    ".mdx": "markdown",
    ".rst": "rst",
    ".tex": "latex",
    ".sql": "sql",
    ".proto": "protobuf",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".tf": "terraform",
    ".hcl": "hcl",
    ".dockerfile": "dockerfile",
    ".nix": "nix",
    ".vim": "vim",
}

# Key config / documentation files to identify
_KEY_FILE_NAMES: set[str] = {
    "readme",
    "readme.md",
    "readme.rst",
    "readme.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "cargo.toml",
    "go.mod",
    "makefile",
    "rakefile",
    "gemfile",
    "build.gradle",
    "pom.xml",
    "cmakeLists.txt",
    "dockerfile",
    ".claude",
    "claude.md",
    ".env.example",
    ".envrc",
    "justfile",
    "taskfile.yml",
    "taskfile.yaml",
}

# Entry-point file names to identify
_ENTRY_POINT_NAMES: set[str] = {
    "main.py",
    "__main__.py",
    "app.py",
    "run.py",
    "server.py",
    "index.ts",
    "index.js",
    "index.mjs",
    "main.ts",
    "main.js",
    "main.go",
    "main.rs",
    "main.c",
    "main.cpp",
    "main.java",
    "app.ts",
    "app.js",
    "app.rb",
    "application.rb",
    "manage.py",
    "cli.py",
    "cmd/main.go",
}


@dataclass
class ProjectIndex:
    """Persistent snapshot of a project's architecture."""

    project_root: str
    created_at: float
    updated_at: float
    file_count: int
    language_distribution: dict[str, int]
    top_level_structure: list[dict[str, Any]]
    key_files: list[str]
    entry_points: list[str]
    custom_notes: str
    schema_version: str


class ProjectIndexManager:
    """Manage the persistent project index stored on disk."""

    CACHE_FILE = ".tree-sitter-cache/project-index.json"
    SCHEMA_VERSION = "1.0"

    def __init__(self, project_root: str) -> None:
        self.project_root = project_root
        self._cache_path = Path(project_root) / self.CACHE_FILE

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> ProjectIndex | None:
        """Load index from disk. Returns None if missing or schema mismatch."""
        if not self._cache_path.exists():
            return None
        try:
            with self._cache_path.open("r", encoding="utf-8") as fh:
                data: dict[str, Any] = json.load(fh)
        except (OSError, json.JSONDecodeError) as err:
            logger.warning("Could not read project index: %s", err)
            return None

        if data.get("schema_version") != self.SCHEMA_VERSION:
            logger.info(
                "Project index schema mismatch (got %s, expected %s) — ignoring",
                data.get("schema_version"),
                self.SCHEMA_VERSION,
            )
            return None

        try:
            return ProjectIndex(
                project_root=data["project_root"],
                created_at=float(data["created_at"]),
                updated_at=float(data["updated_at"]),
                file_count=int(data["file_count"]),
                language_distribution=dict(data.get("language_distribution", {})),
                top_level_structure=list(data.get("top_level_structure", [])),
                key_files=list(data.get("key_files", [])),
                entry_points=list(data.get("entry_points", [])),
                custom_notes=str(data.get("custom_notes", "")),
                schema_version=str(data["schema_version"]),
            )
        except (KeyError, TypeError, ValueError) as err:
            logger.warning("Malformed project index data: %s", err)
            return None

    def save(self, index: ProjectIndex) -> None:
        """Persist index to disk, creating the cache directory if needed."""
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._cache_path.open("w", encoding="utf-8") as fh:
                json.dump(asdict(index), fh, indent=2, ensure_ascii=False)
            logger.info("Project index saved to %s", self._cache_path)
        except OSError as err:
            logger.error("Could not save project index: %s", err)

    def is_stale(self, index: ProjectIndex, max_age_hours: int = 24) -> bool:
        """Return True if the index is older than *max_age_hours*."""
        age_seconds = time.time() - index.updated_at
        return age_seconds > max_age_hours * 3600

    def build(self, roots: list[str] | None = None) -> ProjectIndex:
        """
        Build a fresh index by scanning the project.

        Uses fd (via subprocess) to enumerate files and derives metadata from
        file extensions.  Falls back to os.walk() when fd is not available.
        Does NOT run tree-sitter analysis — the scan must stay fast.
        """
        scan_roots = roots or [self.project_root]
        now = time.time()

        all_files: list[str] = self._list_files(scan_roots)

        # Derive language distribution from extensions
        lang_dist: dict[str, int] = {}
        for filepath in all_files:
            ext = Path(filepath).suffix.lower()
            lang = _EXT_TO_LANGUAGE.get(ext)
            if lang:
                lang_dist[lang] = lang_dist.get(lang, 0) + 1
            else:
                lang_dist["other"] = lang_dist.get("other", 0) + 1

        root_path = Path(self.project_root)

        # Identify key files (must live at project root, case-insensitive match)
        root_entries = {e.name.lower(): e.name for e in root_path.iterdir() if e.is_file()}
        key_files: list[str] = [
            root_entries[name]
            for name in sorted(root_entries)
            if name in _KEY_FILE_NAMES
        ]

        # Identify entry points (search only a few levels deep for performance)
        entry_points: list[str] = self._find_entry_points(root_path)

        # Build top-level directory structure (depth 1 dirs only, count files)
        top_level = self._build_top_level_structure(root_path, all_files)

        existing = self.load()
        created_at = existing.created_at if existing else now

        return ProjectIndex(
            project_root=self.project_root,
            created_at=created_at,
            updated_at=now,
            file_count=len(all_files),
            language_distribution=lang_dist,
            top_level_structure=top_level,
            key_files=key_files,
            entry_points=entry_points,
            custom_notes="",
            schema_version=self.SCHEMA_VERSION,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _list_files(self, roots: list[str]) -> list[str]:
        """Return absolute paths of all regular files under *roots*."""
        # Resolve all roots to absolute paths so downstream logic is consistent
        abs_roots = [str(Path(r).resolve()) for r in roots]

        # Try fd first — run from project_root so fd returns relative paths,
        # then convert them to absolute.
        try:
            result = subprocess.run(
                ["fd", "--type", "f", "--color", "never", "--absolute-path", "."]
                + abs_roots,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return [
                    line.strip() for line in result.stdout.splitlines() if line.strip()
                ]
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

        # Fallback: os.walk
        files: list[str] = []
        skip_dirs = {
            ".git",
            ".tree-sitter-cache",
            "node_modules",
            "__pycache__",
            ".venv",
            "venv",
            ".mypy_cache",
            ".ruff_cache",
            "dist",
            "build",
            "target",
        }
        for root_str in abs_roots:
            for dirpath, dirnames, filenames in os.walk(root_str):
                # Prune skip dirs in-place to prevent descending into them
                dirnames[:] = [d for d in dirnames if d not in skip_dirs]
                for fname in filenames:
                    files.append(os.path.join(dirpath, fname))
        return files

    def _find_entry_points(self, root_path: Path) -> list[str]:
        """Scan the project root (up to 3 levels) for known entry-point files."""
        found: list[str] = []
        for entry_name in _ENTRY_POINT_NAMES:
            candidate = root_path / entry_name
            if candidate.is_file():
                found.append(entry_name)

        # Also check one level of sub-directories (src/, pkg/, cmd/, etc.)
        try:
            for subdir in root_path.iterdir():
                if not subdir.is_dir() or subdir.name.startswith("."):
                    continue
                for entry_name_raw in _ENTRY_POINT_NAMES:
                    # Only bare filenames (no path separator) for sub-dir check
                    if "/" in entry_name_raw:
                        continue
                    candidate2 = subdir / entry_name_raw
                    if candidate2.is_file():
                        rel = str(candidate2.relative_to(root_path))
                        found.append(rel)
        except OSError:
            pass

        # Deduplicate while preserving order
        seen: set[str] = set()
        result: list[str] = []
        for ep in found:
            if ep not in seen:
                seen.add(ep)
                result.append(ep)
        return result

    # Directories that are build/cache artifacts — exclude from structure output
    _ARTIFACT_DIRS: frozenset[str] = frozenset(
        {
            "__pycache__",
            ".git",
            ".tree-sitter-cache",
            "node_modules",
            ".venv",
            "venv",
            ".mypy_cache",
            ".ruff_cache",
            ".pytest_cache",
            "dist",
            "build",
            "target",
            "htmlcov",
            "coverage",
            ".coverage",
            "comprehensive_test_results",
            ".tox",
            ".eggs",
            "*.egg-info",
        }
    )

    def _build_top_level_structure(
        self, root_path: Path, all_files: list[str]
    ) -> list[dict[str, Any]]:
        """Return depth-1 directory entries with file counts and depth-2 breakdown."""
        dir_counts: dict[str, int] = {}
        # sub_counts[top_dir][sub_dir] = file_count
        sub_counts: dict[str, dict[str, int]] = {}

        abs_root = root_path.resolve()
        root_str = str(abs_root) + os.sep

        for filepath in all_files:
            abs_fp = str(Path(filepath).resolve()) if not os.path.isabs(filepath) else filepath
            if abs_fp.startswith(root_str):
                rel = abs_fp[len(root_str):]
            elif abs_fp == str(abs_root):
                continue
            else:
                continue  # skip files outside the project root entirely

            parts = rel.split(os.sep)
            if len(parts) >= 2:
                top_dir = parts[0]
                if top_dir in self._ARTIFACT_DIRS or top_dir.startswith("."):
                    continue
                dir_counts[top_dir] = dir_counts.get(top_dir, 0) + 1
                # Collect depth-2 breakdown
                if len(parts) >= 3:
                    sub_dir = parts[1]
                    if sub_dir not in self._ARTIFACT_DIRS and not sub_dir.startswith("."):
                        sub_counts.setdefault(top_dir, {})
                        sub_counts[top_dir][sub_dir] = (
                            sub_counts[top_dir].get(sub_dir, 0) + 1
                        )

        # Sort by file count descending; only include dirs that actually have files
        structure: list[dict[str, Any]] = []
        for name, count in sorted(dir_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            entry: dict[str, Any] = {
                "name": name,
                "type": "directory",
                "file_count": count,
            }
            # Attach sub-directory breakdown if it exists
            if name in sub_counts:
                entry["subdirectories"] = [
                    {"name": sname, "file_count": scount}
                    for sname, scount in sorted(
                        sub_counts[name].items(), key=lambda kv: (-kv[1], kv[0])
                    )
                ]
            structure.append(entry)
        return structure
