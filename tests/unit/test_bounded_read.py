"""``_bounded_read.read_at_most`` 的行为测试（Issue #1591）。"""

from __future__ import annotations

import io
import os
import sqlite3
from types import SimpleNamespace

from tree_sitter_analyzer import _bounded_read
from tree_sitter_analyzer._bounded_read import read_at_most


def test_reads_whole_file_below_limit(tmp_path):
    path = tmp_path / "a.py"
    path.write_bytes(b"value = 1\n")
    with path.open("rb") as stream:
        assert read_at_most(stream, 64) == b"value = 1\n"


def test_returns_limit_plus_one_bytes_for_oversized_file(tmp_path):
    path = tmp_path / "big.py"
    path.write_bytes(b"x" * 10)
    with path.open("rb") as stream:
        assert read_at_most(stream, 4) == b"xxxxx"


def test_reads_bytes_appended_after_fstat(tmp_path, monkeypatch):
    # Issue #1591：fstat 之后文件增长时，结果仍与 read(limit + 1) 相同。
    path = tmp_path / "grow.py"
    path.write_bytes(b"0123456789")
    real_fstat = os.fstat
    monkeypatch.setattr(
        _bounded_read.os,
        "fstat",
        lambda fd: SimpleNamespace(st_size=3, st_mode=real_fstat(fd).st_mode),
    )
    with path.open("rb") as stream:
        assert read_at_most(stream, 64) == b"0123456789"


def test_streams_without_descriptor_use_plain_bounded_read():
    assert read_at_most(io.BytesIO(b"abcdef"), 2) == b"abc"


class _RecordingStream:
    """包装真实文件对象，记录每次 ``read`` 请求的字节数。"""

    def __init__(self, stream, sizes):
        self._stream = stream
        self._sizes = sizes

    def read(self, size=-1):
        self._sizes.append(size)
        return self._stream.read(size)

    def fileno(self):
        return self._stream.fileno()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._stream.close()


def _record_fdopen(monkeypatch, sizes):
    real = os.fdopen
    monkeypatch.setattr(
        os, "fdopen", lambda *a, **k: _RecordingStream(real(*a, **k), sizes)
    )


def test_index_source_read_requests_file_size_plus_one(tmp_path, monkeypatch):
    # Issue #1592: indexer_io read 64 MiB + 1 per file (27 ms each on Windows).
    from tree_sitter_analyzer.cache import indexer_io

    path = tmp_path / "a.py"
    path.write_bytes(b"x = 1\n")
    sizes = []
    real_open = open
    monkeypatch.setattr(
        indexer_io,
        "open",
        lambda *a, **k: _RecordingStream(real_open(*a, **k), sizes),
        raising=False,
    )
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE ast_index(file_path, content_hash, mtime_ns, file_size, "
        "extractor_version)"
    )
    result = indexer_io.check_cache_or_read(
        connection, "a.py", str(path), path.stat(), lambda s: "h", 1
    )
    assert (result, sizes) == (("x = 1\n", "h"), [7])


def test_health_fingerprint_read_requests_file_size_plus_one(tmp_path, monkeypatch):
    # Issue #1592: the health fingerprint read 64 MiB + 1 per file.
    from tree_sitter_analyzer.registry.health_score_fingerprint import _Fingerprint

    path = tmp_path / "a.py"
    path.write_bytes(b"x = 1\n")
    sizes = []
    _record_fdopen(monkeypatch, sizes)
    fingerprint = _Fingerprint.from_path(str(path))
    assert (fingerprint.size_bytes, sizes) == (6, [7])


def test_symbol_line_scan_read_requests_file_size_plus_one(tmp_path, monkeypatch):
    # Issue #1592: the symbol-line scan read 10 MiB + 1 per file.
    from tree_sitter_analyzer.source_lines import scan_symbol_lines

    (tmp_path / "a.py").write_bytes(b"target = 1\n")
    sizes = []
    _record_fdopen(monkeypatch, sizes)
    matches = scan_symbol_lines(
        "target",
        [str(tmp_path)],
        case_sensitive=True,
        word_match=True,
        include_globs=[],
        exclude_globs=[],
    )
    assert ([m["line"] for m in matches], sizes) == ([1], [12])
