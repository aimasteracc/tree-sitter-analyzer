"""RFC-0039 slice 1：按文件分组的两级 Merkle 认证根（manifest v3）。"""

from __future__ import annotations

import sqlite3
import time

import pytest

from tree_sitter_analyzer import index_certification_tree as tree_mod

_DEADLINE = 60.0


def _deadline() -> float:
    return time.monotonic() + _DEADLINE


def _db(rows: list[tuple[str | None, str]]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE edges (file_path TEXT, callee_name TEXT)")
    conn.execute("CREATE TABLE ast_symbol_comments (symbol_id INTEGER, text TEXT)")
    conn.executemany("INSERT INTO edges VALUES (?, ?)", rows)
    conn.execute("INSERT INTO ast_symbol_comments VALUES (1, 'c')")
    return conn


def _root(conn: sqlite3.Connection) -> str:
    return tree_mod.certification_root(conn, "/root", deadline=_deadline())


def test_root_is_independent_of_insertion_order() -> None:
    rows = [("a.py", "f"), ("b.py", "g"), ("a.py", "h")]
    first, second = _db(rows), _db(list(reversed(rows)))
    assert _root(first).startswith(tree_mod.ROOT_PREFIX)
    assert _root(first) == _root(second)


def test_one_files_change_changes_only_its_leaf() -> None:
    before = _db([("a.py", "f"), ("b.py", "g")])
    after = _db([("a.py", "f"), ("b.py", "changed")])
    old = tree_mod.full_tree(before, deadline=_deadline())
    new = tree_mod.full_tree(after, deadline=_deadline())
    changed = {
        key
        for key in old.leaves["edges"].keys() | new.leaves["edges"].keys()
        if old.leaves["edges"].get(key) != new.leaves["edges"].get(key)
    }
    assert changed == {tree_mod.group_key("b.py")}
    assert old.leaves["ast_symbol_comments"] == new.leaves["ast_symbol_comments"]
    assert _root(before) != _root(after)


def test_group_keys_distinguish_null_from_text() -> None:
    tree = tree_mod.full_tree(_db([(None, "f"), ("None", "g")]), deadline=_deadline())
    assert len(tree.leaves["edges"]) == 2
    assert tree_mod.group_key(None) != tree_mod.group_key("None")
    # 没有 file_path 列的表整表为一组。
    assert list(tree.leaves["ast_symbol_comments"]) == [tree_mod.WHOLE_TABLE_GROUP]


def test_control_leaf_and_fts_tables_are_outside_the_root() -> None:
    conn = _db([("a.py", "f")])
    baseline = _root(conn)
    conn.execute("CREATE TABLE ast_writer_state (id INTEGER, revision INTEGER)")
    conn.execute("INSERT INTO ast_writer_state VALUES (1, 7)")
    conn.execute(tree_mod.LEAF_TABLE_SQL)
    conn.execute(f"INSERT INTO {tree_mod.LEAF_TABLE} VALUES ('x', x'00', x'00')")
    try:
        conn.execute("CREATE VIRTUAL TABLE ast_symbols_fts USING fts5(name, file_path)")
    except sqlite3.OperationalError:  # pragma: no cover - SQLite without FTS5
        pytest.skip("FTS5 unavailable")
    conn.execute("INSERT INTO ast_symbols_fts VALUES ('f', 'a.py')")
    assert _root(conn) == baseline
    names = {t.name for t in tree_mod.rooted_tables(conn, _deadline())}
    assert names == {"edges", "ast_symbol_comments"}


def test_root_frames_the_canonical_root_and_schema() -> None:
    conn = _db([("a.py", "f")])
    other_root = tree_mod.certification_root(conn, "/other", deadline=_deadline())
    assert _root(conn) != other_root
    conn.execute("ALTER TABLE edges ADD COLUMN extra TEXT")
    assert _root(conn) != _root(_db([("a.py", "f")]))


def test_stored_leaves_fold_to_the_stamped_root() -> None:
    conn = _db([("a.py", "f"), ("b.py", "g")])
    tree = tree_mod.full_tree(conn, deadline=_deadline())
    tree_mod.store_leaves(conn, tree)
    stored: dict[str, dict[bytes, bytes]] = {}
    for table, key, leaf in conn.execute(
        f"SELECT tbl, grp, leaf FROM {tree_mod.LEAF_TABLE}"
    ):
        stored.setdefault(table, {})[bytes(key)] = bytes(leaf)
    assert stored == tree.leaves
    refolded = tree_mod.fold_root(
        "/root", tree_mod.CertificationTree(tree.tables, stored), _deadline()
    )
    assert refolded == _root(conn)


@pytest.mark.parametrize(
    ("version", "index", "valid"),
    [
        (2, "sha256:" + "a" * 64, True),
        (3, "merkle:" + "a" * 64, True),
        (3, "sha256:" + "a" * 64, False),
        (2, "merkle:" + "a" * 64, False),
        (4, "merkle:" + "a" * 64, False),
    ],
)
def test_manifest_versions_pair_with_their_commitment(version, index, valid) -> None:
    from tree_sitter_analyzer.index_snapshot_schema import validate_manifest_scalars

    manifest = {
        "canonical_root": "/root",
        "source_fingerprint": "sha256:" + "b" * 64,
        "index_fingerprint": index,
        "file_count": 1,
        "source_scope_descriptor": "{}",
        "manifest_version": version,
    }
    if valid:
        validate_manifest_scalars(manifest)  # type: ignore[arg-type]
    else:
        with pytest.raises(ValueError, match="INDEX_MANIFEST_INVALID"):
            validate_manifest_scalars(manifest)  # type: ignore[arg-type]


def test_index_commitment_dispatches_on_version() -> None:
    from tree_sitter_analyzer.index_snapshot_schema import (
        index_commitment,
        index_fingerprint,
    )

    conn = _db([("a.py", "f")])
    assert index_commitment(conn, "/root", 3, deadline=_deadline()) == _root(conn)
    assert index_commitment(
        conn, "/root", 2, deadline=_deadline()
    ) == index_fingerprint(conn, "/root", deadline=_deadline())


def _sync(root):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.incremental_sync import IncrementalSync

    cache = ASTCache(str(root))
    try:
        return IncrementalSync(cache).sync()
    finally:
        cache.close()


@pytest.fixture
def project(tmp_path):
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    auto_index_guard.reset()
    (tmp_path / "a.py").write_text("def a():\n    return b()\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def b():\n    return 1\n", encoding="utf-8")
    yield tmp_path
    auto_index_guard.reset()


def _published(root) -> sqlite3.Connection:
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_location

    location = resolve_index_location(str(root))
    return sqlite3.connect(f"file:{location.path}?mode=ro", uri=True)


def test_a_refresh_stamps_v3_and_readers_certify_it(project) -> None:
    import os

    from tree_sitter_analyzer.index_snapshot import read_existing_snapshot

    _sync(project)
    conn = _published(project)
    try:
        version, index = conn.execute(
            "SELECT manifest_version, index_fingerprint FROM ast_index_snapshot_manifest"
        ).fetchone()
        assert (version, index) == (
            3,
            tree_mod.certification_root(
                conn, os.path.realpath(project), deadline=_deadline()
            ),
        )
        # 存放的叶正是数据库内容的完整认证树。
        stored = {
            (str(table), bytes(key)): bytes(leaf)
            for table, key, leaf in conn.execute(
                f"SELECT tbl, grp, leaf FROM {tree_mod.LEAF_TABLE}"
            )
        }
        full = tree_mod.full_tree(conn, deadline=_deadline())
        assert stored == {
            (table, key): leaf
            for table, groups in full.leaves.items()
            for key, leaf in groups.items()
        }
    finally:
        conn.close()
    snapshot = read_existing_snapshot(str(project))
    assert (snapshot.completeness, snapshot.index_fingerprint) == ("complete", index)


def test_a_v2_manifest_is_still_certified(project, monkeypatch) -> None:
    # 旧写者盖的 v2 manifest（扁平指纹）照常被读者认证。
    from tree_sitter_analyzer import index_snapshot_schema as schema
    from tree_sitter_analyzer.index_snapshot import read_existing_snapshot

    monkeypatch.setattr(tree_mod, "MANIFEST_VERSION", 2)
    monkeypatch.setattr(
        schema,
        "stamp_commitment",
        lambda conn, root, *, deadline: (
            schema.index_fingerprint(conn, root, deadline=deadline),
            tree_mod.CertificationTree(()),
        ),
    )
    _sync(project)
    conn = _published(project)
    try:
        version, index = conn.execute(
            "SELECT manifest_version, index_fingerprint FROM ast_index_snapshot_manifest"
        ).fetchone()
    finally:
        conn.close()
    assert version == 2 and index.startswith("sha256:")
    snapshot = read_existing_snapshot(str(project))
    assert (snapshot.completeness, snapshot.index_fingerprint) == ("complete", index)


def test_full_tree_keeps_the_fingerprint_row_budget(monkeypatch) -> None:
    from tree_sitter_analyzer import index_snapshot_schema as schema

    # 每张表各自不超（1 行与 2 行），跨表累计 3 行超出预算。
    monkeypatch.setattr(schema, "_FINGERPRINT_ROW_BUDGET", 2)
    with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_BUDGET"):
        tree_mod.full_tree(_db([("a.py", "f"), ("b.py", "g")]), deadline=_deadline())
