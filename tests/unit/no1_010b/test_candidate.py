"""RFC-0026 §3 B1：候选命令的冻结环境（candidate.frozen_env）。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tree_sitter_analyzer.no1_010b.candidate import env_digest, frozen_env


def test_frozen_env_drops_virtual_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / "runner-venv"))
    assert "VIRTUAL_ENV" not in frozen_env(tmp_path / "scratch")


def test_frozen_path_excludes_unrelated_runner_path_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = str(tmp_path / "unrelated-bin")
    monkeypatch.setenv("PATH", os.pathsep.join([sentinel, os.environ["PATH"]]))
    entries = frozen_env(tmp_path / "scratch")["PATH"].split(os.pathsep)
    assert sentinel not in entries


def test_env_digest_is_identical_across_workspaces(tmp_path: Path) -> None:
    # 每次 attempt 的 workspace 路径不同；摘要必须在归一化后保持一致。
    first, second = tmp_path / "ws-a", tmp_path / "ws-b"
    digests = [
        env_digest(frozen_env(first / "scratch"), first),
        env_digest(frozen_env(second / "scratch"), second),
    ]
    assert digests[0] == digests[1]
