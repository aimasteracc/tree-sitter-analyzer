"""
ProjectIndexManager — manages the persistent project index stored on disk.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from ._filesystem import (
    build_top_level_structure,
    collect_root_key_files,
    compute_language_distribution,
    extract_module_descriptions,
    extract_readme_excerpt,
    find_entry_points,
    list_files,
)
from ._models import ProjectIndex
from ._pagerank import collect_critical_nodes
from ._toon import render_toon

logger = logging.getLogger(__name__)


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

    # Build infrastructure directory names — always classified as "core"
    _BUILD_DIR_NAMES: frozenset[str] = frozenset(
        {
            "buildsrc",
            "gradle",
            ".github",
            "build",
            "scripts",
            ".circleci",
            ".gitlab",
            ".husky",
        }
    )

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
                critical_nodes=list(data.get("critical_nodes", [])),
                module_dependency_order=list(data.get("module_dependency_order", [])),
            )
        except (KeyError, TypeError, ValueError) as err:
            logger.warning("Malformed project index data: %s", err)
            return None

    def save(self, index: ProjectIndex) -> None:
        """Persist index to disk, creating the cache directory if needed."""
        # M13: every ``.tree-sitter-cache/`` write goes through the
        # allowlist so an orphan source file (``fresh_dog.py`` and
        # friends) can never land here again.
        from tree_sitter_analyzer.mcp.utils.cache_paths import assert_cache_path

        assert_cache_path(self._cache_path, self.project_root)
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
        scan_roots = self._normalize_scan_roots(roots)
        if not force_refresh:
            cached = self._try_load_fresh_cache(scan_roots)
            if cached is not None:
                return cached

        now = time.time()
        all_files = list_files(scan_roots)
        lang_dist = compute_language_distribution(all_files)

        root_path = Path(self.project_root)
        key_files = collect_root_key_files(root_path)
        entry_points = find_entry_points(root_path)
        top_level = build_top_level_structure(root_path, all_files)

        readme_excerpt = extract_readme_excerpt(root_path)
        top_dirs = [item["name"] for item in top_level]
        module_descriptions = extract_module_descriptions(root_path, top_dirs)
        critical_nodes = collect_critical_nodes(
            all_files, self._extract_edges_from_file
        )

        index = self._assemble_project_index(
            now=now,
            all_files=all_files,
            lang_dist=lang_dist,
            top_level=top_level,
            key_files=key_files,
            entry_points=entry_points,
            readme_excerpt=readme_excerpt,
            module_descriptions=module_descriptions,
            critical_nodes=critical_nodes,
        )
        self._persist_project_index(index, scan_roots, critical_nodes)
        return index

    def render_toon(self, index: ProjectIndex) -> str:
        """Render the project index as TOON-format text."""
        return render_toon(index, self._classify_dir)

    # ------------------------------------------------------------------
    # Build helpers
    # ------------------------------------------------------------------

    def _normalize_scan_roots(self, roots: Path | list[str] | None) -> list[str]:
        """Return ``roots`` as a list[str], defaulting to ``[project_root]``."""
        if isinstance(roots, Path):
            return [str(roots)]
        if roots is None:
            return [self.project_root]
        return list(roots)

    def _try_load_fresh_cache(self, scan_roots: list[str]) -> ProjectIndex | None:
        """Return the cached index if file hashes are unchanged, else None."""
        existing = self.load()
        if existing is None:
            return None
        current_hashes = self._compute_file_hashes(scan_roots)
        saved_hashes = self._load_file_hashes()
        if current_hashes != saved_hashes:
            return None
        return existing

    def _assemble_project_index(
        self,
        *,
        now: float,
        all_files: list[str],
        lang_dist: dict[str, int],
        top_level: list[dict[str, Any]],
        key_files: list[str],
        entry_points: list[str],
        readme_excerpt: str,
        module_descriptions: dict[str, str],
        critical_nodes: list[dict[str, Any]],
    ) -> ProjectIndex:
        """Construct a ``ProjectIndex`` dataclass, preserving ``created_at``."""
        existing_idx = self.load()
        created_at = existing_idx.created_at if existing_idx else now
        return ProjectIndex(
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

    def _persist_project_index(
        self,
        index: ProjectIndex,
        scan_roots: list[str],
        critical_nodes: list[dict[str, Any]],
    ) -> None:
        """Persist index + derived artifacts (hashes, TOON snapshot, nodes)."""
        self.save(index)
        hashes = self._compute_file_hashes(scan_roots)
        self._save_file_hashes(hashes)
        toon = self.render_toon(index)
        self._save_toon(toon)
        self._save_critical_nodes(critical_nodes)

    # ------------------------------------------------------------------
    # Directory classification
    # ------------------------------------------------------------------

    def _classify_dir(self, path: Path) -> Literal["core", "context", "tooling"]:
        """Classify a top-level directory as core / context / tooling.

        Priority (first match wins):
        1. build infrastructure names → core
        2. tooling keywords in name → tooling
        3. independent project (README + build file) → context
        4. everything else → core
        """
        name_lower = path.name.lower()
        if name_lower in self._BUILD_DIR_NAMES:
            return "core"
        if any(kw in name_lower for kw in ("tool", "analyzer", "plugin")):
            return "tooling"
        has_readme = (path / "README.md").exists()
        has_build = any((path / fname).exists() for fname in self._BUILD_FILE_NAMES)
        if has_readme and has_build:
            return "context"
        return "core"

    # ------------------------------------------------------------------
    # Backward-compatible proxies (called by tests / subclasses)
    # ------------------------------------------------------------------

    def _list_files(self, roots: list[str]) -> list[str]:
        """Proxy for ``list_files`` — preserved for test compatibility."""
        return list_files(roots)

    def _extract_readme_excerpt(self, root_path: Path) -> str:
        """Proxy for ``extract_readme_excerpt`` — preserved for test compatibility."""
        return extract_readme_excerpt(root_path)

    @classmethod
    def _describe_dir(cls, dir_path: Path, dir_name: str) -> str:
        """Proxy for ``describe_dir`` — preserved for test compatibility."""
        from ._filesystem import describe_dir

        return describe_dir(dir_path, dir_name)

    def _compute_pagerank(
        self,
        edges: list[tuple[str, str]],
        top_n: int = 10,
        alpha: float = 0.85,
        max_iter: int = 100,
    ) -> list[dict[str, Any]]:
        """Proxy for ``compute_pagerank`` — preserved for test compatibility."""
        from ._pagerank import compute_pagerank

        return compute_pagerank(edges, top_n=top_n, alpha=alpha, max_iter=max_iter)

    # ------------------------------------------------------------------
    # Edge extraction
    # ------------------------------------------------------------------

    def _extract_edges_from_file(self, path: Path) -> list[tuple[str, str]]:
        """Extract edges via language-specific extractor (plugin registry)."""
        from ..edge_extractors import get_extractor

        suffix = path.suffix.lower()
        extractor = get_extractor(suffix)
        if extractor is None:
            return []

        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        return extractor.extract(source, path.stem, self.project_root)

    # ------------------------------------------------------------------
    # Incremental update helpers
    # ------------------------------------------------------------------

    def _compute_file_hashes(self, roots: list[str]) -> dict[str, list[float]]:
        """Return {filepath: [mtime, size]} for all files under roots."""
        result: dict[str, list[float]] = {}
        for fp in list_files(roots):
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
        from tree_sitter_analyzer.mcp.utils.cache_paths import assert_cache_path

        hashes_path = Path(self.project_root) / self.HASHES_FILE
        assert_cache_path(hashes_path, self.project_root)
        hashes_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with hashes_path.open("w", encoding="utf-8") as fh:
                json.dump(hashes, fh, indent=None)
        except OSError as err:
            logger.warning("Could not save file hashes: %s", err)

    def _save_toon(self, toon: str) -> None:
        from tree_sitter_analyzer.mcp.utils.cache_paths import assert_cache_path

        toon_path = Path(self.project_root) / self.TOON_FILE
        assert_cache_path(toon_path, self.project_root)
        toon_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            toon_path.write_text(toon, encoding="utf-8")
        except OSError as err:
            logger.warning("Could not save summary.toon: %s", err)

    def _save_critical_nodes(self, nodes: list[dict[str, Any]]) -> None:
        from tree_sitter_analyzer.mcp.utils.cache_paths import assert_cache_path

        path = Path(self.project_root) / self.CRITICAL_FILE
        assert_cache_path(path, self.project_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("w", encoding="utf-8") as fh:
                json.dump(nodes, fh, indent=2, ensure_ascii=False)
        except OSError as err:
            logger.warning("Could not save critical_nodes.json: %s", err)
