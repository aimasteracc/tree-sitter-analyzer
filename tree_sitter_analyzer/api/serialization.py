"""Three-mode serialization for :class:`PulseResponse`.

Modes:
- ``skeletal``  (~150-250 tokens): symbol identity + counts only.
- ``compact``   (~400-600 tokens, default): short keys, all fields.
- ``verbose``   (~1500-2500 tokens): full keys, all fields.

The ``COMPACT_LEGEND`` constant is embedded in tool descriptions so agents
learn the key mappings once without paying the legend cost on every call.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from .pulse import GitHeat, PulseResponse

# Compact key legend for tool descriptions (embed once, read many times).
COMPACT_LEGEND = (
    "sym=symbol, cr=callers, ce=callees, gh=git_heat, im=imports, ib=imported_by, "
    "sib=siblings, cmt=comments, n=name, k=kind, f=file, l=line, el=end_line, "
    "lang=language, cls=class, doc=docstring, h=hot30, r=resolution, "
    "sha=commit, m=commit_msg, m30=mod_30d, m90=mod_90d, mall=mod_all, "
    "s=git_state, tok=token_estimate, trunc=truncated_fields, cg=call_graph_available"
)


def serialize(pulse: PulseResponse, format: str = "compact") -> dict[str, Any]:
    """Serialize ``pulse`` to a JSON-compatible dict in the requested format.

    Args:
        pulse: The :class:`PulseResponse` to serialize.
        format: One of ``"skeletal"``, ``"compact"``, or ``"verbose"``.

    Returns:
        A dict ready for ``json.dumps``.
    """
    if format == "skeletal":
        return _skeletal(pulse)
    if format == "verbose":
        return _verbose(pulse)
    return _compact(pulse)


def _skeletal(pulse: PulseResponse) -> dict[str, Any]:
    """~150-250 tokens: symbol identity + counts."""
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
    """~400-600 tokens: short keys, all fields."""
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
            {"n": c.name, "f": c.file, "l": c.line, "h": c.hot30}
            for c in pulse.callers
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
        } if gh else None,
        "im": [{"m": i.module, "f": i.file} for i in pulse.imports],
        "ib": list(pulse.imported_by),
        "sib": [{"n": s.name, "k": s.kind, "l": s.line} for s in pulse.siblings],
        "cmt": [{"l": c.line, "t": c.text, "k": c.kind} for c in pulse.comments],
        "tok": pulse.token_estimate,
        "trunc": list(pulse.truncated_fields),
        "cg": pulse.call_graph_available,
    }


def _verbose(pulse: PulseResponse) -> dict[str, Any]:
    """~1500-2500 tokens: full key names, all fields."""
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
        } if gh else None,
        "imports": [{"module": i.module, "file": i.file} for i in pulse.imports],
        "imported_by": list(pulse.imported_by),
        "siblings": [
            {"name": s.name, "kind": s.kind, "line": s.line}
            for s in pulse.siblings
        ],
        "comments": [
            {"line": c.line, "text": c.text, "kind": c.kind}
            for c in pulse.comments
        ],
        "token_estimate": pulse.token_estimate,
        "truncated_fields": list(pulse.truncated_fields),
        "call_graph_available": pulse.call_graph_available,
        "call_graph_reason": pulse.call_graph_reason,
    }
