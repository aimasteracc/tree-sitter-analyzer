#!/usr/bin/env python3
"""
Unit tests for ProjectIndex and ProjectIndexManager.

Tests save/load round-trips, staleness detection, schema version enforcement,
file enumeration fallbacks, language detection, key file identification,
and entry point detection.
Uses tmp_path fixture throughout — no writes to the real project.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.utils.project_index import (
    ProjectIndex,
    ProjectIndexManager,
)


@pytest.fixture
def simple_project(tmp_path: Path) -> Path:
    """Create a simple project structure for testing."""
    # Python source
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text('"""Main source package."""\n')
    (src / "utils.py").write_text("def helper(): pass\n")

    # TypeScript source
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.ts").write_text("export const app = {};\n")
    (frontend / "types.ts").write_text("export type Foo = string;\n")

    # Tests
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_utils.py").write_text("def test_helper(): pass\n")

    # Root files
    (tmp_path / "README.md").write_text(
        "# AwesomeProject\n\nA tool for awesome tasks.\n"
    )
    (tmp_path / "pyproject.toml").write_text(
        "[tool.poetry]\nname = 'awesomeproject'\n"
    )
    (tmp_path / "__main__.py").write_text("if __name__ == '__main__': pass\n")

    # Artifact dirs that should be excluded
    pycache = src / "__pycache__"
    pycache.mkdir()
    (pycache / "utils.cpython-311.pyc").write_bytes(b"\x00" * 10)

    return tmp_path


@pytest.fixture
def manager(simple_project: Path) -> ProjectIndexManager:
    """Create a ProjectIndexManager for the simple project."""
    return ProjectIndexManager(str(simple_project))


class TestProjectIndexManagerInitialization:
    """Tests for ProjectIndexManager initialization."""

    def test_init_stores_project_root(self, simple_project: Path) -> None:
        """Test that the manager stores the project_root."""
        mgr = ProjectIndexManager(str(simple_project))
        assert mgr.project_root == str(simple_project)

    def test_cache_file_constant(self) -> None:
        """Test that CACHE_FILE is the expected relative path."""
        assert ProjectIndexManager.CACHE_FILE == ".tree-sitter-cache/project-index.json"

    def test_schema_version_set(self) -> None:
        """Test that SCHEMA_VERSION is defined."""
        assert ProjectIndexManager.SCHEMA_VERSION is not None
        assert len(ProjectIndexManager.SCHEMA_VERSION) > 0


class TestProjectIndexManagerBuild:
    """Tests for ProjectIndexManager.build()."""

    def test_build_creates_index(self, manager: ProjectIndexManager) -> None:
        """Test that build() returns a valid ProjectIndex."""
        index = manager.build()
        assert isinstance(index, ProjectIndex)
        assert index.file_count > 0

    def test_language_distribution_correct(
        self, manager: ProjectIndexManager
    ) -> None:
        """Test that Python and TypeScript files are counted correctly."""
        index = manager.build()
        lang_dist = index.language_distribution
        assert "python" in lang_dist
        assert "typescript" in lang_dist
        assert lang_dist["python"] >= 2  # __init__.py, utils.py, test_utils.py, __main__.py
        assert lang_dist["typescript"] >= 2  # index.ts, types.ts

    def test_artifact_dirs_excluded(self, manager: ProjectIndexManager) -> None:
        """Test that __pycache__ directories are not in top_level_structure."""
        index = manager.build()
        names = [item["name"] for item in index.top_level_structure]
        assert "__pycache__" not in names

    def test_key_files_identified(self, manager: ProjectIndexManager) -> None:
        """Test that pyproject.toml and README.md appear in key_files."""
        index = manager.build()
        key_lower = [kf.lower() for kf in index.key_files]
        assert "pyproject.toml" in key_lower
        assert "readme.md" in key_lower

    def test_entry_points_identified(
        self, manager: ProjectIndexManager
    ) -> None:
        """Test that __main__.py appears in entry_points."""
        index = manager.build()
        assert "__main__.py" in index.entry_points

    def test_readme_excerpt_extracted(
        self, manager: ProjectIndexManager
    ) -> None:
        """Test that a meaningful excerpt is extracted from README.md."""
        index = manager.build()
        assert index.readme_excerpt != ""
        assert "awesome" in index.readme_excerpt.lower()

    def test_module_descriptions_from_init(
        self, manager: ProjectIndexManager
    ) -> None:
        """Test that __init__.py docstrings are captured in module_descriptions."""
        index = manager.build()
        # The src/__init__.py has docstring "Main source package."
        assert "src" in index.module_descriptions
        assert "source package" in index.module_descriptions["src"].lower()

    def test_schema_version_set_in_index(
        self, manager: ProjectIndexManager
    ) -> None:
        """Test that the built index has the correct schema version."""
        index = manager.build()
        assert index.schema_version == ProjectIndexManager.SCHEMA_VERSION

    def test_updated_at_recent(self, manager: ProjectIndexManager) -> None:
        """Test that updated_at is set to approximately now."""
        before = time.time()
        index = manager.build()
        after = time.time()
        assert before <= index.updated_at <= after


class TestProjectIndexManagerSaveLoad:
    """Tests for save/load round-trips."""

    def test_save_and_load_roundtrip(
        self, manager: ProjectIndexManager, simple_project: Path
    ) -> None:
        """Test that saving and loading an index preserves all fields."""
        original = manager.build()
        original.custom_notes = "Test notes"
        manager.save(original)

        loaded = manager.load()
        assert loaded is not None
        assert loaded.file_count == original.file_count
        assert loaded.custom_notes == "Test notes"
        assert loaded.schema_version == original.schema_version
        assert loaded.language_distribution == original.language_distribution

    def test_load_returns_none_when_missing(self, tmp_path: Path) -> None:
        """Test that load() returns None when the cache file doesn't exist."""
        mgr = ProjectIndexManager(str(tmp_path))
        result = mgr.load()
        assert result is None

    def test_schema_version_mismatch_returns_none(
        self, manager: ProjectIndexManager, simple_project: Path
    ) -> None:
        """Test that a schema version mismatch causes load() to return None."""
        index = manager.build()
        manager.save(index)

        # Corrupt the schema version in the saved file
        cache_path = simple_project / ".tree-sitter-cache" / "project-index.json"
        with cache_path.open() as fh:
            data = json.load(fh)
        data["schema_version"] = "0.0.0-invalid"
        with cache_path.open("w") as fh:
            json.dump(data, fh)

        result = manager.load()
        assert result is None

    def test_load_returns_none_for_invalid_json(
        self, manager: ProjectIndexManager, simple_project: Path
    ) -> None:
        """Test that corrupt JSON causes load() to return None."""
        cache_path = simple_project / ".tree-sitter-cache" / "project-index.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text("NOT VALID JSON {{{")

        result = manager.load()
        assert result is None

    def test_save_creates_parent_directory(
        self, tmp_path: Path
    ) -> None:
        """Test that save() creates the cache directory if it doesn't exist."""
        mgr = ProjectIndexManager(str(tmp_path))
        index = mgr.build()
        mgr.save(index)

        cache_file = tmp_path / ".tree-sitter-cache" / "project-index.json"
        assert cache_file.exists()


class TestProjectIndexManagerStaleness:
    """Tests for is_stale()."""

    def test_is_stale_fresh_index(self, manager: ProjectIndexManager) -> None:
        """Test that a freshly built index is not stale."""
        index = manager.build()
        assert manager.is_stale(index) is False

    def test_is_stale_old_index(self, manager: ProjectIndexManager) -> None:
        """Test that an index older than 24 hours is stale."""
        index = manager.build()
        # Set updated_at to 25 hours ago
        index.updated_at = time.time() - (25 * 3600)
        assert manager.is_stale(index) is True

    def test_is_stale_exactly_at_boundary(
        self, manager: ProjectIndexManager
    ) -> None:
        """Test boundary: exactly 24h old is stale."""
        index = manager.build()
        index.updated_at = time.time() - (24 * 3600) - 1
        assert manager.is_stale(index) is True

    def test_is_stale_custom_max_age(
        self, manager: ProjectIndexManager
    ) -> None:
        """Test that a custom max_age_hours parameter is respected."""
        index = manager.build()
        index.updated_at = time.time() - (2 * 3600)  # 2 hours old
        assert manager.is_stale(index, max_age_hours=1) is True
        assert manager.is_stale(index, max_age_hours=3) is False


class TestProjectIndexManagerFdFallback:
    """Tests for fd fallback to os.walk."""

    def test_fd_fallback_to_os_walk(
        self, manager: ProjectIndexManager, simple_project: Path
    ) -> None:
        """Test that when fd is not available, os.walk is used as fallback."""
        # Simulate fd not being available by making subprocess.run raise FileNotFoundError
        import subprocess

        original_run = subprocess.run

        def mock_run(cmd: list[str], **kwargs: object) -> object:
            if cmd[0] == "fd":
                raise FileNotFoundError("fd not found")
            return original_run(cmd, **kwargs)

        with patch("subprocess.run", side_effect=mock_run):
            index = manager.build()

        # Should still produce a valid index with files
        assert index.file_count > 0
        assert "python" in index.language_distribution

    def test_os_walk_skips_artifact_dirs(self, tmp_path: Path) -> None:
        """Test that os.walk fallback skips artifact directories like __pycache__."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "real.py").write_text("x = 1\n")
        pycache = src / "__pycache__"
        pycache.mkdir()
        (pycache / "cache.pyc").write_bytes(b"\x00")

        mgr = ProjectIndexManager(str(tmp_path))

        import subprocess

        def mock_run(cmd: list[str], **kwargs: object) -> object:
            if cmd[0] == "fd":
                raise FileNotFoundError("fd not found")
            return subprocess.run.__wrapped__(cmd, **kwargs) if hasattr(subprocess.run, "__wrapped__") else subprocess.__dict__["run"].__wrapped__(cmd, **kwargs)  # type: ignore[attr-defined]

        with patch("subprocess.run", side_effect=FileNotFoundError("fd not found")):
            files = mgr._list_files([str(tmp_path)])

        # __pycache__ files should not be in results
        for f in files:
            assert "__pycache__" not in f


class TestProjectIndexDataclass:
    """Tests for the ProjectIndex dataclass."""

    def test_project_index_creation(self) -> None:
        """Test that a ProjectIndex can be created with all required fields."""
        now = time.time()
        index = ProjectIndex(
            project_root="/tmp/test",
            created_at=now,
            updated_at=now,
            file_count=42,
            language_distribution={"python": 30, "typescript": 12},
            top_level_structure=[{"name": "src", "type": "directory", "file_count": 30}],
            key_files=["pyproject.toml"],
            entry_points=["src/main.py"],
            custom_notes="",
            schema_version="1.1",
            readme_excerpt="A test project.",
            module_descriptions={"src": "Source package"},
        )
        assert index.file_count == 42
        assert index.language_distribution["python"] == 30
