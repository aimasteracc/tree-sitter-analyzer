"""一次只读连接取得活动索引的内容身份与调用图标记（dogfood 第 7 轮性能）。

``nav callers`` 每次调用都会：

* 打开一个完整的 ``ASTCache`` 只为回答 ``query_cost`` 的“索引是否有行”；
* 捕获一份认证快照（复制库与 WAL、``backup`` 到内存、复核投影），即使活动
  索引的调用图标记并不精确、捕获注定得到 ``CALL_GRAPH_INCOMPLETE`` 而被丢弃。

本模块用一次 ``query_only`` 连接读出证据，供调用方复用已算出的答案或跳过注定
无效的工作：库路径与发布 generation、``ast_index`` 行数、``edges`` 最大 rowid，
以及 ``ast_call_graph_state`` 的全部行。它只用于其组成部分足以决定答案的场合
（``query_cost`` 的“索引是否有行”只取决于行数是否为 0；认证是否可能只取决于
调用图标记），不是通用的内容身份。读取失败为 ``None``，调用方必须回退到原有的
完整路径。
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import Any

from .callgraph_state import exact_call_graph_marker


@dataclass(frozen=True)
class LiveIndexProbe:
    """活动索引的内容身份，以及其调用图标记是否精确。"""

    identity: tuple[Any, ...]
    call_graph_exact: bool


def probe_live_index(project_root: str) -> LiveIndexProbe | None:
    """只读探测活动索引；库不存在、不可读或结构不符时为 ``None``。"""
    from .generation_routing import resolve_index_location

    try:
        location = resolve_index_location(os.path.realpath(project_root))
    except (OSError, ValueError):
        return None
    database = location.path
    if not database.is_file():
        return None
    generation = getattr(location.selector, "generation_id", None)
    try:
        conn = sqlite3.connect(
            database.absolute().as_uri() + "?mode=rw",
            uri=True,
            timeout=1,
            check_same_thread=False,
        )
    except sqlite3.Error:
        return None
    try:
        conn.execute("PRAGMA query_only=ON")
        # 同一读事务内取全部证据，避免两次读取之间被写入者推进。
        conn.execute("BEGIN")
        # COUNT(*) 走主键索引（约 1 ms）；不取 MAX(indexed_at)：它位于大 JSON
        # 列之后，取值要遍历溢出页，实测 356 MB 的库需约 140 ms。
        files = conn.execute("SELECT COUNT(*) FROM ast_index").fetchone()
        edges = conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM edges").fetchone()
        state = conn.execute(
            "SELECT * FROM ast_call_graph_state ORDER BY rowid"
        ).fetchall()
        exact = exact_call_graph_marker(conn)
        conn.execute("COMMIT")
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    identity = (
        str(database),
        generation,
        tuple(files),
        tuple(edges),
        tuple(tuple(row) for row in state),
    )
    return LiveIndexProbe(identity, bool(exact))
