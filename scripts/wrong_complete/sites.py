"""判定器共用的数据结构：查询目标与调用点。"""

from __future__ import annotations

from dataclasses import dataclass

#: 调用点确定调用目标（静态绑定可证明）。
TARGET = "target"
#: 调用点可能调用目标（接收者无法证明、虚分派到覆盖、Protocol 结构实现等）。
POSSIBLE = "possible"
#: 调用点经判定器证明调用的是别的定义（或内建/外部对象），不必列出。
OTHER = "other"

#: 一次 ``complete`` 回答必须覆盖的判定结果。
MUST_COVER = frozenset({TARGET, POSSIBLE})


@dataclass(frozen=True)
class Target:
    """一次 ``nav callers`` 查询的目标定义。

    ``owner`` 为直接外层类名（模块级函数为 ``None``）；``line`` 为定义所在行，
    用于在同名定义之间消歧。
    """

    file: str
    name: str
    owner: str | None
    line: int

    @property
    def qualified(self) -> str:
        """限定名查询形式（``Class.method``）；模块级函数即裸名。"""
        return f"{self.owner}.{self.name}" if self.owner else self.name


@dataclass(frozen=True)
class Site:
    """判定器找到的一个调用点或非调用引用点。

    ``kind`` 为 ``call`` 或 ``reference``；``verdict`` 为 ``target`` /
    ``possible`` / ``other``；``reason`` 是简短的判定理由代码，用于报告与排除
    说明；``caller`` 是外层函数名（模块级为 ``<module>``）。
    """

    file: str
    line: int
    kind: str
    verdict: str
    reason: str
    caller: str

    @property
    def must_cover(self) -> bool:
        """``complete`` 回答是否必须列出覆盖本点的调用方。"""
        return self.verdict in MUST_COVER

    def key(self) -> tuple[str, int]:
        """``(file, line)`` 形式的位置键。"""
        return (self.file, self.line)
