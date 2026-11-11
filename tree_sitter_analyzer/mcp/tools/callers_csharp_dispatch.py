"""#1953: C# interface dispatch the declaring type's own base list does not show.

.. code-block:: csharp

    public class Engine { public void Run() { } }
    public class Car : Engine, IRun { }        // Engine.Run implements IRun.Run
    public interface IParse<T> where T : IParse<T> { static abstract T Parse(string s); }
    public struct Num : IParse<Num> { public static Num Parse(string s) => default; }

* **Through a subclass**: a ``public`` method of class ``A`` implements a member
  of interface ``I`` for every subclass ``B : A, I`` (also further down), so a
  call through ``I`` reaches ``A.M``. Every project class deriving from ``A``
  is found from source (C# files that mention ``A``); each interface such a
  subclass lists must resolve to a project interface, and when one of them
  (transitively) declares the name, every call edge named like it must be bound
  here or outside the project. A base whose name could denote ``A`` but does
  not resolve blocks.
* **``static abstract``**: a ``public static`` method implements a ``static
  abstract`` / ``static virtual`` interface member, reached through a type
  parameter (``T.Parse(s)``). The interfaces of its type (and of subclasses)
  are checked the same way; an interface outside the project blocks unless it
  is a standard type known to have no static abstract member
  (:data:`NO_STATIC_ABSTRACT`).
"""

from __future__ import annotations

import os
import re
from typing import Any

from .callers_csharp_scope import csharp_files
from .callers_override_common import (
    MAX_TYPES,
    OverrideProof,
    dispatch_proof,
    fail,
    walk,
)
from .evidence_file_cache import FILE_CACHE

#: Outside types (simple names, any arity) that declare no ``static abstract``
#: or ``static virtual`` member: interfaces older than C# 11 and classes.
NO_STATIC_ABSTRACT = frozenset(
    {
        "object",
        "Object",
        "Exception",
        "Attribute",
        "EventArgs",
        "Stream",
        "TextReader",
        "TextWriter",
        "MarshalByRefObject",
        "Collection",
        "KeyedCollection",
        "ReadOnlyCollection",
        "List",
        "Dictionary",
        "DynamicObject",
        "TypeConverter",
        "IDisposable",
        "IAsyncDisposable",
        "ICloneable",
        "IComparable",
        "IComparer",
        "IEqualityComparer",
        "IEquatable",
        "IEnumerable",
        "IEnumerator",
        "IAsyncEnumerable",
        "IAsyncEnumerator",
        "ICollection",
        "IList",
        "IDictionary",
        "IDictionaryEnumerator",
        "IReadOnlyCollection",
        "IReadOnlyList",
        "IReadOnlyDictionary",
        "ISet",
        "IReadOnlySet",
        "IFormattable",
        "ISpanFormattable",
        "IConvertible",
        "ISerializable",
        "IDeserializationCallback",
        "IObjectReference",
        "INotifyPropertyChanged",
        "INotifyPropertyChanging",
        "INotifyCollectionChanged",
        "ICustomTypeDescriptor",
        "ITypedList",
        "IBindingList",
        "ICancelAddNew",
        "IRaiseItemChangedEvents",
        "IDynamicMetaObjectProvider",
        "IServiceProvider",
        "IObservable",
        "IObserver",
        "IStructuralEquatable",
        "IStructuralComparable",
        "IXmlSerializable",
        "IXmlLineInfo",
        "IXmlNamespaceResolver",
    }
)
_CLASSES = frozenset({"class_declaration", "record_declaration"})
_STATIC_SLOTS = frozenset({"abstract", "virtual"})


def subtype_dispatch_proof(
    reader: Any, start: Any, bare: str, rel: str, line: int, *, static: bool
) -> OverrideProof | None:
    """Whether interface dispatch the base list of ``start`` does not show
    could reach ``start.bare``; None when nothing applies."""
    if static:
        own = _scan(reader, start, bare, static=True)
        if own is not None:
            return _verdict(reader, own, bare, rel, line, start, "its type")
    if start.node.type not in _CLASSES:
        return None
    subclasses = _subclasses(reader, start)
    if isinstance(subclasses, str):
        return fail(subclasses)
    for sub in subclasses:
        found = _scan(reader, sub, bare, static=static)
        if found is not None:
            where = f"its subclass `{sub.dotted}` ({sub.file})"
            return _verdict(reader, found, bare, rel, line, start, where)
    return None


def _verdict(
    reader: Any,
    found: tuple[str, str],
    bare: str,
    rel: str,
    line: int,
    start: Any,
    where: str,
) -> OverrideProof | None:
    kind, detail = found
    if kind == "block":
        return fail(f"{where} may map it to an interface member: {detail}")
    proof = dispatch_proof(reader.cache, bare, rel, line, start.name)
    if proof.proved:
        return None
    return OverrideProof(
        False,
        f"{where} lists the interface `{detail}`, which declares it; {proof.detail}",
        proof.sites,
    )


def _scan(reader: Any, t: Any, bare: str, *, static: bool) -> tuple[str, str] | None:
    """``("block", why)``, ``("declares", interface)`` or None for the
    interfaces ``t`` lists (transitively)."""
    seen = {t.key}
    queue = [t]
    while queue:
        current = queue.pop(0)
        entries = _entries(reader, current)
        if isinstance(entries, str):
            return "block", entries
        for _raw, simple, resolved in entries:
            if isinstance(resolved, str):
                if static and simple in NO_STATIC_ABSTRACT:
                    continue
                return "block", resolved
            if resolved.key in seen or resolved.node.type != "interface_declaration":
                continue
            seen.add(resolved.key)
            if len(seen) > MAX_TYPES:
                return "block", "its interfaces are too many to check"
            if _declares(reader, resolved, bare, static=static):
                return "declares", resolved.dotted
            queue.append(resolved)
    return None


def _entries(reader: Any, t: Any) -> list[tuple[str, str, Any]] | str:
    """``(text, simple name, resolved type or why not)`` per base list entry."""
    parts = reader.parts(t)
    if isinstance(parts, str):
        return parts
    found = []
    for part in parts:
        parsed = reader.parse(part.file)
        if parsed is None:
            return "a file in its supertype closure could not be parsed"
        base_list = next((c for c in part.node.children if c.type == "base_list"), None)
        if base_list is None:
            continue
        if base_list.has_error:
            return f"the base list of `{part.name}` could not be parsed"
        for entry in base_list.named_children:
            if entry.type == "primary_constructor_base_type":
                entry = entry.child_by_field_name("type") or entry
            if entry.type == "predefined_type":
                continue  # `object`
            raw = parsed.text(entry)
            found.append((raw, _simple(raw), reader.resolve(part, entry)))
    return found


def _simple(raw: str) -> str:
    """``System.IEquatable<T>`` -> ``IEquatable``."""
    head = raw.partition("<")[0].strip()
    return head.rpartition("::")[2].rpartition(".")[2]


def _declares(reader: Any, iface: Any, bare: str, *, static: bool) -> bool:
    from .callers_csharp_overrides import _members, _name_text

    parts = reader.parts(iface)
    for part in parts if isinstance(parts, list) else [iface]:
        parsed = reader.parse(part.file)
        body = part.node.child_by_field_name("body")
        if parsed is None or body is None:
            continue
        for member in _members(body):
            if member.type != "method_declaration":
                continue
            if _name_text(parsed, member) != bare:
                continue
            modifiers = {
                parsed.text(c) for c in member.children if c.type == "modifier"
            }
            if ("static" in modifiers) != static:
                continue
            if not static or modifiers & _STATIC_SLOTS:
                return True
    return False


def _subclasses(reader: Any, start: Any) -> list[Any] | str:
    """Project classes deriving from ``start`` (transitively), or why not."""
    files = csharp_files(reader.cache)
    if isinstance(files, str):
        return files
    found: list[Any] = []
    seen = {start.key}
    queue = [start]
    while queue:
        current = queue.pop(0)
        direct = _direct_subclasses(reader, files, current)
        if isinstance(direct, str):
            return direct
        for sub in direct:
            if sub.key in seen:
                continue
            seen.add(sub.key)
            if len(seen) > MAX_TYPES:
                return "its subclasses are too many to check"
            found.append(sub)
            queue.append(sub)
    return found


def _direct_subclasses(reader: Any, files: list[str], base: Any) -> list[Any] | str:
    mention = re.compile(r"\b" + re.escape(base.name) + r"\b")
    # A class header naming it after `:` (over-matches; only used on files
    # whose tree has an error, where a header may be lost).
    header = re.compile(
        r"\b(?:class|record)\s+\w+[^{;]*?:[^{;]*?\b" + re.escape(base.name) + r"\b"
    )
    found = []
    for rel in files:
        text = FILE_CACHE.read_text(os.path.join(reader.root, rel))
        if text is None:
            return f"the C# file {rel} could not be read"
        if ":" not in text or not mention.search(text):
            continue
        parsed = reader.parse(rel)
        if parsed is None:
            return f"the C# file {rel} could not be parsed"
        if parsed.root.has_error and header.search(text):
            return (
                f"a class in {rel} may derive from it, but the file has a syntax error"
            )
        for node in walk(parsed.root):
            if node.type not in _CLASSES:
                continue
            first = _first_base(node)
            if first is None:
                continue
            if first.has_error:
                return f"a base list in {rel} could not be parsed"
            raw = parsed.text(first)
            if _simple(raw) != base.name:
                continue
            candidate = reader.type_of(rel, node)
            resolved = reader.resolve(candidate, first)
            if isinstance(resolved, str):
                return (
                    f"`{candidate.dotted}` ({rel}) may derive from it, but "
                    f"{resolved.removeprefix('its ')}"
                )
            if resolved.key == base.key:
                found.append(candidate)
    return found


def _first_base(node: Any) -> Any | None:
    base_list = next((c for c in node.children if c.type == "base_list"), None)
    if base_list is None or not base_list.named_children:
        return None
    entry = base_list.named_children[0]
    if entry.type == "primary_constructor_base_type":
        entry = entry.child_by_field_name("type") or entry
    return entry


__all__ = ["NO_STATIC_ABSTRACT", "subtype_dispatch_proof"]
