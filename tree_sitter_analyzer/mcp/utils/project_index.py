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
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

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
    critical_nodes: list[dict[str, Any]] = field(default_factory=list)
    module_dependency_order: list[str] = field(default_factory=list)


class ProjectIndexManager:
    """Manage the persistent project index stored on disk."""

    CACHE_FILE = ".tree-sitter-cache/project-index.json"
    TOON_FILE = ".tree-sitter-cache/summary.toon"
    HASHES_FILE = ".tree-sitter-cache/file_hashes.json"
    CRITICAL_FILE = ".tree-sitter-cache/critical_nodes.json"
    SCHEMA_VERSION = "2"

    # Build files that mark a directory as a self-contained project
    _BUILD_FILE_NAMES: frozenset[str] = frozenset(
        {
            "package.json",
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
            "pyproject.toml",
            "setup.py",
            "Cargo.toml",
            "go.mod",
            "CMakeLists.txt",
            "composer.json",
        }
    )

    def __init__(self, project_root: str) -> None:
        self.project_root = project_root
        self._cache_path = Path(project_root) / self.CACHE_FILE
        self._java_root_packages: frozenset[str] | None = None

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
                critical_nodes=list(data.get("critical_nodes", [])),
                module_dependency_order=list(
                    data.get("module_dependency_order", [])
                ),
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

    def build(
        self,
        roots: Path | list[str] | None = None,
        force_refresh: bool = False,
    ) -> ProjectIndex:
        """
        Build or load a cached project index.

        Incremental: if file hashes haven't changed and a valid cache exists,
        returns the cached index immediately (no re-scan, no re-parse).

        Args:
            roots: directory to scan (Path), list of root dirs, or None for
                   project_root.
            force_refresh: if True, always rebuild even if cache is fresh.
        """
        # Normalise roots
        if isinstance(roots, Path):
            scan_roots: list[str] = [str(roots)]
        elif roots is None:
            scan_roots = [self.project_root]
        else:
            scan_roots = list(roots)

        # --- Incremental check ---
        if not force_refresh:
            existing = self.load()
            if existing is not None:
                current_hashes = self._compute_file_hashes(scan_roots)
                saved_hashes = self._load_file_hashes()
                if current_hashes == saved_hashes:
                    return existing  # nothing changed

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

        # PageRank over call graph (best-effort; skipped if networkx missing)
        edges: list[tuple[str, str]] = []
        for fp in all_files:
            edges.extend(self._extract_edges_from_file(Path(fp)))
        critical_nodes = self._compute_pagerank(edges, top_n=10)

        existing_idx = self.load()
        created_at = existing_idx.created_at if existing_idx else now

        index = ProjectIndex(
            project_root=self.project_root,
            created_at=created_at,
            updated_at=now,
            file_count=len(all_files),
            language_distribution=lang_dist,
            top_level_structure=top_level,
            key_files=key_files,
            entry_points=entry_points,
            custom_notes=existing_idx.custom_notes if existing_idx else "",
            schema_version=self.SCHEMA_VERSION,
            readme_excerpt=readme_excerpt,
            module_descriptions=module_descriptions,
            critical_nodes=critical_nodes,
        )

        # Persist index + derived artifacts
        self.save(index)
        hashes = self._compute_file_hashes(scan_roots)
        self._save_file_hashes(hashes)
        toon = self.render_toon(index)
        self._save_toon(toon)
        self._save_critical_nodes(critical_nodes)

        return index

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
                    """Strip markdown formatting and HTML tags from a line."""
                    s = re.sub(r"<[^>]+>", "", line)
                    s = re.sub(r"\*\*|(?<!\*)\*(?!\*)|`", "", s)
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
        """Return a short description for a directory.

        Priority:
        1. __init__.py module docstring (Python convention)
        2. README.md first meaningful line (Java / JS / any project)
        3. _DIR_CONVENTIONS lookup (well-known directory names)
        4. Empty string — never dropped, just shown without description
        """
        # 1. __init__.py docstring
        doc = cls._read_module_docstring(dir_path / "__init__.py")
        if doc:
            return doc[:80]

        # 2. README.md first non-heading non-empty line
        readme = dir_path / "README.md"
        if readme.is_file():
            try:
                for line in readme.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines():
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if stripped.startswith("#"):
                        # Extract title from heading, strip HTML
                        title = re.sub(r"<[^>]+>", "", stripped.lstrip("#")).strip()
                        if title:
                            return title[:80]
                        continue
                    if stripped.startswith("[![") or "shields.io" in stripped:
                        continue
                    return re.sub(r"<[^>]+>", "", stripped).strip()[:80]
            except OSError:
                pass

        # 3. Convention table
        return _DIR_CONVENTIONS.get(dir_name.lower(), "")

    # Build infrastructure directory names — always classified as "core"
    _BUILD_DIR_NAMES: frozenset[str] = frozenset(
        {"buildsrc", "gradle", ".github", "build", "scripts",
         ".circleci", ".gitlab", ".husky"}
    )

    def _classify_dir(self, path: Path) -> Literal["core", "context", "tooling"]:
        """Classify a top-level directory as core / context / tooling.

        Priority (first match wins):
        1. build infrastructure names → core
        2. tooling keywords in name → tooling
        3. independent project (README + build file) → context
        4. everything else → core
        """
        name_lower = path.name.lower()
        # 1. Build infrastructure → always core
        if name_lower in self._BUILD_DIR_NAMES:
            return "core"
        # 2. Dev tools by name
        if any(kw in name_lower for kw in ("tool", "analyzer", "plugin")):
            return "tooling"
        # 3. Independent project
        has_readme = (path / "README.md").exists()
        has_build = any(
            (path / fname).exists() for fname in self._BUILD_FILE_NAMES
        )
        if has_readme and has_build:
            return "context"
        return "core"

    # ------------------------------------------------------------------
    # Edge extraction & PageRank
    # ------------------------------------------------------------------

    def _detect_java_root_packages(
        self, project_path: Path
    ) -> frozenset[str]:
        """Read project root packages from pom.xml/build.gradle.

        Returns frozenset of groupId strings (e.g. {"org.springframework"}).
        Empty frozenset means no build file found → caller should skip filtering.
        """
        roots: set[str] = set()

        # Maven: pom.xml → <groupId>
        for pom in project_path.rglob("pom.xml"):
            try:
                text = pom.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            m = re.search(r"<groupId>([^<]+)</groupId>", text)
            if m:
                roots.add(m.group(1).strip())

        # Gradle: build.gradle / build.gradle.kts → group = '...'
        for gf_name in ("build.gradle", "build.gradle.kts"):
            for gradle in project_path.rglob(gf_name):
                try:
                    text = gradle.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                m = re.search(
                    r"""group\s*=\s*['"]([^'"]+)['"]""", text
                )
                if m:
                    roots.add(m.group(1).strip())

        return frozenset(roots)

    def _is_first_party_java(
        self,
        import_package: str,
        root_packages: frozenset[str],
    ) -> bool:
        """Check if a Java import belongs to the project itself."""
        return any(import_package.startswith(rp) for rp in root_packages)

    # java.lang auto-imported classes — filtered from extends/implements
    _JAVA_LANG_CLASSES: frozenset[str] = frozenset(
        {
            "Object", "String", "Integer", "Long", "Double", "Float",
            "Boolean", "Byte", "Short", "Character", "Number", "Void",
            "RuntimeException", "Exception", "Error", "Throwable",
            "IllegalArgumentException", "IllegalStateException",
            "NullPointerException", "UnsupportedOperationException",
            "IndexOutOfBoundsException", "ClassNotFoundException",
            "ClassCastException", "ArithmeticException",
            "Comparable", "Iterable", "AutoCloseable", "Cloneable",
            "Serializable", "Runnable", "Thread", "Class", "ClassLoader",
            "Override", "Deprecated", "SuppressWarnings",
            "FunctionalInterface", "Annotation",
            "StringBuilder", "StringBuffer", "Math", "System", "Enum",
        }
    )

    def _extract_edges_from_file(
        self, path: Path
    ) -> list[tuple[str, str]]:
        """Extract (source_class, target_class) edges from a source file.

        Java strategy (v3): ONLY extends/implements edges (architecture).
        Import statements are used solely to resolve package paths for
        first-party filtering. Plain import edges are NOT created.
        This surfaces architectural hierarchy (BeanFactory, ApplicationContext)
        instead of utility classes (Assert, StringUtils).

        Returns [] for unsupported file types.
        """
        suffix = path.suffix.lower()
        if suffix not in {".java", ".py", ".ts", ".tsx", ".js", ".jsx"}:
            return []

        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        src_name = path.stem
        edges: list[tuple[str, str]] = []

        if suffix == ".java":
            # Detect project root packages (cached after first call)
            if self._java_root_packages is None:
                self._java_root_packages = self._detect_java_root_packages(
                    Path(self.project_root)
                )
            root_packages = self._java_root_packages

            # Step 1: Build import map (class_name → package) for resolving
            # extends/implements package paths. NO edges created from imports.
            import_map: dict[str, str] = {}
            for m in re.finditer(
                r"import\s+(?:static\s+)?([\w.]+\.(\w+))\s*;", source
            ):
                import_map[m.group(2)] = m.group(1).rsplit(".", 1)[0]

            # Step 2: extends — resolve via import map, filter non-first-party
            for m in re.finditer(r"\bextends\s+(\w+)", source):
                cls = m.group(1)
                # Skip single-letter generic params (T, E, K, V)
                if len(cls) <= 2 and cls.isupper():
                    continue
                # Skip java.lang auto-imports
                if cls in self._JAVA_LANG_CLASSES:
                    continue
                if cls in import_map:
                    pkg = import_map[cls]
                    if root_packages and not self._is_first_party_java(
                        pkg, root_packages
                    ):
                        continue  # third-party/stdlib extends → skip
                # First-party or same-package → keep
                edges.append((src_name, cls))

            # Step 3: implements — same logic
            for m in re.finditer(
                r"\bimplements\s+([\w\s,<>]+?)(?:\{|$)", source
            ):
                for cls in re.split(r"[,\s]+", m.group(1)):
                    cls = cls.strip()
                    if not cls or not re.match(r"^[A-Z]\w*$", cls):
                        continue
                    if len(cls) <= 2 and cls.isupper():
                        continue
                    if cls in self._JAVA_LANG_CLASSES:
                        continue
                    if cls in import_map:
                        pkg = import_map[cls]
                        if root_packages and not self._is_first_party_java(
                            pkg, root_packages
                        ):
                            continue
                    edges.append((src_name, cls))

        elif suffix == ".py":
            # from module import ClassName
            for m in re.finditer(
                r"from\s+[\w.]+\s+import\s+([\w,\s]+)", source
            ):
                for cls in re.split(r"[,\s]+", m.group(1)):
                    cls = cls.strip()
                    if cls and re.match(r"^[A-Z]\w*$", cls):
                        edges.append((src_name, cls))
            # import module.ClassName
            for m in re.finditer(r"^import\s+[\w.]+\.(\w+)", source, re.M):
                edges.append((src_name, m.group(1)))

        elif suffix in {".ts", ".tsx", ".js", ".jsx"}:
            # import { ClassName } from '...'
            for m in re.finditer(
                r"import\s+(?:type\s+)?[{]([^}]+)[}]\s+from", source
            ):
                for cls in re.split(r"[,\s]+", m.group(1)):
                    cls = cls.strip()
                    if cls and re.match(r"^[A-Z]\w*$", cls):
                        edges.append((src_name, cls))

        return edges

    def _compute_pagerank(
        self,
        edges: list[tuple[str, str]],
        top_n: int = 10,
        alpha: float = 0.85,
        max_iter: int = 100,
    ) -> list[dict[str, Any]]:
        """Compute PageRank on the call graph and return top_n nodes.

        Pure-Python power iteration — no external dependencies.
        Returns [] gracefully if the edge list is empty.

        Each returned dict has: name, pagerank (float), inbound_refs (int).
        """
        if not edges:
            return []

        try:
            # Build adjacency: out-edges per node
            out_edges: dict[str, set[str]] = {}
            inbound: dict[str, int] = {}
            nodes: set[str] = set()

            for src, dst in edges:
                nodes.add(src)
                nodes.add(dst)
                out_edges.setdefault(src, set()).add(dst)
                inbound[dst] = inbound.get(dst, 0) + 1

            if not nodes:
                return []

            n = len(nodes)
            node_list = sorted(nodes)
            scores: dict[str, float] = dict.fromkeys(node_list, 1.0 / n)
            dangling = {nd for nd in node_list if nd not in out_edges}

            for _ in range(max_iter):
                new_scores: dict[str, float] = {}
                # Dangling nodes distribute their score uniformly
                dangling_sum = alpha * sum(scores[nd] for nd in dangling) / n

                for nd in node_list:
                    new_scores[nd] = (1.0 - alpha) / n + dangling_sum

                for src, dsts in out_edges.items():
                    contrib = alpha * scores[src] / len(dsts)
                    for dst in dsts:
                        new_scores[dst] = new_scores.get(dst, 0.0) + contrib

                # Convergence check
                err = sum(
                    abs(new_scores[nd] - scores[nd]) for nd in node_list
                )
                scores = new_scores
                if err < 1.0e-6 * n:
                    break

            top = sorted(scores.items(), key=lambda kv: -kv[1])[:top_n]
            return [
                {
                    "name": name,
                    "pagerank": round(score, 4),
                    "inbound_refs": inbound.get(name, 0),
                }
                for name, score in top
            ]
        except Exception as exc:  # noqa: BLE001
            logger.debug("PageRank computation failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # TOON rendering
    # ------------------------------------------------------------------

    _NON_CODE_LANGUAGES: frozenset[str] = frozenset(
        {"other", "markdown", "json", "yaml", "toml", "xml", "rst", "latex"}
    )

    def render_toon(self, index: ProjectIndex) -> str:
        """Render the project index as TOON-format text.

        Format:
            project:  <name>
            what:     <readme excerpt>

            critical: (call graph PageRank top 7)
              <Name>   <module>   <score>   (<N> refs)

            scale:    <N> files — <lang1> <pct>%  <lang2> <pct>%
            entry:    <entry_point>

            core:
              <dir>/   <description>
            context:
              <dir>/   (<N> files)
            tooling:
              <dir>/   <description>

            notes:    <custom_notes>
        """
        lines: list[str] = []
        root_path = Path(index.project_root)
        project_name = root_path.resolve().name or root_path.name

        lines.append(f"project:  {project_name}")
        if index.readme_excerpt:
            lines.append(f"what:     {index.readme_excerpt}")

        # --- critical section ---
        if index.critical_nodes:
            lines.append("")
            lines.append("critical:")
            for node in index.critical_nodes[:7]:
                name = node.get("name", "")
                pr = float(node.get("pagerank", 0))
                refs = int(node.get("inbound_refs", 0))
                lines.append(f"  {name:<28}  {pr:.2f}  ({refs} refs)")

        # --- scale ---
        total = max(index.file_count, 1)
        code_langs = [
            (k, v)
            for k, v in index.language_distribution.items()
            if k not in self._NON_CODE_LANGUAGES and v >= 1
        ]
        code_langs.sort(key=lambda kv: -kv[1])
        if code_langs:
            lang_str = "  ".join(
                f"{k} {round(v * 100 / total)}%" for k, v in code_langs[:2]
            )
            lines.append(f"\nscale:    {index.file_count:,} files — {lang_str}")

        # --- entry ---
        if index.entry_points:
            ep = Path(index.entry_points[0]).name
            lines.append(f"entry:    {ep}")

        # --- structure: classify dirs ---
        core_dirs: list[dict[str, Any]] = []
        context_dirs: list[dict[str, Any]] = []
        tooling_dirs: list[dict[str, Any]] = []

        for item in index.top_level_structure:
            name = item["name"]
            dir_path = root_path / name
            if dir_path.is_dir():
                cls_ = self._classify_dir(dir_path)
            else:
                cls_ = "core"

            if cls_ == "context":
                context_dirs.append(item)
            elif cls_ == "tooling":
                tooling_dirs.append(item)
            else:
                core_dirs.append(item)

        DIR_COL = 26

        if core_dirs:
            lines.append("")
            lines.append("core:")
            for item in core_dirs[:7]:
                name = item["name"]
                dir_label = name + "/"
                desc = index.module_descriptions.get(name, "")
                padding = max(1, DIR_COL - len(dir_label))
                desc_str = f"  {desc}" if desc else ""
                lines.append(
                    f"  {dir_label}{' ' * padding}{desc_str}".rstrip()
                )
                for sub in item.get("subdirectories", [])[:4]:
                    sname = sub["name"]
                    rel = f"{name}/{sname}"
                    sdesc = index.module_descriptions.get(rel, "")
                    if sdesc:
                        sub_label = sname + "/"
                        pad2 = max(1, DIR_COL - 2 - len(sub_label))
                        lines.append(
                            f"    {sub_label}{' ' * pad2}  {sdesc}"
                        )

        if context_dirs:
            lines.append("")
            lines.append("context:  (reference projects)")
            for item in context_dirs[:6]:
                name = item["name"]
                count = item.get("file_count", 0)
                lines.append(f"  {name}/  ({count:,} files)")

        if tooling_dirs:
            lines.append("")
            lines.append("tooling:")
            for item in tooling_dirs[:3]:
                name = item["name"]
                desc = index.module_descriptions.get(name, "")
                dir_label = name + "/"
                padding = max(1, DIR_COL - len(dir_label))
                desc_str = f"  {desc}" if desc else ""
                lines.append(
                    f"  {dir_label}{' ' * padding}{desc_str}".rstrip()
                )

        if index.custom_notes:
            lines.append(f"\nnotes:    {index.custom_notes}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Incremental update helpers
    # ------------------------------------------------------------------

    def _compute_file_hashes(
        self, roots: list[str]
    ) -> dict[str, list[float]]:
        """Return {filepath: [mtime, size]} for all files under roots.

        Uses stat() only — no file content read — so it's fast even on
        large trees.
        """
        result: dict[str, list[float]] = {}
        for fp in self._list_files(roots):
            try:
                st = Path(fp).stat()
                result[fp] = [st.st_mtime, float(st.st_size)]
            except OSError:
                pass
        return result

    def _load_file_hashes(self) -> dict[str, list[float]]:
        hashes_path = Path(self.project_root) / self.HASHES_FILE
        if not hashes_path.exists():
            return {}
        try:
            with hashes_path.open("r", encoding="utf-8") as fh:
                data: dict[str, list[float]] = json.load(fh)
            return data
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_file_hashes(self, hashes: dict[str, list[float]]) -> None:
        hashes_path = Path(self.project_root) / self.HASHES_FILE
        hashes_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with hashes_path.open("w", encoding="utf-8") as fh:
                json.dump(hashes, fh, indent=None)
        except OSError as err:
            logger.warning("Could not save file hashes: %s", err)

    def _save_toon(self, toon: str) -> None:
        toon_path = Path(self.project_root) / self.TOON_FILE
        toon_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            toon_path.write_text(toon, encoding="utf-8")
        except OSError as err:
            logger.warning("Could not save summary.toon: %s", err)

    def _save_critical_nodes(
        self, nodes: list[dict[str, Any]]
    ) -> None:
        path = Path(self.project_root) / self.CRITICAL_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("w", encoding="utf-8") as fh:
                json.dump(nodes, fh, indent=2, ensure_ascii=False)
        except OSError as err:
            logger.warning("Could not save critical_nodes.json: %s", err)

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
