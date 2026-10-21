"""#1691（第 3 部分）：索引库文件的“纯内容事实”跨进程复用，按库文件 stat 证据。

冷进程的首个 ``nav callers`` 在构建内存调用图前，必须读出约 19 万条调用边、
计算 #1663 的构图输入摘要，才能找到 #1675 落盘的边解析结果；调用图标记复核
（#1710）同样每个新进程都要对全部边做两次反连接扫描。这些都是库内容的纯函数，
而已发布的 generation 是封存只读的文件。

这里按库文件（及 ``-wal`` / ``-journal``）的 stat 证据记录这些事实：

* **证据**：每个文件的 ``(size, mtime_ns, 变更时间, ino, dev)``。变更时间取
  ``file_change_time``（POSIX 为 ``st_ctime``；Windows 读 NTFS ``ChangeTime``，
  内容改写后把 mtime 设回也会改变它）；取不到即不复用。任何提交都会改变库或
  WAL 的大小 / mtime / 变更时间。
* **竞争窗口**：任一文件的 mtime 或变更时间距当前不足 :data:`RACY_WINDOW_NS` 时
  不读也不记。
* **取用时复核**：每次都重新取证据，与记录逐元素比较；键另含代码指纹（事实由
  代码计算）与库文件的绝对路径。结果记在计算**之前**取得的证据下。
* **不写项目目录**：只读路径对 ``.ast-cache`` 是零写入的；记录放在
  ``~/.tsa/cache/index-facts/``（``TSA_INDEX_FACTS_DIR`` 改目录；值为 ``off`` 或
  ``TSA_EVIDENCE_STORE=off`` 时关闭）。缺失、损坏、格式不符一律当作未命中。
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

#: 记录格式版本。
FORMAT = 1
#: 改写目录的环境变量；``off`` 关闭。
DIR_ENV = "TSA_INDEX_FACTS_DIR"
#: 与 #1691 / #1700 / #1710 共用的落盘总开关。
STORE_ENV = "TSA_EVIDENCE_STORE"
#: mtime / 变更时间距当前不足此值的文件不读不记。
RACY_WINDOW_NS = 5_000_000_000
#: 目录中保留的库文件记录数。
MAX_FILES = 32
_SIDECARS = ("", "-wal", "-journal")
_LOCK = threading.Lock()


def store_dir() -> Path | None:
    """记录目录；关闭时为 None。"""
    if os.environ.get(STORE_ENV, "").strip().lower() in {"off", "0", "false"}:
        return None
    configured = os.environ.get(DIR_ENV, "").strip()
    if configured.lower() == "off":
        return None
    if configured:
        return Path(configured)
    return Path.home() / ".tsa" / "cache" / "index-facts"


def evidence(database: str | None) -> tuple[Any, ...] | None:
    """库文件当前的证据；文件不是磁盘库、不可读或处于竞争窗口时为 None。"""
    from ..file_change_time import change_time_ns

    if not database or database == ":memory:" or store_dir() is None:
        return None  # 落盘层关闭时不取证据（省去每次构图的 stat 与句柄）
    path = os.path.abspath(database)
    stamps: list[Any] = []
    now = time.time_ns()
    for suffix in _SIDECARS:
        target = path + suffix
        try:
            info = os.stat(target)
        except FileNotFoundError:
            if not suffix:
                return None
            stamps.append(None)
            continue
        except OSError:
            return None
        change = change_time_ns(target, info)
        if change is None:
            return None
        if now - info.st_mtime_ns < RACY_WINDOW_NS or now - change < RACY_WINDOW_NS:
            return None
        stamps.append(
            [
                int(info.st_size),
                int(info.st_mtime_ns),
                int(change),
                int(info.st_ino),
                int(info.st_dev),
            ]
        )
    return (path, *stamps)


def _key(stamp: tuple[Any, ...], name: str) -> str:
    from ..source_fingerprint import source_fingerprint

    text = json.dumps([FORMAT, source_fingerprint(), name, list(stamp)])
    return hashlib.blake2b(text.encode("utf-8"), digest_size=20).hexdigest()


def _file(database_path: str) -> Path | None:
    directory = store_dir()
    if directory is None:
        return None
    name = hashlib.blake2b(
        database_path.encode("utf-8", "surrogatepass"), digest_size=16
    )
    return directory / f"{name.hexdigest()}.json"


def _read(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not (isinstance(payload, dict) and payload.get("format") == FORMAT):
        return {}
    facts = payload.get("facts")
    return facts if isinstance(facts, dict) else {}


def lookup(stamp: tuple[Any, ...] | None, name: str) -> Any:
    """``stamp`` 下记录的事实 ``name``；没有、证据不符或无效时为 None。

    ``stamp`` 须由调用方刚用 :func:`evidence` 取得；这里再取一次并比较，二者不同
    （刚刚有写入）也视为未命中。
    """
    if stamp is None or evidence(stamp[0]) != stamp:
        return None
    path = _file(stamp[0])
    if path is None:
        return None
    entry = _read(path).get(_key(stamp, name))
    if not isinstance(entry, dict) or entry.get("stamp") != list(stamp):
        return None
    return entry.get("value")


def record(stamp: tuple[Any, ...] | None, name: str, value: Any) -> None:
    """把计算**之前**取得的 ``stamp`` 下的事实写入记录；任何失败都静默放弃。"""
    if stamp is None:
        return
    path = _file(stamp[0])
    if path is None:
        return
    with _LOCK:
        facts = _read(path)
        facts[_key(stamp, name)] = {"stamp": list(stamp), "value": value}
        while len(facts) > 16:
            facts.pop(next(iter(facts)))
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps({"format": FORMAT, "facts": facts}), encoding="utf-8"
            )
            os.replace(temporary, path)
            _prune(path.parent)
        except (OSError, TypeError, ValueError):
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _prune(directory: Path) -> None:
    files = sorted(
        directory.glob("*.json"), key=lambda path: path.stat().st_mtime_ns, reverse=True
    )
    for stale in files[MAX_FILES:]:
        stale.unlink(missing_ok=True)


def database_of(connection: Any) -> str | None:
    """连接实际读取的主库文件路径（``PRAGMA database_list``）；内存库为 None。"""
    try:
        row = connection.execute("PRAGMA database_list").fetchone()
    except Exception:  # noqa: BLE001 — 任何失败都只是不复用
        return None
    if row is None or len(row) < 3 or not row[2]:
        return None
    return str(row[2])
