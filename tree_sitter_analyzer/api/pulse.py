"""Pulse API：单请求、快照绑定的符号上下文。

query_pulse 在同一保存点内读取身份、关系、修改记录、导入及注释，返回
PulseResponse；单请求不等于单次 SQL 往返。预算裁剪由 apply_budget 负责。

用法::

    conn = cache.get_conn()
    response = query_pulse(conn, "tree_sitter_analyzer/api/pulse.py", "query_pulse")
    budgeted = apply_budget(response, token_budget=600)
    payload  = serialize(budgeted, format="compact")  # 见 serialization.py
"""

from __future__ import annotations

import dataclasses
import json
import logging
import sqlite3
from dataclasses import dataclass as dataclass
from dataclasses import field as field
from typing import Any

from ._pulse_models import (
    BranchContext as BranchContext,
)
from ._pulse_models import (
    CalleeRef as CalleeRef,
)
from ._pulse_models import (
    CallerRef as CallerRef,
)
from ._pulse_models import (
    CommentRef as CommentRef,
)
from ._pulse_models import (
    GitHeat as GitHeat,
)
from ._pulse_models import (
    ImportRef as ImportRef,
)
from ._pulse_models import (
    PulseResponse as PulseResponse,
)
from ._pulse_models import (
    SiblingRef as SiblingRef,
)
from ._pulse_models import (
    SymbolInfo as SymbolInfo,
)
from ._pulse_sql import _PULSE_SQL

logger = logging.getLogger(__name__)

# 尚不支持调用图提取的语言。
_NO_CALL_GRAPH_LANGUAGES = frozenset(
    {
        "bash",
        "scala",
        "css",
        "html",
        "json",
        "yaml",
        "sql",
        "markdown",
    }
)


def _enrich_callees_with_lsp(
    conn: sqlite3.Connection,
    callees: tuple[CalleeRef, ...],
    edge_ids: tuple[int, ...],
) -> tuple[CalleeRef, ...]:
    """按原始调用边关联 LSP 缓存，并把零基定义行转换为一基行。"""
    try:
        enriched: list[CalleeRef] = []
        for ce, edge_id in zip(callees, edge_ids, strict=True):
            if ce.resolution not in ("unknown", "unresolved", "heuristic"):
                enriched.append(ce)
                continue
            try:
                row = conn.execute(
                    """
                    SELECT lrc.resolved_file, lrc.resolved_line, lrc.resolved_type
                    FROM   lsp_resolution_cache lrc
                    WHERE  lrc.edge_id = ?
                    ORDER  BY lrc.cached_at DESC, lrc.lsp_server
                    LIMIT  1
                    """,
                    (edge_id,),
                ).fetchone()
            except sqlite3.OperationalError:
                # 旧 schema 可能尚未创建可选 LSP 缓存表。
                enriched.append(ce)
                continue
            if row:
                resolved_file, resolved_line, _resolved_type = row
                if not resolved_file or resolved_line is None or resolved_line < 0:
                    enriched.append(ce)
                    continue
                enriched.append(
                    CalleeRef(
                        name=ce.name,
                        file=resolved_file,
                        line=resolved_line + 1,
                        resolution="resolved",
                    )
                )
            else:
                enriched.append(ce)
        return tuple(enriched)
    except Exception:
        # 可选富化失败不能破坏基础上下文。
        return callees


def query_pulse(
    conn: sqlite3.Connection,
    file_path: str,
    symbol_name: str,
    *,
    max_callers: int = 10,
    max_callees: int = 10,
    max_siblings: int = 15,
    max_imports: int = 20,
    max_comments: int = 10,
) -> PulseResponse | None:
    """返回符号上下文，缺少符号时返回 None。

    Python 反向 import 复用 Synapse resolver。注释必须来自新提取器写入的
    索引；旧索引或不支持注释的语言需重新索引或显式设置 max_comments=0。
    存量 activation 消息缺失时保持 NULL，并发出 COMMIT_MESSAGE_MISSING。
    """
    params: dict[str, Any] = {
        "file_path": file_path,
        "symbol_name": symbol_name,
        "max_callers": max_callers,
        "max_callees": max_callees,
        "max_siblings": max_siblings,
        "max_imports": max_imports,
        "max_comments": max_comments,
    }
    for name in (
        "max_callers",
        "max_callees",
        "max_siblings",
        "max_imports",
        "max_comments",
    ):
        if type(params[name]) is not int or not 0 <= params[name] <= 1000:
            raise ValueError(f"{name} must be an integer between 0 and 1000")

    # 保存点把身份、CTE、反向导入和可选 LSP 读取绑定到同一版本，不结束调用者事务。
    conn.execute("SAVEPOINT tsa_pulse_read")
    try:
        return _query_pulse_snapshot(conn, file_path, symbol_name, params)
    finally:
        conn.execute("RELEASE SAVEPOINT tsa_pulse_read")


def _query_pulse_snapshot(
    conn: sqlite3.Connection,
    file_path: str,
    symbol_name: str,
    params: dict[str, Any],
) -> PulseResponse | None:
    """在公开入口持有的只读保存点内完成全部上下文读取。"""
    # 先证明唯一身份；同文件同名必须由调用方消歧，不能任意取第一条。
    targets = conn.execute(
        "SELECT id FROM ast_symbol_rows WHERE file_path = ? AND name = ? LIMIT 2",
        (file_path, symbol_name),
    ).fetchall()
    if not targets:
        return None
    if len(targets) != 1:
        raise ValueError(f"AMBIGUOUS_SYMBOL: {file_path}:{symbol_name}")
    params["symbol_id"] = targets[0][0]
    from ..synapse_resolver._context import (
        _build_module_to_file,
        _local_name_as_submodule,
        _resolve_module_to_file,
    )

    modules = _build_module_to_file([file_path])
    params["module_node"] = "module:" + next(iter(modules), "")
    if params["max_comments"]:
        marker = conn.execute(
            "SELECT json_type(symbols_json, '$.comments') FROM ast_index WHERE file_path=?",
            (file_path,),
        ).fetchone()
        if marker is not None and marker[0] != "array":
            raise ValueError(
                "COMMENTS_NOT_INDEXED: rebuild the index, or set max_comments=0 for unsupported languages"
            )

    # 主查询失败不是符号缺失；仅可选 LSP 富化允许降级。
    row = conn.execute(_PULSE_SQL, params).fetchone()

    # 固定 SELECT 总会返回一行；内置 JSON 聚合生成合法 JSON，对象子查询可为 NULL。
    # 按固定列序读取，兼容 tuple 与 sqlite3.Row；索引 7 是原始文档文本，不参与解码。
    target_d, git_heat_d = (
        json.loads(row[index]) if row[index] is not None else None for index in (0, 5)
    )
    if target_d is None:
        return None
    (
        callers_raw,
        callees_raw,
        imports_raw,
        imported_by_raw,
        siblings_raw,
        comments_raw,
    ) = (json.loads(row[index]) for index in (1, 2, 3, 4, 6, 8))

    language = target_d.get("language", "")
    call_graph_available = language not in _NO_CALL_GRAPH_LANGUAGES
    call_graph_reason = (
        f"{language}: call-graph not supported" if not call_graph_available else ""
    )

    docstring_raw = row[7]

    # SQL 在完整 JSON 中定位定义后才截短文档，避免截断序列化对象。
    docstring = (
        docstring_raw if isinstance(docstring_raw, str) and docstring_raw else None
    )

    sym_info = SymbolInfo(
        name=target_d.get("name", symbol_name),
        kind=target_d.get("kind", "unknown"),
        file=target_d.get("file", file_path),
        line=target_d.get("line", 0),
        end_line=target_d.get("end_line", 0),
        language=language,
        docstring=docstring,
    )

    callers = tuple(
        CallerRef(
            name=c.get("name", ""),
            file=c.get("file", ""),
            line=c.get("line", 0) or 0,
            hot30=c.get("hot30", 0) or 0,
        )
        for c in callers_raw
        if c.get("name")
    )

    callees = tuple(
        CalleeRef(
            name=c.get("name", ""),
            file=c.get("file") or None,
            line=c.get("line") or None,
            resolution=c.get("resolution") or "unresolved",
        )
        for c in callees_raw
        if c.get("name")
    )

    git_heat: GitHeat | None = None
    if git_heat_d:
        if git_heat_d.get("commit") and not git_heat_d.get("commit_msg"):
            logger.warning("COMMIT_MESSAGE_MISSING: %s:%s", file_path, symbol_name)
        git_heat = GitHeat(
            commit=git_heat_d.get("commit"),
            commit_msg=git_heat_d.get("commit_msg") or None,
            at=git_heat_d.get("at"),
            mod_30d=git_heat_d.get("mod_30d", 0) or 0,
            mod_90d=git_heat_d.get("mod_90d", 0) or 0,
            mod_all=git_heat_d.get("mod_all", 0) or 0,
            state=git_heat_d.get("state", "tracked") or "tracked",
        )

    imports = tuple(
        ImportRef(module=i.get("module", ""), file=i.get("file"))
        for i in imports_raw
        if i.get("module")
    )

    imported_by = tuple(str(f) for f in imported_by_raw if f)
    if language == "python":
        # 只读既有索引，不做仓库扫描；使用真实模块表解析相对 import 和子模块别名。
        files = conn.execute(
            "SELECT file_path FROM ast_index WHERE language='python' "
            "UNION SELECT file_path FROM ast_symbol_rows WHERE language='python' LIMIT 10001"
        ).fetchall()
        bindings = conn.execute(
            "SELECT module_path,is_relative,file_path,local_name,alias_of FROM ast_imports "
            "WHERE language='python' LIMIT 20001"
        ).fetchall()
        if len(files) > 10000 or len(bindings) > 20000:
            raise ValueError("PULSE_IMPORT_RESOURCE_LIMIT")
        module_to_file = _build_module_to_file([r[0] for r in files])
        importers = set(imported_by)
        for module, relative, caller, local_name, alias_of in bindings:
            resolved = _resolve_module_to_file(
                module, bool(relative), caller, module_to_file
            )
            submodule = (
                _local_name_as_submodule(
                    local_name, alias_of, module, caller, module_to_file
                )
                if relative
                else ""
            )
            if file_path in (resolved, submodule):
                importers.add(caller)
        imported_by = tuple(sorted(importers)[:20])

    siblings = tuple(
        SiblingRef(
            name=s.get("name", ""),
            kind=s.get("kind", "unknown"),
            line=s.get("line", 0) or 0,
        )
        for s in siblings_raw
        if s.get("name")
    )

    comments = tuple(
        CommentRef(
            line=c.get("line", 0) or 0,
            text=c.get("text", ""),
            kind=c.get("kind", "inline"),
        )
        for c in comments_raw
    )

    # 保留 SQL 返回的边身份，不能按文件和名字重新猜测调用点。
    callees = _enrich_callees_with_lsp(
        conn, callees, tuple(c["edge_id"] for c in callees_raw if c.get("name"))
    )

    if not call_graph_available:
        callers = ()
        callees = ()

    return PulseResponse(
        symbol=sym_info,
        call_graph_available=call_graph_available,
        call_graph_reason=call_graph_reason,
        callers=callers,
        callees=callees,
        git_heat=git_heat,
        imports=imports,
        imported_by=imported_by,
        siblings=siblings,
        comments=comments,
    )


# ---------------------------------------------------------------------------
# token 数量估算
# ---------------------------------------------------------------------------


def _estimate_tokens(value: Any) -> int:
    """估算 JSON 序列化后的 token 数量。"""
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(json.dumps(value, ensure_ascii=False, default=str)))
    except ImportError:
        return len(json.dumps(value, ensure_ascii=False, default=str)) // 4


# ---------------------------------------------------------------------------
# apply_budget：按 token 预算裁剪
# ---------------------------------------------------------------------------

# 字段按优先级从高到低排列，裁剪时逆序遍历。
_PRIORITY_ORDER = [
    "callers",
    "callees",
    "git_heat",
    "imports",
    "imported_by",
    "siblings",
    "comments",
]

_FIELD_BUDGETS = {
    "callers": 150,
    "callees": 120,
    "git_heat": 80,
    "imports": 100,
    "imported_by": 60,
    "siblings": 120,
    "comments": 100,
}

_FIELD_TOP_N = {
    "callers": 5,
    "callees": 10,
    "imports": 10,
    "imported_by": 5,
    "siblings": 10,
    "comments": 10,
}


def apply_budget(pulse: PulseResponse, token_budget: int) -> PulseResponse:
    """按估算 token 预算裁剪，始终保留 symbol，其他字段从低优先级开始删除。

    返回新的 PulseResponse，不修改输入；仅保留 symbol 时也可能超过预算。
    """
    # 符号身份始终保留。
    sym_tokens = _estimate_tokens(dataclasses.asdict(pulse.symbol))
    truncated: list[str] = []

    # 收集当前字段值；SQL LIMIT 可能已经做过数量裁剪。
    field_values: dict[str, Any] = {
        "callers": tuple(pulse.callers[: _FIELD_TOP_N.get("callers", 100)]),
        "callees": tuple(pulse.callees[: _FIELD_TOP_N.get("callees", 100)]),
        "git_heat": pulse.git_heat,
        "imports": tuple(pulse.imports[: _FIELD_TOP_N.get("imports", 100)]),
        "imported_by": tuple(pulse.imported_by[: _FIELD_TOP_N.get("imported_by", 100)]),
        "siblings": tuple(pulse.siblings[: _FIELD_TOP_N.get("siblings", 100)]),
        "comments": tuple(pulse.comments[: _FIELD_TOP_N.get("comments", 100)]),
    }

    # 从低优先级开始删减，不因某个高优先字段太大就跳过它保留低优先字段。
    total_estimate = sym_tokens + sum(
        _estimate_tokens(v) for v in field_values.values()
    )
    for field_name in reversed(_PRIORITY_ORDER):
        if total_estimate <= token_budget:
            break
        val = field_values[field_name]
        if val is None or val == ():
            continue
        truncated.append(field_name)
        field_values[field_name] = () if isinstance(val, tuple) else None
        total_estimate += _estimate_tokens(field_values[field_name]) - _estimate_tokens(
            val
        )

    total_estimate = sym_tokens + sum(
        _estimate_tokens(v) for v in field_values.values()
    )

    return dataclasses.replace(
        pulse,
        callers=field_values["callers"],
        callees=field_values["callees"],
        git_heat=field_values["git_heat"],
        imports=field_values["imports"],
        imported_by=field_values["imported_by"],
        siblings=field_values["siblings"],
        comments=field_values["comments"],
        token_estimate=total_estimate,
        truncated_fields=tuple(truncated),
    )
