"""有界回收：写入后版本数有上限，活动与被钉版本保留，被杀构建者的孤儿被删除。

RFC-0032 slice 6（#1554 所有者决定：按数量与年龄，钉住或活动中永不回收）。
rfcs/evidence/0032-feasibility E3（2026-10-13）：被杀构建者留下孤儿目录且从不回收。
"""

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest


@pytest.fixture
def root(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "a.py").write_text("def alpha_0():\n    return 0\n", encoding="utf-8")
    return str(project)


def _storage(root):
    return Path(root) / ".ast-cache" / "index-generations"


def _ids(root):
    return sorted(entry.name for entry in (_storage(root) / "generations").iterdir())


def _active(root):
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_location

    return resolve_index_location(root).path.parent.name


def _write(root, n):  # 一次真实默认定位符写入：改 a.py 后单文件索引并发布
    from tree_sitter_analyzer.ast_cache import ASTCache

    path = os.path.join(root, "a.py")
    Path(path).write_text(f"def alpha_{n}():\n    return {n}\n", encoding="utf-8")
    info = os.stat(path)
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + n * 1_000_000_000))
    cache = ASTCache(root)
    try:
        assert cache.index_file(path)["status"] == "indexed"
    finally:
        cache.close()


def test_consecutive_writes_keep_generation_count_bounded(root):
    from tree_sitter_analyzer.cache.generation_retirement import RETAIN_COUNT

    for n in range(1, 9):
        _write(root, n)
    assert (len(_ids(root)), _active(root) in _ids(root)) == (1 + RETAIN_COUNT, True)


def test_pinned_generation_survives_until_reader_closes(root):
    from tree_sitter_analyzer.ast_cache import ASTCache

    _write(root, 1)
    pinned = _active(root)
    reader = ASTCache(root)
    try:
        reader.get_conn()
        for n in range(2, 8):
            _write(root, n)
        survived = pinned in _ids(root)
        rows = reader.get_conn().execute("SELECT COUNT(*) FROM ast_index").fetchone()[0]
    finally:
        reader.close()
    _write(root, 8)
    assert (survived, rows, pinned in _ids(root)) == (True, 1, False)


def test_live_unpublished_build_survives_other_writer(root):
    from tree_sitter_analyzer.cache.generation_indexing import project_store
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    _write(root, 1)
    store = project_store(root, make_source_scope_descriptor())
    building = store.begin(store.capture()).generation_id
    for n in range(2, 6):
        _write(root, n)
    assert building in _ids(root)


_KILLED_BUILDER = textwrap.dedent(
    """
    import os, signal, sys
    from tree_sitter_analyzer.cache.generation_indexing import project_store
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    store = project_store(sys.argv[1], make_source_scope_descriptor())
    print(store.begin(store.capture()).generation_id, flush=True)
    sys.stdin.readline()
    # 真实解释器在构建中途自行强杀（venv 启动器之下 kill 父进程杀不到它），模拟 E3。
    os.kill(os.getpid(), getattr(signal, "SIGKILL", signal.SIGTERM))
    """
)


@pytest.mark.slow_ok  # 真实子进程导入并被强杀，Windows 上启动即数秒。
def test_killed_mid_build_generation_is_removed_by_next_write(root):
    from tree_sitter_analyzer.cache.generation_pins import has_live_pin, pin_directory

    _write(root, 1)
    builder = subprocess.Popen(
        [sys.executable, "-c", _KILLED_BUILDER, root],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        orphan = builder.stdout.readline().strip()
        builder.stdin.write("\n")
        builder.stdin.flush()
        builder.wait(timeout=30)
    finally:
        builder.kill()
        builder.stdin.close()
        builder.stdout.close()
    pins, deadline = pin_directory(_storage(root), orphan), time.monotonic() + 10
    while has_live_pin(pins) and time.monotonic() < deadline:  # Windows 异步释放字节锁
        time.sleep(0.05)
    before = orphan in _ids(root)
    _write(root, 2)
    assert (before, orphan in _ids(root)) == (True, False)


def test_age_bound_retires_every_inactive_generation(root):
    from tree_sitter_analyzer.cache.generation_retirement import (
        RETAIN_AGE_S,
        retire_generations,
    )

    for n in range(1, 4):
        _write(root, n)
    active = _active(root)
    (_storage(root) / "generations" / ("d" * 32)).mkdir()  # 建目录后、建主库前被杀
    retire_generations(_storage(root), active, now=time.time() + RETAIN_AGE_S + 60)
    assert _ids(root) == [active]


def test_unverified_directories_are_never_removed(root, tmp_path):
    from tree_sitter_analyzer.cache.generation_retirement import retire_generations

    _write(root, 1)
    active = _active(root)
    stranger = _storage(root) / "generations" / "not-a-generation"
    stranger.mkdir()
    (stranger / "index.db").write_bytes(b"")
    (_storage(root) / "generations" / ("e" * 32)).write_bytes(b"")  # 文件而非目录
    (_storage(root) / "generations" / ("c" * 32) / "index.db").mkdir(parents=True)
    expected = sorted([active, "not-a-generation", "e" * 32, "c" * 32])
    if os.name == "posix":  # Windows 建符号链接需特权
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "index.db").write_bytes(b"keep")
        (_storage(root) / "generations" / ("f" * 32)).symlink_to(outside, True)
        expected = sorted([*expected, "f" * 32])
    retire_generations(_storage(root), active, now=time.time() + 10**9)
    assert _ids(root) == expected


def test_failed_deletion_keeps_generation_sealed(root, monkeypatch):
    from tree_sitter_analyzer.cache import generation_retirement as owner

    _write(root, 1)
    _write(root, 2)
    active, before, gens = _active(root), _ids(root), _storage(root) / "generations"
    busy = PermissionError("open elsewhere")
    monkeypatch.setattr(
        owner, "clear_read_only_tree", lambda _d: (_ for _ in ()).throw(busy)
    )
    removed = owner.retire_generations(_storage(root), active, now=time.time() + 10**9)
    writable = [
        os.access(gens / g / "index.db", os.W_OK) for g in before if g != active
    ]
    tombstones = list((_storage(root) / "pins").glob("*/retiring"))
    expected = ([], before, [False] * (len(before) - 1), [])
    assert (removed, _ids(root), writable, tombstones) == expected
