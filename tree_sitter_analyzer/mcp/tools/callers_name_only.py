"""#1672：``NAME_ONLY_INBOUND`` 的证据——计数、有上限的调用点与点名它们的 next_step。

#1578 让仅同名匹配、无法绑定到目标的入边阻止 ``complete``，但答案只给出原因码：
dogfood 第 8 轮 11/11 个带 ``NAME_ONLY_INBOUND`` 的答案没有计数、没有调用点，
``next_step`` 也是通用的“Review callers above”。契约要求“Read them; qualify the
name”，答案却没有说“them”是谁，Agent 只能自己 grep。

这里沿用 ``unresolved_sites`` / ``non_call_reference_sites`` 的形状：列表有上限，
总数与是否截断并列给出；调用点行号取自调用边（``edges.line``），只在读不到时
退回调用方的定义行。
"""

from __future__ import annotations

from typing import Any

#: 响应中列出的调用点上限（与 ``unresolved_sites`` 相同）。
SITES_CAP = 20
#: next_step 中内联点名的调用点数。
_SITES_NAMED = 3


def name_only_sites(
    possible_callers: list[dict[str, Any]],
    call_lines: dict[str, frozenset[int]] | None,
) -> list[dict[str, Any]]:
    """把仅同名匹配的调用方展开为调用点 ``{file, line, caller}``（有序）。

    ``call_lines`` 为以目标裸名为被调方的调用边所在行（按文件分组）；调用方范围
    内的每一行是一个调用点。读不到调用边时以调用方的定义行代替，只会更粗，
    不会少列调用方。
    """
    sites: list[dict[str, Any]] = []
    for caller in possible_callers:
        file_path = str(caller.get("file") or "")
        start = int(caller.get("line") or 0)
        end = int(caller.get("end_line") or start)
        receiver = caller.get("receiver")
        name = str(caller.get("name") or "")
        label = f"{receiver}.{name}" if receiver else name
        in_range = sorted(
            line
            for line in (call_lines or {}).get(file_path, ())
            if start <= line <= end
        )
        for line in in_range or [start]:
            sites.append({"file": file_path, "line": line, "caller": label})
    sites.sort(key=lambda site: (site["file"], site["line"], site["caller"]))
    return sites


def name_only_fields(count: int, sites: list[dict[str, Any]]) -> dict[str, Any]:
    """响应字段：同名入边计数，及有上限的调用点与诚实总数。"""
    return {
        "name_only_inbound": count,
        "name_only_sites": sites[:SITES_CAP],
        "name_only_sites_total": len(sites),
        "name_only_sites_truncated": len(sites) > SITES_CAP,
    }


def name_only_step(func_name: str, sites: list[dict[str, Any]]) -> str:
    """点名调用点并说明如何限定名字的 next_step。"""
    named = [
        f"{site['file']}:{site['line']} ({site['caller']})"
        for site in sites[:_SITES_NAMED]
    ]
    if len(sites) > _SITES_NAMED:
        named.append(f"and {len(sites) - _SITES_NAMED} more")
    owner, _, bare = func_name.rpartition(".")
    if owner:
        qualify = (
            f"A site calls {func_name!r} only if its receiver is a "
            f"`{owner.rpartition('.')[2]}` (or subclass) instance; read each one."
        )
    else:
        qualify = (
            "Read them, then qualify the query as `Class.method` (with "
            "`file_path`) to bind the callers that belong to this definition."
        )
    return (
        f"{len(sites)} call site(s) reach a same-named `{bare}` through a receiver "
        f"that could not be bound to {func_name!r} (`name_only_sites`): "
        f"{'; '.join(named)}. {qualify}"
    )
