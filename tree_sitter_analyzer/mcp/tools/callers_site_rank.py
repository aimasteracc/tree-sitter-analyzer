"""#1706：有上限的证据列表先按“离目标多近”排序，再截断。

dogfood 第 9 轮：``NativeFiles.open`` 有 108 个同名调用点，``name_only_sites`` 按路径
字母序截断在 20 个，列出的全是 ``benchmarks/…``；声明文件里的闭包调用
``api.open(...)`` 排在后面被截掉。本轮漏掉的真实调用方中有 8 个在前 20 个之外。

排序（选定“调用点与目标的接近程度”，生产代码优先作为次级键）：

1. 声明目标的文件；
2. 导入目标所在类或函数名、或导入声明模块的文件；
3. 其余文件。

同一档内生产代码排在测试之前，再按路径与行号。理由：同名调用只有在接收者是目标
类（或子类）的实例时才是真实调用；声明文件与导入了该类 / 模块的文件能直接构造或
持有这种实例，其余文件只能经参数间接得到，命中概率低得多。生产优先是因为测试里
同名的替身（``FakeX.open``）更多。总数与是否截断照旧并列给出。
"""

from __future__ import annotations

import sqlite3
from pathlib import PurePosixPath
from typing import Any

#: 读取导入了这些名字（类名、函数名或模块名）的文件（走 ``idx_imp_local``）。
_IMPORTERS_SQL = (
    "SELECT DISTINCT file_path FROM ast_imports "  # nosec B608 - 占位符由 marks 生成
    "WHERE local_name IN ({marks})"
)
_DECLARING_SQL = (
    "SELECT DISTINCT file_path FROM ast_symbol_rows "
    "WHERE name = ? AND kind IN ('function', 'method')"
)


def rank_sites(
    cache: Any,
    sites: list[dict[str, Any]],
    func_name: str,
    file_path: str | None,
) -> list[dict[str, Any]]:
    """按接近程度排序（稳定、确定）；读不到导入表时只按声明文件与生产 / 测试排序。"""
    if len(sites) < 2:
        return sites
    declaring = {_norm(path) for path in declaring_files(cache, func_name, file_path)}
    importers = _importers(cache, func_name, declaring)

    def key(site: dict[str, Any]) -> tuple[int, int, str, int]:
        path = _norm(str(site.get("file") or ""))
        tier = 0 if path in declaring else 1 if path in importers else 2
        return (tier, int(is_test_path(path)), path, int(site.get("line") or 0))

    return sorted(sites, key=key)


def declaring_files(cache: Any, func_name: str, file_path: str | None) -> list[str]:
    """排序用的声明文件：查询点名的文件，否则为同名定义所在的文件。"""
    if file_path:
        return [file_path]
    try:
        rows = (
            cache.get_conn()
            .execute(_DECLARING_SQL, (func_name.rpartition(".")[2],))
            .fetchall()
        )
    except (sqlite3.Error, AttributeError):
        return []
    return sorted({str(row[0]) for row in rows})


def is_test_path(path: str) -> bool:
    """测试文件：``tests/`` 目录下，或文件名形如 ``test_*.py`` / ``*_test.py`` / conftest。"""
    pure = PurePosixPath(_norm(path))
    name = pure.name
    return (
        "tests" in pure.parts[:-1]
        or "test" in pure.parts[:-1]
        or name.startswith("test_")
        or name.endswith(("_test.py", ".test.ts", ".spec.ts"))
        or name == "conftest.py"
    )


def _importers(cache: Any, func_name: str, declaring: set[str]) -> frozenset[str]:
    owner, _, bare = func_name.rpartition(".")
    names = {owner.rpartition(".")[2] if owner else bare}
    names.update(_module_name(path) for path in declaring)
    marks = ",".join("?" * len(names))
    try:
        rows = (
            cache.get_conn()
            .execute(_IMPORTERS_SQL.format(marks=marks), sorted(names))
            .fetchall()
        )
    except (sqlite3.Error, AttributeError):
        return frozenset()
    return frozenset(_norm(str(row[0])) for row in rows)


def _module_name(path: str) -> str:
    """``pkg/mod.py`` -> ``mod``；``pkg/__init__.py`` -> ``pkg``。"""
    pure = PurePosixPath(path)
    if pure.stem == "__init__" and len(pure.parts) > 1:
        return pure.parts[-2]
    return pure.stem


def _norm(path: str) -> str:
    return path.replace("\\", "/")


__all__ = ["declaring_files", "is_test_path", "rank_sites"]
