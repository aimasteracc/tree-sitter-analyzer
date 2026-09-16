"""Import-reachability evidence for constraint evaluation."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Collection, Iterator

_MAX_MATERIALIZED_ITEMS = 10_000


def _has_import_evidence(db_conn: sqlite3.Connection) -> bool:
    """判断当前索引是否提供导入关系证据。"""
    try:
        db_conn.execute("SELECT 1 FROM ast_imports LIMIT 0")
    except sqlite3.OperationalError:
        return False
    return True


def _build_import_index(
    db_conn: sqlite3.Connection,
    *,
    file_paths: Collection[str] | None = None,
    check_callback: Callable[[], None] | None = None,
    capacity: int = _MAX_MATERIALIZED_ITEMS,
) -> dict[str, set[str]] | None:
    """只为候选调用方构建 ``{文件: 导入模块集合}``，并限制物化行数。"""
    if not _has_import_evidence(db_conn):
        # 测试夹具或新数据库可能尚未创建导入表，此时保持旧的保守行为。
        return None
    if file_paths is not None and not file_paths:
        return {}

    def selected_rows() -> Iterator[tuple[str, str]]:
        if file_paths is None:
            yield from db_conn.execute("SELECT file_path, module_path FROM ast_imports")
            return
        ordered_paths = sorted(file_paths)
        for offset in range(0, len(ordered_paths), 800):
            chunk = ordered_paths[offset : offset + 800]
            placeholders = ",".join("?" for _ in chunk)
            query = (
                "SELECT file_path, module_path FROM ast_imports "
                "WHERE file_path IN (" + placeholders + ")"
            )
            yield from db_conn.execute(query, chunk)

    index: dict[str, set[str]] = {}
    materialized = 0
    for file_path, module_path in selected_rows():
        if check_callback is not None:
            check_callback()
        if not file_path or not module_path:
            continue
        materialized += 1
        if materialized > capacity:
            raise RuntimeError("CONSTRAINT_EVALUATION_CAPACITY")
        entry = index.setdefault(file_path, set())
        # Store full module_path (handles absolute imports).
        entry.add(module_path)
        # Also store the terminal component so relative imports like
        # '.file_health_blocks' and absolute ones both match via the
        # basename 'file_health_blocks'.
        terminal = module_path.lstrip(".").rsplit(".", 1)[-1]
        if terminal:
            entry.add(terminal)
    return index


def _callee_is_imported(
    caller_file: str,
    callee_file: str,
    import_index: dict[str, set[str]],
) -> bool:
    """Return True when the caller's import set covers the callee's module.

    Converts ``callee_file`` (a relative project path like
    ``tree_sitter_analyzer/mcp/tools/utils/file_health_blocks.py``) to:

    * A full dotted module path: ``tree_sitter_analyzer.mcp.tools.utils.file_health_blocks``
    * A terminal component: ``file_health_blocks``

    Then checks whether any entry in the caller's import set matches
    either form — covering both absolute and relative imports.

    Returns ``True`` (caller imports callee) when the import_index has no
    entry for the caller, so that files not recorded in ast_imports (e.g.
    languages not yet extracted) do not produce false negatives.
    """
    caller_imports = import_index.get(caller_file)
    if caller_imports is None:
        # No import data for caller → assume reachable to avoid false negatives.
        return True

    # Derive module identifiers from the callee's file path.
    without_ext = callee_file.removesuffix(".py")
    full_module = without_ext.replace("/", ".")
    terminal = without_ext.rsplit("/", 1)[-1]

    return full_module in caller_imports or terminal in caller_imports
