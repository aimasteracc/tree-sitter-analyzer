"""change-impact 逐文件校验索引依赖图的行为测试（Issue #1591）。"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

from tests.unit._ast_cache_helpers import legacy_cache
from tree_sitter_analyzer.cache.schema import CURRENT_SCHEMA_VERSION
from tree_sitter_analyzer.core.parser import Parser
from tree_sitter_analyzer.mcp.tools.utils import change_impact_analysis as analysis
from tree_sitter_analyzer.mcp.tools.utils import change_impact_index_graph as ig
from tree_sitter_analyzer.mcp.tools.utils.change_impact_cached_graph import (
    CachedDependencyGraph,
)
from tree_sitter_analyzer.project_graph import DependencyGraph

_FIXTURE = {
    "pkg/__init__.py": "",
    "pkg/sub.py": "VALUE = 1\n",
    "pkg/b.py": "def helper():\n    return 1\n",
    "pkg/a.py": (
        "from .b import helper\n"
        "from . import sub as alias\n"
        "import pkg.sub as dotted\n\n\n"
        "def run():\n    return helper() + alias.VALUE + dotted.VALUE\n"
    ),
    "pkg/selfref.py": "import pkg.selfref\n",
    "pkg/dyn.py": (
        "import importlib\n\nfrom .b import helper\n\n"
        "loader = importlib.import_module\nmod = loader('pkg.sub')\n"
    ),
    "web/util.js": "export const x = 1;\n",
    "web/app.js": "import { x } from './util';\nconst y = require('./util');\n",
    "tests/test_b.py": (
        "from pkg.b import helper\n\n\ndef test_helper():\n    assert helper() == 1\n"
    ),
    "tests/test_sub.py": (
        "from pkg import sub\n\n\ndef test_value():\n    assert sub.VALUE == 1\n"
    ),
}
_EDITED = "pkg/b.py"


def _write_fixture(root: Path) -> None:
    for rel, text in _FIXTURE.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _index_project(root: Path) -> None:
    cache = legacy_cache(str(root))
    try:
        cache.index_project(max_files=50)
    finally:
        cache.close()


def _edit(root: Path) -> None:
    (root / _EDITED).write_text("def helper():\n    return 2\n", encoding="utf-8")


def _git_commit(root: Path) -> None:
    for command in (
        ["git", "init", "-q"],
        ["git", "add", "."],
        [
            "git",
            "-c",
            "user.name=TSA Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "baseline",
        ],
    ):
        subprocess.run(command, cwd=root, check=True, capture_output=True)


@pytest.fixture
def indexed_edited(tmp_path: Path) -> Path:
    _write_fixture(tmp_path)
    _index_project(tmp_path)
    _edit(tmp_path)
    return tmp_path


@pytest.fixture
def git_indexed_edited(tmp_path: Path) -> Path:
    # 先提交再建索引，索引库不进入 git，diff 只包含被编辑文件。
    _write_fixture(tmp_path)
    _git_commit(tmp_path)
    _index_project(tmp_path)
    _edit(tmp_path)
    return tmp_path


def test_indexed_impact_graph_parses_only_the_edited_file(indexed_edited, monkeypatch):
    # Issue #1591：已索引项目只改一个文件时，导入图只能完整解析这个文件，
    # 也不能再为全量内容缓存键重读整个项目。
    parsed: list[str] = []
    original = Parser.parse_file

    def counting_parse(self, file_path, language):
        parsed.append(Path(file_path).relative_to(indexed_edited).as_posix())
        return original(self, file_path, language)

    key_calls: list[str] = []
    monkeypatch.setattr(Parser, "parse_file", counting_parse)
    monkeypatch.setattr(
        DependencyGraph,
        "_cache_key_for",
        staticmethod(lambda root: key_calls.append(root)),
    )
    graph = analysis._load_dependency_graph(str(indexed_edited))
    # os.walk 顺序随平台而异，按路径排序后精确比对。
    assert sorted(parsed) == [_EDITED, "pkg/dyn.py"]
    assert key_calls == []
    assert graph.dependents_of(_EDITED) == ["pkg/a.py", "pkg/dyn.py", "tests/test_b.py"]


def test_verified_index_graph_matches_source_graph(indexed_edited):
    # Issue #1591：索引证据与源码重建的节点、边（含 #1557 子模块边与自导入边）完全一致。
    verified = ig.load_verified_index_graph(str(indexed_edited))
    source = DependencyGraph(str(indexed_edited))
    assert (verified.nodes(), verified.edges()) == (source.nodes(), source.edges())


def test_verified_index_graph_reports_evidence_counts(indexed_edited):
    # Issue #1591：被编辑文件与动态加载文件从源码解析，其余 8 个文件复用索引。
    graph = ig.load_verified_index_graph(str(indexed_edited))
    assert ig.dependency_graph_provenance(graph) == {
        "source": "index+source",
        "index_files": 8,
        "source_files": 2,
    }


def test_impact_output_identical_to_source_build(git_indexed_edited, monkeypatch):
    # Issue #1591：测试计划、验证命令与 call_graph_impact 与源码重建逐字相同。
    from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool

    # 两次运行都不自动同步索引，保证二者看到同一份索引状态。
    monkeypatch.setattr(analysis, "_ensure_ast_cache", lambda *_args: None)
    tool = ChangeImpactTool(str(git_indexed_edited))
    args = {"mode": "diff", "output_format": "json"}
    indexed = asyncio.run(tool.execute(args))
    monkeypatch.setattr(analysis, "load_verified_index_graph", lambda _root: None)
    rebuilt = asyncio.run(tool.execute(args))
    assert indexed.pop("dependency_graph")["source"] == "index+source"
    assert rebuilt.pop("dependency_graph")["source"] == "source"
    assert indexed == rebuilt
    assert indexed["tests_to_run"] == ["tests/test_b.py"]


def test_compact_impact_reports_graph_source(git_indexed_edited):
    # Issue #1591：默认紧凑输出同样如实说明导入图证据来源。
    from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool

    result = asyncio.run(
        ChangeImpactTool(str(git_indexed_edited)).execute(
            {"mode": "diff", "output_format": "json", "agent_summary_only": True}
        )
    )
    assert result["dependency_graph"] == {
        "source": "index+source",
        "index_files": 8,
        "source_files": 2,
    }


def test_load_dependency_graph_rebuilds_from_source_without_index(tmp_path):
    _write_fixture(tmp_path)
    graph = analysis._load_dependency_graph(str(tmp_path))
    assert ig.dependency_graph_provenance(graph) == {
        "source": "source",
        "index_files": 0,
        "source_files": 10,
    }


def test_load_dependency_graph_falls_back_when_index_graph_raises(
    indexed_edited, monkeypatch
):
    def broken(_root):
        raise RuntimeError("boom")

    monkeypatch.setattr(analysis, "load_verified_index_graph", broken)
    graph = analysis._load_dependency_graph(str(indexed_edited))
    assert ig.dependency_graph_provenance(graph)["source"] == "source"


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("none", ("unavailable", 0)),
        ("certified", ("certified_index", 2)),
        ("double", ("unknown", 0)),
    ],
)
def test_provenance_labels_non_verified_graphs(tmp_path, kind, expected):
    graph = {
        "none": None,
        "certified": CachedDependencyGraph(str(tmp_path), {"a.py", "b.py"}),
        "double": object(),
    }[kind]
    source, index_files = expected
    assert ig.dependency_graph_provenance(graph) == {
        "source": source,
        "index_files": index_files,
        "source_files": 0,
    }


def test_unmodified_index_uses_index_for_every_file(tmp_path):
    (tmp_path / "a.py").write_text("import b\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("value = 1\n", encoding="utf-8")
    _index_project(tmp_path)
    graph = ig.load_verified_index_graph(str(tmp_path))
    assert ig.dependency_graph_provenance(graph) == {
        "source": "index",
        "index_files": 2,
        "source_files": 0,
    }


def test_preserved_mtime_rewrite_is_reparsed(tmp_path):
    # Issue #1591：等长、等 mtime 的改写必须由内容哈希发现，不能沿用旧索引行。
    importer = tmp_path / "a.py"
    importer.write_text("import b\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("value = 2\n", encoding="utf-8")
    _index_project(tmp_path)
    before = importer.stat()
    importer.write_text("import c\n", encoding="utf-8")
    os.utime(importer, ns=(before.st_atime_ns, before.st_mtime_ns))
    graph = ig.load_verified_index_graph(str(tmp_path))
    assert graph.dependencies_of("a.py") == ["c.py"]


def test_unreadable_source_is_treated_as_changed(indexed_edited, monkeypatch):
    def unreadable(_path):
        raise OSError("gone")

    monkeypatch.setattr(ig, "file_content_hash", unreadable)
    graph = ig.load_verified_index_graph(str(indexed_edited))
    assert ig.dependency_graph_provenance(graph)["source_files"] == 10


def test_verified_graph_requires_project_root():
    assert ig.load_verified_index_graph(None) is None


def test_verified_graph_requires_index(tmp_path):
    _write_fixture(tmp_path)
    assert ig.load_verified_index_graph(str(tmp_path)) is None


@pytest.mark.parametrize("version", [1, CURRENT_SCHEMA_VERSION + 1])
def test_verified_graph_rejects_incompatible_schema(indexed_edited, version):
    conn = sqlite3.connect(indexed_edited / ".ast-cache" / "index.db")
    try:
        conn.execute("DELETE FROM ast_schema_version")
        conn.execute(
            "INSERT INTO ast_schema_version(version, applied_at, description) "
            "VALUES (?, 0, 'test')",
            (version,),
        )
        conn.commit()
    finally:
        conn.close()
    assert ig.load_verified_index_graph(str(indexed_edited)) is None


def test_verified_graph_rejects_unreadable_index(indexed_edited, monkeypatch):
    def broken_connect(*_args, **_kwargs):
        raise sqlite3.OperationalError("locked")

    monkeypatch.setattr(ig.sqlite3, "connect", broken_connect)
    assert ig.load_verified_index_graph(str(indexed_edited)) is None


def test_index_row_imports_skip_empty_text():
    row = {"imports_json": '[{"text": ""}, "from .b import helper"]'}
    imports = ig._imports_from_index_row(Parser(), row, "python")
    assert [imp["module_name"] for imp in imports] == [".b"]
