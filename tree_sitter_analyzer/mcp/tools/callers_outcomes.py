"""RFC-0040：一道 callers 检查的结果——``Checked``（运行过）或 ``NotChecked``（未能运行）。

无依赖的叶子模块：检查的生产者（``callers_absence`` 等）与推导者
（``callers_checks``）都从这里取类型，避免循环导入。纯计数无法区分“检查运行后
得到 0”与“检查根本没有运行”，因此每道必需检查都返回这两种之一。
"""

from __future__ import annotations

from dataclasses import dataclass

#: 检查范围：查询目标集的身份 ``(规范名, file_path)``。
Scope = tuple[str, str | None]


@dataclass(frozen=True)
class Checked:
    """检查已在 ``scope`` 上运行；``problems`` 为它发现的原因码（空即通过）。"""

    scope: Scope
    problems: tuple[str, ...] = ()


@dataclass(frozen=True)
class NotChecked:
    """检查未能运行；``reason`` 是点名该检查的原因码。"""

    reason: str


CheckOutcome = Checked | NotChecked


def checked(scope: Scope, *problems: str | None) -> Checked:
    """``Checked``，只保留真正成立的问题码。"""
    return Checked(scope, tuple(code for code in problems if code))


__all__ = ["CheckOutcome", "Checked", "NotChecked", "Scope", "checked"]
