"""密封索引版本的文件级只读标记，以及删除前恢复属主写位。

边界说明（不夸大）：只读位阻断的是“经公共只读连接 ``ATTACH ... mode=rw``
改写已发布版本”这类 SQL 层逃逸。POSIX 上的 root、以及任何先把写位改回来的
同用户代码，都不受此约束——这不是访问控制（RFC-0032 已声明该边界）。
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

_WRITE_BITS = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
_REPARSE_POINT = 0x400


def mark_read_only(path: Path) -> None:
    """清除全部写位；Windows 上 ``os.chmod`` 只映射为只读属性。"""
    mode = stat.S_IMODE(os.lstat(path).st_mode)
    os.chmod(path, mode & ~_WRITE_BITS)


def _is_link(info: os.stat_result) -> bool:
    """符号链接与 Windows 联接/重解析点一律不跟随、不改权限。"""
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & _REPARSE_POINT
    )


def clear_read_only_tree(root: Path) -> None:
    """删除目录树前给只读普通文件恢复属主写位。

    Windows 上 ``shutil.rmtree`` 遇到只读文件会报 PermissionError（
    ``ignore_errors=True`` 时则静默残留），因此删除路径必须先调用本函数。
    不跟随链接，避免改动树外文件的权限。
    """
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                info = os.lstat(entry.path)
                plain = not _is_link(info)
                if plain and stat.S_ISDIR(info.st_mode):
                    pending.append(Path(entry.path))
                elif (
                    plain
                    and stat.S_ISREG(info.st_mode)
                    and not info.st_mode & stat.S_IWUSR
                ):
                    os.chmod(entry.path, stat.S_IMODE(info.st_mode) | stat.S_IWUSR)
