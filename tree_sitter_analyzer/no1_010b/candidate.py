"""NO1-010B 候选树的隔离副本、补丁应用、快照与受限进程执行（RFC-0026 §2/§3）。

本模块只提供 B1 第一切片的进程级隔离：独立副本、冻结环境、缓存重定向到候选树
之外的 scratch、整棵进程树的超时终止，以及每条命令后的候选树快照复核。
内核级只读挂载、写入日志与网络隔离 **尚未实现**，由 ``verifier`` 显式上报。
"""

from __future__ import annotations

import hashlib
import os
import shlex
import shutil
import subprocess  # nosec B404 - 仅以列表 argv 启动，从不经过 shell
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .oracle import _kill_process_tree, _reap_process

GIT_TIMEOUT_S = 30.0
# 从 runner 环境透传的最小键集合：仅解释器/uv 启动所必需，绝不透传令牌等机密。
_PASSTHROUGH_ENV = ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "VIRTUAL_ENV")
_COPY_IGNORED = (".ast-cache", ".git", ".pytest_cache", "__pycache__")
_IS_WINDOWS = os.name == "nt"


class CandidateError(RuntimeError):
    """runner 自身未能建立候选树或 scratch（基础设施失败，绝非产品判定）。"""


@dataclass(frozen=True)
class CommandResult:
    """一条受限命令的结局：正常退出、超时（已终止整棵进程树）或无法启动。"""

    status: Literal["exited", "timeout", "spawn_error"]
    returncode: int | None = None


def frozen_env(scratch: Path) -> dict[str, str]:
    """构造冻结环境：最小透传键 + 全部工具缓存重定向到 scratch。"""
    env = {key: os.environ[key] for key in _PASSTHROUGH_ENV if key in os.environ}
    tmp = scratch / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    pytest_cache = (scratch / "pytest-cache").as_posix()
    env.update(
        {
            "TMPDIR": str(tmp),
            "TEMP": str(tmp),
            "TMP": str(tmp),
            "PYTHONPYCACHEPREFIX": str(scratch / "pycache"),
            "PYTHONIOENCODING": "utf-8",
            "COVERAGE_FILE": str(scratch / ".coverage"),
            "MYPY_CACHE_DIR": str(scratch / "mypy-cache"),
            "RUFF_CACHE_DIR": str(scratch / "ruff-cache"),
            "UV_CACHE_DIR": str(scratch / "uv-cache"),
            "XDG_CACHE_HOME": str(scratch / "xdg-cache"),
            # pytest 缓存重定向；runner venv 注入的 pytest-benchmark 会在 rootdir
            # 建 .benchmarks 且无对应环境变量可重定向，夹具也不声明 benchmark 测试，
            # 故禁用之（插件未安装时 ``-p no:`` 同样无害）。
            "PYTEST_ADDOPTS": (
                f"-o cache_dir={shlex.quote(pytest_cache)} -p no:benchmark"
            ),
            # 防止 git 向上发现 runner 所在仓库：候选副本本身不是 Git 仓库。
            "GIT_CEILING_DIRECTORIES": str(scratch.parent),
        }
    )
    return env


def copy_fixture(source: Path, destination: Path) -> None:
    """把固定夹具复制为本次 attempt 独占的候选树（不含任何缓存/元数据）。"""
    try:
        shutil.copytree(
            source, destination, ignore=shutil.ignore_patterns(*_COPY_IGNORED)
        )
    except OSError as exc:
        raise CandidateError(f"fixture copy failed: {exc}") from exc


def apply_patch(root: Path, patch_path: Path, env: dict[str, str]) -> bool:
    """先 ``git apply --check`` 再应用；任一步不可应用返回 False（不 fuzz）。"""
    for extra in (("--check",), ()):
        argv = ["git", "-c", "core.autocrlf=false", "apply", *extra, str(patch_path)]
        try:
            completed = subprocess.run(  # nosec B603 B607
                argv,
                cwd=str(root),
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=GIT_TIMEOUT_S,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CandidateError(f"git apply could not run: {exc}") from exc
        if completed.returncode != 0:
            return False
    return True


def tree_snapshot(root: Path) -> dict[str, str]:
    """对整棵候选树（含未跟踪文件与空目录）做内容快照。"""
    entries: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        for name in dirnames:
            path = base / name
            rel = path.relative_to(root).as_posix()
            entries[rel] = f"link:{os.readlink(path)}" if path.is_symlink() else "dir"
        for name in filenames:
            path = base / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                entries[rel] = f"link:{os.readlink(path)}"
            else:
                entries[rel] = "file:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return entries


def changed_entries(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """返回新增、删除或内容改变的全部条目（排序，确定性）。"""
    keys = set(before) | set(after)
    return sorted(key for key in keys if before.get(key) != after.get(key))


def changed_files(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """只保留非目录条目：新建文件引起的父目录出现不是独立的路径改动。"""
    return [
        key
        for key in changed_entries(before, after)
        if "dir" not in (before.get(key), after.get(key))
    ]


def run_bounded(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_s: float,
    log_path: Path,
) -> CommandResult:
    """无 shell 运行列表 argv；超时则终止整棵进程树。输出写入 scratch 日志。"""
    executable = shutil.which(argv[0], path=env.get("PATH", ""))
    if executable is None:
        return CommandResult("spawn_error")
    # 独立进程组/会话，使超时终止能覆盖命令派生的全部子孙进程。
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    with log_path.open("wb") as log:
        try:
            proc = subprocess.Popen(  # nosec B603
                [executable, *argv[1:]],
                cwd=str(cwd),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=flags if _IS_WINDOWS else 0,
                start_new_session=not _IS_WINDOWS,
            )
        except OSError:
            return CommandResult("spawn_error")
        try:
            returncode = proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            _kill_process_tree(proc)
            _reap_process(proc)
            return CommandResult("timeout")
    return CommandResult("exited", returncode)
