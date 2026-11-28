"""#1835: the certification walk runs its per-entry system calls concurrently.

A fresh process pays the certified capture before its first ``nav callers``:
four pathname walks, each one ``lstat`` + metadata-change-time probe per source
file, plus a content read of every file on the first walk. Run one after the
other, these calls were most of the cold first query on a ~1.2k-file project.
The walk now spreads directories (and chunks of large directories) over a small
thread pool. These tests pin that it stays concurrent and that it still gives
the same rows and the same verdicts as a one-worker walk.
"""

from __future__ import annotations

import os
import random
import threading
import time
from pathlib import Path

import pytest

import tree_sitter_analyzer.portable_source_snapshot as portable
from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor
from tree_sitter_analyzer.source_hash_cache import SOURCE_HASHES


def _inventory(root: Path, deadline: float = float("inf")):
    scope = make_source_scope_descriptor()
    return portable._portable_inventory(str(root), scope, deadline)


def _tree(root: Path, *, directories: int, files: int, seed: int = 1835) -> None:
    rng = random.Random(seed)
    paths = [root]
    for index in range(directories):
        parent = rng.choice(paths)
        child = parent / f"d{index}"
        child.mkdir()
        paths.append(child)
    for index in range(files):
        folder = rng.choice(paths)
        suffix = rng.choice((".py", ".py", ".ts", ".txt", ".md"))
        (folder / f"f{index}{suffix}").write_text(f"value_{index} = {index}\n")


@pytest.fixture(autouse=True)
def _fresh_hash_cache():
    SOURCE_HASHES.clear()
    yield
    SOURCE_HASHES.clear()


def test_walk_stats_entries_of_different_directories_concurrently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for index in range(6):
        folder = tmp_path / f"pkg{index}"
        folder.mkdir()
        (folder / "module.py").write_text("x = 1\n")
    real_lstat = os.lstat
    lock = threading.Lock()
    running = 0
    peak = 0

    def slow_lstat(path):
        nonlocal running, peak
        if not str(path).endswith(".py"):
            return real_lstat(path)
        with lock:
            running += 1
            peak = max(peak, running)
        try:
            time.sleep(0.05)
            return real_lstat(path)
        finally:
            with lock:
                running -= 1

    monkeypatch.setattr(portable, "_WALK_WORKERS", 4)
    monkeypatch.setattr(portable.os, "lstat", slow_lstat)

    rows, unsafe = _inventory(tmp_path)

    assert unsafe is None
    assert {row[0] for row in rows} == {f"pkg{i}/module.py" for i in range(6)}
    # Six 50 ms lstat calls in six directories on four workers overlap unless
    # the walk runs them one after another.
    assert peak > 1, "serialised lstat"  # ratchet: nondeterministic thread overlap


def test_large_directory_is_split_into_concurrent_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for index in range(12):
        (tmp_path / f"m{index}.py").write_text(f"v = {index}\n")
    seen_threads: set[int] = set()
    real_lstat = os.lstat
    lock = threading.Lock()

    def recording_lstat(path):
        if str(path).endswith(".py"):
            with lock:
                seen_threads.add(threading.get_ident())
            time.sleep(0.02)
        return real_lstat(path)

    monkeypatch.setattr(portable, "_WALK_WORKERS", 4)
    monkeypatch.setattr(portable, "_WALK_CHUNK", 3)
    monkeypatch.setattr(portable.os, "lstat", recording_lstat)

    rows, unsafe = _inventory(tmp_path)

    assert unsafe is None
    assert len(rows) == 12
    assert len(seen_threads) > 1  # ratchet: nondeterministic thread assignment


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_concurrent_walk_matches_a_single_worker_walk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seed: int
) -> None:
    _tree(tmp_path, directories=40, files=150, seed=seed)
    monkeypatch.setattr(portable, "_WALK_CHUNK", 4)
    monkeypatch.setattr(portable, "_WALK_WORKERS", 8)
    concurrent = _inventory(tmp_path)
    SOURCE_HASHES.clear()
    monkeypatch.setattr(portable, "_WALK_WORKERS", 1)
    single = _inventory(tmp_path)

    expected = {
        (Path(folder) / name).relative_to(tmp_path).as_posix()
        for folder, _dirs, names in os.walk(tmp_path)
        for name in names
        if name.endswith((".py", ".ts"))
    }
    assert concurrent == single
    assert concurrent[1] is None
    assert {row[0] for row in concurrent[0]} == expected


def test_byte_budget_is_shared_by_all_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Each file fits the budget on its own; together they exceed it.
    for index in range(4):
        folder = tmp_path / f"p{index}"
        folder.mkdir()
        (folder / "big.py").write_text("x" * 100 + "\n")
    monkeypatch.setattr(portable, "_SOURCE_BYTE_BUDGET", 250)

    with pytest.raises(OverflowError):
        _inventory(tmp_path)


def test_entry_budget_is_shared_by_all_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for index in range(4):
        folder = tmp_path / f"p{index}"
        folder.mkdir()
        (folder / "a.py").write_text("a = 1\n")
    # 4 directories + 4 files = 8 entries.
    monkeypatch.setattr(portable, "_SOURCE_ENTRY_BUDGET", 7)

    with pytest.raises(OverflowError):
        _inventory(tmp_path)


def test_supported_file_limit_counts_across_workers(tmp_path: Path) -> None:
    for index in range(5):
        folder = tmp_path / f"p{index}"
        folder.mkdir()
        (folder / "a.py").write_text("a = 1\n")
    scope = portable.SourceScopeDescriptor((".",), False, (), 4)

    with pytest.raises(OverflowError):
        portable._portable_inventory(str(tmp_path), scope, float("inf"))


def test_entry_that_vanishes_mid_walk_stops_the_walk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for index in range(4):
        folder = tmp_path / f"p{index}"
        folder.mkdir()
        (folder / "a.py").write_text("a = 1\n")
    real_lstat = os.lstat

    def vanishing(path):
        if Path(path).parent.name == "p2" and str(path).endswith(".py"):
            raise FileNotFoundError(path)
        return real_lstat(path)

    monkeypatch.setattr(portable.os, "lstat", vanishing)

    assert _inventory(tmp_path) == (frozenset(), "walk_oserror")


def test_directory_changed_during_the_walk_is_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A directory whose identity differs at the end of the walk is unsafe,
    # exactly as when it was re-checked right after its own scan.
    target = tmp_path / "pkg"
    target.mkdir()
    (target / "a.py").write_text("a = 1\n")
    real_lstat = os.lstat
    reads = 0

    def changing(path):
        nonlocal reads
        info = real_lstat(path)
        if Path(path) == target:
            reads += 1
            if reads >= 3:  # discovered, scanned, then the end-of-walk re-check
                values, attributes = info.__reduce__()[1]
                changed = list(values)
                changed[6] = info.st_size + 1
                return os.stat_result(changed, attributes)
        return info

    monkeypatch.setattr(portable.os, "lstat", changing)

    rows, unsafe = _inventory(tmp_path)

    assert unsafe == "dir_identity_changed"
    assert {row[0] for row in rows} == {"pkg/a.py"}


def test_expired_deadline_cancels_the_walk(tmp_path: Path) -> None:
    _tree(tmp_path, directories=10, files=30)

    assert _inventory(tmp_path, deadline=-1.0) == (frozenset(), "walk_oserror")


def test_flag_reason_does_not_depend_on_completion_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("a", "b"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "x.py").write_text("x = 1\n")

    def unclean_or_clean(_fd, path, *args):
        if Path(path).parent.name == "a":
            return "marker", "<unsafe>", False
        return "marker", "digest", True

    monkeypatch.setattr(portable, "hash_source_at", unclean_or_clean)
    reasons = set()
    for _ in range(5):
        reasons.add(_inventory(tmp_path)[1])

    assert reasons == {"hash_unclean"}
