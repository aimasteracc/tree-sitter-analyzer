"""#1691：``project_walk_cache`` 的遍历证据跨进程复用（落盘层）。

#1651 的遍历记忆只在进程内：每个新启动的 MCP 进程的首个 ``nav callers`` 都要
重新遍历整棵项目树并对每一项做 ``.gitignore`` 匹配（约 2,900 项，负载下数秒，
偶尔超出发现预算而把冷答案降级为 ``UNINDEXED_SOURCE_UNCHECKED``）。

这里把同一份记忆条目——遍历结果与其 ``lstat`` 证据——写到
``<项目>/.ast-cache/evidence-memo/``，冷进程按与进程内完全相同的规则复用：

* **键**：文件格式、代码指纹（``source_fingerprint``，覆盖遍历与忽略规则代码）、
  ``pathspec`` 版本、项目根绝对路径、起点与遍历参数。键文本原样存入文件，读出后
  逐字比对；键只决定找哪个文件，从不单独证明“未变”。
* **证据**：每个被列出目录及其规则文件的 ``lstat``（mode、size、mtime、ctime、
  inode、device）。取用时**全部重新 lstat**，任一不同即视为未命中（RFC-0030：
  绝不以“仅路径”判定为未变）。
* **竞争窗口**：只有进程内记忆接受的证据才会落盘，而进程内记忆拒绝遍历开始前
  ``RACY_WINDOW_NS`` 内修改过的目录 / 规则文件，因此落盘条目里没有 5 s 内的证据。
* **失败即不用**：目录缺失或是链接、文件损坏、格式或键不符一律当作未命中；
  写入失败静默放弃。``TSA_EVIDENCE_STORE=off`` 关闭落盘层。
"""

from __future__ import annotations

import hashlib
import marshal
import os
import stat
from collections.abc import Sequence
from pathlib import Path
from typing import Any

#: 文件格式版本；记录结构变化时递增。
FORMAT = 1
#: ``.ast-cache`` 下的目录名。
DIR_NAME = "evidence-memo"
#: 关闭落盘层的环境变量（值为 ``off`` / ``0`` / ``false``）。
ENV_VAR = "TSA_EVIDENCE_STORE"
_MARSHAL_VERSION = 4
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_PREFIX = "walk-"
#: 保留的遍历记忆文件数（每个起点一份，另留代码更新前后的余量）。
KEEP = 8

#: 一条证据：(路径, lstat 键)。
Evidence = tuple[tuple[str, tuple[int, ...]], ...]


def enabled() -> bool:
    """落盘层是否启用。"""
    return os.environ.get(ENV_VAR, "").strip().lower() not in {"off", "0", "false"}


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


def _pathspec_version() -> str:
    try:
        import pathspec
    except ImportError:  # pragma: no cover - pathspec is a hard dependency
        return "-"
    return str(getattr(pathspec, "__version__", "-"))


def key_text(full_key: tuple[object, ...]) -> str:
    """记忆键的稳定文本形式（集合按值排序，跨进程不受字符串哈希随机化影响）。"""
    from ...source_fingerprint import source_fingerprint

    parts = [
        str(FORMAT),
        source_fingerprint(),
        _pathspec_version(),
        *(_stable(part) for part in full_key),
    ]
    return "\x1f".join(parts)


def _stable(value: object) -> str:
    if isinstance(value, frozenset | set):
        return repr(sorted(repr(item) for item in value))
    return repr(value)


def _file_name(text: str) -> str:
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=20).hexdigest()
    return f"{_PREFIX}{digest}.bin"


def load(project_root: str, text: str) -> tuple[Evidence, tuple[str, ...]] | None:
    """键文本相符的已存条目（证据尚未复核）；否则 None。"""
    if not enabled():
        return None
    try:
        directory = _store_dir(project_root, create=False)
        if directory is None:
            return None
        data = (directory / _file_name(text)).read_bytes()
        payload = marshal.loads(data)  # nosec B302 — 只读本进程族写入的内建值，校验后才用
    except (OSError, ValueError, EOFError, TypeError):
        return None
    if not (
        isinstance(payload, tuple)
        and len(payload) == 4
        and payload[0] == FORMAT
        and payload[1] == text
    ):
        return None
    evidence, paths = payload[2], payload[3]
    if not (_valid_evidence(evidence) and _valid_paths(paths)):
        return None
    return evidence, paths


def _valid_evidence(evidence: Any) -> bool:
    return isinstance(evidence, tuple) and all(
        isinstance(item, tuple)
        and len(item) == 2
        and isinstance(item[0], str)
        and isinstance(item[1], tuple)
        and all(isinstance(number, int) for number in item[1])
        for item in evidence
    )


def _valid_paths(paths: Any) -> bool:
    return isinstance(paths, tuple) and all(isinstance(path, str) for path in paths)


def save(
    project_root: str, text: str, evidence: Evidence, paths: Sequence[str]
) -> None:
    """原子写入一条遍历记忆；任何失败都静默放弃。"""
    if not enabled():
        return
    directory = _store_dir(project_root, create=True)
    if directory is None:
        return
    try:
        data = marshal.dumps((FORMAT, text, evidence, tuple(paths)), _MARSHAL_VERSION)
    except ValueError:
        return
    target = directory / _file_name(text)
    temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, target)
        _prune(directory)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _prune(directory: Path) -> None:
    """只保留最近写入的 :data:`KEEP` 份（代码或参数变化后旧键不再被读到）。"""
    files = sorted(
        directory.glob(f"{_PREFIX}*.bin"),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for stale in files[KEEP:]:
        stale.unlink(missing_ok=True)
