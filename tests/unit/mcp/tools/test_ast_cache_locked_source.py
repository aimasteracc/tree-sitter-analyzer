"""#1654: a locked source file is a per-file indexing failure, not a bare error.

``index action=cache mode=index`` raised a bare ``PermissionError`` from
``index_source_stream.hash_source_at`` when another process held a source file
locked. The lock is simulated by making every read of that one file raise
``PermissionError``: the source-hash binding (``os.open`` / ``os.read`` in
``index_source_stream``) and the indexer's own ``open``. The path-only binding
used on Windows is forced on so the case runs the same way on every platform.
"""

from __future__ import annotations

import builtins
import os
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

_LOCKED = "m1.py"


def _functions(prefix: str, count: int) -> str:
    return "".join(f"def {prefix}{n}():\n    return {n}\n\n\n" for n in range(count))


def _write_project(root: Path) -> None:
    for module in range(3):
        (root / f"m{module}.py").write_text(
            _functions(f"f{module}_", 5), encoding="utf-8"
        )


class _LockedOs:
    """``os`` stand-in for ``index_source_stream``: one file cannot be read."""

    def __init__(self, phase: str) -> None:
        self._phase = phase
        self._locked_fds: set[int] = set()

    def __getattr__(self, name: str) -> Any:
        return getattr(os, name)

    def open(self, name: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        locked = os.path.basename(os.fsdecode(name)) == _LOCKED
        if locked and self._phase == "open":
            raise PermissionError(13, "Permission denied", os.fsdecode(name))
        fd = os.open(name, flags, *args, **kwargs)
        if locked:
            self._locked_fds.add(fd)
        return fd

    def read(self, fd: int, size: int) -> bytes:
        if fd in self._locked_fds:
            raise PermissionError(13, "Permission denied")
        return os.read(fd, size)

    def close(self, fd: int) -> None:
        # Descriptor numbers are reused; only the open locked handle is locked.
        self._locked_fds.discard(fd)
        os.close(fd)


@pytest.fixture
def lock(monkeypatch):
    import tree_sitter_analyzer.cache.generation_store as generation_store
    import tree_sitter_analyzer.cache.indexer_io as indexer_io
    import tree_sitter_analyzer.index_source_stream as stream

    monkeypatch.setattr(generation_store, "_PATH_ONLY_SOURCE", True)

    def apply(phase: str = "read") -> None:
        monkeypatch.setattr(stream, "os", _LockedOs(phase))

        def locked_open(file: Any, *args: Any, **kwargs: Any) -> Any:
            if os.path.basename(os.fsdecode(file)) == _LOCKED:
                raise PermissionError(13, "Permission denied", os.fsdecode(file))
            return builtins.open(file, *args, **kwargs)

        monkeypatch.setattr(indexer_io, "open", locked_open, raising=False)

    return apply


def _detail(result: dict[str, Any], rel_path: str) -> dict[str, Any]:
    matches = [d for d in result["files"] if d.get("file") == rel_path]
    assert len(matches) == 1, result["files"]
    return matches[0]


@pytest.fixture
async def indexed_root(tmp_path, lock) -> Path:
    _write_project(tmp_path)
    first = await ASTCacheTool(str(tmp_path)).execute({"mode": "index"})
    assert first["published"] is True
    return tmp_path


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["read", "open"])
async def test_locked_file_on_refresh_is_a_per_file_failure(
    indexed_root, lock, phase
) -> None:
    (indexed_root / "added.py").write_text(_functions("n", 4), encoding="utf-8")
    lock(phase)

    refreshed = await ASTCacheTool(str(indexed_root)).execute({"mode": "index"})

    locked = _detail(refreshed, _LOCKED)
    assert locked["status"] == "error"
    assert "Permission denied" in locked["reason"]
    # The rest of the run continued: the new file was parsed.
    assert _detail(refreshed, "added.py")["status"] == "indexed"
    assert refreshed["errors"] == 1
    # A read failure is not a stable failure: the parent generation stays.
    assert refreshed["published"] is False
    assert refreshed["publication_reason"] == "INDEX_NOT_PUBLISHABLE"
    stats = await ASTCacheTool(str(indexed_root)).execute({"mode": "stats"})
    assert stats["total_symbols"] == 15


@pytest.mark.asyncio
async def test_locked_file_on_first_index_is_not_published_as_indexed(
    tmp_path, lock
) -> None:
    _write_project(tmp_path)
    lock("read")

    result = await ASTCacheTool(str(tmp_path)).execute({"mode": "index"})

    locked = _detail(result, _LOCKED)
    assert (locked["status"], "Permission denied" in locked["reason"]) == (
        "error",
        True,
    )
    assert result["errors"] == 1
    # #1554: the first index publishes the other files ...
    assert result["published"] is True
    tool = ASTCacheTool(str(tmp_path))
    stats = await tool.execute({"mode": "stats"})
    assert stats["total_symbols"] == 10
    # ... but never a row for the locked file (RFC-0030: not claimed fresh).
    lookup = await tool.execute({"mode": "lookup", "file_path": _LOCKED})
    assert lookup["summary_line"].endswith("status=not_found")


def _hash(path: Path, hasher: Any = None, deadline: float = float("inf")) -> Any:
    import tree_sitter_analyzer.index_source_stream as stream

    return (hasher or stream.hash_source_at)(
        None,
        str(path),
        path.stat(),
        deadline,
        {"input": 0, "output": 0},
        1 << 20,
        lambda info: "marker",
        lambda *_args: True,
    )


@pytest.mark.parametrize("phase", ["read", "open"])
def test_hash_source_at_names_the_lock_reason(tmp_path, monkeypatch, phase) -> None:
    import tree_sitter_analyzer.index_source_stream as stream

    target = tmp_path / _LOCKED
    target.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(stream, "os", _LockedOs(phase))

    with pytest.raises(stream.SourceUnreadable) as caught:
        _hash(target)

    reason = "source unreadable: PermissionError [Errno 13] Permission denied"
    assert caught.value.reason == reason
    assert stream.unreadable_source_reason(caught.value.marker) == reason
    # Certification scans keep treating an unreadable file as unsafe.
    assert _hash(target, stream.hash_source_or_unsafe) == ("marker", "<unsafe>", False)


def test_vanished_file_stays_a_source_change(tmp_path) -> None:
    import tree_sitter_analyzer.index_source_stream as stream

    target = tmp_path / "gone.py"
    target.write_text("x = 1\n", encoding="utf-8")
    admitted = target.stat()
    target.unlink()
    result = stream.hash_source_at(
        None,
        str(target),
        admitted,
        float("inf"),
        {"input": 0, "output": 0},
        1 << 20,
        lambda info: "marker",
        lambda *_args: True,
    )
    assert result == ("marker", "<unsafe>", False)
    assert stream.unreadable_source_reason("0" * 64) is None


def test_read_timeout_is_not_reported_as_unreadable(tmp_path) -> None:
    import tree_sitter_analyzer.index_source_stream as stream

    target = tmp_path / "slow.py"
    target.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(TimeoutError) as caught:
        _hash(target, deadline=-1.0)
    assert not isinstance(caught.value, stream.SourceUnreadable)


@pytest.mark.asyncio
async def test_unlocked_file_still_indexes(tmp_path, monkeypatch) -> None:
    # Control: same forced path-only binding, no lock.
    import tree_sitter_analyzer.cache.generation_store as generation_store

    monkeypatch.setattr(generation_store, "_PATH_ONLY_SOURCE", True)
    _write_project(tmp_path)

    result = await ASTCacheTool(str(tmp_path)).execute({"mode": "index"})

    assert (result["published"], result["errors"]) == (True, 0)
    assert _detail(result, _LOCKED)["status"] == "indexed"
    stats = await ASTCacheTool(str(tmp_path)).execute({"mode": "stats"})
    assert stats["total_symbols"] == 15
