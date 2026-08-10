from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from tree_sitter_analyzer.frozen_git_index import (
    parse_stage_zero_entries,
    private_index_file,
)
from tree_sitter_analyzer.source_oracle import SourceOracleError


def test_parse_stage_zero_entries_returns_exact_headers() -> None:
    raw = b"100644 a 0\ta.py\0" + b"100755 b 0\tb.py\0"

    entries = parse_stage_zero_entries(raw, max_paths=2)

    assert entries == {b"a.py": b"100644 a 0", b"b.py": b"100755 b 0"}


def test_private_index_file_is_mode_600_and_removed(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    observed_path = ""
    with private_index_file(str(project), b"exact") as path:
        observed_path = path
        assert Path(path).read_bytes() == b"exact"
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600

    assert Path(observed_path).exists() is False


def test_private_index_file_rejects_project_directory(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    target = project / "private-index"

    def create_inside(*, prefix: str) -> tuple[int, str]:
        del prefix
        return os.open(target, os.O_CREAT | os.O_RDWR, 0o600), str(target)

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_UNSAFE_PATH$"):
        with private_index_file(str(project), b"exact", mkstemp=create_inside):
            pass

    assert target.exists() is False
