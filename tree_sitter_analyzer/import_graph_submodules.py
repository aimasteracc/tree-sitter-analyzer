"""``ImportGraph`` 的 ``from pkg import sub`` 子模块边（Issue #1579）。

``ImportGraph`` 只持有 import 语句文本，过去只把 ``from pkg import sub`` 解析到
``pkg/__init__.py``，于是 ``health imports mode=dependents`` 在 ``pkg/sub.py`` 上
无标记地漏掉这类导入方。本模块把语句文本解析为（模块, 名称），再复用 #1566 的
:func:`python_submodule_import_targets`，让 dependents 与依赖图遵循同一条规则。
"""

from __future__ import annotations

import ast

from .project_graph import python_submodule_import_targets


def python_submodule_targets_from_text(
    import_text: str, source_rel: str, nodes: set[str]
) -> list[str]:
    """返回一条 Python import 语句中真实存在的子模块文件（POSIX 相对路径）。

    ``nodes`` 与 ``source_rel`` 均为 POSIX 风格的项目相对路径。无法解析的文本
    （截断、非 Python 语法）返回空列表：只会少加边，不会凭空造边。
    """
    try:
        tree = ast.parse(import_text.strip())
    except (SyntaxError, ValueError):
        return []
    targets: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        module = "." * node.level + (node.module or "")
        targets.extend(
            python_submodule_import_targets(
                module,
                [alias.name for alias in node.names],
                source_rel,
                nodes,
                node.level > 0,
            )
        )
    return targets
