"""``_bounded_read.read_at_most`` 的行为测试（Issue #1591）。"""

from __future__ import annotations

import io
import os
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
