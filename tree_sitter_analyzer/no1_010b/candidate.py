"""NO1-010B 候选树的隔离副本、补丁应用、快照与受限进程执行（RFC-0026 §2/§3）。

本模块只提供 B1 第一切片的进程级隔离：独立副本、冻结环境（PATH 仅含解释器 /
git / uv 所在目录，其绝对路径与二进制 sha256 纳入环境摘要）、缓存重定向到候选
树之外的 scratch、每条命令独占进程组并在命令结束后（无论是否超时或输出超限）
终止整组，以及每条命令后基于 ``lstat`` 的候选树快照复核（含根目录与文件 mode，
绝不打开 FIFO 等特殊文件）。

**尚未实现的边界**（由 ``verifier`` 显式上报）：内核级只读挂载、写入日志、网络
隔离、runner venv 与 $HOME 隔离；``setsid``/双 fork 逃逸出进程组的后代，以及
Windows 上父进程退出后的孤儿进程，在沙箱实现前都无法被终止。
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import signal
import stat
import subprocess  # nosec B404 - 仅以列表 argv 启动，从不经过 shell
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

GIT_TIMEOUT_S = 30.0
GROUP_GRACE_S = 2.0
_REAP_TIMEOUT_S = 5.0
_POLL_S = 0.05
# 从 runner 环境透传的最小键集合：仅 Windows 进程启动所必需，绝不透传令牌等机密，
# 也不透传 VIRTUAL_ENV（它会把候选命令绑定到 runner 自身的 venv 语义）。
_PASSTHROUGH_ENV = ("PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC")
_PATH_TOOLS = ("git", "uv")
COPY_IGNORED = (".ast-cache", ".git", ".pytest_cache", "__pycache__")
_IS_WINDOWS = sys.platform == "win32"
_READ_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_BINARY", 0)
)


class CandidateError(RuntimeError):
    """runner 自身未能建立候选树或 scratch（基础设施失败，绝非产品判定）。"""


@dataclass(frozen=True)
class CommandResult:
    """一条受限命令的结局：正常退出、超时或输出超限（均已终止整个进程组）、
    或无法启动。"""

    status: Literal["exited", "timeout", "output_limit", "spawn_error"]
    returncode: int | None = None


@dataclass(frozen=True)
class OutputCap:
    """运行期间监视的输出文件及其字节上限；超过即终止整个进程组。"""

    path: Path
    max_bytes: int


@dataclass(frozen=True)
class ToolIdentity:
    """冻结环境中一个工具的身份：未解析的绝对路径 + 二进制内容 sha256。

    工具不存在时两者皆为 ``None``；同目录替换二进制会改变 ``sha256``。
    """

    name: str
    path: str | None
    sha256: str | None


def _binary_sha256(path: Path) -> str:
    """对工具二进制求 sha256（跟随 venv 的符号链接到真实解释器）。"""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError:
        return "unreadable"
    return digest.hexdigest()


def _identify(name: str, found: str | None) -> ToolIdentity:
    if found is None:
        return ToolIdentity(name, None, None)
    path = Path(found).absolute()
    return ToolIdentity(name, str(path), _binary_sha256(path))


def resolve_tools() -> tuple[ToolIdentity, ...]:
    """一次性解析解释器、git、uv；同一份结果同时用于 PATH 与 ``env_digest``。"""
    located: dict[str, str | None] = {"python": sys.executable}
    located.update({tool: shutil.which(tool) for tool in _PATH_TOOLS})
    return tuple(_identify(name, found) for name, found in located.items())


def _frozen_path(tools: Sequence[ToolIdentity]) -> str:
    """PATH 只由解释器、git、uv 的绝对目录（及 Windows 系统目录）组成。

    刻意不 ``resolve()``：POSIX venv 的 ``bin/python`` 是指向系统解释器的符号
    链接，解析后会丢掉 venv 的 ``bin``（及其中的 pytest），实测使参考补丁的
    ``uv run pytest`` 无法启动。
    """
    dirs = [str(Path(tool.path).parent) for tool in tools if tool.path is not None]
    system_root = os.environ.get("SYSTEMROOT")
    if _IS_WINDOWS and system_root:  # pragma: no cover - Windows-only system dirs
        dirs.extend([str(Path(system_root) / "System32"), system_root])
    return os.pathsep.join(dict.fromkeys(dirs))


def frozen_env(scratch: Path, tools: Sequence[ToolIdentity]) -> dict[str, str]:
    """构造冻结环境：最小透传键 + 受限 PATH + 全部工具缓存重定向到 scratch。"""
    env = {key: os.environ[key] for key in _PASSTHROUGH_ENV if key in os.environ}
    tmp = scratch / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    pytest_cache = (scratch / "pytest-cache").as_posix()
    env.update(
        {
            "PATH": _frozen_path(tools),
            "TMPDIR": str(tmp),
            "TEMP": str(tmp),
            "TMP": str(tmp),
            "PYTHONPYCACHEPREFIX": str(scratch / "pycache"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
            "COVERAGE_FILE": str(scratch / ".coverage"),
            "MYPY_CACHE_DIR": str(scratch / "mypy-cache"),
            "RUFF_CACHE_DIR": str(scratch / "ruff-cache"),
            "UV_CACHE_DIR": str(scratch / "uv-cache"),
            "UV_OFFLINE": "1",
            "UV_NO_SYNC": "1",
            "XDG_CACHE_HOME": str(scratch / "xdg-cache"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
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


def env_digest(
    env: dict[str, str], workspace: Path, tools: Sequence[ToolIdentity]
) -> str:
    """对冻结环境与工具身份求 sha256；每次 attempt 不同的 workspace 路径先归一化。

    只记录目录不够：同目录替换的二进制会改变行为，因此纳入各工具的绝对路径与
    二进制 sha256。
    """
    variants = (str(workspace), workspace.as_posix())
    normalized = {}
    for key, value in env.items():
        for variant in variants:
            value = value.replace(variant, "<workspace>")
        normalized[key] = value
    payload = {
        "env": sorted(normalized.items()),
        "tools": [[tool.name, tool.path, tool.sha256] for tool in tools],
    }
    encoded = json.dumps(payload, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def copy_fixture(source: Path, destination: Path) -> None:
    """把固定夹具复制为本次 attempt 独占的候选树（不含任何缓存/元数据）。"""
    try:
        shutil.copytree(
            source, destination, ignore=shutil.ignore_patterns(*COPY_IGNORED)
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


def _file_digest(path: Path, expected: os.stat_result) -> str:
    """以非阻塞方式打开并复核 inode：期间被换成 FIFO/特殊文件则判为异常条目。"""
    try:
        fd = os.open(path, _READ_FLAGS)
    except OSError:
        return "unreadable"
    with os.fdopen(fd, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_ino, opened.st_dev) != (
            expected.st_ino,
            expected.st_dev,
        ):
            return "special"
        try:
            return hashlib.sha256(handle.read()).hexdigest()
        except OSError:
            return "unreadable"


def _entry_signature(path: Path) -> tuple[str, bool]:
    """返回 ``(签名, 是否为可下钻目录)``；只用 lstat，绝不跟随符号链接。"""
    try:
        info = os.lstat(path)
    except OSError:
        return "unreadable", False
    mode = f"{stat.S_IMODE(info.st_mode):o}"
    if stat.S_ISLNK(info.st_mode):
        try:
            return f"link:{os.readlink(path)}", False
        except OSError:
            return "unreadable", False
    if stat.S_ISDIR(info.st_mode):
        return f"dir:{mode}", True
    if stat.S_ISREG(info.st_mode):
        return f"file:{mode}:{_file_digest(path, info)}", False
    return f"special:{mode}", False


def tree_snapshot(root: Path, ignored: Sequence[str] = ()) -> dict[str, str]:
    """对整棵树（含未跟踪文件、空目录与 mode）做快照；``ignored`` 按名跳过。

    FIFO/socket/设备等特殊条目与不可读条目都以独立签名记录而绝不打开，
    因此任何此类新增或变化都会被 ``changed_entries`` 视为改动。
    """
    # 根条目本身也入快照：否则 ``chmod('.')`` 这类只改根 mode 的写入会漏检。
    entries: dict[str, str] = {".": _entry_signature(root)[0]}
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            rel = directory.relative_to(root).as_posix()
            entries[rel] = "unreadable"
            continue
        for name in names:
            if name in ignored:
                continue
            path = directory / name
            signature, descend = _entry_signature(path)
            entries[path.relative_to(root).as_posix()] = signature
            if descend:
                pending.append(path)
    return entries


def changed_entries(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """返回新增、删除或内容/mode 改变的全部条目（排序，确定性）。"""
    keys = set(before) | set(after)
    return sorted(key for key in keys if before.get(key) != after.get(key))


def changed_files(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """只保留非目录条目：新建文件引起的父目录出现不是独立的路径改动。"""
    return [
        key
        for key in changed_entries(before, after)
        if not any(
            value.startswith("dir:")
            for value in (before.get(key, ""), after.get(key, ""))
        )
    ]


def remove_tree(path: Path) -> None:
    """尽力删除 workspace：先恢复候选可能移除的写/读权限，再递归删除。"""
    for dirpath, dirnames, filenames in os.walk(path):
        for name in (*dirnames, *filenames):
            child = os.path.join(dirpath, name)
            if os.path.islink(child):
                continue
            try:
                os.chmod(child, stat.S_IRWXU)
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)


# Windows 分支只在 Windows 上可达；CI 覆盖率在 ubuntu 轴采集，故排除（else 不受影响）。
if sys.platform == "win32":  # pragma: no cover - Windows-only taskkill branch

    def terminate_group(proc: subprocess.Popen[bytes]) -> None:
        """Windows：组长仍存活时 ``taskkill /T /F`` 终止其整棵进程树。

        ``taskkill /T`` 只能沿仍存活的父进程遍历；父进程已退出后的孤儿无法被
        找到——这是已上报的 ``process_escape_containment`` 缺口。因此组长已退出
        时不再调用 taskkill：它必然找不到目标（实测每次约 0.9 s），且该 pid 可能
        已被无关进程复用。
        """
        if proc.poll() is not None:
            return
        try:
            subprocess.run(  # nosec B603 B607
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=_REAP_TIMEOUT_S,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

else:

    def _killpg(pgid: int, signum: int) -> bool:
        """向进程组发信号；组已不存在（或无权限）返回 False。"""
        try:
            os.killpg(pgid, signum)
        except OSError:
            return False
        return True

    def terminate_group(proc: subprocess.Popen[bytes]) -> None:
        """POSIX：对命令的进程组 SIGTERM → 宽限期 → SIGKILL。

        ``setsid``/双 fork 逃出该组的后代不受影响——已上报的
        ``process_escape_containment`` 缺口。
        """
        _killpg(proc.pid, signal.SIGTERM)
        deadline = time.monotonic() + GROUP_GRACE_S
        # poll() 回收已退出的组长，避免其僵尸身份让整组看似仍然存活。
        while proc.poll() is None or _killpg(proc.pid, 0):
            if time.monotonic() >= deadline:
                break
            time.sleep(_POLL_S)
        _killpg(proc.pid, signal.SIGKILL)


def _reap(proc: subprocess.Popen[bytes]) -> None:
    for _ in range(2):
        try:
            proc.wait(timeout=_REAP_TIMEOUT_S)
            return
        except subprocess.TimeoutExpired:
            proc.kill()


def _resolve_executable(argv0: str, cwd: Path, search_path: str) -> str | None:
    """解析 argv[0]：裸名走冻结 PATH；含路径分隔符的相对路径相对候选根解析。

    相对路径解析后（含符号链接）必须仍在候选根内，``..`` 逃逸一律拒绝；绝对
    路径（如 corpus 记录中的解释器）按原样校验可执行性。
    """
    if not any(sep and sep in argv0 for sep in (os.sep, os.altsep)):
        return shutil.which(argv0, path=search_path)
    if Path(argv0).is_absolute():
        return _executable_file(Path(argv0))
    root = cwd.resolve()
    target = (root / argv0).resolve()
    if not target.is_relative_to(root):
        return None
    return _executable_file(target)


def _executable_file(target: Path) -> str | None:
    """校验带目录的可执行路径；Windows 上显式按 PATHEXT 补后缀。

    Python 3.11 的 ``shutil.which`` 对含目录的命令不应用 PATHEXT（3.12 起才应用），
    这里自行展开，使解析结果不随解释器版本变化；也不借道 ``which(name, path=...)``，
    因为 Windows 上它会先搜索当前目录。
    """
    candidates = [target]
    if _IS_WINDOWS:  # pragma: no cover - Windows-only PATHEXT expansion
        exts = [
            e for e in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";") if e
        ]
        if target.suffix.casefold() not in {e.casefold() for e in exts}:
            candidates = [target.with_name(target.name + ext) for ext in exts]
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _file_size(path: Path) -> int:
    try:
        return os.stat(path).st_size
    except OSError:
        return 0


def _await_exit(
    proc: subprocess.Popen[bytes], timeout_s: float, cap: OutputCap | None
) -> CommandResult:
    """等待退出；有 ``cap`` 时按 ``_POLL_S`` 轮询输出文件大小，超限立即返回。"""
    deadline = time.monotonic() + timeout_s
    while True:
        if cap is not None and _file_size(cap.path) > cap.max_bytes:
            return CommandResult("output_limit")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return CommandResult("timeout")
        step = remaining if cap is None else min(remaining, _POLL_S)
        try:
            return CommandResult("exited", proc.wait(timeout=step))
        except subprocess.TimeoutExpired:
            continue


def run_bounded(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_s: float,
    log_path: Path,
    output_cap: OutputCap | None = None,
) -> CommandResult:
    """无 shell 运行列表 argv；命令结束、超时或输出超限后一律终止其整个进程组。"""
    executable = _resolve_executable(argv[0], cwd, env.get("PATH", ""))
    if executable is None:
        return CommandResult("spawn_error")
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
        result = _await_exit(proc, timeout_s, output_cap)
        terminate_group(proc)
        if result.status != "exited":
            _reap(proc)
    return result
