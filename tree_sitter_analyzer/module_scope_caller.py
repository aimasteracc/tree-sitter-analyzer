"""#1622：模块作用域调用点的伪调用方身份。

不在任何函数体内的调用点——模块顶层、类体、``if __name__ == "__main__":``、
装饰器实参、模块级 lambda / 推导式——在调用边里记为 ``caller_name=''``
（边写入器把来源映射到文件节点）。它们是真实的调用方：只调用于这些位置的符号
若被报告为 ``0 callers, complete``，就是危险的假“不存在”。

统一表示：调用方名为 ``<module>``（沿用 Python traceback 的写法），``file`` 为
调用所在文件，``line`` / ``end_line`` 为调用行，``scope`` 为 ``module``。SQL 路径
与内存调用图使用同一表示，因此影响面、测试选择与 ``possible_*`` 也能看到它们。
表示在查询时由既有边推导，已有索引无需重建。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .call_graph import FunctionRef

#: 无外围函数的调用点所归属的伪调用方名。
MODULE_CALLER_NAME = "<module>"
#: 伪调用方条目的 ``scope`` 字段值。
MODULE_SCOPE = "module"


def module_caller_ref(file_path: str, call_line: int, language: str) -> FunctionRef:
    """为一个模块作用域调用点构造伪调用方：定义行即调用行，每个调用点各自独立。"""
    from .call_graph import FunctionRef

    return FunctionRef(
        file_path=file_path,
        name=MODULE_CALLER_NAME,
        start_line=call_line,
        language=language,
        end_line=call_line,
    )


def is_module_caller(name: str) -> bool:
    """调用方名是否为模块作用域伪调用方。"""
    return name == MODULE_CALLER_NAME


def module_caller_entry(edge: dict[str, Any]) -> dict[str, Any] | None:
    """SQL 调用边（``caller_name=''``）对应的伪调用方条目；缺调用行时为 None。

    返回 None 的调用点无法给出可导航的坐标，由调用方计入
    ``unattributed_call_sites``，并阻止 ``complete``。
    """
    call_line = int(edge.get("callee_line") or 0)
    caller_file = str(edge.get("caller_file") or "")
    if call_line < 1 or not caller_file:
        return None
    return {
        "name": MODULE_CALLER_NAME,
        "file": caller_file,
        "line": call_line,
        "end_line": call_line,
        "scope": MODULE_SCOPE,
    }
