"""#1596：import 依赖的文件级视图与带行号的 import 条目读取。

``ImportGraph`` 的边是一条 import 语句；同一文件导入目标两次就是两条边。
“谁依赖这个文件”问的是文件，因此 ``imports dependents`` 按依赖文件分组，
语句与行号作为明细保留。
"""

from __future__ import annotations

from typing import Any


def group_dependents_by_file(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把语句级的依赖边合并为每个依赖文件一条；不修改输入。

    每条保留旧字段（``source`` / ``target`` / ``import`` / ``line`` 取该文件
    行号最小的语句），并在 ``statements`` 中列出全部语句。按文件路径排序，
    文件内按行号排序，输出确定。
    """
    by_file: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        by_file.setdefault(str(edge["source"]), []).append(edge)
    grouped: list[dict[str, Any]] = []
    for source in sorted(by_file):
        statements = sorted(
            by_file[source], key=lambda e: (int(e.get("line") or 0), e["import"])
        )
        first = statements[0]
        grouped.append(
            {
                "source": source,
                "target": first["target"],
                "import": first["import"],
                "line": first["line"],
                "statements": [
                    {"import": e["import"], "line": e["line"]} for e in statements
                ],
            }
        )
    return grouped


def import_entries(cache: Any) -> dict[str, Any]:
    """每个文件的 import 条目；缓存能给出行号时为 ``{"text", "line"}`` 字典。

    只实现了 ``get_imports`` 的缓存（旧实现与测试替身）照旧返回纯文本，
    行号退回 0。
    """
    getter = getattr(cache, "get_import_entries", None)
    if callable(getter):
        entries: dict[str, Any] = getter()
        return entries
    imports: dict[str, Any] = cache.get_imports()
    return imports
