"""#1596：缓存调用图中调用边的调用方绑定与调用方身份。

调用边只记录调用方的裸名、文件与定义行。同一文件里可以有多个同名函数——
``PulseTool.execute`` 与 ``PulseBatchTool.execute``，或两个嵌套的 ``inner``——
按“同文件第一个同名函数”绑定会把它们合并成一个调用方，丢掉其余的。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .call_graph import FunctionRef


def pick_caller_ref(
    candidates: Sequence[FunctionRef], caller_file: str, caller_line: int
) -> FunctionRef | None:
    """为一条调用边选出调用方：定义行精确匹配 > 包含该行 > 同文件第一个 > 任意第一个。

    ``caller_line`` 为调用方的定义行；旧库中可能为 0 或调用行，因此依次放宽，
    最后两档与修复前的行为一致。
    """
    same_file = [ref for ref in candidates if ref.file_path == caller_file]
    for ref in same_file:
        if caller_line and ref.start_line == caller_line:
            return ref
    for ref in same_file:
        if caller_line and ref.start_line <= caller_line <= ref.end_line:
            return ref
    if same_file:
        return same_file[0]
    return candidates[0] if candidates else None


def ref_identity(ref: FunctionRef) -> tuple[str, str, int]:
    """调用方 / 被调方的去重键：与 ``FunctionRef.__eq__`` 一致（文件、名字、定义行）。

    ``qualified_name()`` 在没有 receiver 时只有 ``file:name``，会合并同名函数。
    """
    return (ref.file_path, ref.name, ref.start_line)
