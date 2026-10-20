"""RFC-0038: resolve ``x.m()`` through the type an annotation gives ``x``.

The extractor records a receiver hint on the call edge (``receiver_hints.py``);
this module turns it into a project method:

1. the hint's type text (or the return annotation of the factory it names) is
   normalised — quotes stripped, ``Optional[T]`` / ``T | None`` reduced to
   ``T``, anything wider rejected;
2. the name is resolved to a class in the annotating file's context: a local
   class, a ``from M import T [as A]`` binding (following package re-exports),
   or ``alias.T`` through a module import — never by a project-wide guess;
3. the method is looked up on the class, then its project bases, depth-first;
   two distinct definitions from different base branches are ambiguous.

Anything that cannot be decided returns ``None`` and the call falls through to
the ordinary cascade, exactly as before this RFC.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..cached_annotated_binding import ANNOTATED_RECEIVER

if TYPE_CHECKING:
    from . import ResolvedCallee
    from ._context import ResolverContext

#: Fixed confidence of such an edge: below an import binding (0.9), above the
#: global name fallback (0.5). An annotation is a claim the runtime never checks.
ANNOTATED_CONFIDENCE = 0.8

_MAX_REEXPORT_HOPS = 4
_MAX_BASE_DEPTH = 6
_DOTTED = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_OPTIONAL_PREFIXES = ("Optional[", "typing.Optional[", "t.Optional[")
_UNION_PREFIXES = ("Union[", "typing.Union[", "t.Union[")
#: Names that never denote a project class.
_NON_CLASS_NAMES = frozenset(
    {
        "Any",
        "object",
        "None",
        "NoReturn",
        "Never",
        "type",
        "str",
        "int",
        "float",
        "bool",
        "bytes",
        "list",
        "dict",
        "set",
        "tuple",
        "frozenset",
        "complex",
    }
)
_TRIVIAL_BASES = frozenset(
    {"object", "Generic", "Protocol", "ABC", "typing.Protocol", "abc.ABC"}
)


def normalize_annotation(text: str) -> str | None:
    """Reduce an annotation to one dotted class name, or ``None`` if it is wider.

    ``"T"`` / ``'T'`` / ``Optional[T]`` / ``Union[T, None]`` / ``T | None`` all
    become ``T``; ``Self`` stays ``Self``. A union of two classes, any other
    subscript (``list[T]``, ``type[T]``), and builtin names are rejected.
    """
    value = (text or "").strip()
    for _ in range(4):
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1].strip()
            continue
        inner = _strip_wrapper(value, _OPTIONAL_PREFIXES)
        if inner is not None:
            value = inner
            continue
        union = _strip_wrapper(value, _UNION_PREFIXES)
        parts = (
            _split_top_level(union, ",")
            if union is not None
            else _split_top_level(value, "|")
        )
        if len(parts) > 1:
            members = [p for p in parts if p.strip() not in ("None", "type(None)")]
            if len(members) != 1:
                return None
            value = members[0].strip()
            continue
        break
    if not _DOTTED.match(value) or value.rsplit(".", 1)[-1] in _NON_CLASS_NAMES:
        return None
    return value


def _strip_wrapper(value: str, prefixes: tuple[str, ...]) -> str | None:
    for prefix in prefixes:
        if value.startswith(prefix) and value.endswith("]"):
            return value[len(prefix) : -1].strip()
    return None


def _split_top_level(value: str, separator: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in value:
        if char in "[(":
            depth += 1
        elif char in "])":
            depth -= 1
        if char == separator and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return [part.strip() for part in parts]


@dataclass
class AnnotationIndex:
    """Per-snapshot facts the rule needs beyond ``ResolverContext``."""

    classes: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    returns: dict[int, tuple[str, str, str | None]] = field(default_factory=dict)
    kinds: dict[int, str] = field(default_factory=dict)
    lines: dict[int, int] = field(default_factory=dict)
    #: file -> {module-level name: receiver hint} (``symbols_json.module_types``)
    module_types: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)


def annotation_index(ctx: ResolverContext) -> AnnotationIndex:
    """Build (once per context) class bases, return annotations and symbol lines."""
    cached = getattr(ctx, "_annotation_index", None)
    if isinstance(cached, AnnotationIndex):
        return cached
    index = AnnotationIndex()
    cache = getattr(ctx, "cache", None)
    if cache is not None:
        try:
            _load_index(cache.get_conn(), index)
        except Exception:  # nosec B110 — missing tables: no annotation evidence.
            index = AnnotationIndex()
    ctx._annotation_index = index  # type: ignore[attr-defined]  # noqa: SLF001
    return index


def _load_index(conn: Any, index: AnnotationIndex) -> None:
    by_position: dict[tuple[str, str, int], int] = {}
    for row in conn.execute(
        "SELECT id, name, kind, file_path, line FROM ast_symbol_rows "
        "WHERE kind IN ('function', 'method', 'class')"
    ):
        sym_id = int(row[0])
        index.kinds[sym_id] = str(row[2])
        index.lines[sym_id] = int(row[4] or 0)
        by_position[(str(row[3]), str(row[1]), int(row[4] or 0))] = sym_id
    for file_path, symbols_json in conn.execute(
        "SELECT file_path, symbols_json FROM ast_index WHERE language = 'python'"
    ):
        try:
            payload = json.loads(symbols_json)
            symbols = payload.get("symbols", [])
        except (TypeError, ValueError, AttributeError):
            continue
        module_types = payload.get("module_types")
        if isinstance(module_types, dict) and module_types:
            index.module_types[file_path] = module_types
        for symbol in symbols:
            kind = symbol.get("kind")
            name = str(symbol.get("name") or "")
            if kind == "class" and name:
                index.classes.setdefault(file_path, {})[name] = [
                    str(parent) for parent in symbol.get("parents") or []
                ]
            elif kind in ("function", "method") and symbol.get("return_type"):
                found = by_position.get((file_path, name, int(symbol.get("line") or 0)))
                if found is not None:
                    index.returns[found] = (
                        str(symbol["return_type"]),
                        file_path,
                        symbol.get("class"),
                    )


def resolve_class(
    name: str, file_path: str, ctx: ResolverContext, hops: int = 0
) -> tuple[str, str] | None:
    """Resolve a dotted class name in ``file_path``'s import context."""
    if hops > _MAX_REEXPORT_HOPS:
        return None
    index = annotation_index(ctx)
    if "." in name:
        head, _, rest = name.partition(".")
        target = ctx.import_alias_target.get(file_path, {}).get(head)
        if not target or "." in rest:
            return None
        return resolve_class(rest, target, ctx, hops + 1)
    if name in index.classes.get(file_path, {}):
        return (file_path, name)
    for entry in ctx.imports_by_file.get(file_path, []):
        if entry.is_star or entry.local_name != name:
            continue
        target = ctx.name_to_source.get(file_path, {}).get(name)
        if not target or target == file_path:
            return None
        return resolve_class(entry.alias_of or name, target, ctx, hops + 1)
    target = ctx.name_to_source.get(file_path, {}).get(name)  # star import
    if target and target != file_path:
        return resolve_class(name, target, ctx, hops + 1)
    return None


def find_method(
    cls: tuple[str, str], method: str, ctx: ResolverContext
) -> tuple[str, int, str] | None:
    """``(file, symbol id, owner class)`` of ``method`` on ``cls`` or its bases.

    #1699：多个基类分支都定义了 ``method`` 时，按 C3 线性化取最近的定义
    （``Sub(Mixin, Base)`` 中 ``Mixin.fmt`` 遮蔽 ``Base.fmt``）；线性化不一致才放弃。
    """
    found = _method_candidates(cls, method, ctx, 0, set())
    distinct = {(file, sym_id): owner for file, sym_id, owner in found}
    if len(distinct) == 1:
        (file, sym_id), owner = next(iter(distinct.items()))
        return file, sym_id, owner
    if not distinct:
        return None
    order = linearize(cls, ctx)
    if order is None:
        return None
    return next(
        (
            (file_path, own[method], class_name)
            for file_path, class_name in order
            for own in [ctx.file_class_methods.get(file_path, {}).get(class_name, {})]
            if method in own
        ),
        None,
    )


def linearize(
    cls: tuple[str, str], ctx: ResolverContext, stack: tuple[tuple[str, str], ...] = ()
) -> list[tuple[str, str]] | None:
    """``cls`` 的 C3 线性化（只含能解析到的项目类）；不一致或过深时为 ``None``。"""
    if cls in stack or len(stack) > _MAX_BASE_DEPTH:
        return None
    sequences: list[list[tuple[str, str]]] = []
    direct: list[tuple[str, str]] = []
    file_path, class_name = cls
    for parent in annotation_index(ctx).classes.get(file_path, {}).get(class_name, []):
        if parent in _TRIVIAL_BASES:
            continue
        base = resolve_class(parent.split("[", 1)[0], file_path, ctx)
        if base is None:
            continue
        order = linearize(base, ctx, (*stack, cls))
        if order is None:
            return None
        sequences.append(order)
        direct.append(base)
    merged = _c3_merge([*sequences, direct])
    return None if merged is None else [cls, *merged]


def _c3_merge(
    sequences: list[list[tuple[str, str]]],
) -> list[tuple[str, str]] | None:
    pending = [list(seq) for seq in sequences if seq]
    result: list[tuple[str, str]] = []
    while pending:
        for seq in pending:
            head = seq[0]
            if not any(head in other[1:] for other in pending):
                break
        else:
            return None
        result.append(head)
        pending = [[c for c in seq if c != head] for seq in pending]
        pending = [seq for seq in pending if seq]
    return result


def _method_candidates(
    cls: tuple[str, str],
    method: str,
    ctx: ResolverContext,
    depth: int,
    visited: set[tuple[str, str]],
) -> list[tuple[str, int, str]]:
    if depth > _MAX_BASE_DEPTH or cls in visited:
        return []
    visited.add(cls)
    file_path, class_name = cls
    own = ctx.file_class_methods.get(file_path, {}).get(class_name, {})
    if method in own:
        return [(file_path, own[method], class_name)]
    found: list[tuple[str, int, str]] = []
    for parent in annotation_index(ctx).classes.get(file_path, {}).get(class_name, []):
        if parent in _TRIVIAL_BASES:
            continue
        base = resolve_class(parent, file_path, ctx)
        if base is not None:
            found.extend(_method_candidates(base, method, ctx, depth + 1, visited))
    return found


def _factory_symbol(
    callee: str, caller_file: str, caller_name: str, ctx: ResolverContext
) -> int | None:
    """Symbol id of the project function / class a factory call names."""
    from . import _try_class_method, _try_import, _try_local, _try_self_method

    qualifier, _, base = callee.rpartition(".")
    if qualifier in ("self", "cls"):
        resolved = _try_self_method(base, qualifier, caller_file, caller_name, ctx)
    elif qualifier:
        resolved = _try_import(base, qualifier, caller_file, ctx) or _try_class_method(
            base, qualifier, ctx
        )
    else:
        local = _try_local(base, caller_file, ctx)
        if local is not None and (
            annotation_index(ctx).kinds.get(local.callee_symbol_id or -1) == "method"
        ):
            local = None  # a bare call never names a method of some class
        resolved = local or _try_import(base, "", caller_file, ctx)
    return resolved.callee_symbol_id if resolved is not None else None


def _module_variable(
    hint: dict[str, Any], caller_file: str, ctx: ResolverContext
) -> tuple[str, dict[str, Any]] | None:
    """(defining file, its hint) for ``alias.NAME`` / an imported ``NAME``."""
    if "module_attr" in hint:
        alias, _, name = str(hint["module_attr"]).partition(".")
        target = ctx.import_alias_target.get(caller_file, {}).get(alias)
    else:
        name = str(hint.get("imported") or "")
        target, name = _imported_name_target(caller_file, name, ctx)
    for _ in range(_MAX_REEXPORT_HOPS):
        if not target or not name:
            return None
        found = annotation_index(ctx).module_types.get(target, {}).get(name)
        if isinstance(found, dict):
            return target, found
        target, name = _imported_name_target(target, name, ctx)  # re-export
    return None


def _imported_name_target(
    file_path: str, name: str, ctx: ResolverContext
) -> tuple[str | None, str]:
    for entry in ctx.imports_by_file.get(file_path, []):
        if entry.local_name == name and not entry.is_star:
            target = ctx.name_to_source.get(file_path, {}).get(name)
            if target and target != file_path:
                return target, entry.alias_of or name
            return None, name
    return None, name


def _hint_class(
    hint: dict[str, Any], caller_file: str, caller_name: str, ctx: ResolverContext
) -> tuple[str, str] | None:
    index = annotation_index(ctx)
    if "module_attr" in hint or "imported" in hint:
        located = _module_variable(hint, caller_file, ctx)
        if located is None:
            return None
        return _hint_class(located[1], located[0], "", ctx)
    if "type" in hint:
        name = normalize_annotation(str(hint["type"]))
        if name is None or name == "Self":
            return None
        return resolve_class(name, caller_file, ctx)
    callee = str(hint.get("returns_of") or "")
    sym_id = _factory_symbol(callee, caller_file, caller_name, ctx)
    if sym_id is None:
        return None
    if index.kinds.get(sym_id) == "class":
        return _class_of_symbol(sym_id, ctx)
    returned = index.returns.get(sym_id)
    if returned is None:
        return None
    text, def_file, owner = returned
    name = normalize_annotation(text)
    if name is None:
        return None
    if name == "Self":
        return (def_file, owner) if owner else None
    return resolve_class(name, def_file, ctx)


def _class_of_symbol(sym_id: int, ctx: ResolverContext) -> tuple[str, str] | None:
    """A factory that is itself a class (``x = make_thing()`` where it is one)."""
    for file_path, symbols in ctx.file_symbols.items():
        for name, kind, candidate in symbols:
            if candidate == sym_id and kind == "class":
                return (file_path, name)
    return None


def resolve_annotated_receiver(
    hint: dict[str, Any] | None,
    method: str,
    caller_file: str,
    caller_name: str,
    ctx: ResolverContext,
) -> ResolvedCallee | None:
    """Bind ``x.method()`` through ``hint``; ``None`` when undecidable."""
    if not hint or not method:
        return None
    from . import ResolvedCallee

    cls = _hint_class(hint, caller_file, caller_name, ctx)
    if cls is None:
        return None
    bound = find_method(cls, method, ctx)
    if bound is None:
        return None
    file_path, sym_id, owner = bound
    binding = {
        "source": "return"
        if "returns_of" in hint and hint.get("source") == "local"
        else str(hint.get("source") or ""),
        # The resolved class, so an aliased import (`as GS`) still names it.
        "type": cls[1],
        "type_file": cls[0],
        "owner": owner,
        "line": annotation_index(ctx).lines.get(sym_id, 0),
        "confidence": ANNOTATED_CONFIDENCE,
    }
    return ResolvedCallee(sym_id, ANNOTATED_RECEIVER, file_path, binding=binding)


def receiver_hint_from_metadata(metadata: Any) -> dict[str, Any] | None:
    """The persisted ``receiver_hint`` of an edge's metadata JSON, if any."""
    if not metadata:
        return None
    try:
        parsed = json.loads(metadata) if isinstance(metadata, str) else metadata
    except (TypeError, ValueError):
        return None
    hint = parsed.get("receiver_hint") if isinstance(parsed, dict) else None
    return hint if isinstance(hint, dict) else None
