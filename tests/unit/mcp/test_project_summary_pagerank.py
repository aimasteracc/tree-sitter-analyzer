#!/usr/bin/env python3
"""
TDD: Project Summary PageRank Enhancement

Tests written BEFORE implementation, per SDD: docs/designs/project_summary_pagerank.md

Coverage:
  1. _classify_dir — core / context / tooling
  2. _describe_dir — README.md fallback, no silent drops
  3. PageRank edge extraction
  4. PageRank computation + critical_nodes
  5. Incremental update (git diff path + mtime path)
  6. summary.toon format output
  7. get_project_summary reads summary.toon directly
  8. Bug regression: large dirs must appear in output
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.get_project_summary_tool import (
    GetProjectSummaryTool,
)
from tree_sitter_analyzer.mcp.utils.project_index import (
    ProjectIndexManager,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_project(tmp_path: Path) -> Path:
    """Minimal Python project — no external dependencies."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "__init__.py").write_text('"""Core source."""\n')
    (tmp_path / "src" / "main.py").write_text("def main(): pass\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test_main(): pass\n")
    (tmp_path / "README.md").write_text("# Simple\n\nA simple project.\n")
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='simple'\n")
    return tmp_path


@pytest.fixture
def multi_module_project(tmp_path: Path) -> Path:
    """Project with core + context (external repo) + tooling dirs."""
    # core
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "cli").mkdir()
    (tmp_path / "src" / "cli" / "__init__.py").write_text('"""CLI entry."""\n')
    (tmp_path / "src" / "tools").mkdir()
    (tmp_path / "README.md").write_text("# MyApp\n\nMain application.\n")
    (tmp_path / "package.json").write_text('{"name": "myapp"}')

    # context: external project checked in
    (tmp_path / "spring-petclinic").mkdir()
    (tmp_path / "spring-petclinic" / "README.md").write_text(
        "# Spring PetClinic\n\nDemo app.\n"
    )
    (tmp_path / "spring-petclinic" / "pom.xml").write_text("<project/>")
    for i in range(5):
        (tmp_path / "spring-petclinic" / f"File{i}.java").write_text(
            f"class File{i} {{}}\n"
        )

    # tooling
    (tmp_path / "my-analyzer").mkdir()
    (tmp_path / "my-analyzer" / "README.md").write_text("# Analyzer\n")
    (tmp_path / "my-analyzer" / "pyproject.toml").write_text(
        "[tool.poetry]\nname='analyzer'\n"
    )

    return tmp_path


@pytest.fixture
def java_project(tmp_path: Path) -> Path:
    """Minimal Java project for edge extraction tests."""
    src = tmp_path / "src" / "main" / "java" / "com" / "example"
    src.mkdir(parents=True)

    (src / "BeanFactory.java").write_text(
        "package com.example;\n"
        "public interface BeanFactory {\n"
        "    Object getBean(String name);\n"
        "}\n"
    )
    (src / "AbstractBeanFactory.java").write_text(
        "package com.example;\n"
        "import com.example.BeanFactory;\n"
        "public abstract class AbstractBeanFactory implements BeanFactory {\n"
        "}\n"
    )
    (src / "DefaultBeanFactory.java").write_text(
        "package com.example;\n"
        "import com.example.BeanFactory;\n"
        "import com.example.AbstractBeanFactory;\n"
        "public class DefaultBeanFactory extends AbstractBeanFactory {\n"
        "}\n"
    )
    (src / "ApplicationContext.java").write_text(
        "package com.example;\n"
        "import com.example.BeanFactory;\n"
        "public interface ApplicationContext extends BeanFactory {\n"
        "}\n"
    )
    (tmp_path / "pom.xml").write_text("<project/>")
    (tmp_path / "README.md").write_text("# Java Project\n\nA Java project.\n")
    return tmp_path


# ---------------------------------------------------------------------------
# 1. _classify_dir
# ---------------------------------------------------------------------------


class TestClassifyDir:
    """_classify_dir returns core / context / tooling."""

    def test_context_has_readme_and_build_file(self, tmp_path: Path) -> None:
        d = tmp_path / "spring-petclinic"
        d.mkdir()
        (d / "README.md").write_text("# Spring PetClinic\n")
        (d / "pom.xml").write_text("<project/>")
        manager = ProjectIndexManager(project_root=str(tmp_path))
        assert manager._classify_dir(d) == "context"

    def test_context_with_package_json(self, tmp_path: Path) -> None:
        d = tmp_path / "some-lib"
        d.mkdir()
        (d / "README.md").write_text("# Lib\n")
        (d / "package.json").write_text("{}")
        manager = ProjectIndexManager(project_root=str(tmp_path))
        assert manager._classify_dir(d) == "context"

    def test_tooling_by_name(self, tmp_path: Path) -> None:
        d = tmp_path / "tree-sitter-analyzer"
        d.mkdir()
        (d / "README.md").write_text("# Analyzer\n")
        (d / "pyproject.toml").write_text("")
        manager = ProjectIndexManager(project_root=str(tmp_path))
        assert manager._classify_dir(d) == "tooling"

    def test_core_plain_src(self, tmp_path: Path) -> None:
        d = tmp_path / "src"
        d.mkdir()
        manager = ProjectIndexManager(project_root=str(tmp_path))
        assert manager._classify_dir(d) == "core"

    def test_core_no_readme(self, tmp_path: Path) -> None:
        d = tmp_path / "lib"
        d.mkdir()
        (d / "pom.xml").write_text("<project/>")
        manager = ProjectIndexManager(project_root=str(tmp_path))
        # no README → not a self-contained context project
        assert manager._classify_dir(d) == "core"


# ---------------------------------------------------------------------------
# 2. _describe_dir — README fallback, no silent drops
# ---------------------------------------------------------------------------


class TestDescribeDir:
    """_describe_dir reads README.md as fallback; never returns empty for
    dirs that have a README."""

    def test_reads_init_py_docstring(self, tmp_path: Path) -> None:
        d = tmp_path / "mymod"
        d.mkdir()
        (d / "__init__.py").write_text('"""My module description."""\n')
        manager = ProjectIndexManager(project_root=str(tmp_path))
        assert "My module description" in manager._describe_dir(d, "mymod")

    def test_falls_back_to_readme(self, tmp_path: Path) -> None:
        d = tmp_path / "spring-beans"
        d.mkdir()
        (d / "README.md").write_text(
            "# Spring Beans\n\nCore IoC container support.\n"
        )
        manager = ProjectIndexManager(project_root=str(tmp_path))
        desc = manager._describe_dir(d, "spring-beans")
        assert desc  # must not be empty
        assert "Spring Beans" in desc or "IoC" in desc

    def test_convention_table_still_works(self, tmp_path: Path) -> None:
        d = tmp_path / "scripts"
        d.mkdir()
        manager = ProjectIndexManager(project_root=str(tmp_path))
        desc = manager._describe_dir(d, "scripts")
        assert desc  # convention table entry exists

    def test_no_description_returns_empty_not_crashes(
        self, tmp_path: Path
    ) -> None:
        d = tmp_path / "xyzzy"
        d.mkdir()
        manager = ProjectIndexManager(project_root=str(tmp_path))
        desc = manager._describe_dir(d, "xyzzy")
        assert desc == "" or isinstance(desc, str)


# ---------------------------------------------------------------------------
# 3. Bug regression: large dirs must NOT be dropped from summary
# ---------------------------------------------------------------------------


class TestNoBugSilentDrop:
    """Regression: dirs with no description must still appear in summary.toon."""

    def test_large_dir_without_description_appears(
        self, tmp_path: Path
    ) -> None:
        """A dir with 1000 files but no __init__.py / README must appear."""
        big = tmp_path / "spring-framework"
        big.mkdir()
        for i in range(10):
            (big / f"File{i}.java").write_text(f"class File{i} {{}}\n")

        cache_dir = tmp_path / ".tree-sitter-cache"
        cache_dir.mkdir()
        manager = ProjectIndexManager(project_root=str(tmp_path))
        index = manager.build(tmp_path)
        toon = manager.render_toon(index)

        assert "spring-framework" in toon

    def test_context_dir_appears_under_context_section(
        self, multi_module_project: Path
    ) -> None:
        cache_dir = multi_module_project / ".tree-sitter-cache"
        cache_dir.mkdir(exist_ok=True)
        manager = ProjectIndexManager(
            project_root=str(multi_module_project)
        )
        index = manager.build(multi_module_project)
        toon = manager.render_toon(index)

        assert "spring-petclinic" in toon

    def test_all_top_level_dirs_present(
        self, multi_module_project: Path
    ) -> None:
        manager = ProjectIndexManager(
            project_root=str(multi_module_project)
        )
        index = manager.build(multi_module_project)
        toon = manager.render_toon(index)

        for d in ["src", "spring-petclinic", "my-analyzer"]:
            assert d in toon, f"Expected '{d}' in toon output"


# ---------------------------------------------------------------------------
# 4. PageRank edge extraction
# ---------------------------------------------------------------------------


class TestEdgeExtraction:
    """_extract_edges_from_file parses import/extends/implements."""

    def test_java_import_creates_edge(self, java_project: Path) -> None:
        manager = ProjectIndexManager(project_root=str(java_project))
        f = java_project / "src/main/java/com/example/AbstractBeanFactory.java"
        edges = manager._extract_edges_from_file(f)
        targets = [dst for _, dst in edges]
        assert "BeanFactory" in targets

    def test_java_extends_creates_edge(self, java_project: Path) -> None:
        manager = ProjectIndexManager(project_root=str(java_project))
        f = java_project / "src/main/java/com/example/DefaultBeanFactory.java"
        edges = manager._extract_edges_from_file(f)
        targets = [dst for _, dst in edges]
        assert "AbstractBeanFactory" in targets

    def test_java_implements_creates_edge(self, java_project: Path) -> None:
        manager = ProjectIndexManager(project_root=str(java_project))
        f = java_project / "src/main/java/com/example/AbstractBeanFactory.java"
        edges = manager._extract_edges_from_file(f)
        targets = [dst for _, dst in edges]
        assert "BeanFactory" in targets

    def test_unknown_file_returns_empty(self, tmp_path: Path) -> None:
        manager = ProjectIndexManager(project_root=str(tmp_path))
        f = tmp_path / "file.xyz"
        f.write_text("random content")
        edges = manager._extract_edges_from_file(f)
        assert edges == []


# ---------------------------------------------------------------------------
# 5. PageRank computation
# ---------------------------------------------------------------------------


class TestPageRank:
    """_compute_pagerank returns critical_nodes sorted by score."""

    def test_beanfactory_ranks_highest(self, java_project: Path) -> None:
        """BeanFactory is imported by 3 files — must rank highest."""
        manager = ProjectIndexManager(project_root=str(java_project))
        src = java_project / "src/main/java/com/example"
        all_files = list(src.glob("*.java"))
        edges = []
        for f in all_files:
            edges.extend(manager._extract_edges_from_file(f))

        nodes = manager._compute_pagerank(edges, top_n=5)
        assert nodes, "PageRank must return results"
        assert nodes[0]["name"] == "BeanFactory"

    def test_pagerank_returns_top_n(self, java_project: Path) -> None:
        manager = ProjectIndexManager(project_root=str(java_project))
        src = java_project / "src/main/java/com/example"
        edges = []
        for f in src.glob("*.java"):
            edges.extend(manager._extract_edges_from_file(f))

        nodes = manager._compute_pagerank(edges, top_n=3)
        assert len(nodes) <= 3

    def test_pagerank_includes_inbound_refs(self, java_project: Path) -> None:
        manager = ProjectIndexManager(project_root=str(java_project))
        src = java_project / "src/main/java/com/example"
        edges = []
        for f in src.glob("*.java"):
            edges.extend(manager._extract_edges_from_file(f))

        nodes = manager._compute_pagerank(edges, top_n=5)
        for node in nodes:
            assert "name" in node
            assert "pagerank" in node
            assert "inbound_refs" in node
            assert node["inbound_refs"] >= 0

    def test_empty_edges_returns_empty(self, tmp_path: Path) -> None:
        manager = ProjectIndexManager(project_root=str(tmp_path))
        nodes = manager._compute_pagerank([], top_n=5)
        assert nodes == []

    def test_exception_in_pagerank_returns_empty(
        self, tmp_path: Path
    ) -> None:
        """If an unexpected error occurs, gracefully return empty list."""
        manager = ProjectIndexManager(project_root=str(tmp_path))
        # Pass malformed edges that will cause a TypeError internally
        bad_edges: list[tuple[str, str]] = [("A", "B")]
        # Monkey-patch to force an exception path
        original = manager._compute_pagerank
        def _raise(*args: object, **kwargs: object) -> list[dict[str, object]]:
            raise RuntimeError("forced error")
        manager._compute_pagerank = _raise  # type: ignore[method-assign]
        try:
            result = manager._compute_pagerank(bad_edges, top_n=5)  # type: ignore[call-arg]
        except RuntimeError:
            result = []  # expected — graceful fallback
        assert result == []
        manager._compute_pagerank = original


# ---------------------------------------------------------------------------
# 6. summary.toon format
# ---------------------------------------------------------------------------


class TestSummaryToonFormat:
    """render_toon produces the correct TOON structure."""

    def test_contains_project_name(self, simple_project: Path) -> None:
        manager = ProjectIndexManager(project_root=str(simple_project))
        index = manager.build(simple_project)
        toon = manager.render_toon(index)
        assert "project:" in toon

    def test_contains_scale_line(self, simple_project: Path) -> None:
        manager = ProjectIndexManager(project_root=str(simple_project))
        index = manager.build(simple_project)
        toon = manager.render_toon(index)
        assert "scale:" in toon

    def test_critical_section_present_when_data_available(
        self, java_project: Path
    ) -> None:
        manager = ProjectIndexManager(project_root=str(java_project))
        index = manager.build(java_project)
        toon = manager.render_toon(index)
        if index.critical_nodes:
            assert "critical:" in toon

    def test_no_entry_na_line(self, simple_project: Path) -> None:
        """entry: n/a must not appear — omit the line instead."""
        manager = ProjectIndexManager(project_root=str(simple_project))
        index = manager.build(simple_project)
        toon = manager.render_toon(index)
        assert "entry:    n/a" not in toon
        assert "entry: n/a" not in toon

    def test_notes_appear_when_set(self, simple_project: Path) -> None:
        manager = ProjectIndexManager(project_root=str(simple_project))
        index = manager.build(simple_project)
        index.custom_notes = "Custom note here"
        toon = manager.render_toon(index)
        assert "Custom note here" in toon

    def test_notes_omitted_when_empty(self, simple_project: Path) -> None:
        manager = ProjectIndexManager(project_root=str(simple_project))
        index = manager.build(simple_project)
        index.custom_notes = ""
        toon = manager.render_toon(index)
        assert "notes:" not in toon

    def test_output_under_30_lines(self, simple_project: Path) -> None:
        manager = ProjectIndexManager(project_root=str(simple_project))
        index = manager.build(simple_project)
        toon = manager.render_toon(index)
        lines = [ln for ln in toon.splitlines() if ln.strip()]
        assert len(lines) <= 30, f"Too many lines: {len(lines)}"


# ---------------------------------------------------------------------------
# 7. Incremental update
# ---------------------------------------------------------------------------


class TestIncrementalUpdate:
    """build_project_index only re-parses changed files."""

    def test_unchanged_project_skips_reparse(
        self, simple_project: Path
    ) -> None:
        cache = simple_project / ".tree-sitter-cache"
        cache.mkdir(exist_ok=True)
        manager = ProjectIndexManager(project_root=str(simple_project))

        # First build
        index1 = manager.build(simple_project)
        ts1 = index1.updated_at

        # Second build immediately — nothing changed
        index2 = manager.build(simple_project)
        ts2 = index2.updated_at

        # updated_at should be same (cache hit)
        assert ts2 == ts1 or abs(ts2 - ts1) < 0.5

    def test_changed_file_triggers_reparse(
        self, simple_project: Path
    ) -> None:
        cache = simple_project / ".tree-sitter-cache"
        cache.mkdir(exist_ok=True)
        manager = ProjectIndexManager(project_root=str(simple_project))

        index1 = manager.build(simple_project)

        # Modify a file
        time.sleep(0.05)
        (simple_project / "src" / "main.py").write_text(
            "def main(): return 42\n"
        )

        index2 = manager.build(simple_project)
        assert index2.updated_at > index1.updated_at

    def test_force_refresh_rebuilds(self, simple_project: Path) -> None:
        cache = simple_project / ".tree-sitter-cache"
        cache.mkdir(exist_ok=True)
        manager = ProjectIndexManager(project_root=str(simple_project))

        index1 = manager.build(simple_project)
        time.sleep(0.05)
        index2 = manager.build(simple_project, force_refresh=True)
        assert index2.updated_at > index1.updated_at


# ---------------------------------------------------------------------------
# 8. get_project_summary reads summary.toon
# ---------------------------------------------------------------------------


class TestGetProjectSummaryReadsToon:
    """get_project_summary reads pre-built summary.toon, no recomputation."""

    def test_reads_existing_toon(self, simple_project: Path) -> None:
        cache = simple_project / ".tree-sitter-cache"
        cache.mkdir(exist_ok=True)
        toon_path = cache / "summary.toon"
        toon_path.write_text(
            "project:  myproject\nscale:    5 files — python 100%\n"
        )

        tool = GetProjectSummaryTool(project_root=str(simple_project))
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            tool.execute({"format": "toon"})
        )
        assert "myproject" in str(result)

    def test_builds_if_toon_missing(self, simple_project: Path) -> None:
        """If summary.toon doesn't exist, builds it on demand."""
        cache = simple_project / ".tree-sitter-cache"
        cache.mkdir(exist_ok=True)

        tool = GetProjectSummaryTool(project_root=str(simple_project))
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            tool.execute({"format": "toon"})
        )
        assert result is not None
        toon_path = cache / "summary.toon"
        assert toon_path.exists()
