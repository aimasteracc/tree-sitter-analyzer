#!/usr/bin/env python3
"""Module-level helpers for ``get_code_outline`` (split out of the tool, #1956).

The tool module re-exports every name here, so existing imports such as
``from ...get_code_outline_tool import _method_entry`` keep working.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Outline helpers (r37d2) — lifted from ``_build_outline`` so the latter
# stays at ~25 lines of phase dispatch. Each helper preserves byte-for-byte
# the dict layout the original code produced.
# ---------------------------------------------------------------------------


def _cap_class_members(cls: dict[str, Any], cap: int) -> tuple[dict[str, Any], bool]:
    """Cap a class outline's ``methods``/``fields`` lists to ``cap`` (#571).

    A single wide class (e.g. a 10k-method generated stub) otherwise blows the
    outline response past any byte budget with ``truncated=False``. When a list
    exceeds ``cap`` it is sliced and the pre-cap total recorded as
    ``<key>_total`` (the count is never corrupted — same #505 lesson as the
    top-level cap). Returns ``(capped_class, was_truncated)``. ``cls`` is always
    a ``_build_class_outlines`` dict.
    """
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
    # Owner of out-of-class/receiver-bound definitions (#590, Codex P2 on
    # #598): without this, `void math::Foo::bar()` outlines as a bare `bar`
    # with no trace of its owner. Additive, only present when bound — same
    # Theme-A convention as #429/#474.
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
    """Strip a leading ``*`` from a Go receiver type (``*Counter`` → ``Counter``).

    Returns ``None`` when ``receiver_type`` is falsy so callers can use a
    simple truthiness check before comparing against class names.
    """
    if not receiver_type:
        return None
    return receiver_type.removeprefix("*")


def _method_owned_by_class(
    method: Any, cls_name: str, cls_start: int, cls_end: int
) -> bool:
    """Return True when ``method`` belongs to ``cls``.

    Primary: line-range containment (works for Java, Python, C#, …).
    Secondary: receiver_type matching (Go, Rust, Kotlin — methods declared
    outside the struct/impl body carry ``receiver_type`` instead of being
    physically nested).
    """
    m_start = getattr(method, "start_line", 0)
    if cls_start <= m_start <= cls_end:
        return True
    # Secondary: receiver_type-based association for Go/Rust/Kotlin.
    rt = _normalize_receiver_type(getattr(method, "receiver_type", None))
    return rt is not None and rt == cls_name


def _in_class_ranges(
    method: Any,
    class_ranges: list[tuple[int, int]],
    class_names: list[str] | None = None,
) -> bool:
    """Return True iff ``method`` falls inside any class range or owns a receiver_type match.

    ``class_names`` is parallel to ``class_ranges``: when provided, the
    secondary receiver_type check is also applied so Go/Rust/Kotlin methods
    declared outside the struct body are not leaked to ``top_level_functions``.
    """
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

    A function is nested when another function's span contains it entirely:
    ``other_start <= fn_start and fn_end <= other_end`` and the spans are not
    identical (prevents false-positive when two functions share the same lines,
    e.g. a one-liner or same-line arrow functions).

    Issue #534: without this check, decorator-helper functions (Python
    ``wrapper`` inside ``my_decorator``), curried inner lambdas (TS), and Scala
    ``loop`` all leaked into ``top_level_functions``.
    """
    fn_start, fn_end = fn_spans[fn_idx]
    for j, (other_start, other_end) in enumerate(fn_spans):
        if j == fn_idx:
            continue
        # fn is contained within other (non-identical spans)
        if (
            other_start <= fn_start
            and fn_end <= other_end
            and (other_start, other_end) != (fn_start, fn_end)
        ):
            return True
    return False


def _resolve_extends(cls: Any) -> str | None:
    """Return the superclass name for a Class element.

    Tries ``extends_class`` first (the Java plugin spelling, also set by the
    Java plugin as the canonical alias) then falls back to ``superclass`` (the
    spelling used by JS, TS, Python, Ruby, PHP, C++, C#, and Go plugins).

    Issue #530: before this helper existed, ``_build_class_outlines`` only
    checked ``extends_class``, so all plugins that write ``superclass`` silently
    produced ``extends: null`` in the outline.
    """
    for attr in ("extends_class", "superclass"):
        v = getattr(cls, attr, None)
        # Strings only — a Mock's auto-generated attribute (or any odd
        # object) must not leak its repr into the response (memory
        # addresses made the byte-budget pins nondeterministic).
        if isinstance(v, str) and v:
            return v
    return None


def _resolve_implements(cls: Any) -> list[str]:
    """Return the list of implemented interface names for a Class element.

    Tries ``implements_interfaces`` first (the Java plugin spelling, also set
    by the Rust plugin) then falls back to ``interfaces`` (the spelling used by
    TS, Python, PHP, C++, C#, Go, and Ruby plugins).

    Issue #530: before this helper existed, ``_build_class_outlines`` only
    checked ``implements_interfaces``, so all plugins that write ``interfaces``
    silently produced ``implements: []`` in the outline.
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
    Precedence: line-range containment wins over receiver_type matching.
    A method is never offered to multiple classes.
    """
    # Build a set of (class_idx, method_idx) pairs using FIRST-CLAIM-WINS.
    # Process each method once; the first class that claims it (by line-range,
    # then by receiver_type) owns it exclusively.
    method_to_class: dict[int, int] = {}  # method_idx -> class_idx

    for method_idx, method in enumerate(all_methods):
        m_start = getattr(method, "start_line", 0)
        # First try: line-range containment (innermost wins)
        claimed_by = None
        for cls_idx, cls in enumerate(classes):
            cls_start = getattr(cls, "start_line", 0)
            cls_end = getattr(cls, "end_line", 0)
            if cls_start <= m_start <= cls_end:
                claimed_by = cls_idx
                break  # First match wins
        # If no line-range match, try receiver_type matching
        if claimed_by is None:
            rt = _normalize_receiver_type(getattr(method, "receiver_type", None))
            if rt is not None:
                for cls_idx, cls in enumerate(classes):
                    if getattr(cls, "name", "") == rt:
                        claimed_by = cls_idx
                        break
        # Record the claim (if any)
        if claimed_by is not None:
            method_to_class[method_idx] = claimed_by

    # Build class outlines using the ownership map
    class_outlines: list[dict[str, Any]] = []
    for cls_idx, cls in enumerate(classes):
        cls_start = getattr(cls, "start_line", 0)
        cls_end = getattr(cls, "end_line", 0)
        cls_name = getattr(cls, "name", "")
        # Gather methods owned by this class
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


def _enrich_markup_outline(
    outline: dict[str, Any], elements: list[Any], classes: list[Any]
) -> None:
    """Attach HTML / CSS element summaries when no class structure is present."""
    if classes:
        return
    markup_elements = [
        e for e in elements if getattr(e, "element_type", "") == "html_element"
    ]
    if markup_elements:
        outline["html_elements"] = [
            {
                "tag": getattr(e, "tag_name", getattr(e, "name", "?")),
                "class": getattr(e, "element_class", ""),
                "line_start": getattr(e, "start_line", 0),
                "line_end": getattr(e, "end_line", 0),
                "attributes": list(getattr(e, "attributes", {}).keys()),
            }
            for e in markup_elements
        ]
        outline["statistics"]["html_element_count"] = len(markup_elements)
    css_elements = [e for e in elements if getattr(e, "element_type", "") == "css_rule"]
    if css_elements:
        outline["css_rules"] = [
            {
                "selector": getattr(e, "selector", getattr(e, "name", "?")),
                "class": getattr(e, "element_class", ""),
                "line_start": getattr(e, "start_line", 0),
                "line_end": getattr(e, "end_line", 0),
            }
            for e in css_elements
        ]
        outline["statistics"]["css_rule_count"] = len(css_elements)


_SQL_OBJECT_TYPES: frozenset[str] = frozenset(
    {"table", "view", "procedure", "trigger", "index"}
)


def _enrich_sql_outline(
    outline: dict[str, Any], elements: list[Any], classes: list[Any]
) -> None:
    """Attach SQL object summaries (tables / views / procedures / ...).

    ``sql_function`` has element_type="function" so it already lands in
    ``top_level_functions`` — we only emit ``sql_objects`` for the non-
    function DDL elements that wouldn't otherwise surface.
    """
    if classes:
        return
    sql_elements = [
        e for e in elements if getattr(e, "element_type", "") in _SQL_OBJECT_TYPES
    ]
    if not sql_elements:
        return
    by_type: dict[str, list[dict[str, Any]]] = {}
    for e in sql_elements:
        etype = getattr(e, "element_type", "unknown")
        by_type.setdefault(etype, []).append(
            {
                "name": getattr(e, "name", "?"),
                "line_start": getattr(e, "start_line", 0),
                "line_end": getattr(e, "end_line", 0),
            }
        )
    outline["sql_objects"] = by_type
    outline["statistics"]["sql_object_count"] = len(sql_elements)


_MD_HEADING_TYPES: frozenset[str] = frozenset({"heading"})
_MD_BLOCK_TYPES: frozenset[str] = frozenset(
    {"code_block", "table", "list", "task_list"}
)


def _enrich_markdown_outline(
    outline: dict[str, Any], elements: list[Any], classes: list[Any]
) -> None:
    """Attach Markdown headings + block summaries (guarded by language)."""
    if classes:
        return
    md_headings = [
        e
        for e in elements
        if getattr(e, "element_type", "") in _MD_HEADING_TYPES
        and getattr(e, "language", "") == "markdown"
    ]
    md_blocks = [
        e
        for e in elements
        if getattr(e, "element_type", "") in _MD_BLOCK_TYPES
        and getattr(e, "language", "") == "markdown"
    ]
    if md_headings:
        outline["headings"] = [
            {
                "text": getattr(e, "name", "?"),
                "level": getattr(e, "level", 0),
                "line_start": getattr(e, "start_line", 0),
                "line_end": getattr(e, "end_line", 0),
            }
            for e in md_headings
        ]
        outline["statistics"]["heading_count"] = len(md_headings)
    if md_blocks:
        outline["blocks"] = [
            {
                "type": getattr(e, "element_type", "?"),
                "name": getattr(e, "name", "?"),
                "line_start": getattr(e, "start_line", 0),
                "line_end": getattr(e, "end_line", 0),
            }
            for e in md_blocks
        ]
        outline["statistics"]["block_count"] = len(md_blocks)


def _enrich_yaml_outline(
    outline: dict[str, Any], elements: list[Any], classes: list[Any]
) -> None:
    """Attach YAML document + top-level mapping summaries (guarded by language)."""
    if classes:
        return
    yaml_docs = [
        e
        for e in elements
        if getattr(e, "element_type", "") == "document"
        and getattr(e, "language", "") == "yaml"
    ]
    yaml_mappings = [
        e
        for e in elements
        if getattr(e, "element_type", "") == "mapping"
        and getattr(e, "nesting_level", 1) == 0
    ]
    if yaml_docs:
        outline["yaml_documents"] = [
            {
                "index": getattr(e, "document_index", i),
                "line_start": getattr(e, "start_line", 0),
                "line_end": getattr(e, "end_line", 0),
            }
            for i, e in enumerate(yaml_docs)
        ]
        outline["statistics"]["yaml_document_count"] = len(yaml_docs)
    if yaml_mappings:
        outline["yaml_top_keys"] = [
            {
                "key": getattr(e, "key", getattr(e, "name", "?")),
                "value_type": getattr(e, "value_type", "?"),
                "line_start": getattr(e, "start_line", 0),
                "line_end": getattr(e, "end_line", 0),
            }
            for e in yaml_mappings
        ]
        outline["statistics"]["yaml_top_key_count"] = len(yaml_mappings)


def _enrich_json_outline(
    outline: dict[str, Any], elements: list[Any], classes: list[Any]
) -> None:
    """Attach JSON document root + top-level property summaries.

    Top-level here means ``nesting_level == 1`` because the document root
    itself is at level 0 — properties at level 1 are the file's outermost
    object keys.
    """
    if classes:
        return
    json_doc = next(
        (
            e
            for e in elements
            if getattr(e, "element_type", "") == "document"
            and getattr(e, "language", "") == "json"
        ),
        None,
    )
    json_props = [
        e
        for e in elements
        if getattr(e, "element_type", "") in ("property", "pair")
        and getattr(e, "nesting_level", 0) == 1
    ]
    if json_doc is None and not json_props:
        return
    if json_doc is not None:
        outline["json_root"] = {
            "type": getattr(json_doc, "value_type", "unknown"),
            "child_count": getattr(json_doc, "child_count", None),
            "line_start": getattr(json_doc, "start_line", 0),
            "line_end": getattr(json_doc, "end_line", 0),
        }
    if json_props:
        outline["json_top_keys"] = [
            {
                "key": getattr(e, "key", getattr(e, "name", "?")),
                "value_type": getattr(e, "value_type", "?"),
                "child_count": getattr(e, "child_count", None),
                "line_start": getattr(e, "start_line", 0),
                "line_end": getattr(e, "end_line", 0),
            }
            for e in json_props
        ]
        outline["statistics"]["json_top_key_count"] = len(json_props)
