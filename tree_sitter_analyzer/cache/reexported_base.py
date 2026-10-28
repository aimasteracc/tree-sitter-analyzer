"""#1834：沿导入与包再导出找到基类名所指的类定义文件。

第二遍解析按名字挑基类候选，只把导入语句点名的模块文件当作“已导入”：
``from lib.security import HTTPBearer`` 指向 ``lib/security/__init__.py``，类却定义在
它再导出的 ``lib/security/http.py`` 中。项目里另有一个同名的无关类时，两个候选
得分相同，继承边便停在 ``class:HTTPBearer`` 占位（fastapi：``openapi/models.py``
与 ``security/http.py`` 都定义 ``HTTPBase`` / ``HTTPBearer``）。

这里只用索引中的静态证据（``ast_imports`` 的非星号导入与 ``ast_symbol_rows`` 的类
定义），从引用所在文件出发，经导入、再经包 ``__init__.py`` 的再导出链定位类定义。
任何一步缺证据（星号导入、惰性导出、模块不在索引中）都返回 ``None``：调用方保持
原来的排序，绝不猜测。
"""

from __future__ import annotations

import sqlite3

from ..synapse_resolver._context import _build_module_to_file, _resolve_module_to_file

#: 再导出链的最大跳数（与 ``cached_reexport_binding`` 一致），防止环状再导出。
_MAX_HOPS = 8

_IMPORT_SQL = (
    "SELECT module_path, alias_of, is_relative FROM ast_imports "
    "WHERE file_path = ? AND local_name = ? AND is_star = 0"
)
_CLASS_SQL = (
    "SELECT 1 FROM ast_symbol_rows WHERE file_path = ? AND name = ? "
    "AND kind = 'class' LIMIT 1"
)
_FILES_SQL = "SELECT file_path FROM ast_index WHERE language = 'python'"


def imported_class_file(
    conn: sqlite3.Connection, source_file: str, reference_name: str
) -> str | None:
    """``source_file`` 中名字 ``reference_name`` 经导入绑定到的类定义文件；不能证明为 None。

    只处理简单名（``from m import Name [as Alias]`` 的本地名）；``mod.Name`` 这类属性
    引用不在此列，由调用方按未绑定处理。
    """
    simple = reference_name.split("[", 1)[0].strip()  # ``Base[T]`` 的下标不属于名字。
    if not simple.isidentifier():
        return None
    try:
        module_to_file: dict[str, str] | None = None
        file_path, name = source_file, simple
        for _ in range(_MAX_HOPS):
            row = conn.execute(_IMPORT_SQL, (file_path, name)).fetchone()
            if row is None:
                return None
            module_path, alias_of, is_relative = row[0], row[1], row[2]
            if module_to_file is None:
                module_to_file = _build_module_to_file(
                    [str(item[0]) for item in conn.execute(_FILES_SQL)]
                )
            target = _resolve_module_to_file(
                str(module_path or ""), bool(is_relative), file_path, module_to_file
            )
            if not target:
                return None
            file_path, name = target, str(alias_of or name)
            if conn.execute(_CLASS_SQL, (file_path, name)).fetchone() is not None:
                return file_path
    except sqlite3.Error:
        return None
    return None


__all__ = ["imported_class_file"]
