"""#1700：索引指纹备忘录（#1561 / #1634）的跨进程落盘层。

``index_fingerprint`` 对每张查询可见表做全行排序哈希（本仓库约 50 万行）。进程内
备忘录让同一进程只算一次，但每个新启动的 MCP 进程都要重算：调用图标记精确的
索引（全部语法均已安装，即用户的常态）上，冷进程首个 ``nav callers`` 因此要
25–40 s。

备忘录的键本就是内容寻址的：项目根 + 主库 / WAL **完整字节**的 SHA-256（每次
捕获都对固定的私有副本或固定句柄重新计算）。指纹与符号投影判定都是“库内容 +
计算代码”的纯函数，因此这里按同一个键落盘：

* **键**：``(格式, 代码指纹, Python 版本, SQLite 版本, *备忘录键)``。备忘录键含
  每次捕获现算的字节摘要；任何字节变化（重写、失效标记、增量同步、新 generation）
  都换键。路径、generation id、mtime 都不单独构成证据（RFC-0030）。
* **读时复核**：取用时把完整键逐元素与记录比对，不只比对文件名哈希；记录的值须
  是 ``sha256:`` 指纹（或投影判定 ``"0"`` / ``"1"``）。任一不符即当作未命中重算。
* **只记成功**：与进程内备忘录相同，失败与超时从不入表。
* **不写项目目录**：只读捕获对 ``.ast-cache`` 是零写入的（快照测试逐字节核对），
  因此记录放在用户缓存目录 ``~/.tsa/cache/index-fingerprint/``（与 tools/list 的
  定义缓存同处），每个项目根一个文件；``TSA_INDEX_FINGERPRINT_CACHE_DIR`` 改目录，
  值为 ``off`` 或 ``TSA_EVIDENCE_STORE=off`` 时关闭落盘层。
* 有界：每个文件最近 :data:`MAX_ENTRIES` 条、目录最多 :data:`MAX_FILES` 个文件；
  缺失、损坏、格式不符一律当作空表，写入失败静默放弃。
"""

from __future__ import annotations

import hashlib
import marshal
import os
import re
import sqlite3
import stat
import sys
import threading
from pathlib import Path

#: 文件格式版本。
FORMAT = 1
#: 改写缓存目录的环境变量；值为 ``off`` 时关闭落盘层。
CACHE_DIR_ENV = "TSA_INDEX_FINGERPRINT_CACHE_DIR"
#: 关闭落盘层的总开关（与 #1691 的证据落盘层共用）。
ENV_VAR = "TSA_EVIDENCE_STORE"
#: 每个文件保留的记录数（每个库版本占指纹与投影判定两条）。
MAX_ENTRIES = 32
#: 目录中保留的项目文件数（最近写入者优先）。
MAX_FILES = 64
_MARSHAL_VERSION = 4
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
#: 指纹为 ``sha256:`` 加 64 位十六进制摘要；投影判定为 "0" / "1"。其他值不落盘。
_VALUE = re.compile(r"sha256:[0-9a-f]{64}|[01]")
_LOCK = threading.Lock()


def enabled() -> bool:
    """落盘层是否启用。"""
    return os.environ.get(ENV_VAR, "").strip().lower() not in {"off", "0", "false"}


def cache_dir() -> Path | None:
    """记录所在目录；关闭时为 None。"""
    configured = os.environ.get(CACHE_DIR_ENV, "").strip()
    if configured.lower() == "off":
        return None
    if configured:
        return Path(configured)
    return Path.home() / ".tsa" / "cache" / "index-fingerprint"


def _environment() -> tuple[str, ...]:
    from .source_fingerprint import source_fingerprint

    return (str(FORMAT), source_fingerprint(), sys.version, sqlite3.sqlite_version)


def stored_key(key: tuple[str, ...]) -> tuple[str, ...]:
    """备忘录键在落盘记录中的完整形式（含代码与运行时版本）。"""
    return (*_environment(), *key)


def _real_directory(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISDIR(info.st_mode) and not (
        getattr(info, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT
    )


def _store_file(root: str, create: bool) -> Path | None:
    directory = cache_dir()
    if directory is None:
        return None
    if create and not os.path.lexists(directory):
        try:
            directory.mkdir(parents=True)
        except OSError:
            return None
    if not _real_directory(directory):
        return None
    name = hashlib.blake2b(root.encode("utf-8", "surrogatepass"), digest_size=16)
    return directory / f"{name.hexdigest()}.bin"


def _read(path: Path | None) -> list[tuple[tuple[str, ...], str]]:
    if path is None:
        return []
    try:
        payload = marshal.loads(path.read_bytes())  # nosec B302 — 只读本进程族写入的内建值，校验后才用
    except (OSError, ValueError, EOFError, TypeError):
        return []
    if not (
        isinstance(payload, tuple)
        and len(payload) == 2
        and payload[0] == FORMAT
        and isinstance(payload[1], list)
    ):
        return []
    return [entry for entry in payload[1] if _valid_entry(entry)]


def _valid_entry(entry: object) -> bool:
    return (
        isinstance(entry, tuple)
        and len(entry) == 2
        and isinstance(entry[0], tuple)
        and all(isinstance(part, str) for part in entry[0])
        and isinstance(entry[1], str)
        and _VALUE.fullmatch(entry[1]) is not None
    )


def lookup(root: str, key: tuple[str, ...]) -> str | None:
    """完整键逐元素相符的已存值；否则 None（调用方照常计算）。"""
    if not enabled():
        return None
    wanted = stored_key(key)
    for recorded, value in _read(_store_file(root, create=False)):
        if recorded == wanted:
            return value
    return None


def store(root: str, key: tuple[str, ...], value: str) -> None:
    """记录一次成功计算的值（有界、原子写入）；任何失败都静默放弃。"""
    if not enabled() or _VALUE.fullmatch(value) is None:
        return
    path = _store_file(root, create=True)
    if path is None:
        return
    wanted = stored_key(key)
    with _LOCK:
        entries = [entry for entry in _read(path) if entry[0] != wanted]
        entries.append((wanted, value))
        entries = entries[-MAX_ENTRIES:]
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            temporary.write_bytes(marshal.dumps((FORMAT, entries), _MARSHAL_VERSION))
            os.replace(temporary, path)
            _prune(path.parent)
        except (OSError, ValueError):
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _prune(directory: Path) -> None:
    """目录最多保留 :data:`MAX_FILES` 个项目文件（按写入时间，最近的优先）。"""
    files = sorted(
        directory.glob("*.bin"), key=lambda path: path.stat().st_mtime_ns, reverse=True
    )
    for stale in files[MAX_FILES:]:
        stale.unlink(missing_ok=True)
