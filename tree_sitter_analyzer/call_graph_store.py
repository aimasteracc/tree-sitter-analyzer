"""冷进程复用已构建调用图的边解析结果（#1675）。

#1663 让同一进程内容相同的重建直接复用内存图；新启动的进程仍要从索引重新
解析约 19 万条调用边（构图中最贵的一步）。这里把那一步的结果落盘：

* **只保存边解析的结果**：每条边的调用方、确定目标、模糊候选、注解绑定与
  调用行。函数表、import 映射等廉价部分照旧从索引现建；读出的结果与现场
  解析走同一个应用函数（``CachedCallGraph._apply_edge_records``），因此
  两条路径构出的图状态相同。
* **键 = 代码指纹 + 构图输入摘要**。摘要即 #1663 的 ``input_digest``（本次构图
  实际读取的边、函数、import 行与再导出 / 子类证据）；代码指纹覆盖全部解析
  代码。两者都相同，解析结果必然相同；generation、路径、时间都不进键
  （RFC-0030）。摘要仍须照常读取全部输入计算，所以这不会让陈旧的结果生效。
* **失败即不用**：文件缺失、损坏、格式或计数不符一律当作未命中，照常解析；
  写入失败静默放弃。只有显式要求的调用方（``persist=True``，即 ``nav``
  的 callers / callees）才写入，``read_existing`` 等零写入路由不受影响。

文件放在 ``<项目>/.ast-cache/graph-memo/``（目录须已存在且不是链接），只保留
最近 :data:`KEEP` 份。
"""

from __future__ import annotations

import hashlib
import marshal
import os
import stat
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .source_fingerprint import source_fingerprint

#: 文件格式版本；记录结构变化时递增。
FORMAT = 1
#: ``.ast-cache`` 下的目录名。
DIR_NAME = "graph-memo"
#: 保留的文件数（当前图与上一张图）。
KEEP = 2
#: marshal 版本 4：字节只取决于值（写入只在本进程内进行）。
_MARSHAL_VERSION = 4
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400

#: 一条边的解析结果：(调用方, 确定目标, 模糊候选, 注解绑定, 调用行)；无调用方为 None。
EdgeRecord = tuple[Any, Sequence[Any], Sequence[Any], Any, int] | None


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


def _file_name(input_digest: str) -> str:
    key = hashlib.blake2b(
        f"{FORMAT}|{source_fingerprint()}|{input_digest}".encode(), digest_size=20
    ).hexdigest()
    return f"{key}.bin"


def load(
    project_root: str, input_digest: str, *, functions: int, edges: int
) -> list[Any] | None:
    """摘要与计数都相符的已存解析结果（编码形式）；否则 None。"""
    try:
        directory = _store_dir(project_root, create=False)
        if directory is None:
            return None
        data = (directory / _file_name(input_digest)).read_bytes()
        payload = marshal.loads(data)  # nosec B302 — 只读本进程族写入的内建值，校验后才用
    except (OSError, ValueError, EOFError, TypeError):
        return None
    if not (
        isinstance(payload, tuple)
        and len(payload) == 5
        and payload[0] == FORMAT
        and payload[1] == input_digest
        and payload[2] == functions
        and payload[3] == edges
        and isinstance(payload[4], list)
        and len(payload[4]) == edges
    ):
        return None
    return payload[4]


def save(
    project_root: str,
    input_digest: str,
    functions: Sequence[Any],
    records: Sequence[EdgeRecord],
) -> None:
    """原子写入本次构图的解析结果；任何失败都静默放弃。"""
    directory = _store_dir(project_root, create=True)
    if directory is None:
        return
    index = {id(ref): position for position, ref in enumerate(functions)}
    try:
        encoded = [_encode_record(record, index) for record in records]
        data = marshal.dumps(
            (FORMAT, input_digest, len(functions), len(records), encoded),
            _MARSHAL_VERSION,
        )
    except ValueError:
        return  # 绑定证据里有不可编码的值：不落盘
    target = directory / _file_name(input_digest)
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
    files = sorted(
        directory.glob("*.bin"), key=lambda path: path.stat().st_mtime_ns, reverse=True
    )
    for stale in files[KEEP:]:
        stale.unlink(missing_ok=True)


def _encode_ref(ref: Any, index: dict[int, int]) -> Any:
    position = index.get(id(ref))
    if position is not None:
        return position
    # 不在函数表里的引用（模块作用域伪调用方等）按值保存。
    return (ref.file_path, ref.name, ref.start_line, ref.language, ref.receiver, ref.end_line)


def _encode_record(record: EdgeRecord, index: dict[int, int]) -> Any:
    if record is None:
        return None
    caller, certain, possible, binding, line = record
    return (
        _encode_ref(caller, index),
        tuple(_encode_ref(ref, index) for ref in certain),
        tuple(_encode_ref(ref, index) for ref in possible),
        binding,
        line,
    )


def decode(encoded: list[Any], functions: Sequence[Any], ref_type: Any) -> list[EdgeRecord]:
    """把已存结果还原为引用对象；结构或下标不符时抛 ValueError。"""
    count = len(functions)

    def ref(value: Any) -> Any:
        if isinstance(value, int):
            if not 0 <= value < count:
                raise ValueError("function index out of range")
            return functions[value]
        file_path, name, start_line, language, receiver, end_line = value
        return ref_type(
            file_path=file_path,
            name=name,
            start_line=start_line,
            language=language,
            receiver=receiver,
            end_line=end_line,
        )

    records: list[EdgeRecord] = []
    for item in encoded:
        if item is None:
            records.append(None)
            continue
        caller, certain, possible, binding, line = item
        records.append(
            (
                ref(caller),
                [ref(value) for value in certain],
                [ref(value) for value in possible],
                binding,
                int(line),
            )
        )
    return records
