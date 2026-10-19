"""#1700：索引指纹 / 投影判定备忘录的落盘层——跨进程复用，读时按完整键复核。

“新进程”在这里用清空进程内备忘录来模拟：之后的捕获只能从落盘记录取值或重算。
每个键成分都做过变异检验：强制“总是命中”会让这里至少一个测试变红。
"""

from __future__ import annotations

import marshal
import sqlite3
import sys
from pathlib import Path

import pytest

from tree_sitter_analyzer import index_fingerprint_memo as memo
from tree_sitter_analyzer import index_fingerprint_store as store

_FP = "sha256:" + "a" * 64
_OTHER_FP = "sha256:" + "b" * 64


@pytest.fixture(autouse=True)
def _isolated_memo():
    memo.clear_index_fingerprint_memo()
    yield
    memo.clear_index_fingerprint_memo()


@pytest.fixture
def root(tmp_path: Path) -> str:
    (tmp_path / ".ast-cache").mkdir()
    return str(tmp_path)


def _store_path(root: str) -> Path:
    return Path(root) / ".ast-cache" / store.DIR_NAME / store.FILE_NAME


# --------------------------------------------------------------------------- #
# 落盘层本身
# --------------------------------------------------------------------------- #


def test_a_stored_value_is_found_by_its_full_key(root: str) -> None:
    store.store(root, (root, "index.db:abc"), _FP)

    assert store.lookup(root, (root, "index.db:abc")) == _FP


@pytest.mark.parametrize(
    "other",
    [
        ("elsewhere", "index.db:abc"),  # 项目根
        ("ROOT", "index.db:abd"),  # 字节摘要
        ("ROOT", "index.db:abc", "index.db-wal:00"),  # 多出的 WAL 摘要
        ("symbol_projection_exact", "ROOT", "index.db:abc"),  # 判定种类
    ],
)
def test_every_key_element_is_compared(root: str, other: tuple[str, ...]) -> None:
    store.store(root, (root, "index.db:abc"), _FP)

    key = tuple(root if part == "ROOT" else part for part in other)
    assert store.lookup(root, key) is None


@pytest.mark.parametrize(
    ("module", "attribute"),
    [
        ("tree_sitter_analyzer.source_fingerprint", "source_fingerprint"),
        ("sys", "version"),
        ("sqlite3", "sqlite_version"),
    ],
)
def test_the_key_includes_code_and_runtime_versions(
    root: str, monkeypatch, module: str, attribute: str
) -> None:
    import importlib

    store.store(root, (root, "index.db:abc"), _FP)
    target = importlib.import_module(module)
    original = getattr(target, attribute)
    changed = (lambda: "other-code") if callable(original) else f"{original}-other"
    monkeypatch.setattr(target, attribute, changed)

    assert store.lookup(root, (root, "index.db:abc")) is None


def test_the_key_includes_the_format(root: str, monkeypatch) -> None:
    store.store(root, (root, "index.db:abc"), _FP)
    monkeypatch.setattr(store, "FORMAT", store.FORMAT + 1)

    assert store.lookup(root, (root, "index.db:abc")) is None


def test_values_that_are_not_fingerprints_or_verdicts_are_never_stored(
    root: str,
) -> None:
    for value in ("fp", "sha256:xyz", "2", ""):
        store.store(root, (root, value or "empty"), value)

    assert not _store_path(root).exists()
    store.store(root, (root, "verdict"), "1")
    assert store.lookup(root, (root, "verdict")) == "1"


def test_malformed_payloads_are_empty(root: str) -> None:
    store.store(root, (root, "k"), _FP)
    path = _store_path(root)
    wanted = store.stored_key((root, "k"))
    malformed = [
        (store.FORMAT, [(wanted, "not a fingerprint")]),
        (store.FORMAT, [(wanted,)]),
        (store.FORMAT, [(list(wanted), _FP)]),
        (store.FORMAT, [((*wanted[:-1], 7), _FP)]),
        (store.FORMAT, {wanted: _FP}),
        (store.FORMAT + 1, [(wanted, _FP)]),
        (store.FORMAT, [(wanted, _FP)], "extra"),
    ]
    for payload in malformed:
        path.write_bytes(marshal.dumps(payload))
        assert store.lookup(root, (root, "k")) is None, payload
    path.write_bytes(b"\x00not marshal")
    assert store.lookup(root, (root, "k")) is None


def test_the_store_is_bounded_and_keeps_the_newest(root: str, monkeypatch) -> None:
    monkeypatch.setattr(store, "MAX_ENTRIES", 3)
    for index in range(5):
        store.store(root, (root, f"k{index}"), _FP)

    assert [store.lookup(root, (root, f"k{i}")) for i in range(5)] == [
        None,
        None,
        _FP,
        _FP,
        _FP,
    ]


def test_a_rewritten_value_replaces_the_old_one(root: str) -> None:
    store.store(root, (root, "k"), _FP)
    store.store(root, (root, "k"), _OTHER_FP)

    assert store.lookup(root, (root, "k")) == _OTHER_FP
    assert len(marshal.loads(_store_path(root).read_bytes())[1]) == 1


def test_nothing_is_stored_without_an_ast_cache_directory(tmp_path: Path) -> None:
    store.store(str(tmp_path), (str(tmp_path), "k"), _FP)

    assert not (tmp_path / ".ast-cache").exists()
    assert store.lookup(str(tmp_path), (str(tmp_path), "k")) is None


def test_an_evidence_dir_that_is_a_file_disables_the_store(root: str) -> None:
    (Path(root) / ".ast-cache" / store.DIR_NAME).write_text("not a dir")

    store.store(root, (root, "k"), _FP)

    assert store.lookup(root, (root, "k")) is None


def test_a_write_failure_is_silent(root: str, monkeypatch) -> None:
    def refuse(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(store.os, "replace", refuse)

    store.store(root, (root, "k"), _FP)

    assert sorted(p.name for p in _store_path(root).parent.iterdir()) == []


@pytest.mark.parametrize("value", ["off", "0", "FALSE"])
def test_the_store_can_be_turned_off(root: str, monkeypatch, value: str) -> None:
    monkeypatch.setenv(store.ENV_VAR, value)

    store.store(root, (root, "k"), _FP)

    assert not _store_path(root).exists()
    assert store.lookup(root, (root, "k")) is None


def test_the_memo_reads_the_store_before_computing(root: str) -> None:
    calls: list[int] = []

    def compute() -> str:
        calls.append(1)
        return _FP

    assert memo.memoized_index_fingerprint((root, "c"), compute) == _FP
    memo.clear_index_fingerprint_memo()  # 新进程
    assert memo.memoized_index_fingerprint((root, "c"), compute) == _FP
    assert memo.memoized_projection_exact((root, "c"), lambda: True) is True
    memo.clear_index_fingerprint_memo()
    assert memo.memoized_projection_exact((root, "c"), lambda: False) is True

    assert calls == [1]


def test_a_failed_compute_is_never_stored(root: str) -> None:
    def failing() -> str:
        raise RuntimeError("INDEX_SNAPSHOT_DEADLINE")

    with pytest.raises(RuntimeError, match="INDEX_SNAPSHOT_DEADLINE"):
        memo.memoized_index_fingerprint((root, "c"), failing)

    assert not _store_path(root).exists()


# --------------------------------------------------------------------------- #
# 端到端：真实认证索引
# --------------------------------------------------------------------------- #


async def _certified_project(root: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (root / "leaf.py").write_text("def leaf():\n    return 1\n", encoding="utf-8")
    result = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert result["scope_complete"] is True
    memo.clear_index_fingerprint_memo()


def _counting(monkeypatch, name: str) -> list[int]:
    from tree_sitter_analyzer import index_snapshot

    calls: list[int] = []
    original = getattr(index_snapshot, name)

    def counting(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(index_snapshot, name, counting)
    return calls


def _summary(snapshot) -> tuple:
    return (snapshot.completeness, snapshot.reason, snapshot.index_fingerprint)


async def test_a_new_process_reuses_the_stored_fingerprint_and_verdict(
    tmp_path, monkeypatch
) -> None:
    from tree_sitter_analyzer import index_snapshot

    await _certified_project(tmp_path)
    fingerprints = _counting(monkeypatch, "index_fingerprint")
    projections = _counting(monkeypatch, "symbol_projection_is_exact")
    warm_first = index_snapshot.read_existing_snapshot(str(tmp_path))
    warm = index_snapshot.read_existing_snapshot(str(tmp_path))

    memo.clear_index_fingerprint_memo()  # 新进程
    cold = index_snapshot.read_existing_snapshot(str(tmp_path))

    assert _summary(cold) == _summary(warm) == _summary(warm_first)
    assert cold.completeness == "complete"
    assert (len(fingerprints), len(projections)) == (1, 1)


async def test_changed_index_bytes_are_recomputed_in_a_new_process(
    tmp_path, monkeypatch
) -> None:
    from tree_sitter_analyzer import index_snapshot
    from tree_sitter_analyzer.ast_cache import ASTCache

    await _certified_project(tmp_path)
    fingerprints = _counting(monkeypatch, "index_fingerprint")
    index_snapshot.read_existing_snapshot(str(tmp_path))
    cache = ASTCache(str(tmp_path))
    try:
        cache.invalidate(str(tmp_path / "leaf.py"))
    finally:
        cache.close()

    memo.clear_index_fingerprint_memo()
    stored = index_snapshot.read_existing_snapshot(str(tmp_path))
    memo.clear_index_fingerprint_memo()
    monkeypatch.setenv(store.ENV_VAR, "off")
    unstored = index_snapshot.read_existing_snapshot(str(tmp_path))

    assert (stored.completeness, stored.reason) == ("partial", "CALL_GRAPH_INCOMPLETE")
    assert _summary(stored) == _summary(unstored)
    assert len(fingerprints) == 3


async def test_a_reindexed_project_is_recomputed_in_a_new_process(
    tmp_path, monkeypatch
) -> None:
    from tree_sitter_analyzer import index_snapshot

    await _certified_project(tmp_path)
    first = index_snapshot.read_existing_snapshot(str(tmp_path))
    (tmp_path / "leaf.py").write_text("def leaf():\n    return 2\n", encoding="utf-8")
    await _certified_project(tmp_path)
    fingerprints = _counting(monkeypatch, "index_fingerprint")

    second = index_snapshot.read_existing_snapshot(str(tmp_path))

    assert second.completeness == "complete"
    assert second.index_fingerprint != first.index_fingerprint
    assert len(fingerprints) == 1


def test_runtime_versions_are_strings_for_the_key() -> None:
    environment = store.stored_key(())
    assert environment[2:] == (sys.version, sqlite3.sqlite_version)
