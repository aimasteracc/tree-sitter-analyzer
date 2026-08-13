"""Exact behavior tests for portable source snapshot certification."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import tree_sitter_analyzer.portable_source_snapshot as portable
from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor


class _ModuleProxy:
    def __init__(self, module: ModuleType, **overrides: Any) -> None:
        self._module = module
        self._overrides = overrides

    def __getattr__(self, name: str) -> Any:
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._module, name)


def _changed_identity(info: os.stat_result) -> os.stat_result:
    values, attributes = info.__reduce__()[1]
    changed = list(values)
    changed[stat.ST_SIZE] = info.st_size + 1
    return os.stat_result(changed, attributes)


def _inventory(tmp_path: Path, *, roots: tuple[str, ...] = (".",)):
    scope = make_source_scope_descriptor(roots=roots)
    return portable._portable_inventory(str(tmp_path), scope, float("inf"))


def test_scope_root_rejects_absolute_path(tmp_path: Path) -> None:
    with pytest.raises(OSError, match="^source root escapes project$"):
        portable._scope_root(tmp_path, "/src")


def test_scope_root_normalizes_backslash_components(tmp_path: Path) -> None:
    result = portable._scope_root(tmp_path, r"pkg\nested")

    assert result == tmp_path / "pkg" / "nested"


def test_portable_inventory_rejects_non_directory_project_root(tmp_path: Path) -> None:
    project = tmp_path / "project.py"
    project.write_text("value = 1\n")

    rows, unsafe = _inventory(project)

    assert (rows, unsafe) == (frozenset(), True)


def test_portable_inventory_rejects_reparse_project_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(portable, "_is_reparse", lambda _info: True)

    rows, unsafe = _inventory(tmp_path)

    assert (rows, unsafe) == (frozenset(), True)


def test_portable_inventory_rejects_missing_scope_root(tmp_path: Path) -> None:
    rows, unsafe = _inventory(tmp_path, roots=("missing",))

    assert (rows, unsafe) == (frozenset(), True)


def test_portable_inventory_rejects_non_directory_scope_root(tmp_path: Path) -> None:
    (tmp_path / "scope").write_text("not a directory")

    rows, unsafe = _inventory(tmp_path, roots=("scope",))

    assert (rows, unsafe) == (frozenset(), True)


def test_portable_inventory_enforces_deadline(tmp_path: Path) -> None:
    (tmp_path / "sample.py").write_text("value = 1\n")
    scope = make_source_scope_descriptor()

    rows, unsafe = portable._portable_inventory(str(tmp_path), scope, -1.0)

    assert (rows, unsafe) == (frozenset(), True)


def test_portable_inventory_counts_unsupported_entries_against_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "notes.txt").write_text("ignored")
    monkeypatch.setattr(portable, "_SOURCE_ENTRY_BUDGET", 0)

    with pytest.raises(OverflowError):
        _inventory(tmp_path)


def test_portable_inventory_skips_hidden_and_excluded_directories(
    tmp_path: Path,
) -> None:
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    (hidden / "hidden.py").write_text("hidden = True\n")
    excluded = tmp_path / "node_modules"
    excluded.mkdir()
    (excluded / "dependency.py").write_text("dependency = True\n")
    source = tmp_path / "pkg"
    source.mkdir()
    (source / "kept.py").write_text("kept = True\n")

    rows, unsafe = _inventory(tmp_path)

    assert ({row[0] for row in rows}, unsafe) == ({"pkg/kept.py"}, False)


def test_portable_inventory_skips_reparse_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / "inside.py").write_text("inside = True\n")
    linked_identity = (linked.stat().st_dev, linked.stat().st_ino)
    real_is_reparse = portable._is_reparse

    def classify(info: os.stat_result) -> bool:
        if (info.st_dev, info.st_ino) == linked_identity:
            return True
        return real_is_reparse(info)

    monkeypatch.setattr(portable, "_is_reparse", classify)

    rows, unsafe = _inventory(tmp_path)

    assert (rows, unsafe) == (frozenset(), False)


def test_portable_inventory_marks_supported_reparse_leaf_unsafe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "sample.py"
    source.write_text("value = 1\n")
    source_identity = (source.stat().st_dev, source.stat().st_ino)
    real_is_reparse = portable._is_reparse

    def classify(info: os.stat_result) -> bool:
        if (info.st_dev, info.st_ino) == source_identity:
            return True
        return real_is_reparse(info)

    monkeypatch.setattr(portable, "_is_reparse", classify)

    rows, unsafe = _inventory(tmp_path)

    assert (rows, unsafe) == (frozenset(), True)


def test_portable_inventory_ignores_unsupported_reparse_leaf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    notes = tmp_path / "notes.txt"
    notes.write_text("ignored")
    notes_identity = (notes.stat().st_dev, notes.stat().st_ino)
    real_is_reparse = portable._is_reparse

    def classify(info: os.stat_result) -> bool:
        if (info.st_dev, info.st_ino) == notes_identity:
            return True
        return real_is_reparse(info)

    monkeypatch.setattr(portable, "_is_reparse", classify)

    rows, unsafe = _inventory(tmp_path)

    assert (rows, unsafe) == (frozenset(), False)


def test_portable_inventory_omits_effectively_excluded_source(tmp_path: Path) -> None:
    source = tmp_path / "generated.py"
    source.write_text("generated = True\n")
    scope = make_source_scope_descriptor(exclude_patterns=("generated.py",))

    rows, unsafe = portable._portable_inventory(str(tmp_path), scope, float("inf"))

    assert (rows, unsafe) == (frozenset(), False)


def test_portable_inventory_marks_supported_nonregular_leaf_unsafe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "sample.py"
    source.write_text("value = 1\n")
    source_identity = (source.stat().st_dev, source.stat().st_ino)
    real_isreg = stat.S_ISREG

    def is_regular(mode: int) -> bool:
        info = os.lstat(source)
        if mode == info.st_mode and (info.st_dev, info.st_ino) == source_identity:
            return False
        return real_isreg(mode)

    monkeypatch.setattr(
        portable,
        "stat",
        _ModuleProxy(stat, S_ISREG=is_regular),
    )

    rows, unsafe = _inventory(tmp_path)

    assert (rows, unsafe) == (frozenset(), True)


def test_portable_inventory_enforces_supported_file_capacity(
    tmp_path: Path,
) -> None:
    (tmp_path / "sample.py").write_text("value = 1\n")
    scope = portable.SourceScopeDescriptor((".",), False, (), 0)

    with pytest.raises(OverflowError):
        portable._portable_inventory(str(tmp_path), scope, float("inf"))


def test_portable_inventory_marks_unclean_source_hash_unsafe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "sample.py").write_text("value = 1\n")
    observed: list[tuple[object, ...]] = []

    def unclean_hash(*args: object):
        observed.append(args)
        return "marker", "<unsafe>", False

    monkeypatch.setattr(portable, "hash_source_at", unclean_hash)

    rows, unsafe = _inventory(tmp_path)

    assert (rows, unsafe) == (
        frozenset({("sample.py", "<unsafe>", "python")}),
        True,
    )
    assert len(observed) == 1
    assert observed[0][0] is None
    assert observed[0][1] == str(tmp_path / "sample.py")
    assert observed[0][5] == portable._SOURCE_BYTE_BUDGET
    assert observed[0][6:] == (portable._marker, portable._same)


def test_portable_inventory_normalizes_scandir_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(_path: os.PathLike[str] | str):
        raise PermissionError("denied")

    monkeypatch.setattr(portable.os, "scandir", denied)

    rows, unsafe = _inventory(tmp_path)

    assert (rows, unsafe) == (frozenset(), True)


def test_portable_inventory_detects_directory_identity_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_lstat = os.lstat
    reads = 0

    def changing_lstat(path: os.PathLike[str] | str) -> os.stat_result:
        nonlocal reads
        info = real_lstat(path)
        if Path(path) == tmp_path:
            reads += 1
            return _changed_identity(info) if reads == 3 else info
        return info

    monkeypatch.setattr(portable.os, "lstat", changing_lstat)

    rows, unsafe = _inventory(tmp_path)

    assert (rows, unsafe) == (frozenset(), True)


def test_portable_inventory_detects_scope_root_identity_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first"
    first.mkdir()
    second = tmp_path / "second"
    second.mkdir()
    real_lstat = os.lstat
    second_reads = 0

    def changing_lstat(path: os.PathLike[str] | str) -> os.stat_result:
        nonlocal second_reads
        info = real_lstat(path)
        if Path(path) == second:
            second_reads += 1
            return _changed_identity(info) if second_reads == 4 else info
        return info

    monkeypatch.setattr(portable.os, "lstat", changing_lstat)

    rows, unsafe = _inventory(tmp_path, roots=("first", "second"))

    assert (rows, unsafe) == (frozenset(), True)


def test_portable_inventory_retains_unsafe_state_from_earlier_scope_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first"
    first.mkdir()
    second = tmp_path / "second"
    second.mkdir()
    real_lstat = os.lstat
    first_reads = 0

    def changing_lstat(path: os.PathLike[str] | str) -> os.stat_result:
        nonlocal first_reads
        info = real_lstat(path)
        if Path(path) == first:
            first_reads += 1
            return _changed_identity(info) if first_reads == 2 else info
        return info

    monkeypatch.setattr(portable.os, "lstat", changing_lstat)

    rows, unsafe = _inventory(tmp_path, roots=("first", "second"))

    assert (rows, unsafe) == (frozenset(), True)


def test_portable_inventory_detects_project_identity_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope_root = tmp_path / "src"
    scope_root.mkdir()
    real_lstat = os.lstat
    root_reads = 0

    def changing_lstat(path: os.PathLike[str] | str) -> os.stat_result:
        nonlocal root_reads
        info = real_lstat(path)
        if Path(path) == tmp_path:
            root_reads += 1
            return _changed_identity(info) if root_reads == 2 else info
        return info

    monkeypatch.setattr(portable.os, "lstat", changing_lstat)

    rows, unsafe = _inventory(tmp_path, roots=("src",))

    assert (rows, unsafe) == (frozenset(), True)


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (TimeoutError, "SOURCE_SCAN_DEADLINE"),
        (OverflowError, "SOURCE_SCOPE_UNBOUNDED"),
        (OSError, "SOURCE_SCOPE_UNREADABLE"),
    ],
)
def test_capture_portable_source_snapshot_maps_inventory_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: type[Exception],
    reason: str,
) -> None:
    def fail(*_args: object, **_kwargs: object):
        raise failure("capture failed")

    monkeypatch.setattr(portable, "_portable_inventory", fail)

    result = portable.capture_portable_source_snapshot(
        str(tmp_path), make_source_scope_descriptor(), deadline=float("inf")
    )

    assert (
        result.rows,
        result.fingerprint,
        result.generation,
        result.state,
        result.reason,
    ) == (frozenset(), None, None, "unknown", reason)


def test_capture_portable_source_snapshot_rejects_changed_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = frozenset({("first.py", "digest", "python")})
    second = frozenset({("second.py", "digest", "python")})
    inventories = iter(((first, False), (second, False)))
    monkeypatch.setattr(
        portable, "_portable_inventory", lambda *_args: next(inventories)
    )

    result = portable.capture_portable_source_snapshot(
        str(tmp_path), make_source_scope_descriptor(), deadline=float("inf")
    )

    assert (result.rows, result.state, result.reason) == (
        first,
        "unsafe",
        "SOURCE_SCOPE_UNSAFE",
    )
    assert result.fingerprint is not None
    assert result.generation == "idxsrc-v3:" + result.fingerprint.removeprefix(
        "sha256:"
    )
