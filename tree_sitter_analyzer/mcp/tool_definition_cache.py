"""按安装源码指纹缓存门面工具定义，``tools/list`` 不再构建整个注册表（#1675）。

冷启动时 ``tools/list`` 为了 8 个门面的定义导入并实例化全部约 100 个内部工具
（约 500 个模块）；定义本身只取决于包源码（动作名、描述、核心参数、昂贵路由
表），与项目根、环境变量和已安装语法无关。

缓存键是包源码的内容指纹：包版本、Python 版本，以及包目录下每个 ``.py``
文件的相对路径、字节数与 mtime（``os.scandir`` 自带，无需逐个打开文件）。
任何源码变化都会改变键而未命中，未命中即照旧构建注册表并写回缓存；读写
失败只会退回构建，绝不影响答复。缓存内容是定义的 JSON 原文，命中与构建
交给 MCP SDK 的字典逐字节相同。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

#: 覆盖缓存目录（测试与只读主目录）；值为 ``off`` 时停用缓存。
CACHE_DIR_ENV = "TSA_TOOL_DEFINITION_CACHE_DIR"
_CACHE_PREFIX = "tool-definitions-"
_FORMAT = 1
#: 保留的缓存文件个数（不同工作树或版本各一份）。
_KEEP = 8


def _package_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def source_fingerprint(package_dir: Path | None = None) -> str:
    """包源码的指纹：版本、解释器与每个 ``.py`` 的 (相对路径, 字节数, mtime)。"""
    from .. import __version__

    root = package_dir or _package_dir()
    hasher = hashlib.blake2b(digest_size=20)
    hasher.update(f"{_FORMAT}|{__version__}|{sys.version}\n".encode())
    stack = [root]
    entries: list[str] = []
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as scan:
            for entry in scan:
                if entry.is_dir(follow_symlinks=False):
                    if entry.name != "__pycache__":
                        stack.append(Path(entry.path))
                elif entry.name.endswith(".py"):
                    info = entry.stat(follow_symlinks=False)
                    rel = Path(entry.path).relative_to(root).as_posix()
                    entries.append(f"{rel}|{info.st_size}|{info.st_mtime_ns}")
    for line in sorted(entries):
        hasher.update(line.encode("utf-8") + b"\n")
    return hasher.hexdigest()


def cache_dir() -> Path | None:
    configured = os.environ.get(CACHE_DIR_ENV)
    if configured == "off":
        return None
    if configured:
        return Path(configured)
    return Path.home() / ".tsa" / "cache"


def _cache_file(directory: Path, fingerprint: str) -> Path:
    return directory / f"{_CACHE_PREFIX}{fingerprint}.json"


def load(fingerprint: str) -> list[dict[str, Any]] | None:
    """指纹相同的缓存定义；不存在、损坏或指纹不符时 None。"""
    directory = cache_dir()
    if directory is None:
        return None
    try:
        payload = json.loads(_cache_file(directory, fingerprint).read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("fingerprint") != fingerprint:
        return None
    definitions = payload.get("definitions")
    if not isinstance(definitions, list) or not all(
        isinstance(item, dict) for item in definitions
    ):
        return None
    return definitions


def store(fingerprint: str, text: str) -> None:
    """原子写入本指纹的缓存，只保留最近的几份；任何失败都静默放弃。"""
    directory = cache_dir()
    if directory is None:
        return
    target = _cache_file(directory, fingerprint)
    temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps({"fingerprint": fingerprint, "definitions": json.loads(text)}),
            encoding="utf-8",
        )
        os.replace(temporary, target)
        _prune(directory)
    except OSError:
        temporary.unlink(missing_ok=True)


def _prune(directory: Path) -> None:
    """多个安装（工作树、版本）共用目录：按修改时间只留最近的 ``_KEEP`` 份。"""
    files = sorted(
        directory.glob(f"{_CACHE_PREFIX}*.json"),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for stale in files[_KEEP:]:
        stale.unlink(missing_ok=True)


def cached_definitions(
    build: Callable[[], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """命中则返回缓存定义，否则调用 ``build`` 构建并写回。

    未命中时也返回 JSON 往返后的定义，命中与未命中走同一条数据路径。
    """
    try:
        fingerprint = source_fingerprint()
    except OSError:
        return build()
    definitions = load(fingerprint)
    if definitions is not None:
        return definitions
    built = build()
    try:
        text = json.dumps(built)
    except (TypeError, ValueError):
        return built  # 不可 JSON 化的定义不缓存
    store(fingerprint, text)
    roundtrip: list[dict[str, Any]] = json.loads(text)
    return roundtrip
