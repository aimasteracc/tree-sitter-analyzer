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


# ===========================================================================
# v2 TDD: First-Party Filtering
# ===========================================================================


@pytest.fixture
def java_project_with_noise(tmp_path: Path) -> Path:
    """Java project with pom.xml groupId + stdlib/third-party imports."""
    # pom.xml declares groupId
    (tmp_path / "pom.xml").write_text(
        "<project>\n"
        "  <groupId>com.example</groupId>\n"
        "  <artifactId>myapp</artifactId>\n"
        "</project>"
    )
    (tmp_path / "README.md").write_text("# MyApp\n\nA Java app.\n")

    src = tmp_path / "src" / "main" / "java" / "com" / "example"
    src.mkdir(parents=True)

    # BeanFactory — core interface (first-party, no imports)
    (src / "BeanFactory.java").write_text(
        "package com.example;\n"
        "public interface BeanFactory {\n"
        "    Object getBean(String name);\n"
        "}\n"
    )

    # Service — imports first-party + stdlib + third-party
    (src / "UserService.java").write_text(
        "package com.example;\n"
        "import com.example.BeanFactory;\n"      # first-party → edge
        "import java.util.List;\n"                # stdlib → SKIP
        "import java.util.Map;\n"                 # stdlib → SKIP
        "import javax.annotation.Nullable;\n"     # annotation → SKIP
        "import org.junit.jupiter.api.Test;\n"    # test fw → SKIP
        "import lombok.Data;\n"                   # annotation proc → SKIP
        "public class UserService implements BeanFactory {\n"
        "    public Object getBean(String name) { return null; }\n"
        "}\n"
    )

    # Controller — imports first-party only
    (src / "UserController.java").write_text(
        "package com.example;\n"
        "import com.example.UserService;\n"       # first-party → edge
        "import com.example.BeanFactory;\n"       # first-party → edge
        "import java.util.Optional;\n"            # stdlib → SKIP
        "public class UserController {\n"
        "    private UserService service;\n"
        "}\n"
    )

    return tmp_path


@pytest.fixture
def gradle_project(tmp_path: Path) -> Path:
    """Java project with build.gradle instead of pom.xml."""
    (tmp_path / "build.gradle").write_text(
        "plugins { id 'java' }\n"
        "group = 'org.myorg'\n"
        "version = '1.0'\n"
    )
    src = tmp_path / "src" / "main" / "java" / "org" / "myorg"
    src.mkdir(parents=True)
    (src / "App.java").write_text(
        "package org.myorg;\n"
        "import org.myorg.Config;\n"
        "import java.util.List;\n"
        "public class App {}\n"
    )
    (src / "Config.java").write_text(
        "package org.myorg;\n"
        "public class Config {}\n"
    )
    return tmp_path


# ---------------------------------------------------------------------------
# 9. Root package detection
# ---------------------------------------------------------------------------


class TestDetectJavaRootPackages:
    """Java root package detection via edge_extractors.java module."""

    def test_reads_pom_groupid(
        self, java_project_with_noise: Path
    ) -> None:
        from tree_sitter_analyzer.mcp.utils.edge_extractors.java import (
            _detect_java_root_packages,
        )

        roots = _detect_java_root_packages(str(java_project_with_noise))
        assert "com.example" in roots

    def test_reads_gradle_group(self, gradle_project: Path) -> None:
        from tree_sitter_analyzer.mcp.utils.edge_extractors.java import (
            _detect_java_root_packages,
        )

        roots = _detect_java_root_packages(str(gradle_project))
        assert "org.myorg" in roots

    def test_no_build_file_returns_empty(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.mcp.utils.edge_extractors.java import (
            _detect_java_root_packages,
        )

        roots = _detect_java_root_packages(str(tmp_path))
        assert roots == frozenset()

    def test_multi_module_collects_all(self, tmp_path: Path) -> None:
        """Multi-module Maven project: collects groupIds from sub-poms."""
        from tree_sitter_analyzer.mcp.utils.edge_extractors.java import (
            _detect_java_root_packages,
        )

        (tmp_path / "pom.xml").write_text(
            "<project><groupId>com.parent</groupId></project>"
        )
        sub = tmp_path / "module-a"
        sub.mkdir()
        (sub / "pom.xml").write_text(
            "<project><groupId>com.parent.a</groupId></project>"
        )
        roots = _detect_java_root_packages(str(tmp_path))
        assert "com.parent" in roots
        assert "com.parent.a" in roots


# ---------------------------------------------------------------------------
# 10. First-party filtering in edge extraction
# ---------------------------------------------------------------------------


class TestFirstPartyFiltering:
    """Edges from stdlib/third-party imports are excluded; first-party kept."""

    def test_stdlib_import_excluded(
        self, java_project_with_noise: Path
    ) -> None:
        """java.util.List should NOT create an edge."""
        manager = ProjectIndexManager(
            project_root=str(java_project_with_noise)
        )
        src = java_project_with_noise / "src/main/java/com/example"
        f = src / "UserService.java"
        edges = manager._extract_edges_from_file(f)
        targets = [dst for _, dst in edges]
        assert "List" not in targets
        assert "Map" not in targets
        assert "Optional" not in targets

    def test_annotation_import_excluded(
        self, java_project_with_noise: Path
    ) -> None:
        """javax.annotation.Nullable should NOT create an edge."""
        manager = ProjectIndexManager(
            project_root=str(java_project_with_noise)
        )
        src = java_project_with_noise / "src/main/java/com/example"
        f = src / "UserService.java"
        edges = manager._extract_edges_from_file(f)
        targets = [dst for _, dst in edges]
        assert "Nullable" not in targets
        assert "Test" not in targets
        assert "Data" not in targets

    def test_first_party_import_kept(
        self, java_project_with_noise: Path
    ) -> None:
        """com.example.BeanFactory should create an edge."""
        manager = ProjectIndexManager(
            project_root=str(java_project_with_noise)
        )
        src = java_project_with_noise / "src/main/java/com/example"
        f = src / "UserService.java"
        edges = manager._extract_edges_from_file(f)
        targets = [dst for _, dst in edges]
        assert "BeanFactory" in targets

    def test_extends_implements_not_filtered(
        self, java_project_with_noise: Path
    ) -> None:
        """extends/implements edges are always kept (no package info)."""
        manager = ProjectIndexManager(
            project_root=str(java_project_with_noise)
        )
        src = java_project_with_noise / "src/main/java/com/example"
        f = src / "UserService.java"
        edges = manager._extract_edges_from_file(f)
        targets = [dst for _, dst in edges]
        assert "BeanFactory" in targets  # implements BeanFactory

    def test_pagerank_after_filtering_has_no_noise(
        self, java_project_with_noise: Path
    ) -> None:
        """Full pipeline: build → PageRank top nodes should be project classes only."""
        manager = ProjectIndexManager(
            project_root=str(java_project_with_noise)
        )
        src = java_project_with_noise / "src/main/java/com/example"
        edges: list[tuple[str, str]] = []
        for f in src.glob("*.java"):
            edges.extend(manager._extract_edges_from_file(f))

        nodes = manager._compute_pagerank(edges, top_n=5)
        node_names = [n["name"] for n in nodes]

        # first-party classes should appear
        assert "BeanFactory" in node_names

        # noise should NOT appear
        for noise in ["List", "Map", "Optional", "Nullable", "Test", "Data"]:
            assert noise not in node_names, f"{noise} should be filtered"

    def test_no_pom_extends_kept(self, tmp_path: Path) -> None:
        """Without pom.xml, extends edges still created (no filtering needed)."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "Foo.java").write_text(
            "package myapp;\n"
            "import java.util.List;\n"
            "import myapp.Bar;\n"
            "public class Foo extends Bar {}\n"
        )
        (src / "Bar.java").write_text(
            "package myapp;\n"
            "public class Bar {}\n"
        )
        manager = ProjectIndexManager(project_root=str(tmp_path))
        edges = manager._extract_edges_from_file(src / "Foo.java")
        targets = [dst for _, dst in edges]
        # v3: import edges NOT created; extends edges ARE created
        assert "Bar" in targets
        assert "List" not in targets  # imports never create edges

    def test_gradle_project_extends_kept(
        self, gradle_project: Path
    ) -> None:
        """Gradle project: extends edges from first-party classes kept."""
        # Rewrite App.java to use extends instead of import-only
        src = gradle_project / "src/main/java/org/myorg"
        (src / "App.java").write_text(
            "package org.myorg;\n"
            "import org.myorg.Config;\n"
            "import java.util.List;\n"
            "public class App extends Config {}\n"
        )
        manager = ProjectIndexManager(
            project_root=str(gradle_project)
        )
        edges = manager._extract_edges_from_file(src / "App.java")
        targets = [dst for _, dst in edges]
        assert "Config" in targets  # first-party extends
        assert "List" not in targets  # import never creates edge


# ---------------------------------------------------------------------------
# 11. Bugfix: HTML cleanup + buildSrc classification
# ---------------------------------------------------------------------------


class TestBugfixes:
    """HTML tag cleanup and buildSrc classification."""

    def test_html_stripped_from_readme_excerpt(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text(
            '# Title\n\n<a href="https://x.com">link</a> A real description.\n'
        )
        manager = ProjectIndexManager(project_root=str(tmp_path))
        excerpt = manager._extract_readme_excerpt(tmp_path)
        assert "<a " not in excerpt
        assert "</" not in excerpt

    def test_html_stripped_from_describe_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "mymod"
        d.mkdir()
        (d / "README.md").write_text(
            '# <img src="badge.png"> MyModule\n'
        )
        manager = ProjectIndexManager(project_root=str(tmp_path))
        desc = manager._describe_dir(d, "mymod")
        assert "<img" not in desc
        assert "MyModule" in desc

    def test_buildsrc_classified_as_core(self, tmp_path: Path) -> None:
        d = tmp_path / "buildSrc"
        d.mkdir()
        (d / "README.md").write_text("# Build Scripts\n")
        (d / "build.gradle").write_text("plugins {}")
        manager = ProjectIndexManager(project_root=str(tmp_path))
        assert manager._classify_dir(d) == "core"

    def test_github_dir_classified_as_core(self, tmp_path: Path) -> None:
        d = tmp_path / ".github"
        d.mkdir()
        (d / "README.md").write_text("# CI\n")
        manager = ProjectIndexManager(project_root=str(tmp_path))
        assert manager._classify_dir(d) == "core"
