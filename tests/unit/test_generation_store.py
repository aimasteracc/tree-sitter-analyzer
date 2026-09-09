"""隔离版本存储的真实 SQLite 发布与过期候选契约。"""

import multiprocessing
import os
import signal
import sqlite3
from dataclasses import replace
from types import SimpleNamespace

import pytest

from tree_sitter_analyzer.cache.generation_selector import InvalidGenerationSelector
from tree_sitter_analyzer.cache.generation_store import GenerationStore, Superseded
from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "a.py").write_text("def original(): return 0\n", encoding="utf-8")
    return GenerationStore(str(root), str(tmp_path / "storage"))


def database_dump(store):
    selector = store.active_selector()
    if selector is None:
        pytest.fail("核验完整数据库内容前必须已有发布版本")
    connection = sqlite3.connect(
        store.database(selector).as_uri() + "?mode=ro", uri=True
    )
    try:
        return tuple(connection.iterdump())
    finally:
        connection.close()


def test_real_incremental_build_is_invisible_until_publication(store):
    first = store.sync()
    before = database_dump(store)
    (store.root / "a.py").write_text("def changed(): return 1\n", encoding="utf-8")
    prepared = store.prepare(store.capture())
    assert store.active_selector() == first
    assert database_dump(store) == before
    assert prepared.result.updated_files == 1
    second = store.publish(prepared)
    assert store.active_selector() == second
    assert second.generation_id != first.generation_id
    assert database_dump(store) != before


@pytest.mark.parametrize("prepared_first", [False, True])
def test_obsolete_candidate_cannot_modify_published_database(store, prepared_first):
    # 2026-09-09：源码未变也必须拒绝旧发布权限，不能仅以内容哈希充当版本号。
    store.sync()
    candidate = store.capture()
    prepared = store.prepare(candidate) if prepared_first else None
    latest = store.sync()
    before = database_dump(store)
    with pytest.raises(Superseded):
        if prepared is None:
            store.prepare(candidate)
        else:
            store.publish(prepared)
    assert store.active_selector() == latest
    assert database_dump(store) == before


@pytest.mark.parametrize("prepared_first", [False, True])
def test_epoch_replacement_revokes_old_candidate(store, prepared_first):
    # 2026-09-09：保留 generation_id 的命名空间重建也必须撤销原候选权限。
    first = store.sync()
    candidate = store.capture()
    prepared = store.prepare(candidate) if prepared_first else None
    replacement = replace(first, storage_epoch="f" * 32)
    store.selector_path.write_bytes(replacement.encode())
    with pytest.raises(Superseded):
        if prepared is None:
            store.prepare(candidate)
        else:
            store.publish(prepared)
    assert store.active_selector() == replacement


def test_changed_source_prevents_publication(store):
    first = store.sync()
    prepared = store.prepare(store.capture())
    (store.root / "a.py").write_text("def changed(): return 1\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="SOURCE_CHANGED"):
        store.publish(prepared)
    assert store.active_selector() == first


def test_content_change_with_equal_metadata_prevents_publication(store, monkeypatch):
    # 2026-09-09：通用快照相等运算忽略内容摘要，发布必须显式检查它。
    first = store.sync()
    prepared = store.prepare(store.capture())
    (store.root / "a.py").write_text("def modified(): return 1\n", encoding="utf-8")
    current = store._snapshot()
    original = prepared.candidate.snapshot
    entry = current.selected_entries[0]
    old_fingerprint = original.selected_entries[0].fingerprint
    assert entry.fingerprint is not None
    assert old_fingerprint is not None
    same_metadata = replace(
        entry,
        fingerprint=replace(
            old_fingerprint, content_hash=entry.fingerprint.content_hash
        ),
    )
    current = replace(current, entries=(same_metadata,))
    assert current == original
    monkeypatch.setattr(store, "_snapshot", lambda: current)
    with pytest.raises(RuntimeError, match="SOURCE_CHANGED"):
        store.publish(prepared)
    assert store.active_selector() == first


def test_reader_cannot_mutate_published_database(store):
    store.sync()
    before = database_dump(store)
    with store.read() as connection:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("DELETE FROM ast_index")
    assert database_dump(store) == before


def test_reader_remains_on_one_generation_across_publication(store):
    first = store.sync()
    with store.read() as connection:
        before = tuple(connection.iterdump())
        (store.root / "a.py").write_text("def changed(): return 1\n", encoding="utf-8")
        second = store.sync()
        assert tuple(connection.iterdump()) == before
        assert second != first
    assert database_dump(store) != before


def test_unpublished_store_read_does_not_create_database(store):
    with pytest.raises(FileNotFoundError):
        with store.read():
            pytest.fail("不能读到不存在的已发布版本")
    assert list(store.storage.glob("**/index.db")) == []


def _paused_publication(root, storage, channel, phase):
    store = GenerationStore(root, storage)
    candidate = store.capture()
    prepared = store.prepare(candidate) if phase == "prepared" else None
    channel.send("ready")
    if channel.recv() != "release":
        raise RuntimeError("未收到发布屏障信号")
    try:
        store.publish(prepared or store.prepare(candidate))
    except Superseded:
        channel.send("superseded")
    else:
        channel.send("published")
    finally:
        channel.close()


@pytest.mark.parametrize("phase", ["captured", "prepared"])
def test_other_process_cannot_replay_old_publication(store, phase):
    store.sync()
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(
        target=_paused_publication,
        args=(str(store.root), str(store.storage), child, phase),
    )
    process.start()
    child.close()
    try:
        assert parent.poll(15)
        assert parent.recv() == "ready"
        newest = store.sync()
        before = database_dump(store)
        parent.send("release")
        assert parent.poll(15)
        assert parent.recv() == "superseded"
        process.join(5)
        assert process.exitcode == 0
        assert store.active_selector() == newest
        assert database_dump(store) == before
    finally:
        if process.is_alive():
            process.kill()
        process.join(5)
        parent.close()


def test_truncated_build_cannot_replace_complete_generation(store):
    first = store.sync()
    (store.root / "b.py").write_text("def second(): return 2\n", encoding="utf-8")
    capped = GenerationStore(
        str(store.root),
        str(store.storage),
        scope=make_source_scope_descriptor(certification_max_files=1),
    )
    with pytest.raises(RuntimeError, match="INDEX_GENERATION_INCOMPLETE"):
        capped.prepare(capped.capture())
    assert store.active_selector() == first


def test_foreign_store_candidate_is_rejected(store, tmp_path):
    other = GenerationStore(str(store.root), str(tmp_path / "other-storage"))
    with pytest.raises(Superseded, match="SUPERSEDED"):
        other.prepare(store.capture())
    assert list(other.storage.glob("**/index.db")) == []


def test_foreign_store_selector_cannot_supply_database_path(store, tmp_path):
    first = store.sync()
    other = GenerationStore(str(store.root), str(tmp_path / "other-storage"))
    with pytest.raises(Superseded, match="FOREIGN_STORE"):
        other.database(first)


def test_missing_prepared_database_cannot_be_published(store):
    first = store.sync()
    prepared = store.prepare(store.capture())
    store.database(prepared.selector).unlink()
    with pytest.raises(FileNotFoundError, match="DATABASE_MISSING"):
        store.publish(prepared)
    assert store.active_selector() == first


def test_corrupt_selector_cannot_be_treated_as_empty_store(store):
    store.sync()
    store.selector_path.write_bytes(b"{invalid")
    with pytest.raises(InvalidGenerationSelector):
        store.capture()


def test_deleted_selector_after_activation_cannot_reinitialize_store(store):
    store.sync()
    store.selector_path.unlink()
    with pytest.raises(InvalidGenerationSelector, match="SELECTOR_MISSING"):
        store.capture()


def test_replaced_storage_directory_revokes_old_store(store):
    candidate = store.capture()
    displaced = store.storage.with_name("displaced")
    store.storage.rename(displaced)
    store.storage.mkdir()
    (store.storage / "generations").mkdir()
    with pytest.raises(Superseded, match="DIRECTORY_CHANGED"):
        store.prepare(candidate)
    assert list(store.storage.iterdir()) == [store.storage / "generations"]


def test_nonregular_selector_is_rejected_without_reading_it(store):
    store.selector_path.mkdir()
    with pytest.raises((InvalidGenerationSelector, OSError)):
        store.active_selector()


def test_windows_flush_does_not_invoke_posix_directory_open(store, monkeypatch):
    # 此测试仅验证平台分支，不作为 Windows 原生持久性验收。
    from tree_sitter_analyzer.cache.generation_store import _flush_directory

    def forbidden_open(*args, **kwargs):
        pytest.fail("Windows 分支不能调用 POSIX 目录打开")

    with monkeypatch.context() as patch:
        patch.setattr(os, "name", "nt")
        patch.setattr(os, "open", forbidden_open)
        _flush_directory(store.storage)


def test_busy_checkpoint_cannot_publish_uncheckpointed_generation(store, monkeypatch):
    from tree_sitter_analyzer.incremental_sync import IncrementalSync

    first = store.sync()
    original = IncrementalSync.sync
    readers = []

    def hold_staged_reader(sync, *args, **kwargs):
        result = original(sync, *args, **kwargs)
        sync._cache.get_conn().execute("PRAGMA busy_timeout=1")
        reader = sqlite3.connect(sync._cache.db_path)
        readers.append(reader)
        reader.execute("BEGIN")
        reader.execute("SELECT * FROM ast_index").fetchall()
        return result

    monkeypatch.setattr(IncrementalSync, "sync", hold_staged_reader)
    try:
        with pytest.raises(RuntimeError, match="CHECKPOINT_BUSY"):
            store.prepare(store.capture())
        assert store.active_selector() == first
    finally:
        for reader in readers:
            reader.close()


def test_legacy_database_write_lock_cannot_block_or_mutate_new_generation(store):
    from tree_sitter_analyzer.ast_cache import ASTCache

    legacy = ASTCache(str(store.root))
    source = store.root / "a.py"
    try:
        legacy.index_file(str(source))
        legacy.get_conn().execute("BEGIN IMMEDIATE")
        first = store.sync()
        before = database_dump(store)
        legacy.invalidate(str(source))
        legacy.get_conn().commit()
        assert store.active_selector() == first
        assert database_dump(store) == before
        assert (
            legacy.get_conn().execute("SELECT count(*) FROM ast_index").fetchone()[0]
            == 0
        )
    finally:
        legacy.close()


def _hold_publication_lease(root, storage, channel):
    store = GenerationStore(root, storage)
    with store._lease():
        channel.send("leased")
        channel.recv()


def test_killed_lease_owner_does_not_block_next_publisher(store):
    first = store.sync()
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(
        target=_hold_publication_lease,
        args=(str(store.root), str(store.storage), child),
    )
    process.start()
    child.close()
    try:
        assert parent.poll(15)
        assert parent.recv() == "leased"
        process.kill()
        process.join(5)
        assert process.exitcode == -(
            signal.SIGKILL if os.name == "posix" else signal.SIGTERM
        )
        assert store.active_selector() == first
        second = store.sync()
        assert second != first
        assert store.active_selector() == second
    finally:
        if process.is_alive():
            process.kill()
        process.join(5)
        parent.close()


def test_missing_default_generation_directory_cannot_fall_back_to_legacy(tmp_path):
    # 2026-09-09：整个版本目录丢失也不能复活旧进程遗留的数据库。
    from tree_sitter_analyzer.cache.generation_indexing import project_store
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_path

    (tmp_path / "a.py").write_text("def saved(): return 1\n", encoding="utf-8")
    active = project_store(str(tmp_path), make_source_scope_descriptor())
    active.sync()
    active.storage.rename(tmp_path / "displaced")
    with pytest.raises(InvalidGenerationSelector, match="SELECTOR_MISSING"):
        resolve_index_path(str(tmp_path))


@pytest.mark.parametrize("change", ["content", "missing", "during_read"])
def test_path_only_candidates_bind_content_and_reject_unstable_reads(
    store, monkeypatch, change
):
    # 2026-09-09：验证路径平台摘要分支；此测试不代替 Windows 原生验收。
    import tree_sitter_analyzer.cache.generation_store as owner
    import tree_sitter_analyzer.index_source_stream as stream

    (store.root / "note.txt").write_text("excluded", encoding="utf-8")
    snapshot = store._snapshot()
    monkeypatch.setattr(owner, "_PATH_ONLY_SOURCE", True)
    first = owner._bind_source_hashes(snapshot)
    source = store.root / "a.py"
    if change == "missing":
        source.unlink()
        with pytest.raises(FileNotFoundError):
            owner._bind_source_hashes(snapshot)
    elif change == "during_read":
        original = stream.hash_source_at

        def mutate_before_read(*args, **kwargs):
            source.write_text("def replaced(): return 4\n", encoding="utf-8")
            return original(*args, **kwargs)

        monkeypatch.setattr(stream, "hash_source_at", mutate_before_read)
        with pytest.raises(RuntimeError, match="SOURCE_CHANGED"):
            owner._bind_source_hashes(snapshot)
    else:
        source.write_text("def replaced(): return 4\n", encoding="utf-8")
        second = store._snapshot()
        assert (
            first.entries[0].fingerprint.content_hash
            != second.entries[0].fingerprint.content_hash
        )


def test_nonregular_publication_lock_is_rejected(store):
    (store.storage / "publication.lock.db").mkdir()
    with pytest.raises(Superseded, match="LOCK_UNSAFE"):
        store.capture()


def test_seal_rejects_database_with_pinned_uncheckpointed_frames(store, monkeypatch):
    candidate = store.capture()
    selector = store.begin(candidate)
    database = store.database(selector)
    writer = sqlite3.connect(database)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE payload(value)")
    writer.commit()
    reader = sqlite3.connect(database)
    reader.execute("BEGIN")
    reader.execute("SELECT * FROM payload").fetchall()
    writer.execute("INSERT INTO payload VALUES(1)")
    writer.commit()
    original = sqlite3.connect

    def impatient(*args, **kwargs):
        connection = original(*args, **kwargs)
        connection.execute("PRAGMA busy_timeout=1")
        return connection

    monkeypatch.setattr(sqlite3, "connect", impatient)
    try:
        with pytest.raises(RuntimeError, match="CHECKPOINT_BUSY"):
            store.seal(selector)
        assert store.active_selector() is None
    finally:
        reader.close()
        writer.close()


@pytest.mark.parametrize("replacement", [False, True])
def test_seal_rejects_removed_or_replaced_database(store, replacement):
    selector = store.begin(store.capture())
    path = store.database(selector)
    path.rename(path.with_suffix(".displaced"))
    if replacement:
        path.touch()
    with pytest.raises((OSError, RuntimeError)):
        store.seal(selector)
    assert path.exists() is replacement
    assert store.active_selector() is None


@pytest.mark.parametrize("phase", ["selector", "completion"])
def test_initial_publication_recovers_with_fresh_writer(store, monkeypatch, phase):
    import tree_sitter_analyzer.cache.generation_store as owner

    original = owner._write_atomic

    def interrupt(path, data):
        if (phase == "selector" and path == store.selector_path) or (
            phase == "completion" and data == b"1\n"
        ):
            raise OSError("publication interrupted")
        return original(path, data)

    with monkeypatch.context() as patch:
        patch.setattr(owner, "_write_atomic", interrupt)
        with pytest.raises(OSError, match="interrupted"):
            store.sync()
    if phase == "selector":
        with pytest.raises(InvalidGenerationSelector, match="MISSING"):
            store.active_selector()
    else:
        assert store.active_selector() is not None
    retry = GenerationStore(str(store.root), str(store.storage))
    assert retry.sync() == retry.active_selector()
    retry.selector_path.unlink()
    with pytest.raises(InvalidGenerationSelector, match="MISSING"):
        retry.capture()


def test_path_platform_hashes_do_not_change_indexer_candidate_metadata(
    store, monkeypatch
):
    import tree_sitter_analyzer.cache.generation_store as owner
    import tree_sitter_analyzer.indexing_snapshot as snapshots

    monkeypatch.setattr(snapshots, "os", SimpleNamespace(**{**vars(os), "name": "nt"}))
    monkeypatch.setattr(owner, "_PATH_ONLY_SOURCE", True)
    candidate = store.capture()
    assert candidate.snapshot.selected_entries[0].fingerprint.content_hash == ""
    assert candidate.source_contents[0][1][0]
    assert (
        snapshots.changed_since_snapshot(candidate.snapshot.selected_entries[0]) is None
    )
    prepared = store.prepare(candidate)
    assert store.publish(prepared) == store.active_selector()
