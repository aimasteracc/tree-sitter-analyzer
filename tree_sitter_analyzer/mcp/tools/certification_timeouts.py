"""#1710：不再为“注定超时”的认证捕获每次付出 10 s。

调用图标记精确的索引上，``nav callers`` 每次都先尝试认证快照捕获（复制库与 WAL、
内存 backup、四遍源码清单、投影核验）。本仓库（约 2.5k 文件）上捕获要 15 s 左右，
超过 10 s 的捕获期限，于是每次都以 ``INDEX_SNAPSHOT_DEADLINE`` 失败、被丢弃，再走
未认证的回退路径——冷、热调用都白付约 10 s。

这里记住“这份索引 + 这份源码状态下，捕获在期限内完成不了”，状态不变时直接走
同一条未认证回退路径：

* **只会更保守**：跳过捕获与捕获超时走的是完全相同的回退代码，答案逐字节相同；
  记忆从不让答案变成“已认证”。真正完成的捕获照常给出认证答案，并清除记忆。
* **键**：代码指纹、项目根、``relation_freshness.index_identity``（generation、
  ``ast_index`` 行数与最新 ``indexed_at``、``edges`` 最大 rowid；按库文件 stat 记忆），
  以及源码的 stat 证据摘要：每个已索引文件的 ``(size, mtime_ns)``（不存在记为缺失）
  与其所在目录（含项目根）的 ``mtime_ns``——编辑、删除、新增文件都会改变它。
  任一不同即视为未命中，重新尝试捕获。路径或 generation id 从不单独作数。
* **定期重试**：即使状态不变，距记录超过 :data:`RETRY_SECONDS` 也重新尝试一次
  （机器负载下降后可恢复认证）。
* 只记录期限类失败（:data:`TIMEOUT_REASONS`）；其他失败原样照旧。
* 记录同时落盘到用户缓存目录 ``~/.tsa/cache/certification-timeouts/``（不写项目
  的 ``.ast-cache``），使新进程的首个调用同样跳过；``TSA_CERTIFICATION_TIMEOUT_DIR``
  改目录，值为 ``off`` 或 ``TSA_EVIDENCE_STORE=off`` 时只在进程内记忆。
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

#: 记录格式版本。
FORMAT = 1
#: 视为“在期限内完成不了”的捕获失败原因。
TIMEOUT_REASONS = frozenset({"INDEX_SNAPSHOT_DEADLINE", "SOURCE_SCAN_DEADLINE"})
#: 状态不变时，距记录多久后重新尝试一次捕获。
RETRY_SECONDS = 600.0
#: 改写落盘目录的环境变量；``off`` 只在进程内记忆。
DIR_ENV = "TSA_CERTIFICATION_TIMEOUT_DIR"
#: 与 #1691 / #1700 共用的落盘总开关。
STORE_ENV = "TSA_EVIDENCE_STORE"

_LOCK = threading.Lock()
#: 进程内记忆：项目根 -> (键, 记录时刻 time.time())。
_MEMO: dict[str, tuple[str, float]] = {}


def _now() -> float:
    """记录与重试判定使用的墙钟（测试可替换）。"""
    return time.time()


def clear() -> None:
    """丢弃进程内记忆（测试用：如同新进程）。"""
    with _LOCK:
        _MEMO.clear()


def store_dir() -> Path | None:
    """落盘目录；关闭时为 None。"""
    if os.environ.get(STORE_ENV, "").strip().lower() in {"off", "0", "false"}:
        return None
    configured = os.environ.get(DIR_ENV, "").strip()
    if configured.lower() == "off":
        return None
    if configured:
        return Path(configured)
    return Path.home() / ".tsa" / "cache" / "certification-timeouts"


def evidence_key(project_root: str) -> str | None:
    """当前“索引 + 源码”状态的键；读不到索引时为 None（不记忆、不跳过）。"""
    from ...source_fingerprint import source_fingerprint
    from .relation_freshness import index_identity

    root = os.path.realpath(project_root)
    identity = index_identity(root)
    if "unreadable" in identity or "absent" in identity or "unresolvable" in identity:
        return None
    files = _indexed_files(root)
    if files is None:
        return None
    hasher = hashlib.blake2b(digest_size=20)
    hasher.update(f"{FORMAT}\x1f{source_fingerprint()}\x1f{root}\x1f".encode())
    hasher.update(repr(identity).encode("utf-8", "surrogatepass"))
    for part in _source_stamps(root, files):
        hasher.update(part.encode("utf-8", "surrogatepass") + b"\n")
    return hasher.hexdigest()


def _indexed_files(root: str) -> list[str] | None:
    from ...cache.generation_routing import resolve_index_location

    try:
        database = resolve_index_location(root).path
        conn = sqlite3.connect(
            database.absolute().as_uri() + "?mode=rw",
            uri=True,
            timeout=10,
            check_same_thread=False,
        )
    except (OSError, ValueError, sqlite3.Error):
        return None
    try:
        conn.execute("PRAGMA query_only=ON")
        return sorted(
            str(row[0]) for row in conn.execute("SELECT file_path FROM ast_index")
        )
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _source_stamps(root: str, files: list[str]) -> list[str]:
    """每个已索引文件与其所在目录（含项目根）的 stat 证据，有序。"""
    parts: list[str] = []
    directories = {""}
    for relative in files:
        parts.append(f"f\x1f{relative}\x1f{_stamp(os.path.join(root, relative))}")
        parent = relative.rpartition("/")[0]
        while parent not in directories:
            directories.add(parent)
            parent = parent.rpartition("/")[0]
    for relative in sorted(directories):
        path = os.path.join(root, relative) if relative else root
        parts.append(f"d\x1f{relative}\x1f{_stamp(path, directory=True)}")
    return parts


def _stamp(path: str, *, directory: bool = False) -> str:
    try:
        info = os.stat(path)
    except OSError:
        return "missing"
    if directory:
        return str(info.st_mtime_ns)
    return f"{info.st_size}:{info.st_mtime_ns}"


def should_skip(project_root: str) -> bool:
    """当前状态下是否已知捕获在期限内完成不了（记录存在、键相符且未到重试时刻）。

    没有任何记录时不计算证据（不增加正常路径的开销）。
    """
    root = os.path.realpath(project_root)
    with _LOCK:
        known = _MEMO.get(root)
    if known is None:
        known = _load(root)
        if known is None:
            return False
        with _LOCK:
            _MEMO.setdefault(root, known)
    if _now() - known[1] >= RETRY_SECONDS:
        return False
    return evidence_key(project_root) == known[0]


def record(project_root: str, reason: str | None) -> None:
    """一次捕获的结果：期限类失败记下当前状态的键；其他结果清除记录。"""
    root = os.path.realpath(project_root)
    if reason in TIMEOUT_REASONS:
        key = evidence_key(project_root)
        if key is None:
            return
        entry = (key, _now())
        with _LOCK:
            _MEMO[root] = entry
        _save(root, entry)
        return
    with _LOCK:
        removed = _MEMO.pop(root, None)
    if removed is not None or _file_exists(root):
        _remove(root)


def _file_exists(root: str) -> bool:
    path = _file(root)
    return path is not None and path.exists()


def _file(root: str) -> Path | None:
    directory = store_dir()
    if directory is None:
        return None
    name = hashlib.blake2b(root.encode("utf-8", "surrogatepass"), digest_size=16)
    return directory / f"{name.hexdigest()}.json"


def _load(root: str) -> tuple[str, float] | None:
    path = _file(root)
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not (
        isinstance(payload, dict)
        and payload.get("format") == FORMAT
        and payload.get("root") == root
        and isinstance(payload.get("key"), str)
        and isinstance(payload.get("recorded_at"), int | float)
    ):
        return None
    return str(payload["key"]), float(payload["recorded_at"])


def _save(root: str, entry: tuple[str, float]) -> None:
    path = _file(root)
    if path is None:
        return
    data: dict[str, Any] = {
        "format": FORMAT,
        "root": root,
        "key": entry[0],
        "recorded_at": entry[1],
    }
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(data), encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _remove(root: str) -> None:
    path = _file(root)
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
