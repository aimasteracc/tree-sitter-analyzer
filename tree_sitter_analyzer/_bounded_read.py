"""按文件实际大小读取的有界读取（Issue #1591）。"""

from __future__ import annotations

import io
import os
from typing import BinaryIO


def read_at_most(stream: BinaryIO, limit: int) -> bytes:
    """返回与 ``stream.read(limit + 1)`` 完全相同的字节，但不预分配整块上限缓冲。

    Windows 上 ``read(64 MiB + 1)`` 每次调用都会先申请约 64 MiB 再收缩；在 2.4k 文件
    仓库实测为 27 ms/次，而按文件大小读取约 0.5 ms/次（Issue #1591 的主要耗时）。
    因此先按 ``fstat`` 大小读取；读取期间文件增长时再补读剩余额度，结果语义不变。
    """
    try:
        size = os.fstat(stream.fileno()).st_size
    except (AttributeError, OSError, io.UnsupportedOperation):
        return stream.read(limit + 1)
    first = min(size, limit) + 1
    data = stream.read(first)
    if len(data) < first:
        return data
    return data + stream.read(limit + 1 - len(data))
