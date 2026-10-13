"""RFC-0026 §3 B1：候选命令的冻结环境与受限执行（candidate 模块）。"""

from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.unit.no1_010b._verifier_helpers import (
    kill_quietly,
    still_running,
    write_exit_script,
)
from tree_sitter_analyzer.no1_010b import candidate
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


def test_unreadable_tool_binary_is_recorded_as_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # which() 指向无法作为文件读取的路径（此处为目录）：身份记为 unreadable。
    monkeypatch.setattr(
        "tree_sitter_analyzer.no1_010b.candidate.shutil.which",
        lambda _name: str(tmp_path),
    )
    (git,) = (tool for tool in resolve_tools() if tool.name == "git")
    assert git == ToolIdentity("git", str(tmp_path.absolute()), "unreadable")


def test_reap_kills_a_process_that_outlives_the_reap_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(candidate, "_REAP_TIMEOUT_S", 0.05)
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    candidate._reap(proc)
    # POSIX 上 kill() 即 SIGKILL（-9）；Windows 上 TerminateProcess 退出码为 1。
    assert proc.returncode == (1 if sys.platform == "win32" else -signal.SIGKILL)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-only: Windows has no SIGTERM handler to ignore (taskkill /F)",
)
def test_group_member_ignoring_sigterm_is_killed_after_grace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 组长已退出，但组内后代忽略 SIGTERM：宽限期满后必须以 SIGKILL 收掉。
    monkeypatch.setattr(candidate, "GROUP_GRACE_S", 0.3)
    pid_file = tmp_path / "child.pid"
    child = (
        "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "time.sleep(60)"
    )
    leader = (
        "import pathlib, subprocess, sys, time\n"
        f"proc = subprocess.Popen([sys.executable, '-c', {child!r}])\n"
        "time.sleep(0.5)\n"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(proc.pid))\n"
    )
    result = _run([sys.executable, "-c", leader], tmp_path, tmp_path)
    pid = int(pid_file.read_text())
    try:
        alive = still_running(pid)
    finally:
        kill_quietly(pid)
    assert (result, alive) == (CommandResult("exited", 0), False)


class _Unkillable:
    """kill() 无效、wait() 永远超时的进程替身（模拟不可中断睡眠中的进程）。"""

    def __init__(self) -> None:
        self.kills = 0

    def wait(self, timeout: float) -> int:
        raise subprocess.TimeoutExpired(["unkillable"], timeout)

    def kill(self) -> None:
        self.kills += 1


def test_reap_gives_up_after_two_kill_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 回收有界：两次 kill 仍收不回就返回，绝不让 runner 无限挂起。
    monkeypatch.setattr(candidate, "_REAP_TIMEOUT_S", 0.01)
    proc = _Unkillable()
    candidate._reap(proc)  # type: ignore[arg-type]
    assert proc.kills == 2
