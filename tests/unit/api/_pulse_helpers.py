"""#1546：test_pulse 行为组共享的非测试辅助；从 test_pulse.py 原样迁移。"""

from __future__ import annotations

from tree_sitter_analyzer.api.pulse import SymbolInfo

# ---------------------------------------------------------------------------
# Minimal symbol for constructing PulseResponse in tests
# ---------------------------------------------------------------------------

_MINIMAL_SYM = SymbolInfo(
    name="fn",
    kind="function",
    file="a.py",
    line=1,
    end_line=5,
    language="python",
)


# ---------------------------------------------------------------------------
# Helpers for seeding data in the in-memory DB
# ---------------------------------------------------------------------------


def _seed_symbol(conn, name: str, file_path: str, language: str = "python") -> int:
    cur = conn.execute(
        "INSERT INTO ast_symbol_rows (name, kind, file_path, language, line, end_line) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, "function", file_path, language, 1, 10),
    )
    conn.commit()
    return cur.lastrowid


def _call(
    conn,
    caller,
    callee,
    *,
    caller_line=1,
    call_line=5,
    target_id=None,
    target_file="",
    file="a.py",
):
    return conn.execute(
        "INSERT INTO edges (source_node_id, target_node_id, kind, line, "
        "file_path, caller_name, caller_line, callee_name, callee_line, "
        "callee_symbol_id, callee_resolved_file, callee_resolution) "
        "VALUES (?, ?, 'calls', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"{file}:{caller}:{caller_line}",
            f"{target_file}:{callee}:{call_line}",
            call_line,
            file,
            caller,
            caller_line,
            callee,
            call_line,
            target_id,
            target_file,
            "project" if target_file else "unknown",
        ),
    ).lastrowid
