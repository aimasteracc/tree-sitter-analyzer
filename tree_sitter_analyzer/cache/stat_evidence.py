"""#1707：内容未变、只有 stat 戳记变化的文件的待合并戳记（不发布新版本）。

dogfood 第 9 轮：只改 mtime、字节完全相同（``touch``、同内容的 ``git checkout``、
编辑器“保存未修改”、换入再换回的工具）也会让刷新重新提取文件、跑全局回填并
发布一份约 350 MB 的新版本（35–47 s）。内容证据（RFC-0030）说的是“未变”，
只有活动版本行里的 ``(mtime_ns, file_size)`` 戳记过期了。

零变化判定（``generation_noop_precheck``）现在以内容摘要为准：本次捕获读取的
**当前字节**的摘要与行相同、大小相同、只有 mtime 不同的文件仍算未变。活动版本
已封存（RFC-0032），不能原地改行；新戳记写到本模块的旁路记录里：

    ``<项目>/.ast-cache/evidence-memo/stat-stamps.bin``

一条记录 ``路径 -> (mtime_ns, file_size, content_hash)`` 的含义是：“处于这个戳记
的该文件，其当前字节的摘要是 ``content_hash``（本次刷新读取并核对过）”。读者在行
戳记与磁盘不一致时查它：记录的戳记等于磁盘戳记、且记录的摘要等于**该行**的摘要，
该行即可为这个文件作证——与发布一份只改了戳记的新版本得到的行完全相同。

* **绑定内容**：记录绑定行的摘要，不绑定版本或路径；行摘要不同（文件之后真的
  改过并已重新索引）时记录不起作用。
* **竞争窗口**：mtime 距写入时刻不足 :data:`RACY_WINDOW_NS`（或在未来）的文件不
  记录——同一时间戳刻度内的第二次同大小写入不会改变戳记，必须每次重新读取摘要。
  这样的文件留给下一次刷新（届时已出窗口）记录；在此之前读者照常按摘要比对。
* **替换语义**：每次零变化刷新写入当时的完整漂移集合；发布新版本时删除记录
  （新版本的行已带新戳记，见 ``indexer_io.walk_and_partition``）。
* **失败即不用**：目录缺失或是链接、文件损坏、格式或根目录不符一律视为没有记录；
  写入失败静默放弃。``TSA_EVIDENCE_STORE=off`` 关闭本层（读者退回按摘要比对）。
"""

from __future__ import annotations

import marshal
import os
import stat
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

#: 文件格式版本；记录结构变化时递增。
FORMAT = 1
#: ``.ast-cache`` 下的目录名（与 #1691 的证据记忆同一目录）。
DIR_NAME = "evidence-memo"
FILE_NAME = "stat-stamps.bin"
#: 关闭落盘证据层的环境变量（值为 ``off`` / ``0`` / ``false``）。
ENV_VAR = "TSA_EVIDENCE_STORE"
#: mtime 距当前不足此值的文件不记录（与 ``source_hash_cache`` 相同）。
RACY_WINDOW_NS = 5_000_000_000
#: 记录条数上限；超出时整份不写（读者按摘要比对，结果不变，只是更慢）。
MAX_ENTRIES = 200_000
_MARSHAL_VERSION = 4
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400

#: 一条记录：(mtime_ns, file_size, content_hash)。
Stamp = tuple[int, int, str]
_EMPTY: Mapping[str, Stamp] = {}


def enabled() -> bool:
    """落盘层是否启用。"""
    return os.environ.get(ENV_VAR, "").strip().lower() not in {"off", "0", "false"}


def _now_ns() -> int:
    """竞争窗口判定使用的墙钟（测试可替换）。"""
    return time.time_ns()


def _real_directory(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISDIR(info.st_mode) and not (
        getattr(info, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT
    )


def _store_dir(project_root: str, create: bool) -> Path | None:
    base = Path(project_root) / ".ast-cache"
    if not _real_directory(base):
        return None
    directory = base / DIR_NAME
    if create and not os.path.lexists(directory):
        try:
            directory.mkdir()
        except OSError:
            return None
    return directory if _real_directory(directory) else None


def _root_text(project_root: str) -> str:
    return os.path.normcase(os.path.realpath(project_root))


def is_racy(mtime_ns: int, now_ns: int | None = None) -> bool:
    """戳记处于时间戳竞争窗口内（或在未来），不能作为“未变”的证据记录。"""
    now = _now_ns() if now_ns is None else now_ns
    return now - int(mtime_ns) < RACY_WINDOW_NS


def record(project_root: str, stamps: Mapping[str, Stamp]) -> int:
    """以 ``stamps``（本次刷新核对过的漂移文件）替换记录；返回写入的条数。

    竞争窗口内的文件被跳过。没有可写条目时删除旧记录。
    """
    if not enabled():
        return 0
    now = _now_ns()
    kept = {
        str(path): (int(entry[0]), int(entry[1]), str(entry[2]))
        for path, entry in stamps.items()
        if not is_racy(entry[0], now)
    }
    if not kept or len(kept) > MAX_ENTRIES:
        clear(project_root)
        return 0
    directory = _store_dir(project_root, create=True)
    if directory is None:
        return 0
    try:
        data = marshal.dumps((FORMAT, _root_text(project_root), kept), _MARSHAL_VERSION)
    except ValueError:
        return 0
    target = directory / FILE_NAME
    temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, target)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return 0
    return len(kept)


def clear(project_root: str) -> None:
    """删除记录（发布新版本后、或没有漂移时）。"""
    directory = _store_dir(project_root, create=False)
    if directory is None:
        return
    try:
        (directory / FILE_NAME).unlink(missing_ok=True)
    except OSError:
        pass


#: 进程内记忆：记录文件路径 -> (文件 stat 证据, 内容)。
_MEMO: dict[str, tuple[tuple[int, ...], Mapping[str, Stamp]]] = {}
_MEMO_LOCK = threading.Lock()


def load(project_root: str) -> Mapping[str, Stamp]:
    """当前记录（只读映射）；没有或不可用时为空映射。"""
    if not enabled():
        return _EMPTY
    directory = _store_dir(project_root, create=False)
    if directory is None:
        return _EMPTY
    path = directory / FILE_NAME
    try:
        info = os.lstat(path)
    except OSError:
        return _EMPTY
    if not stat.S_ISREG(info.st_mode):
        return _EMPTY
    evidence = (info.st_size, info.st_mtime_ns, info.st_ino, info.st_dev)
    with _MEMO_LOCK:
        cached = _MEMO.get(str(path))
    if cached is not None and cached[0] == evidence:
        return cached[1]
    stamps = _read(path, project_root)
    if not is_racy(info.st_mtime_ns):
        # 记录文件本身在竞争窗口内被替换时不记忆（下一次重新读取）。
        with _MEMO_LOCK:
            _MEMO[str(path)] = (evidence, stamps)
    return stamps


def _read(path: Path, project_root: str) -> Mapping[str, Stamp]:
    try:
        payload: Any = marshal.loads(path.read_bytes())  # nosec B302 — 校验后才用
    except (OSError, ValueError, EOFError, TypeError):
        return _EMPTY
    if not (
        isinstance(payload, tuple)
        and len(payload) == 3
        and payload[0] == FORMAT
        and payload[1] == _root_text(project_root)
        and isinstance(payload[2], dict)
    ):
        return _EMPTY
    stamps = payload[2]
    if not all(_valid(path_, entry) for path_, entry in stamps.items()):
        return _EMPTY
    return stamps


def _valid(path: Any, entry: Any) -> bool:
    return (
        isinstance(path, str)
        and isinstance(entry, tuple)
        and len(entry) == 3
        and type(entry[0]) is int
        and type(entry[1]) is int
        and isinstance(entry[2], str)
        and bool(entry[2])
    )


def vouches(
    stamps: Mapping[str, Stamp],
    rel_path: str,
    live: tuple[int, int],
    row_hash: str,
) -> bool:
    """记录证明：磁盘戳记 ``live`` = ``(mtime_ns, size)`` 下该文件的内容即该行。"""
    entry = stamps.get(rel_path.replace("\\", "/"))
    return entry is not None and entry == (int(live[0]), int(live[1]), str(row_hash))


def effective_stamp(
    stamps: Mapping[str, Stamp],
    rel_path: str,
    row: tuple[int, int, str],
    live: tuple[int, int] | None,
) -> tuple[int, int]:
    """行在合并记录后的 ``(mtime_ns, file_size)``：记录为当前文件作证时取磁盘戳记。"""
    if live is not None and vouches(stamps, rel_path, live, row[2]):
        return (int(live[0]), int(live[1]))
    return (int(row[0]), int(row[1]))
