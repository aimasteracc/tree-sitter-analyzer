"""PulseResponse 的三种序列化视图。

skeletal 仅保留身份与计数，compact 使用短键，verbose 使用完整键名。
COMPACT_LEGEND 为工具描述提供固定键名映射；实际大小取决于内容与裁剪结果。
"""

from __future__ import annotations

from typing import Any

from ._pulse_models import PulseResponse

# 工具描述共用的紧凑键名映射，内容属于既有公开协议。
COMPACT_LEGEND = (
    "sym=symbol, cr=callers, ce=callees, gh=git_heat, im=imports, ib=imported_by, "
    "sib=siblings, cmt=comments, n=name, k=kind, f=file, l=line, el=end_line, "
    "lang=language, cls=class, doc=docstring, h=hot30, r=resolution, "
    "sha=commit, m=commit_msg, m30=mod_30d, m90=mod_90d, mall=mod_all, "
    "s=git_state, tok=token_estimate, trunc=truncated_fields, cg=call_graph_available"
)


def serialize(pulse: PulseResponse, format: str = "compact") -> dict[str, Any]:
    """按 skeletal、compact 或 verbose 视图返回可供 json.dumps 使用的字典。"""
    if format == "skeletal":
        return _skeletal(pulse)
    if format == "verbose":
        return _verbose(pulse)
    return _compact(pulse)


def _skeletal(pulse: PulseResponse) -> dict[str, Any]:
    """仅返回符号身份、关系计数与调用图可用性。"""
    sym = pulse.symbol
    return {
        "n": sym.name,
        "k": sym.kind,
        "f": f"{sym.file}:{sym.line}",
        "callers": len(pulse.callers),
        "callees": len(pulse.callees),
        "hot30": pulse.git_heat.mod_30d if pulse.git_heat else 0,
        "call_graph": pulse.call_graph_available,
    }


def _compact(pulse: PulseResponse) -> dict[str, Any]:
    """以既有短键输出全部字段。"""
    sym = pulse.symbol
    gh = pulse.git_heat

    return {
        "sym": {
            "n": sym.name,
            "k": sym.kind,
            "f": sym.file,
            "l": sym.line,
            "el": sym.end_line,
            "lang": sym.language,
            "cls": sym.class_name,
            "doc": sym.docstring,
        },
        "cr": [
            {"n": c.name, "f": c.file, "l": c.line, "h": c.hot30} for c in pulse.callers
        ],
        "ce": [
            {"n": c.name, "f": c.file, "l": c.line, "r": c.resolution}
            for c in pulse.callees
        ],
        "gh": {
            "sha": gh.commit,
            "m": gh.commit_msg,
            "at": gh.at,
            "m30": gh.mod_30d,
            "m90": gh.mod_90d,
            "mall": gh.mod_all,
            "s": gh.state,
        }
        if gh
        else None,
        "im": [{"m": i.module, "f": i.file} for i in pulse.imports],
        "ib": list(pulse.imported_by),
        "sib": [{"n": s.name, "k": s.kind, "l": s.line} for s in pulse.siblings],
        "cmt": [{"l": c.line, "t": c.text, "k": c.kind} for c in pulse.comments],
        "tok": pulse.token_estimate,
        "trunc": list(pulse.truncated_fields),
        "cg": pulse.call_graph_available,
    }


def _verbose(pulse: PulseResponse) -> dict[str, Any]:
    """以完整键名输出全部字段。"""
    sym = pulse.symbol
    gh = pulse.git_heat

    return {
        "symbol": {
            "name": sym.name,
            "kind": sym.kind,
            "file": sym.file,
            "line": sym.line,
            "end_line": sym.end_line,
            "language": sym.language,
            "class_name": sym.class_name,
            "docstring": sym.docstring,
        },
        "callers": [
            {"name": c.name, "file": c.file, "line": c.line, "hot30": c.hot30}
            for c in pulse.callers
        ],
        "callees": [
            {
                "name": c.name,
                "file": c.file,
                "line": c.line,
                "resolution": c.resolution,
            }
            for c in pulse.callees
        ],
        "git_heat": {
            "commit": gh.commit,
            "commit_msg": gh.commit_msg,
            "at": gh.at,
            "mod_30d": gh.mod_30d,
            "mod_90d": gh.mod_90d,
            "mod_all": gh.mod_all,
            "state": gh.state,
        }
        if gh
        else None,
        "imports": [{"module": i.module, "file": i.file} for i in pulse.imports],
        "imported_by": list(pulse.imported_by),
        "siblings": [
            {"name": s.name, "kind": s.kind, "line": s.line} for s in pulse.siblings
        ],
        "comments": [
            {"line": c.line, "text": c.text, "kind": c.kind} for c in pulse.comments
        ],
        "token_estimate": pulse.token_estimate,
        "truncated_fields": list(pulse.truncated_fields),
        "call_graph_available": pulse.call_graph_available,
        "call_graph_reason": pulse.call_graph_reason,
    }
