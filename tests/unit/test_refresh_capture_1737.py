"""#1737：1 文件刷新少做的源码扫描与复核——且发布安全性不变（RFC-0030 / RFC-0032）。"""

from __future__ import annotations

import os
import random
import sqlite3
from types import SimpleNamespace

import pathspec
import pytest

from tree_sitter_analyzer import ignore_rules

# --- 盖章：发布路由用候选行，不再现场扫描 -------------------------------------


def _entry(
    rel: str, language: str = "python", content_hash: str = ""
) -> SimpleNamespace:
    return SimpleNamespace(
        rel_path=rel,
        language=language,
        fingerprint=SimpleNamespace(content_hash=content_hash),
    )


def test_candidate_rows_need_the_publisher_route_and_every_digest() -> None:
    from tree_sitter_analyzer.incremental_sync_support import publication_candidate_rows

    snapshot = SimpleNamespace(selected_entries=[_entry("a.py"), _entry("b.py")])
    digests = {"a.py": "sha256:a", "b.py": "sha256:b"}
    publisher = SimpleNamespace(
        _publication_rechecks_sources=True, _bound_source_digests=digests
    )
    assert publication_candidate_rows(publisher, snapshot) == frozenset(
        {("a.py", "sha256:a", "python"), ("b.py", "sha256:b", "python")}
    )
    # 不是发布路由、没有候选、缺摘要或缺语言：照常现场捕获。
    assert (
        publication_candidate_rows(
            SimpleNamespace(_bound_source_digests=digests), snapshot
        )
        is None
    )
    assert publication_candidate_rows(publisher, None) is None
    no_digests = SimpleNamespace(
        _publication_rechecks_sources=True, _bound_source_digests=None
    )
    assert publication_candidate_rows(no_digests, snapshot) is None
    partial = SimpleNamespace(
        _publication_rechecks_sources=True, _bound_source_digests={"a.py": "sha256:a"}
    )
    assert publication_candidate_rows(partial, snapshot) is None
    unknown = SimpleNamespace(selected_entries=[_entry("a.py", language="")])
    assert publication_candidate_rows(publisher, unknown) is None


def _project(tmp_path):
    (tmp_path / "a.py").write_text("def a():\n    return b()\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def b():\n    return 1\n", encoding="utf-8")
    return tmp_path


@pytest.fixture(autouse=True)
def _fresh_guard():
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    auto_index_guard.reset()
    yield
    auto_index_guard.reset()


def _sync(root):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.incremental_sync import IncrementalSync

    cache = ASTCache(str(root))
    try:
        return IncrementalSync(cache).sync()
    finally:
        cache.close()


def _touch(path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    info = os.stat(path)
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))


# slow_ok：两次真实的版本路由同步（捕获、构建、盖章、发布复核）。
@pytest.mark.slow_ok
# slow_ok：两次真实的版本路由同步（捕获、构建、盖章、发布复核）。
@pytest.mark.slow_ok
def test_the_publisher_route_stamps_without_a_second_source_capture(
    tmp_path, monkeypatch
) -> None:
    from tree_sitter_analyzer import portable_source_snapshot
    from tree_sitter_analyzer.index_snapshot import read_existing_snapshot

    root = _project(tmp_path)
    _sync(root)
    calls: list[str] = []
    original = portable_source_snapshot.capture_portable_source_snapshot

    def counting(*args, **kwargs):
        calls.append("capture")
        return original(*args, **kwargs)

    monkeypatch.setattr(
        portable_source_snapshot, "capture_portable_source_snapshot", counting
    )
    _touch(root / "b.py", "def b():\n    return 2\n")
    result = _sync(root)

    assert (result.published, result.manifest_certification_failed) == (True, False)
    assert calls == []  # 盖章没有再扫描一遍源码
    # 读者仍独立复核当前源码：认证完整。
    assert read_existing_snapshot(str(root)).completeness == "complete"


# slow_ok：两次真实的版本路由同步（捕获、构建、盖章、发布复核）。
@pytest.mark.slow_ok
# slow_ok：两次真实的版本路由同步，第二次在发布复核处被拒绝。
@pytest.mark.slow_ok
def test_a_same_metadata_rewrite_before_publish_is_still_rejected(
    tmp_path, monkeypatch
) -> None:
    # 盖章不再现场扫描；在盖章与发布之间、保持 mtime 与大小不变的改写，必须由发布复核
    # （逐文件内容摘要）拒绝，活动版本不变。
    from tree_sitter_analyzer.cache import generation_store

    root = _project(tmp_path)
    _sync(root)
    target = root / "b.py"
    _touch(target, "def b():\n    return 2\n")
    original_seal = generation_store.GenerationStore.seal

    def seal_then_rewrite(self, selector):
        original_seal(self, selector)
        info = os.stat(target)
        target.write_text("def b():\n    return 3\n", encoding="utf-8")  # 同样长度
        os.utime(target, ns=(info.st_atime_ns, info.st_mtime_ns))

    monkeypatch.setattr(generation_store.GenerationStore, "seal", seal_then_rewrite)
    with pytest.raises(generation_store.SourceChanged):
        _sync(root)


def test_the_stamp_rejects_candidate_rows_that_differ_from_the_index(
    monkeypatch,
) -> None:
    from tree_sitter_analyzer import index_snapshot_schema as schema
    from tree_sitter_analyzer.index_certification_tree import CertificationTree

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        schema.SCHEMA_V13_INDEX_SNAPSHOT
        + "CREATE TABLE ast_index(file_path TEXT, content_hash TEXT, language TEXT);"
        + "INSERT INTO ast_index VALUES ('a.py', 'sha256:a', 'python');"
    )
    monkeypatch.setattr(schema, "strict_call_graph_marker", lambda _conn: True)
    monkeypatch.setattr(
        schema,
        "stamp_commitment",
        lambda *_a, **_k: ("merkle:" + "a" * 64, CertificationTree(())),
    )
    with pytest.raises(sqlite3.OperationalError, match="CANDIDATE_ROWS_DIFFER"):
        schema.stamp_full_index_manifest(
            conn, "/root", candidate_rows=frozenset({("a.py", "sha256:x", "python")})
        )
    rows = conn.execute("SELECT COUNT(*) FROM ast_index_snapshot_manifest").fetchone()
    assert rows[0] == 0
    # 与索引一致的候选行：盖章成功，且不做现场源码捕获。
    schema.stamp_full_index_manifest(
        conn, "/root", candidate_rows=frozenset({("a.py", "sha256:a", "python")})
    )
    assert tuple(
        conn.execute(
            "SELECT file_count, manifest_version FROM ast_index_snapshot_manifest"
        ).fetchone()
    ) == (1, 3)


# --- 校验：发布路由不再逐文件 realpath 第二遍 ---------------------------------


def test_validation_without_path_resolution_keeps_the_structural_checks(
    tmp_path,
) -> None:
    from tree_sitter_analyzer.indexing_snapshot import (
        build_index_candidate_snapshot,
        validate_index_candidate_snapshot,
    )

    root = _project(tmp_path)
    from tree_sitter_analyzer.constants import EXCLUDE_DIRS
    from tree_sitter_analyzer.indexing_snapshot import walk_index_candidate_entries
    from tree_sitter_analyzer.project_graph import _language_from_ext

    snapshot = build_index_candidate_snapshot(
        str(root),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda base: walk_index_candidate_entries(
            base, excluded_dir_names=frozenset(EXCLUDE_DIRS)
        ),
        language_fn=_language_from_ext,
    )
    validate_index_candidate_snapshot(str(root), 10, snapshot, resolve_paths=False)
    with pytest.raises(ValueError, match="max_files"):
        validate_index_candidate_snapshot(str(root), 11, snapshot, resolve_paths=False)
    with pytest.raises(ValueError, match="different project root"):
        validate_index_candidate_snapshot(
            str(tmp_path / "elsewhere"), 10, snapshot, resolve_paths=False
        )


# --- gitignore：合并正则快速路径与逐模式判定完全一致 ---------------------------


def _naive(rel_path: str, rules, *, directory: bool) -> bool:
    ignored = False
    posix = rel_path.replace(os.sep, "/")
    for base, spec in rules:
        if base:
            if not posix.startswith(base + "/"):
                continue
            target = posix[len(base) + 1 :]
        else:
            target = posix
        if not target:
            continue
        result = spec.check_file(target + ("/" if directory else ""))
        if result.include is not None:
            ignored = bool(result.include)
    return ignored


_PATTERNS = [
    "*.pyc",
    "build/",
    "!keep.pyc",
    "/root.txt",
    "**/x/**",
    "docs/*.md",
    "!docs/a.md",
    "*.log",
    "tmp*",
    "a/**/b",
    "\\#lit",
    "dir/",
    "!dir/sub/",
    "*~",
    "[ab].txt",
    "",
    "# comment",
]
_NAMES = [
    "a.pyc",
    "keep.pyc",
    "root.txt",
    "x",
    "docs",
    "a.md",
    "b.md",
    "build",
    "tmp1",
    "b",
    "dir",
    "sub",
    "file~",
    "a.txt",
    "c.txt",
    "#lit",
    "run.log",
    "src",
]


def test_the_fast_path_agrees_with_pathspec_on_random_trees() -> None:
    rng = random.Random(1737)
    for _ in range(200):
        rules = []
        for base in ("", "pkg", "pkg/inner"):
            if rng.random() < 0.7:
                lines = rng.sample(_PATTERNS, rng.randint(1, 8))
                rules.append((base, pathspec.GitIgnoreSpec.from_lines(lines)))
        for _ in range(30):
            depth = rng.randint(1, 4)
            path = "/".join(rng.choice(["pkg", "inner", *_NAMES]) for _ in range(depth))
            directory = rng.random() < 0.3
            assert ignore_rules.is_gitignored(
                path, rules, directory=directory
            ) == _naive(path, rules, directory=directory), (
                path,
                directory,
                [(b, [p.pattern for p in s.patterns]) for b, s in rules],
            )


def test_rule_files_are_reused_by_content(tmp_path) -> None:
    (tmp_path / ".gitignore").write_text("*.log\n", encoding="utf-8")
    first = ignore_rules.load_ignore_rules(str(tmp_path), "", [])
    second = ignore_rules.load_ignore_rules(str(tmp_path), "", [])
    assert first[0][1] is second[0][1]
    (tmp_path / ".gitignore").write_text("*.txt\n", encoding="utf-8")
    third = ignore_rules.load_ignore_rules(str(tmp_path), "", [])
    assert third[0][1] is not first[0][1]
    assert ignore_rules.is_gitignored("a.txt", third, directory=False) is True
    assert ignore_rules.is_gitignored("a.log", third, directory=False) is False


def test_an_uncombinable_spec_falls_back_to_pathspec() -> None:
    spec = pathspec.GitIgnoreSpec.from_lines(["*.log"])
    spec._tsa_any_pattern = None  # type: ignore[attr-defined]
    assert ignore_rules.is_gitignored("a.log", [("", spec)], directory=False) is True


# --- 解析上下文：各语言在第一次需要时才构建 -----------------------------------


def test_language_contexts_are_built_once_and_only_on_demand() -> None:
    from tree_sitter_analyzer.synapse_resolver._context import LazyLanguageContexts

    built: list[str] = []

    def builder(name: str, value: object):
        def build():
            built.append(name)
            return value

        return build

    contexts = LazyLanguageContexts(
        {"typescript": builder("typescript", "ts"), "java": builder("java", None)}
    )
    assert built == []
    assert contexts.get("typescript") == "ts"
    assert contexts.get("typescript") == "ts"
    assert built == ["typescript"]
    assert contexts.get("java") is None and "java" not in contexts
    assert contexts.get("missing", "fallback") == "fallback"
    assert contexts.setdefault("java", "explicit") == "explicit"
    assert contexts.setdefault("typescript", "other") == "ts"
    assert built == ["typescript", "java"]
