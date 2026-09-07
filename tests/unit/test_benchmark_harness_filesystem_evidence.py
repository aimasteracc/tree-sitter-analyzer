"""Issue #1376：test_benchmark_harness_filesystem_evidence 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import hashlib
import os
import sys
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.unit._benchmark_harness_platform import (
    mark_posix_qualification_section_tests,
)

_POSIX_QUALIFICATION_SECTION_START = sys._getframe().f_lineno
_mark_posix_qualification_section_tests = partial(
    mark_posix_qualification_section_tests, globals()
)


def test_harness_artifact_rejects_huge_sparse_file(tmp_path: Path):
    # PR #1247: 固定的 harness 验证不能实体化恶意文件。
    import pytest

    from benchmarks.codegraph_compare.setup_qualification import HarnessArtifactV1

    sparse = tmp_path / "tool.bin"
    with sparse.open("wb") as stream:
        stream.seek(512 * 1024 * 1024)
        stream.write(b"x")

    with pytest.raises(ValueError, match="trusted size ceiling"):
        HarnessArtifactV1.read(sparse)


def test_canonical_path_rejects_alias_and_escape_mutations():
    import pytest

    from benchmarks.codegraph_compare.setup_qualification import canonical_relative_path

    rejected = (
        "../outside.ts",
        "dir/../outside.ts",
        "dir\\outside.ts",
        "./main.ts",
        "main.ts\x00x",
    )
    errors = []
    for value in rejected:
        with pytest.raises(ValueError) as caught:
            canonical_relative_path(value)
        errors.append(str(caught.value).split(":", 1)[0])

    assert tuple(errors) == ("Non-canonical POSIX path",) * 5


def test_index_tree_hash_binds_exact_paths_and_bytes(tmp_path: Path):
    from benchmarks.codegraph_compare.setup_qualification import _hash_tree

    index = tmp_path / "index"
    (index / "nested").mkdir(parents=True)
    (index / "a.bin").write_bytes(b"a")
    (index / "nested/b.bin").write_bytes(b"bb")
    digest = hashlib.sha256()
    for relative, payload in ((b"a.bin", b"a"), (b"nested/b.bin", b"bb")):
        digest.update(b"F" + len(relative).to_bytes(8, "big") + relative)
        digest.update(len(payload).to_bytes(8, "big") + payload)
    directory = b"nested"
    digest.update(b"D" + len(directory).to_bytes(8, "big") + directory)
    digest.update(b"C" + (2).to_bytes(8, "big") + (1).to_bytes(8, "big"))

    assert _hash_tree(index) == digest.hexdigest()


def test_index_tree_hash_binds_empty_directory_mutation(tmp_path: Path):
    # PR #1247: 空索引分片虽然不含字节，仍属于拓扑结构。
    from benchmarks.codegraph_compare.setup_qualification import _hash_tree

    index = tmp_path / "index"
    index.mkdir()
    before = _hash_tree(index)
    (index / "empty-shard").mkdir()

    assert _hash_tree(index) != before


def test_index_tree_breadth_is_rejected_before_unbounded_sort(tmp_path: Path):
    # PR #1247: 每次 scandir 最多收集剩余额度加一个条目。
    import pytest

    from benchmarks.codegraph_compare import setup_qualification_paths as paths

    index = tmp_path / "index"
    index.mkdir()
    for number in range(5):
        (index / f"{number}.bin").write_bytes(b"x")
    root_fd = paths._open_root(index)
    try:
        with pytest.raises(ValueError, match="entry count ceiling"):
            paths._visit_tree(root_fd, lambda _fd, _path: None, max_entries=3)
    finally:
        os.close(root_fd)


def test_index_tree_enumeration_checks_deadline_before_chunk_sort(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3745026816: 宽目录不能掩盖已经过期的截止时间。
    from benchmarks.codegraph_compare import setup_qualification_paths as paths

    index = tmp_path / "index"
    index.mkdir()
    for number in range(256):
        (index / f"{number:03d}").write_bytes(b"")
    root_fd = paths._open_root(index)
    monkeypatch.setattr(
        paths, "time", SimpleNamespace(monotonic=iter((0.0, 1.0)).__next__)
    )
    try:
        with pytest.raises(TimeoutError, match="traversal deadline"):
            paths._visit_tree(
                root_fd,
                lambda _fd, _path: None,
                deadline_monotonic=0.5,
            )
    finally:
        os.close(root_fd)


def test_index_tree_rejects_directory_topology_race(tmp_path: Path):
    # PR #1247: 目录操作前后的元数据必须绑定同一份拓扑快照。
    import pytest

    from benchmarks.codegraph_compare import setup_qualification_paths as paths

    index = tmp_path / "index"
    index.mkdir()
    (index / "first.bin").write_bytes(b"x")
    root_fd = paths._open_root(index)

    def mutate(_descriptor: int, _relative: str) -> None:
        (index / "late.bin").write_bytes(b"y")

    try:
        with pytest.raises(ValueError, match="directory changed while hashing"):
            paths._visit_tree(root_fd, mutate)
    finally:
        os.close(root_fd)


def test_index_snapshot_returns_hash_bytes_and_exact_counts(tmp_path: Path):
    # PR #1247: 哈希、大小和拓扑计数必须来自同一次遍历。
    from benchmarks.codegraph_compare import setup_qualification_paths as paths

    index = tmp_path / "index"
    (index / "nested").mkdir(parents=True)
    (index / "a.bin").write_bytes(b"a")
    (index / "nested/b.bin").write_bytes(b"bb")
    root_fd = paths._open_root(tmp_path)
    try:
        snapshot = paths._snapshot_tree_at(root_fd, "index")
    finally:
        os.close(root_fd)

    assert snapshot == (paths._hash_tree(index), 3, 1, 2)


def test_index_tree_hash_rejects_concurrent_append(tmp_path: Path, monkeypatch):
    # PR #1247: 生产者不能扩大 verifier 已快照化的读取范围。
    import os
    import threading

    import pytest

    from benchmarks.codegraph_compare import setup_qualification_paths as paths

    index = tmp_path / "index"
    index.mkdir()
    target = index / "artifact.bin"
    target.write_bytes(b"a" * (paths._HASH_CHUNK_BYTES + 1))
    append_requested = threading.Event()
    appended = threading.Event()
    real_read = os.read

    def append() -> None:
        assert append_requested.wait(timeout=2)
        with target.open("ab") as stream:
            stream.write(b"growth")
            stream.flush()
            os.fsync(stream.fileno())
        appended.set()

    writer = threading.Thread(target=append)
    writer.start()
    first_read = True

    def coordinated_read(descriptor: int, size: int) -> bytes:
        nonlocal first_read
        if first_read and size == paths._HASH_CHUNK_BYTES:
            first_read = False
            append_requested.set()
            assert appended.wait(timeout=2)
        return real_read(descriptor, size)

    monkeypatch.setattr(paths.os, "read", coordinated_read)
    try:
        with pytest.raises(ValueError, match="grew while hashing"):
            paths._hash_tree(index)
    finally:
        writer.join(timeout=2)

    assert writer.is_alive() is False


def test_index_tree_hash_handles_one_thousand_directory_levels(
    tmp_path: Path, request: pytest.FixtureRequest
):
    # PR #1247: 生产者控制的深度不能耗尽 Python 递归栈。
    import os

    from benchmarks.codegraph_compare.setup_qualification import _hash_tree

    index = tmp_path / "index"
    index.mkdir()
    root_fd = os.open(index, os.O_RDONLY | os.O_DIRECTORY)

    def cleanup() -> None:
        descriptors = [os.dup(root_fd)]
        try:
            for _ in range(1000):
                descriptors.append(
                    os.open("d", os.O_RDONLY | os.O_DIRECTORY, dir_fd=descriptors[-1])
                )
            os.unlink("leaf.bin", dir_fd=descriptors[-1])
            for number in range(999, -1, -1):
                os.rmdir("d", dir_fd=descriptors[number])
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)
            os.close(root_fd)

    request.addfinalizer(cleanup)
    current = os.dup(root_fd)
    try:
        for _ in range(1000):
            os.mkdir("d", dir_fd=current)
            child = os.open("d", os.O_RDONLY | os.O_DIRECTORY, dir_fd=current)
            os.close(current)
            current = child
        descriptor = os.open(
            "leaf.bin", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=current
        )
        os.write(descriptor, b"deep")
        os.close(descriptor)
    finally:
        os.close(current)

    digest = hashlib.sha256()
    relative = "/".join(("d",) * 1000 + ("leaf.bin",)).encode()
    digest.update(b"F" + len(relative).to_bytes(8, "big") + relative)
    digest.update((4).to_bytes(8, "big") + b"deep")
    for depth in range(1000, 0, -1):
        directory = "/".join(("d",) * depth).encode()
        digest.update(b"D" + len(directory).to_bytes(8, "big") + directory)
    digest.update(b"C" + (1).to_bytes(8, "big") + (1000).to_bytes(8, "big"))
    assert _hash_tree(index) == digest.hexdigest()


def test_index_tree_hash_rejects_same_size_concurrent_rewrite(
    tmp_path: Path, monkeypatch
):
    # PR #1247: 仅大小稳定不能认证可变的索引字节。
    import os

    import pytest

    from benchmarks.codegraph_compare import setup_qualification_paths as paths

    index = tmp_path / "index"
    index.mkdir()
    target = index / "artifact.bin"
    target.write_bytes(b"original")
    real_read = os.read
    rewritten = False

    def coordinated_read(descriptor: int, size: int) -> bytes:
        nonlocal rewritten
        if size == 1 and not rewritten:
            rewritten = True
            with target.open("r+b") as stream:
                stream.write(b"modified")
                stream.flush()
                os.fsync(stream.fileno())
        return real_read(descriptor, size)

    monkeypatch.setattr(paths.os, "read", coordinated_read)

    with pytest.raises(ValueError, match="changed while hashing"):
        paths._hash_tree(index)

    assert rewritten is True


def test_index_hash_rejects_fifo_without_waiting_for_writer(tmp_path: Path):
    import pytest

    from benchmarks.codegraph_compare.setup_qualification_paths import _hash_tree

    os.mkfifo(tmp_path / "producer.fifo")
    with pytest.raises(ValueError, match="special file"):
        _hash_tree(tmp_path)


def test_index_hash_fails_closed_without_openat_support(tmp_path: Path):
    from benchmarks.codegraph_compare.setup_qualification_paths import _hash_tree

    with (
        patch.object(os, "supports_dir_fd", set()),
        pytest.raises(RuntimeError, match="requires openat/O_NOFOLLOW support"),
    ):
        _hash_tree(tmp_path)


def test_index_hash_enforces_trusted_total_size_ceiling(tmp_path: Path):
    import pytest

    from benchmarks.codegraph_compare.setup_qualification_paths import _hash_tree

    (tmp_path / "large.bin").write_bytes(b"x" * 32)
    with pytest.raises(ValueError, match="trusted size ceiling"):
        _hash_tree(tmp_path, max_bytes=31)


def test_index_hash_rejects_sparse_files(tmp_path: Path):
    import pytest

    from benchmarks.codegraph_compare.setup_qualification_paths import _hash_tree

    sparse = tmp_path / "sparse.bin"
    with sparse.open("wb") as stream:
        stream.truncate(2 * 1024 * 1024)
    if sparse.stat().st_blocks * 512 >= sparse.stat().st_size:
        pytest.skip("tracked: filesystem does not represent sparse allocation")
    with pytest.raises(ValueError, match="Sparse artifact files"):
        _hash_tree(tmp_path)


_mark_posix_qualification_section_tests()
