"""已知答案语料（known-answer corpus）的数据结构与标记解析。

每个用例是一个最小夹具项目，来自一个真实的错误 ``complete`` / 召回缺陷。
真值（ground truth）**手写在夹具源码里**，用行尾注释标记：

* ``# target`` / ``// target``：查询目标的定义行（唯一）；
* ``# gt`` / ``// gt``：一个真实（或运行时可能）调用目标的调用点；
* ``# gt listed`` / ``// gt listed``：同上，且当前 develop 在两种查询模式下都已
  列出它——之后必须一直列出（召回棘轮：“已列出的真调用方保持列出”）。

标记只是注释，不含目标名，不影响 TSA 的解析与非调用引用扫描。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from scripts.wrong_complete.sites import Target

_TARGET_MARK = re.compile(r"(?:#|//)\s*target\s*$")
_GT_MARK = re.compile(r"(?:#|//)\s*gt(?P<listed>\s+listed)?\s*$")
MODES = ("bare", "qualified")


@dataclass(frozen=True)
class Case:
    """一个已知答案用例：夹具文件 + 目标名 + 外层类。"""

    case_id: str
    issue: str
    files: Mapping[str, str]
    target_name: str
    owner: str | None

    def _marks(self, pattern: re.Pattern[str]) -> list[tuple[str, int, re.Match[str]]]:
        return [
            (path, number, match)
            for path, text in sorted(self.files.items())
            for number, line in enumerate(text.splitlines(), 1)
            if (match := pattern.search(line)) is not None
        ]

    @property
    def target(self) -> Target:
        """由 ``target`` 标记定位的查询目标。"""
        hits = self._marks(_TARGET_MARK)
        if len(hits) != 1:
            raise ValueError(
                f"{self.case_id}: expected one target mark, found {len(hits)}"
            )
        path, number, _ = hits[0]
        return Target(path, self.target_name, self.owner, number)

    @property
    def truth(self) -> frozenset[tuple[str, int]]:
        """手写真值调用点 ``(file, line)``。"""
        return frozenset((path, number) for path, number, _ in self._marks(_GT_MARK))

    @property
    def listed_floor(self) -> frozenset[tuple[str, int]]:
        """两种模式都必须保持列出的真值调用点。"""
        return frozenset(
            (path, number)
            for path, number, match in self._marks(_GT_MARK)
            if match["listed"]
        )

    def query_name(self, mode: str) -> str:
        """该模式下传给 ``function_name`` 的名字。"""
        return self.target_name if mode == "bare" else self.target.qualified
