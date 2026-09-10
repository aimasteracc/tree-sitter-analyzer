"""Project-aware verification command selection for agent workflows."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DefaultTestCommand:
    """Default test command detected for a project root."""

    runner: str
    command: str
    pytest_marker: str | None = None
    pytest_config_root: str | None = None


PYTEST_DEFAULT_COMMAND = "uv run pytest -q"
PYTEST_COMMAND = DefaultTestCommand("pytest", PYTEST_DEFAULT_COMMAND)


def detect_default_test_command(project_root: str | Path | None) -> DefaultTestCommand:
    """Detect a directly runnable default test command for a project root."""
    root = Path(project_root or ".")

    package_json = root / "package.json"
    if package_json.exists() and _package_json_has_test_script(package_json):
        return _node_test_command(root)

    if (root / "go.mod").exists():
        return DefaultTestCommand("go", "go test ./...")

    if (root / "Cargo.toml").exists():
        return DefaultTestCommand("cargo", "cargo test")

    if (root / "gradlew").exists():
        return DefaultTestCommand("gradle", "./gradlew test")

    if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        return DefaultTestCommand("gradle", "gradle test")

    if (root / "mvnw").exists():
        return DefaultTestCommand("maven", "./mvnw test")

    if (root / "pom.xml").exists():
        return DefaultTestCommand("maven", "mvn test")

    from .verification_pytest_config import targeted_marker_expression

    marker = targeted_marker_expression(root)
    return DefaultTestCommand(
        "pytest",
        PYTEST_DEFAULT_COMMAND,
        marker,
        str(root.resolve()) if marker else None,
    )


def certified_default_test_command(
    file_path: str,
) -> DefaultTestCommand | None:
    """Extension-derived default test command, snapshot-bound.

    Codex P2 (#1299 round-7/8, C32/C35): the certified route cannot read
    live config files (package.json/go.mod/...), so the runner is inferred
    from the TARGET's extension — a fact bound to the snapshot inventory.
    Only ecosystems with an unambiguous canonical runner map; ambiguous
    ones (Java's Maven-vs-Gradle, Kotlin, C#, PHP, C/C++, Ruby's
    rspec-vs-minitest, and JavaScript/TypeScript's npm-vs-pnpm-vs-Yarn-
    vs-Bun, which only non-inventoried lockfiles can distinguish) return
    ``None`` so the route OMITS the command rather than advertising an
    unverifiable choice. Python keeps the pytest default.
    """

    ext = Path(file_path).suffix.lower()
    if ext == ".go":
        return DefaultTestCommand("go", "go test ./...")
    if ext == ".rs":
        return DefaultTestCommand("cargo", "cargo test")
    if ext == ".py":
        return PYTEST_COMMAND
    return None


_TARGETED_RUNNERS = frozenset({"pytest", "npm", "pnpm", "yarn", "bun"})


def _for_targets(default: DefaultTestCommand, targets: list[str]) -> DefaultTestCommand:
    """每个完整目标集合只核对子项目配置一次，预算试装参数时不重复访问磁盘。"""
    from .verification_pytest_config import targets_share_root_config

    if (
        default.pytest_marker
        and default.pytest_config_root
        and targets
        and not targets_share_root_config(default.pytest_config_root, targets)
    ):
        return replace(default, pytest_marker=None, pytest_config_root=None)
    return default


def _test_argv(default_command: DefaultTestCommand, targets: list[str]) -> list[str]:
    """从结构化目标直接构造参数，命令文本只在最后渲染。"""
    runner = default_command.runner
    if not targets or runner not in _TARGETED_RUNNERS:
        return shlex.split(default_command.command)
    if runner == "pytest":
        marker = default_command.pytest_marker
        options = ["-m", marker] if marker else []
        return ["uv", "run", "pytest", *options, *targets, "-q"]
    separator = ["--"] if runner in {"npm", "pnpm"} else []
    return [runner, "test", *separator, *targets]


def _shell_test_argv(
    default_command: DefaultTestCommand, target: str
) -> list[str] | None:
    """shell 测试交给 Bash，Python 项目保留 uv 环境与 pytest 节点语义。"""
    file_part, separator, _ = target.partition("::")
    if separator and Path(file_part).suffix.lower() == ".py":
        return None
    if Path(target).suffix.lower() == ".sh":
        prefix = ["uv", "run"] if default_command.runner == "pytest" else []
        executable = "bash"
        if not prefix and sys.platform == "win32":
            # CreateProcess 的搜索顺序不同于 PATH；固定发现的原生执行文件。
            executable = shutil.which("bash") or ""
            if not executable:
                raise ValueError("BASH_EXECUTABLE_NOT_FOUND")
        if sys.platform == "win32":
            # MSYS 会剥掉原生未引用参数中的撇号；整条含空格命令获得外层引用。
            quoted_target = "'" + target.replace("'", "'\\''") + "'"
            return [*prefix, executable, "-c", f"exec bash -- {quoted_target}"]
        return [*prefix, executable, "--", target]
    return None


def build_test_command(
    default_command: DefaultTestCommand,
    tests_to_run: list[str],
) -> str:
    """支持定向执行时渲染精确参数，其余情况保留项目默认命令。"""
    if not tests_to_run or default_command.runner not in _TARGETED_RUNNERS:
        return default_command.command
    default_command = _for_targets(default_command, tests_to_run)
    if any(_shell_test_argv(default_command, target) for target in tests_to_run):
        return join_verification_steps(
            build_test_commands(default_command, tests_to_run)
        )
    return shlex.join(_test_argv(default_command, tests_to_run))


@lru_cache(maxsize=128)
def _argument_lengths(argument: str) -> tuple[int, int]:
    """缓存单参数的纯转义长度，避免试装批次时反复转义已有路径。"""
    return (
        len(shlex.quote(argument).encode("utf-8")),
        len(subprocess.list2cmdline([argument]).encode("utf-16-le")) // 2,
    )


def _argv_within_budget(argv: list[str]) -> bool:
    """按参数累加精确转义长度，包含分隔空格与 Windows 末尾 NUL。"""
    posix = max(0, len(argv) - 1)
    windows = max(1, len(argv))
    for argument in argv:
        # 超长参数必定超限，也不能进入有界转义缓存。
        if len(argument) > 6000:
            return False
        posix_size, windows_size = _argument_lengths(argument)
        posix += posix_size
        windows += windows_size
    return posix <= 6000 and windows <= 6000


def build_test_argv_batches(
    default_command: DefaultTestCommand, tests_to_run: list[str]
) -> list[list[str]]:
    """编译完整有序批次，保留重复目标，且不经过 shell 文本反向解析。"""
    if not tests_to_run or default_command.runner not in _TARGETED_RUNNERS:
        return [_test_argv(default_command, [])]
    default_command = _for_targets(default_command, tests_to_run)
    batches: list[list[str]] = []
    batch: list[str] = []
    for target in tests_to_run:
        shell_argv = _shell_test_argv(default_command, target)
        if shell_argv is not None:
            if not _argv_within_budget(shell_argv):
                raise ValueError("TEST_TARGET_EXCEEDS_COMMAND_BUDGET")
            if batch:
                batches.append(_test_argv(default_command, batch))
                batch = []
            batches.append(shell_argv)
            continue
        if not _argv_within_budget(_test_argv(default_command, [target])):
            raise ValueError("TEST_TARGET_EXCEEDS_COMMAND_BUDGET")
        candidate = _test_argv(default_command, [*batch, target])
        if batch and (len(batch) == 20 or not _argv_within_budget(candidate)):
            batches.append(_test_argv(default_command, batch))
            batch = []
        batch.append(target)
    if batch:
        batches.append(_test_argv(default_command, batch))
    return batches


def build_test_commands(
    default_command: DefaultTestCommand, tests_to_run: list[str]
) -> list[str]:
    """复用结构化批次渲染命令，避免计划与可复制文本丢失不同的目标。"""
    if not tests_to_run or default_command.runner not in _TARGETED_RUNNERS:
        return [default_command.command]
    return [
        shlex.join(argv)
        for argv in build_test_argv_batches(default_command, tests_to_run)
    ]


def _package_json_has_test_script(package_json: Path) -> bool:
    """Return True when package.json has a non-empty scripts.test entry."""
    try:
        data: Any = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    scripts = data.get("scripts")
    return isinstance(scripts, dict) and bool(scripts.get("test"))


def _node_test_command(root: Path) -> DefaultTestCommand:
    """Choose the local Node package manager's test command."""
    if (root / "bun.lockb").exists() or (root / "bun.lock").exists():
        return DefaultTestCommand("bun", "bun test")
    if (root / "pnpm-lock.yaml").exists():
        return DefaultTestCommand("pnpm", "pnpm test")
    if (root / "yarn.lock").exists():
        return DefaultTestCommand("yarn", "yarn test")
    return DefaultTestCommand("npm", "npm test")


def join_verification_steps(steps: list[str]) -> str:
    """组合内部 POSIX 引用的命令；Windows 使用 PowerShell 5.1 的失败即停语法。"""
    if sys.platform == "win32" and (len(steps) > 1 or (steps and "'" in steps[0])):
        return _powershell_verification_steps(steps)
    return " && ".join(steps)


def _powershell_verification_steps(steps: list[str]) -> str:
    """把各步骤的参数原样传给 PowerShell；检查每一步的退出状态。"""
    commands = []
    for step in steps:
        arguments = shlex.split(step)
        quoted = " ".join(
            "'" + argument.replace("'", "''") + "'" for argument in arguments
        )
        commands.append(
            "& " + quoted + "; if (-not $?) { throw 'Verification failed' }"
        )
    return "& { " + "; ".join(commands) + " }"
