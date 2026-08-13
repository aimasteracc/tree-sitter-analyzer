"""Import-reachability evidence for constraint evaluation."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

_MAX_MATERIALIZED_ITEMS = 10_000


def _build_import_index(
    db_conn: sqlite3.Connection,
    *,
    check_callback: Callable[[], None] | None = None,
    capacity: int = _MAX_MATERIALIZED_ITEMS,
) -> dict[str, set[str]] | None:
    """Build a lookup of {file_path: set(module_path_suffixes)} from ast_imports.

    Returns ``None`` when the ``ast_imports`` table is absent (e.g. in
    test fixtures that only populate the ``edges`` table) so callers can
    skip the import-reachability guard and fall back to pre-guard behaviour.

    The set stored per file is the union of the raw module_path and its
    terminal component (the basename after the last ``.`` or ``/``).
    This handles both absolute imports (``tree_sitter_analyzer.mcp.x``)
    and relative imports (``.x``) with a single membership test.
    """
    try:
        cursor = db_conn.execute("SELECT file_path, module_path FROM ast_imports")
    except sqlite3.OperationalError:
        # Table absent (test fixture, fresh DB) — degrade gracefully.
        return None

    index: dict[str, set[str]] = {}
    materialized = 0
    for file_path, module_path in cursor:
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
