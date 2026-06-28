"""Tests for the FileMetaCache persistent line-count cache."""

from __future__ import annotations

import os
import time

import pytest

from tree_sitter_analyzer.registry.file_meta_cache import FileMetaCache


@pytest.fixture
def project(tmp_path):
    (tmp_path / "a.py").write_text("line1\nline2\nline3\n")
    (tmp_path / "b.py").write_text("only one")
    return tmp_path


def test_count_lines_caches_first_call(project):
    cache = FileMetaCache(str(project))
    assert cache.enabled

    target = str(project / "a.py")
    n1 = cache.count_lines(target)
    n2 = cache.count_lines(target)
    assert n1 == n2 == 3

    # Mutate the file to a different content with different mtime+size; a
    # cached lookup MUST detect the staleness and re-read.
    (project / "a.py").write_text("x\n" * 7)
    # Bump mtime to be unambiguously newer than the cached entry.
    future = time.time() + 10
    os.utime(project / "a.py", (future, future))
    assert cache.count_lines(target) == 7
    cache.close()


def test_get_line_count_returns_none_for_unknown_path(project):
    cache = FileMetaCache(str(project))
    missing = cache.get_line_count(str(project / "ghost.py"), mtime_ns=0, size_bytes=0)
    assert missing is None
    cache.close()


def test_store_then_get_returns_count(project):
    cache = FileMetaCache(str(project))
    target = str(project / "a.py")
    st = os.stat(target)
    cache.store_line_count(
        target, mtime_ns=st.st_mtime_ns, size_bytes=st.st_size, line_count=42
    )
    assert (
        cache.get_line_count(target, mtime_ns=st.st_mtime_ns, size_bytes=st.st_size)
        == 42
    )
    # Wrong fingerprint => miss.
    assert cache.get_line_count(target, mtime_ns=0, size_bytes=st.st_size) is None
    cache.close()


def test_disabled_cache_returns_safe_defaults(tmp_path):
    blocker = tmp_path / "block"
    blocker.write_text("not a dir")
    cache = FileMetaCache(str(tmp_path), db_path=str(blocker / "nested" / "f.db"))
    assert cache.enabled is False
    assert cache.get_line_count("x", mtime_ns=0, size_bytes=0) is None
    cache.store_line_count("x", mtime_ns=0, size_bytes=0, line_count=10)
    # count_lines should still work via direct read.
    f = tmp_path / "real.py"
    f.write_text("a\nb\nc\n")
    assert cache.count_lines(str(f)) == 3
    cache.close()


def test_count_lines_unknown_file_returns_zero(project):
    cache = FileMetaCache(str(project))
    assert cache.count_lines(str(project / "does-not-exist.py")) == 0
    cache.close()
