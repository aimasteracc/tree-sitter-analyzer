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
import re
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

# Fallback descriptions for well-known directory names
_DIR_CONVENTIONS: dict[str, str] = {
    "tests": "Test suite",
    "test": "Test suite",
    "unit": "Unit tests",
    "integration": "Integration tests",
    "golden": "Golden master test fixtures",
    "golden_masters": "Golden master test fixtures",
    "fixtures": "Test fixtures",
    "docs": "Documentation",
    "doc": "Documentation",
    "examples": "Example code files",
    "scripts": "Build and utility scripts",
    "tools": "Tool implementations",
    "utils": "Shared utilities",
    "core": "Core implementation",
    "cli": "Command-line interface",
    "api": "API layer",
    "models": "Data models",
    "config": "Configuration",
    "resources": "Resource files",
    "assets": "Static assets",
    "security": "Security and validation",
    "formatters": "Output formatters",
    "languages": "Language-specific configurations",
    "queries": "Query definitions",
    "plugins": "Plugin system",
    "platform_compat": "Platform compatibility",
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
    readme_excerpt: str
    module_descriptions: dict[str, str]


class ProjectIndexManager:
    """Manage the persistent project index stored on disk."""

    CACHE_FILE = ".tree-sitter-cache/project-index.json"
    SCHEMA_VERSION = "1.1"

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
                readme_excerpt=str(data.get("readme_excerpt", "")),
                module_descriptions=dict(data.get("module_descriptions", {})),
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

        # Extract semantic information
        readme_excerpt = self._extract_readme_excerpt(root_path)
        top_dirs = [item["name"] for item in top_level]
        module_descriptions = self._extract_module_descriptions(root_path, top_dirs)

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
            readme_excerpt=readme_excerpt,
            module_descriptions=module_descriptions,
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

        for filepath in all_files:
            fp = Path(filepath)
            abs_fp = fp.resolve() if not fp.is_absolute() else fp
            try:
                rel_path = abs_fp.relative_to(abs_root)
            except ValueError:
                continue  # skip files outside the project root

            parts = rel_path.parts
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

    @staticmethod
    def _extract_readme_excerpt(root_path: Path) -> str:
        """Extract the first meaningful paragraph from README.md (max 200 chars).

        Prefers blockquote lines (``> ...``), then falls back to the first
        non-heading non-badge paragraph.
        """
        for candidate in ("README.md", "README.rst", "README.txt", "README"):
            readme = root_path / candidate
            if readme.is_file():
                try:
                    text = readme.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue

                def _clean(line: str) -> str:
                    """Strip markdown formatting from a line."""
                    s = re.sub(r"\*\*|(?<!\*)\*(?!\*)|`", "", line)
                    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
                    return s.strip()

                def _is_noise(line: str) -> bool:
                    """Return True for lines that are not useful descriptions."""
                    s = line.strip()
                    if not s:
                        return True
                    if s.startswith("#"):
                        return True
                    # Badge / shield lines
                    if "shields.io" in s or s.startswith("[!["):
                        return True
                    # Image lines
                    if s.startswith("!["):
                        return True
                    # Language-navigation lines (many pipe characters)
                    if s.count("|") >= 2:
                        return True
                    # Code fence lines
                    if s.startswith("```") or s.startswith("~~~"):
                        return True
                    return False

                # First pass: prefer blockquote lines
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith(">"):
                        inner = stripped.lstrip(">").strip()
                        if inner and not _is_noise(inner):
                            cleaned = _clean(inner)
                            if cleaned:
                                return cleaned[:200]

                # Second pass: first non-noise non-blockquote paragraph line
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith(">"):
                        continue
                    if _is_noise(stripped):
                        continue
                    cleaned = _clean(stripped)
                    if cleaned:
                        return cleaned[:200]
        return ""

    @staticmethod
    def _read_module_docstring(init_path: Path) -> str:
        """Extract the module-level docstring from a Python __init__.py file."""
        if not init_path.is_file():
            return ""
        try:
            source = init_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

        # Match triple-quoted strings at the top of the file (after optional shebang/encoding)
        pattern = re.compile(
            r'^(?:#[^\n]*\n)*\s*(?:"""(.*?)"""|\'\'\'(.*?)\'\'\')',
            re.DOTALL,
        )
        m = pattern.match(source)
        if not m:
            return ""
        raw = m.group(1) if m.group(1) is not None else m.group(2)
        # Take first non-empty line of the docstring
        for line in raw.splitlines():
            cleaned = line.strip()
            if cleaned:
                return cleaned[:80]
        return ""

    @classmethod
    def _describe_dir(cls, dir_path: Path, dir_name: str) -> str:
        """Return a short description for a directory."""
        # 1. Try __init__.py docstring
        doc = cls._read_module_docstring(dir_path / "__init__.py")
        if doc:
            return doc[:80]
        # 2. Fall back to convention table
        return _DIR_CONVENTIONS.get(dir_name.lower(), "")

    def _extract_module_descriptions(
        self, root_path: Path, top_dirs: list[str]
    ) -> dict[str, str]:
        """
        Return a mapping of relative directory path → short description.

        Covers depth-1 and depth-2 directories.
        """
        descriptions: dict[str, str] = {}

        for top_name in top_dirs:
            top_path = root_path / top_name
            if not top_path.is_dir():
                continue
            desc = self._describe_dir(top_path, top_name)
            if desc:
                descriptions[top_name] = desc

            # Depth-2
            try:
                for sub in sorted(top_path.iterdir()):
                    if not sub.is_dir():
                        continue
                    if sub.name in self._ARTIFACT_DIRS or sub.name.startswith("."):
                        continue
                    rel = f"{top_name}/{sub.name}"
                    sub_desc = self._describe_dir(sub, sub.name)
                    if sub_desc:
                        descriptions[rel] = sub_desc
            except OSError:
                pass

        return descriptions
