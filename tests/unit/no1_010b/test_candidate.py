"""RFC-0026 §3 B1：候选命令的冻结环境与受限执行（candidate 模块）。"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

import pytest

from tests.unit.no1_010b._verifier_helpers import write_exit_script
from tree_sitter_analyzer.no1_010b.candidate import (
    CommandResult,
    OutputCap,
    ToolIdentity,
    env_digest,
    frozen_env,
    resolve_tools,
    run_bounded,
)


def _digest(workspace: Path) -> str:
    tools = resolve_tools()
    return env_digest(frozen_env(workspace / "scratch", tools), workspace, tools)


def _prepend_path(monkeypatch: pytest.MonkeyPatch, directory: Path) -> None:
    monkeypatch.setenv("PATH", os.pathsep.join([str(directory), os.environ["PATH"]]))


def test_frozen_env_drops_virtual_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / "runner-venv"))
    assert "VIRTUAL_ENV" not in frozen_env(tmp_path / "scratch", resolve_tools())


def test_frozen_path_excludes_unrelated_runner_path_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = str(tmp_path / "unrelated-bin")
    _prepend_path(monkeypatch, Path(sentinel))
    env = frozen_env(tmp_path / "scratch", resolve_tools())
    assert sentinel not in env["PATH"].split(os.pathsep)


def test_env_digest_is_identical_across_workspaces(tmp_path: Path) -> None:
    # 每次 attempt 的 workspace 路径不同；摘要必须在归一化后保持一致。
    assert _digest(tmp_path / "ws-a") == _digest(tmp_path / "ws-b")


def test_tool_identity_records_absolute_path_and_binary_sha256(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_git = write_exit_script(tmp_path / "bin" / "git", 0)
    _prepend_path(monkeypatch, fake_git.parent)
    (git,) = (tool for tool in resolve_tools() if tool.name == "git")
    expected = hashlib.sha256(fake_git.read_bytes()).hexdigest()
    assert (Path(git.path or "").resolve(), git.sha256) == (
        fake_git.resolve(),
        expected,
    )


def test_env_digest_changes_when_a_tool_binary_is_swapped_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Codex P2：同目录替换二进制会改变行为，摘要必须随之改变（不仅记录目录）。
    stem = tmp_path / "bin" / "git"
    _prepend_path(monkeypatch, write_exit_script(stem, 0).parent)
    before = _digest(tmp_path / "ws")
    write_exit_script(stem, 1)
    assert _digest(tmp_path / "ws") != before


def test_missing_tool_is_recorded_as_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tree_sitter_analyzer.no1_010b.candidate.shutil.which", lambda _name: None
    )
    absent = {tool.name: tool for tool in resolve_tools() if tool.name != "python"}
    assert absent == {
        "git": ToolIdentity("git", None, None),
        "uv": ToolIdentity("uv", None, None),
    }


def _run(argv: list[str], cwd: Path, tmp_path: Path) -> CommandResult:
    return run_bounded(
        argv,
        cwd=cwd,
        env=frozen_env(tmp_path / "scratch", resolve_tools()),
        timeout_s=30.0,
        log_path=tmp_path / "run.log",
    )


def test_relative_argv0_with_separator_resolves_against_candidate_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Codex P2：``./tools/check`` 必须相对候选根解析，而不是 verifier 自身的 cwd。
    root = tmp_path / "candidate"
    write_exit_script(root / "tools" / "check", 7)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert _run(["./tools/check"], root, tmp_path) == CommandResult("exited", 7)


def test_relative_argv0_escaping_the_root_is_a_spawn_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 即使 verifier 的 cwd 恰好能解析到它，``..`` 逃出候选根也绝不执行。
    root = tmp_path / "candidate"
    root.mkdir()
    write_exit_script(tmp_path / "outside" / "tool", 0)
    monkeypatch.chdir(root)
    assert _run(["../outside/tool"], root, tmp_path) == CommandResult("spawn_error")


def test_unstartable_command_is_a_spawn_error(tmp_path: Path) -> None:
    # 解释器存在但 cwd 不存在：Popen 抛 OSError，结局是 spawn_error 而非异常。
    missing = tmp_path / "no-such-dir"
    assert _run([sys.executable, "-c", "pass"], missing, tmp_path) == CommandResult(
        "spawn_error"
    )


def test_output_cap_stops_a_continuous_writer_before_the_timeout(
    tmp_path: Path,
) -> None:
    # Codex P2：输出上限在运行期间执行；持续写入者应远早于 60 s 超时被终止。
    capture = tmp_path / "capture.log"
    writer = (
        "import sys\n"
        f"out = open({str(capture)!r}, 'wb')\n"
        "while True:\n"
        "    out.write(b'x' * 65536)\n"
        "    out.flush()\n"
    )
    started = time.monotonic()
    result = run_bounded(
        [sys.executable, "-c", writer],
        cwd=tmp_path,
        env=frozen_env(tmp_path / "scratch", resolve_tools()),
        timeout_s=60.0,
        log_path=tmp_path / "run.log",
        output_cap=OutputCap(capture, 1024 * 1024),
    )
    elapsed = time.monotonic() - started
    # ratchet: nondeterministic 墙钟上界（远小于 60 s 超时），证明是提前终止
    assert (result, elapsed < 30.0) == (CommandResult("output_limit"), True)
