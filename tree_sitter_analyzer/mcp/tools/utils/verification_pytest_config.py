"""从项目配置提取保守的定向测试层级策略，不导入用户测试。"""

from __future__ import annotations

import configparser
import os
import re
import shlex
import stat
import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    # tomli 只随 Python 3.10 安装；检查器环境可能缺包，或已忽略缺失导入。
    import tomli as tomllib  # type: ignore[import-not-found, unused-ignore]

_CONFIG_NAMES = (
    "pytest.toml",
    ".pytest.toml",
    "pytest.ini",
    ".pytest.ini",
    "pyproject.toml",
    "tox.ini",
    "setup.cfg",
)
_TARGET_TIERS = frozenset({"e2e", "slow", "full_language"})
_MAX_CONFIG_BYTES = 65536
_open_config = os.open


class _CaseSensitiveConfig(configparser.ConfigParser):
    def optionxform(self, optionstr: str) -> str:
        return optionstr


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _path_identity(info: os.stat_result) -> tuple[int, ...]:
    """路径与句柄之间只比较同语义时间；同句柄读取前后仍检查 ctime。"""
    # Windows 3.12 的 lstat.ctime 是创建时间，fstat.ctime 却是元数据变更时间。
    if os.name == "nt":
        return (
            *_identity(info)[:-1],
            getattr(info, "st_birthtime_ns", info.st_ctime_ns),
        )
    return _identity(info)


def _read_config(path: Path) -> str:
    """只读取已核对身份的普通文件，拒绝链接、特殊文件及超大配置。"""
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_CONFIG_BYTES:
        raise ValueError("PYTEST_CONFIG_UNSUPPORTED")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = _open_config(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        current = os.fstat(stream.fileno())
        if not stat.S_ISREG(current.st_mode) or _path_identity(
            before
        ) != _path_identity(current):
            raise ValueError("PYTEST_CONFIG_CHANGED")
        raw = stream.read(_MAX_CONFIG_BYTES + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > _MAX_CONFIG_BYTES:
        raise ValueError("PYTEST_CONFIG_TOO_LARGE")
    if _identity(current) != _identity(after):
        raise ValueError("PYTEST_CONFIG_CHANGED")
    return raw.decode("utf-8")


def _config_options(root: Path) -> Any:
    for name in _CONFIG_NAMES:
        path = root / name
        if not os.path.lexists(path):
            continue
        # 原生 TOML 配置的优先级依赖 pytest 版本，不能擅自选用旧文件。
        if name in {"pytest.toml", ".pytest.toml"}:
            return None
        text = _read_config(path)
        if name == "pyproject.toml":
            pytest = tomllib.loads(text).get("tool", {}).get("pytest")
            if pytest is None:
                continue
            # 原生表在新 pytest 中优先；版本不明时不能采用低优先级配置。
            if "ini_options" not in pytest or set(pytest) != {"ini_options"}:
                return None
            return pytest["ini_options"].get("addopts", "")
        parser = _CaseSensitiveConfig(interpolation=None)
        parser.read_string(text)
        # pytest 的 INI 解析没有 DEFAULT 继承，也不把选项名转成小写。
        if parser.defaults():
            return None
        section = "tool:pytest" if name == "setup.cfg" else "pytest"
        if parser.has_section(section):
            return parser.get(section, "addopts", fallback="")
        if name in {"pytest.ini", ".pytest.ini"}:
            return ""
    return None


def targeted_marker_expression(root: Path) -> str | None:
    """仅放行配置中明确排除的常规层级，保留外部资源和未知限制。"""
    if os.environ.get("PYTEST_ADDOPTS"):
        return None
    try:
        options = _config_options(root)
        argv = shlex.split(options) if isinstance(options, str) else options
        if not isinstance(argv, list) or any(not isinstance(arg, str) for arg in argv):
            return None
        expression = None
        for index, argument in enumerate(argv):
            if argument in {
                "-c",
                "-o",
                "--config-file",
                "--override-ini",
            } or argument.startswith(("--config-file=", "--override-ini=", "-c", "-o")):
                return None
            if argument == "-m":
                expression = argv[index + 1]
            elif argument.startswith("-m"):
                expression = argument[2:]
        if not expression:
            return None
        terms = re.split(r"\s+and\s+", expression.strip())
        matches = [
            re.fullmatch(r"not\s+([A-Za-z_]\w*)", term.strip()) for term in terms
        ]
        if not all(matches):
            return None
        markers = [match.group(1) for match in matches if match is not None]
        if not _TARGET_TIERS.intersection(markers):
            return None
        retained = [marker for marker in markers if marker not in _TARGET_TIERS]
        # 定向选择常规层级不代表授权外部网络或基准测量。
        for marker in ("network", "benchmark"):
            if marker not in retained:
                retained.append(marker)
        return " and ".join("not " + marker for marker in retained)
    except (
        OSError,
        ValueError,
        configparser.Error,
        IndexError,
        AttributeError,
        TypeError,
    ):
        return None


def targets_share_root_config(root: str, targets: list[str]) -> bool:
    """子项目配置或越界目标存在时，不用根配置覆盖它们自己的选择规则。"""
    checked: set[Path] = set()
    try:
        base = Path(root).resolve()
        for target in targets:
            path = (base / target.partition("::")[0]).resolve()
            if not path.is_relative_to(base):
                return False
            parent = path if path.is_dir() else path.parent
            while parent != base:
                if parent in checked:
                    break
                checked.add(parent)
                if any(os.path.lexists(parent / name) for name in _CONFIG_NAMES):
                    return False
                parent = parent.parent
        return True
    except (OSError, RuntimeError):
        return False
