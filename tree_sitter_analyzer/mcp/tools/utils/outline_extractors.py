"""Outline extractor helpers — Phase 3 REQ-CLEAN-003.

Class and method extraction logic for GetCodeOutlineTool.

Functions:
    _cap_class_members
    _method_entry
    _field_entry
    _normalize_receiver_type
    _method_owned_by_class
    _in_class_ranges
    _in_function_spans
    _resolve_extends
    _resolve_implements
    _build_class_outlines
"""

from __future__ import annotations

from typing import Any


def _cap_class_members(cls: dict[str, Any], cap: int) -> tuple[dict[str, Any], bool]:
    """Cap a class outline's ``methods``/``fields`` lists to ``cap`` (#571)."""
    capped = dict(cls)
    was_truncated = False
    for key in ("methods", "fields"):
        members = capped.get(key)
        if isinstance(members, list) and len(members) > cap:
            capped[f"{key}_total"] = len(members)
            capped[f"{key}_listed"] = cap
            capped[key] = members[:cap]
            was_truncated = True
    return capped, was_truncated


def _method_entry(m: Any) -> dict[str, Any]:
    """Convert a method element to an outline entry."""
    params = getattr(m, "parameters", [])
    if params and isinstance(params[0], str):
        param_list = params
    else:
        param_list = [
            f"{getattr(p, 'type', 'Object')} {getattr(p, 'name', 'param')}"
            for p in params
        ]
    entry = {
        "name": getattr(m, "name", "unknown"),
        "return_type": getattr(m, "return_type", "void"),
        "parameters": param_list,
        "visibility": getattr(m, "visibility", "public"),
        "is_constructor": getattr(m, "is_constructor", False),
        "is_static": getattr(m, "is_static", False),
        "line_start": getattr(m, "start_line", 0),
        "line_end": getattr(m, "end_line", 0),
    }
    receiver = getattr(m, "receiver_type", None)
    if receiver:
        entry["receiver_type"] = receiver
    return entry


def _field_entry(f: Any) -> dict[str, Any]:
    """Convert a field element to an outline entry."""
    return {
        "name": getattr(f, "name", "unknown"),
        "type": getattr(f, "field_type", "Object"),
        "visibility": getattr(f, "visibility", "private"),
        "is_static": getattr(f, "is_static", False),
        "line_start": getattr(f, "start_line", 0),
        "line_end": getattr(f, "end_line", 0),
    }


def _normalize_receiver_type(receiver_type: str | None) -> str | None:
    """Strip a leading ``*`` from a Go receiver type (``*Counter`` → ``Counter``)."""
    if not receiver_type:
        return None
    return receiver_type.removeprefix("*")


def _method_owned_by_class(
    method: Any, cls_name: str, cls_start: int, cls_end: int
) -> bool:
    """Return True when ``method`` belongs to ``cls``."""
    m_start = getattr(method, "start_line", 0)
    if cls_start <= m_start <= cls_end:
        return True
    rt = _normalize_receiver_type(getattr(method, "receiver_type", None))
    return rt is not None and rt == cls_name


def _in_class_ranges(
    method: Any,
    class_ranges: list[tuple[int, int]],
    class_names: list[str] | None = None,
) -> bool:
    """Return True iff ``method`` falls inside any class range or owns a receiver_type match."""
    m_start = getattr(method, "start_line", 0)
    for i, (cls_start, cls_end) in enumerate(class_ranges):
        if cls_start <= m_start <= cls_end:
            return True
        if class_names is not None:
            rt = _normalize_receiver_type(getattr(method, "receiver_type", None))
            if rt is not None and rt == class_names[i]:
                return True
    return False


def _in_function_spans(
    fn_idx: int,
    fn_spans: list[tuple[int, int]],
) -> bool:
    """Return True iff function at ``fn_idx`` is strictly nested inside another.

    Issue #534: without this check, decorator-helper functions, curried inner
    lambdas, and Scala ``loop`` all leaked into ``top_level_functions``.
    """
    fn_start, fn_end = fn_spans[fn_idx]
    for j, (other_start, other_end) in enumerate(fn_spans):
        if j == fn_idx:
            continue
        if (
            other_start <= fn_start
            and fn_end <= other_end
            and (other_start, other_end) != (fn_start, fn_end)
        ):
            return True
    return False


def _resolve_extends(cls: Any) -> str | None:
    """Return the superclass name for a Class element.

    Issue #530: before this helper existed, ``_build_class_outlines`` only
    checked ``extends_class``, so all plugins that write ``superclass``
    silently produced ``extends: null`` in the outline.
    """
    for attr in ("extends_class", "superclass"):
        v = getattr(cls, attr, None)
        if isinstance(v, str) and v:
            return v
    return None


def _resolve_implements(cls: Any) -> list[str]:
    """Return the list of implemented interface names for a Class element.

    Issue #530: before this helper existed, ``_build_class_outlines`` only
    checked ``implements_interfaces``.
    """
    for attr in ("implements_interfaces", "interfaces"):
        v = getattr(cls, attr, None)
        if isinstance(v, (list, tuple)) and v:
            return [str(item) for item in v]
    return []


def _build_class_outlines(
    classes: list[Any],
    all_methods: list[Any],
    all_fields: list[Any],
    include_fields: bool,
) -> list[dict[str, Any]]:
    """Build the ``classes`` outline section, sorted by ``line_start``.

    SINGLE-OWNERSHIP INVARIANT (P2): Each method is assigned to at most one class.
    """
    method_to_class: dict[int, int] = {}

    for method_idx, method in enumerate(all_methods):
        m_start = getattr(method, "start_line", 0)
        claimed_by = None
        for cls_idx, cls in enumerate(classes):
            cls_start = getattr(cls, "start_line", 0)
            cls_end = getattr(cls, "end_line", 0)
            if cls_start <= m_start <= cls_end:
                claimed_by = cls_idx
                break
        if claimed_by is None:
            rt = _normalize_receiver_type(getattr(method, "receiver_type", None))
            if rt is not None:
                for cls_idx, cls in enumerate(classes):
                    if getattr(cls, "name", "") == rt:
                        claimed_by = cls_idx
                        break
        if claimed_by is not None:
            method_to_class[method_idx] = claimed_by

    class_outlines: list[dict[str, Any]] = []
    for cls_idx, cls in enumerate(classes):
        cls_start = getattr(cls, "start_line", 0)
        cls_end = getattr(cls, "end_line", 0)
        cls_name = getattr(cls, "name", "")
        cls_methods = [
            _method_entry(all_methods[m_idx])
            for m_idx in method_to_class
            if method_to_class[m_idx] == cls_idx
        ]
        cls_methods.sort(key=lambda x: x["line_start"])
        class_entry: dict[str, Any] = {
            "name": cls_name,
            "type": getattr(cls, "class_type", "class"),
            "line_start": cls_start,
            "line_end": cls_end,
            "extends": _resolve_extends(cls),
            "implements": _resolve_implements(cls),
            "methods": cls_methods,
        }
        if include_fields:
            cls_fields = [
                _field_entry(f)
                for f in all_fields
                if cls_start <= getattr(f, "start_line", 0) <= cls_end
            ]
            cls_fields.sort(key=lambda x: x["line_start"])
            class_entry["fields"] = cls_fields
        class_outlines.append(class_entry)
    class_outlines.sort(key=lambda x: x["line_start"])
    return class_outlines
