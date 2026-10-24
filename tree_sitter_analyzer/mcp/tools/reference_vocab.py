"""#1691：非调用引用扫描的跨进程证据——每个文件的“词表”，按 stat 证据复用。

#1598 的扫描先按字节预筛：同语言的约 1,700 个已索引文件（另加配置文件）中，
只有字节含名字的文件才进入剥离与逐行匹配。冷进程没有 #1651 的进程内字节缓存，
每个新进程的首个 ``nav callers`` 都要重新打开、读取全部文件，只为得出
“不含名字”。

预筛只问“名字的字节是否出现在文件里”。名字是标识符：它的每个字节都属于
:data:`_WORD_BYTE`（ASCII 字母数字、``_``、``$`` 与全部非 ASCII 字节）。名字的
任何一次出现都落在文件中某个由这些字节组成的极大连续段（“词”）之内，因此

    名字 in 文件字节  ⟺  名字 in 任一词  ⟺  名字 in b"\\0".join(词集合)

（``\\0`` 不属于 :data:`_WORD_BYTE`，拼接不会造出跨词的出现）。名字含有该集合
之外的字节时，这条等价不成立，照常读取文件。

* **键**：每条记录绑定读取时的 stat 证据 ``(size, mtime_ns, ctime_ns, ino, dev)``，
  与 ``evidence_file_cache`` 完全相同；取用前**重新 stat**，任一不同即照常读取
  （RFC-0030：绝不以“仅路径”判定为未变）。
* **竞争窗口**：只有 mtime 早于记录时刻 ``RACY_WINDOW_NS``（5 s）的读取才被记录，
  与进程内字节缓存相同；读取前后 stat 不一致的读取不记录。
* **只会读得更少，不会答得不同**：判定“含名字”的文件照常经 ``FILE_CACHE`` 读取
  当前字节并剥离；只有证据仍成立、且词表证明不含名字的文件才不打开。
* 落盘于 ``<项目>/.ast-cache/evidence-memo/``，键另含代码指纹与项目根；文件缺失、
  损坏或格式不符即当作空表。``TSA_EVIDENCE_STORE=off`` 关闭落盘（进程内仍记录）。
"""

from __future__ import annotations

import bisect
import hashlib
import marshal
import os
import re
import threading
import time
from pathlib import Path

from . import walk_evidence_store
from .evidence_file_cache import RACY_WINDOW_NS, StatKey, _stat_key

#: 文件格式版本。
FORMAT = 1
_PREFIX = "vocab-"
_MARSHAL_VERSION = 4
#: 保留的词表文件数（当前代码与上一版代码各一份）。
KEEP = 2
#: 一个项目的词表总字节上限；超出时只保留本进程用到的记录。
MAX_TOTAL_BYTES = 64 * 1024 * 1024
#: 构成“词”的字节：名字（标识符）的字节都在其中。
_WORD_BYTE = rb"A-Za-z0-9_$\x80-\xff"
_ONLY_WORD_BYTES = re.compile(rb"[" + _WORD_BYTE + rb"]+\Z")
#: 把每个非词字节换成空格的转换表；之后按空白切分即得全部极大词段
#: （与 ``re.findall(rb"[A-Za-z0-9_$\x80-\xff]+")`` 相同，实测约快 1.7 倍）。
_SPACE_OUT_NON_WORD = bytes(
    byte if _ONLY_WORD_BYTES.match(bytes((byte,))) else 0x20 for byte in range(256)
)


def vocabulary(data: bytes) -> bytes:
    """``data`` 中全部极大词段的去重集合（有序、以 ``\\0`` 分隔）。"""
    return b"\0".join(sorted(set(data.translate(_SPACE_OUT_NON_WORD).split())))


def searchable(needle: bytes) -> bool:
    """``needle`` 的出现能否只凭词表判定（全部字节都是词字节）。"""
    return bool(needle) and _ONLY_WORD_BYTES.match(needle) is not None


class ReferenceVocabulary:
    """一个项目根的词表：``abs_path -> (stat 证据, 词表)``（线程安全）。"""

    def __init__(self, project_root: str, entries: dict[str, tuple[StatKey, bytes]]):
        self._root = project_root
        self._entries = entries
        self._touched: set[str] = set()
        self._dirty = False
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._entries)

    def lacks(self, path: str, needle: bytes) -> bool:
        """证据仍成立且词表证明 ``path`` 不含 ``needle`` 时为真；否则须照常读取。"""
        if not searchable(needle):
            return False
        with self._lock:
            entry = self._entries.get(path)
        if entry is None:
            return False
        current = _current_stamp(path)
        if current is None:
            return False  # 交给照常读取：不可读由那里报告
        if current != entry[0]:
            return False
        with self._lock:
            self._touched.add(path)
        return needle not in entry[1]

    def lacking(self, paths: list[str], needle: bytes) -> set[str]:
        """``paths`` 中词表证明不含 ``needle`` 的路径（查询作用域内批量判定）。

        RFC-0041：每个路径的 stat 证据在一个查询作用域内只核对一次（按需、只核对
        被问到的路径），之后每个名字的判定只是字典查找与字节包含测试。与逐个
        :meth:`lacks` 的结论相同。
        """
        if not searchable(needle):
            return set()
        from ...query_scope import scoped

        # RFC-0041 跨名批量：同一组路径的有效词表在作用域内只拼接一次；之后每个名字
        # 是一次（C 层的）字节查找，命中后直接跳到下一个文件，而不是逐路径做包含测试。
        joined: _JoinedVocab = scoped(
            ("reference_vocab.joined", self._root, tuple(paths)),
            lambda: self._joined(paths),
        )
        out = joined.lacking(needle)
        with self._lock:
            self._touched.update(out)
        return out

    def _joined(self, paths: list[str]) -> _JoinedVocab:
        """``paths`` 中 stat 证据仍成立的词表，拼接为一段（每个路径只核对一次）。"""
        from ...query_scope import scoped, scoped_stats

        valid: dict[str, bytes | None] = scoped(
            ("reference_vocab.valid", self._root), dict
        )
        with self._lock:
            pending = [p for p in paths if p not in valid and p in self._entries]
        # 尚未核对的路径一次（并行）stat；之后的 ``_current_stamp`` 只是查记忆。
        scoped_stats(pending)
        with self._lock:
            entries = self._entries
            for path in paths:
                if path not in valid:
                    entry = entries.get(path)
                    if entry is None:
                        valid[path] = None
                    else:
                        valid[path] = (
                            entry[1] if _current_stamp(path) == entry[0] else None
                        )
        known = [(path, words) for path in paths if (words := valid[path]) is not None]
        return _JoinedVocab(known)

    def learn(self, path: str, data: bytes, stamp: StatKey | None) -> None:
        """记录一次完整读取的词表；读取期间被改写或处于竞争窗口时不记录。"""
        if stamp is None or time.time_ns() - stamp[1] < RACY_WINDOW_NS:
            return
        with self._lock:
            self._touched.add(path)
            known = self._entries.get(path)
        if known is not None and known[0] == stamp:
            return  # 同一份证据已有词表：字节未变，词表也不变
        words = vocabulary(data)
        with self._lock:
            self._entries[path] = (stamp, words)
            self._dirty = True

    def flush(self) -> None:
        """有新记录时原子落盘；任何失败都静默放弃（下次进程照常读取）。"""
        with self._lock:
            if not self._dirty:
                return
            entries = dict(self._entries)
            touched = set(self._touched)
            self._dirty = False
        total = sum(len(words) for _stamp, words in entries.values())
        if total > MAX_TOTAL_BYTES:
            entries = {path: entries[path] for path in touched if path in entries}
        _save(self._root, entries)


#: 拼接词表时文件之间的分隔字节：不是词字节，名字的出现不会跨越它。
_FILE_SEPARATOR = b"\n"


class _JoinedVocab:
    """一组文件的有效词表拼接为一段字节，供作用域内的许多名字共用（RFC-0041）。

    ``needle in words_i`` 对每个文件逐一测试与“在拼接段中查找、命中落在第 i 段”
    等价：名字只含词字节，而段内以 ``\\0``、段间以 :data:`_FILE_SEPARATOR` 分隔，
    二者都不是词字节，因此任何一次出现都完整落在某一段之内。
    """

    __slots__ = ("_blob", "_ends", "_paths", "_starts")

    def __init__(self, known: list[tuple[str, bytes]]) -> None:
        self._paths = [path for path, _words in known]
        self._starts: list[int] = []
        self._ends: list[int] = []
        offset = 0
        for _path, words in known:
            self._starts.append(offset)
            offset += len(words)
            self._ends.append(offset)
            offset += len(_FILE_SEPARATOR)
        self._blob = _FILE_SEPARATOR.join(words for _path, words in known)

    def lacking(self, needle: bytes) -> set[str]:
        """词表证明不含 ``needle`` 的路径（``needle`` 须为 :func:`searchable`）。"""
        containing: set[int] = set()
        blob, starts, ends = self._blob, self._starts, self._ends
        at = blob.find(needle)
        while at != -1:
            index = bisect.bisect_right(starts, at) - 1
            containing.add(index)
            at = blob.find(needle, ends[index])
        return {
            path for index, path in enumerate(self._paths) if index not in containing
        }


def _current_stamp(path: str) -> StatKey | None:
    """``path`` 的当前 stat 证据；不可 stat 为 None。

    RFC-0041：统一查询在一个答案里对许多名字各做一次引用扫描，同一批文件被逐一
    重复 stat（TSA 自身约 2.7k 个文件 × 每个名字）。查询作用域内一个答案只对应
    一个源码时刻，因此每个路径只 stat 一次；作用域外照旧每次实时 stat。
    """
    from ...query_scope import scoped_stats

    info = scoped_stats((path,))[0]
    return None if info is None else _stat_key(info)


_LOCK = threading.Lock()
_BY_ROOT: dict[str, ReferenceVocabulary] = {}


def for_root(project_root: str) -> ReferenceVocabulary:
    """本进程中 ``project_root`` 的词表（首次取用时读入落盘记录）。"""
    root = os.path.abspath(project_root)
    with _LOCK:
        found = _BY_ROOT.get(root)
        if found is None:
            found = ReferenceVocabulary(root, _load(root))
            _BY_ROOT[root] = found
    return found


def clear() -> None:
    """丢弃进程内的全部词表（测试用：如同新进程）。"""
    with _LOCK:
        _BY_ROOT.clear()


def _key_text(root: str) -> str:
    from ...source_fingerprint import source_fingerprint

    return f"{FORMAT}\x1f{source_fingerprint()}\x1f{root}"


def _file_name(text: str) -> str:
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=20).hexdigest()
    return f"{_PREFIX}{digest}.bin"


def _load(root: str) -> dict[str, tuple[StatKey, bytes]]:
    if not walk_evidence_store.enabled():
        return {}
    directory = walk_evidence_store.store_dir(root, create=False)
    if directory is None:
        return {}
    text = _key_text(root)
    try:
        payload = marshal.loads((directory / _file_name(text)).read_bytes())  # nosec B302
    except (OSError, ValueError, EOFError, TypeError):
        return {}
    if not (
        isinstance(payload, tuple)
        and len(payload) == 3
        and payload[0] == FORMAT
        and payload[1] == text
        and isinstance(payload[2], dict)
    ):
        return {}
    entries: dict[str, tuple[StatKey, bytes]] = {}
    for path, entry in payload[2].items():
        if _valid_entry(path, entry):
            entries[path] = (tuple(entry[0]), entry[1])
    return entries


def _valid_entry(path: object, entry: object) -> bool:
    return (
        isinstance(path, str)
        and isinstance(entry, tuple)
        and len(entry) == 2
        and isinstance(entry[0], tuple)
        and len(entry[0]) == 5
        and all(isinstance(number, int) for number in entry[0])
        and isinstance(entry[1], bytes)
    )


def _save(root: str, entries: dict[str, tuple[StatKey, bytes]]) -> None:
    if not walk_evidence_store.enabled():
        return
    directory = walk_evidence_store.store_dir(root, create=True)
    if directory is None:
        return
    text = _key_text(root)
    try:
        data = marshal.dumps((FORMAT, text, entries), _MARSHAL_VERSION)
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
    """只留最近写入的 :data:`KEEP` 份（旧代码指纹的文件不会再被读到）。"""
    files = sorted(
        directory.glob(f"{_PREFIX}*.bin"),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for stale in files[KEEP:]:
        stale.unlink(missing_ok=True)
