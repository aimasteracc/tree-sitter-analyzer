"""Behavioral tests for bounded qualitative index lag."""

from __future__ import annotations

import os

from tree_sitter_analyzer.index_lag import _newest_source_mtime, compute_qualitative_lag


def test_missing_cache_has_unknown_lag(tmp_path):
    assert compute_qualitative_lag(str(tmp_path), str(tmp_path / "missing.db")) is None


def test_missing_project_has_no_source_mtime(tmp_path):
    assert _newest_source_mtime(str(tmp_path / "missing")) is None


def test_lag_uses_newest_supported_source_and_clamps_at_zero(tmp_path):
    cache = tmp_path / "index.db"
    source = tmp_path / "app.py"
    ignored = tmp_path / "notes.txt"
    cache.write_bytes(b"db")
    source.write_text("value = 1\n")
    ignored.write_text("not source\n")
    os.utime(cache, (20, 20))
    os.utime(source, (10, 10))
    os.utime(ignored, (30, 30))

    assert compute_qualitative_lag(str(tmp_path), str(cache)) == 0.0


def test_source_scan_stops_at_cap(tmp_path, monkeypatch):
    import tree_sitter_analyzer.index_lag as lag

    (tmp_path / "first.py").write_text("first = 1\n")
    (tmp_path / "second.py").write_text("second = 2\n")
    monkeypatch.setattr(lag, "_LAG_WALK_FILE_CAP", 1)
    monkeypatch.setattr(lag.os.path, "getmtime", lambda _path: 7.0)

    assert lag._newest_source_mtime(str(tmp_path)) == 7.0


def test_unreadable_source_is_ignored(tmp_path, monkeypatch):
    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    monkeypatch.setattr(
        os.path, "getmtime", lambda _path: (_ for _ in ()).throw(OSError())
    )

    assert _newest_source_mtime(str(tmp_path)) is None
