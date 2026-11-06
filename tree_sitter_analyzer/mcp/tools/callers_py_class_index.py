"""#1896: the classes of a project's Python files, read from source on demand.

:mod:`.callers_py_subtypes` needs the project subclasses of a class. Parsing
and resolving every class of a project up front costs tens of seconds where
there are thousands of classes (pydantic), so everything is lazy:

* built once per project state: which files contain each identifier (a word
  index of the source text) and which files cannot be read;
* per file, on first use: its classes (name, span, names bound in the body,
  names their bases and class keywords mention, and for a module-level name
  what it is bound to) and its renames (``import X as Y``,
  ``from m import X as Y``, ``Y = X``, ``Y = m.X``). Only files that contain
  a name the walk looks for are parsed;
* per class, on first use: its bases through the import resolver of
  :mod:`.callers_py_supertypes`.

The state is the index snapshot identity and the stat of every indexed Python
file. A file modified within :data:`_RACY_NS` keeps the index from being
stored.
"""

from __future__ import annotations

import ast
import os
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .callers_py_supertypes import (
    _Class,
    _eval,
    _keyword_problem,
    _Module,
    _parse,
    _Reader,
    _scopes_for,
)
from .evidence_file_cache import FILE_CACHE

#: Project states (roots) whose index is kept.
_INDEXES_MAX = 4
#: A file modified this recently may change again within its stat granularity.
_RACY_NS = 5_000_000_000
_WORD = re.compile(r"\w+")

#: ``(file, line, column)`` of a ``class`` statement.
Key = tuple[str, int, int]
#: The project's top-level module names (see :func:`.python_project_tops`).
Tops = Callable[[], frozenset[str] | None]


@dataclass(frozen=True)
class Unknown:
    """A base (or class keyword) the resolver cannot follow."""

    clause: str
    why: str
    #: Names the clause mentions (and the names they are bound to).
    mentions: frozenset[str]
    #: A class keyword (``metaclass=``): it may rewrite the bases, but naming a
    #: class there does not make the class a subclass of it.
    keyword: bool = False


#: A resolved base: a project class, ``None`` for an external one, or unknown.
Base = Key | Unknown | None


@dataclass(frozen=True)
class ClassFacts:
    name: str
    rel: str
    line: int
    column: int
    end: int
    #: Names bound in the class body.
    names: frozenset[str]
    #: Names its bases and class keywords mention.
    mentions: frozenset[str]

    @property
    def key(self) -> Key:
        return (self.rel, self.line, self.column)


@dataclass(frozen=True)
class FileFacts:
    classes: tuple[ClassFacts, ...]
    #: ``(original, alias)`` renames in the file.
    renames: tuple[tuple[str, str], ...]


@dataclass
class ClassIndex:
    """The project's classes, read and resolved on demand."""

    root: str
    #: identifier -> files whose text contains it.
    by_word: dict[str, list[str]] = field(default_factory=dict)
    unreadable: list[str] = field(default_factory=list)
    _files: dict[str, FileFacts | None] = field(default_factory=dict)
    _bases: dict[Key, tuple[Base, ...]] = field(default_factory=dict)
    _ancestors: dict[Key, frozenset[Key] | tuple[Key, Unknown]] = field(
        default_factory=dict
    )
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def files_with(self, names: Iterable[str], shape: str = "header") -> list[str]:
        """Files whose text may hold a class header (``shape="header"``) or a
        rename (``"rename"``) naming one of ``names``; unreadable ones too."""
        wanted = sorted(set(names))
        files = sorted({rel for name in wanted for rel in self.by_word.get(name, ())})
        if not files:
            return []
        pattern = _shape(wanted, shape)
        found = []
        for rel in files:
            text = FILE_CACHE.read_text(os.path.join(self.root, *rel.split("/")))
            if text is None or pattern.search(text):
                found.append(rel)
        return found

    def file(self, rel: str) -> FileFacts | None:
        """The classes of ``rel``; None when it cannot be read or parsed."""
        with self._lock:
            if rel not in self._files:
                self._files[rel] = _read_file_facts(self.root, rel)
            return self._files[rel]

    def klass(self, key: Key) -> ClassFacts | None:
        facts = self.file(key[0])
        if facts is None:
            return None
        return next((c for c in facts.classes if c.key == key), None)

    def spelled(self, names: Iterable[str]) -> tuple[set[str], str | None]:
        """``names`` and every name a rename chain binds them to, or an
        unparsable file that may rename one."""
        found = set(names)
        fresh = set(found)
        while fresh:
            added: set[str] = set()
            for rel in self.files_with(fresh, "rename"):
                facts = self.file(rel)
                if facts is None:
                    return found, rel
                added.update(
                    alias
                    for original, alias in facts.renames
                    if original in fresh and alias not in found
                )
            found |= added
            fresh = added
        return found, None

    def bases(self, key: Key, tops: Tops) -> tuple[Base, ...]:
        """The bases of ``key``, resolved once (``tops``: the query's index)."""
        with self._lock:
            found = self._bases.get(key)
            if found is None:
                found = _resolve(_Reader(self.root, tops), key)
                self._bases[key] = found
            return found

    def ancestors(self, key: Key, tops: Tops) -> frozenset[Key] | tuple[Key, Unknown]:
        """``key`` and every class above it, or the first base that cannot be followed."""
        with self._lock:
            found = self._ancestors.get(key)
            if found is None:
                found = self._walk_up(key, tops)
                self._ancestors[key] = found
            return found

    def _walk_up(self, key: Key, tops: Tops) -> frozenset[Key] | tuple[Key, Unknown]:
        seen = {key}
        stack = [key]
        while stack:
            current = stack.pop()
            for base in self.bases(current, tops):
                if isinstance(base, Unknown):
                    return current, base
                if base is not None and base not in seen:
                    if self.klass(base) is None:
                        why = "a class in a file that is not indexed"
                        return current, Unknown(base[0], why, frozenset())
                    seen.add(base)
                    stack.append(base)
        return frozenset(seen)

    def class_at(self, rel: str, line: int, name: str = "") -> Key | None:
        """The innermost class of ``rel`` spanning ``line`` (binding ``name``)."""
        facts = self.file(rel)

        best: ClassFacts | None = None
        for klass in () if facts is None else facts.classes:
            if not klass.line <= line <= klass.end:
                continue
            if name and name not in klass.names:
                continue
            if best is None or klass.line >= best.line:
                best = klass
        return None if best is None else best.key


def _shape(names: list[str], shape: str) -> re.Pattern[str]:
    alternation = "|".join(map(re.escape, names))
    if shape == "rename":
        return re.compile(
            rf"\b(?:{alternation})\s+as\s+\w"
            rf"|^[ \t]*\w+[ \t]*=[ \t]*(?:[\w.]+\.)?(?:{alternation})[ \t]*(?:#.*)?$",
            re.MULTILINE,
        )
    # A class header naming it, or a module-level assignment naming it\n    # (``Base = mix(A)``: :func:`_bound_to` reads only module-level bindings).
    return re.compile(
        rf"\bclass\s+\w+\s*\([^:]*?\b(?:{alternation})\b"
        rf"|^\w+[ \t]*(?::[^=\n]*)?=[^=\n]*\b(?:{alternation})\b",
        re.MULTILINE,
    )


def class_key(rel: str, node: ast.ClassDef) -> Key:
    return (rel, node.lineno, node.col_offset)


def _resolve(reader: _Reader, key: Key) -> tuple[Base, ...]:
    rel, line, column = key
    module = reader.module(rel)
    node = None if module is None else _class_node(module, line, column)
    if module is None or node is None:
        return (Unknown("?", "its file could not be read or parsed", frozenset()),)
    scopes = _scopes_for(module, node)
    bases: list[Base] = [_base(reader, module, scopes, expr) for expr in node.bases]
    for keyword in node.keywords:
        try:
            why = _keyword_problem(reader, module, scopes, keyword)
        except RecursionError:
            why = "a class keyword the index cannot follow"
        if why is not None:
            bases.append(
                Unknown(
                    ast.unparse(keyword),
                    why,
                    _mentions(module, [keyword.value]),
                    keyword=True,
                )
            )
    return tuple(bases)


def _class_node(module: _Module, line: int, column: int) -> ast.ClassDef | None:
    for node in ast.walk(module.tree):
        if (
            isinstance(node, ast.ClassDef)
            and node.lineno == line
            and node.col_offset == column
        ):
            return node
    return None


def _base(
    reader: _Reader, module: _Module, scopes: list[ast.AST], expr: ast.expr
) -> Base:
    """A base class; a subscripted project class (``A[int]``) is the class."""
    try:
        value: Any = _eval(
            reader,
            module,
            scopes,
            expr.value if isinstance(expr, ast.Subscript) else expr,
            0,
        )
    except RecursionError:
        value = "a base too deeply nested to follow"
    if isinstance(value, _Class):
        return class_key(value.module.rel, value.node)
    if value is None:
        return None
    why = value if isinstance(value, str) else "a module, not a class"
    return Unknown(
        " ".join(ast.unparse(expr).split())[:80], why, _mentions(module, [expr])
    )


# --- per file -------------------------------------------------------------------------


def _read_file_facts(root: str, rel: str) -> FileFacts | None:
    """The classes and renames of ``rel`` as read now; None when unreadable or unparsable.

    RFC-0043: :func:`_file_facts` is a pure function of the file's bytes (and
    ``rel``, which every fact names), so it is reused per content digest across
    index states (a renewed snapshot or a refresh rebuilds the index but not the
    facts of unchanged files). The bytes are read live through the evidence file
    cache on every call; no syntax tree is kept.
    """
    from ...resident import parse_facts

    found = FILE_CACHE.read_stamped(os.path.join(root, *rel.split("/")))
    if found is None:
        return None
    data = found[0]

    def compute() -> FileFacts | None:
        module = _parse(rel, data)
        return None if module is None else _file_facts(module)

    return parse_facts.facts("py.class_facts", "python", data, compute, extra=(rel,))


def _file_facts(module: _Module) -> FileFacts:
    classes: list[ClassFacts] = []
    renames: list[tuple[str, str]] = []
    for node in ast.walk(module.tree):
        if isinstance(node, ast.alias) and node.asname and node.name != "*":
            renames.append((node.name.rpartition(".")[2], node.asname))
        elif isinstance(node, ast.ClassDef):
            clauses = [*node.bases, *(keyword.value for keyword in node.keywords)]
            classes.append(
                ClassFacts(
                    node.name,
                    module.rel,
                    node.lineno,
                    node.col_offset,
                    node.end_lineno or node.lineno,
                    frozenset(module.bindings(node)),
                    _mentions(module, clauses),
                )
            )
    for stmt in module.tree.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and isinstance(stmt.value, ast.Name | ast.Attribute)
        ):
            value = stmt.value
            original = value.id if isinstance(value, ast.Name) else value.attr
            renames.append((original, stmt.targets[0].id))
    return FileFacts(tuple(classes), tuple(r for r in renames if r[0] != r[1]))


def _mentions(module: _Module, exprs: Iterable[ast.AST]) -> frozenset[str]:
    """Names in ``exprs``, and what a module-level name among them is bound to."""
    found: set[str] = set()
    for expr in exprs:
        for node in ast.walk(expr):
            if isinstance(node, ast.Attribute):
                found.add(node.attr)
            elif isinstance(node, ast.Name):
                found.add(node.id)
                found |= _bound_to(module, node.id)
    return frozenset(found)


def _bound_to(module: _Module, name: str) -> set[str]:
    found: set[str] = set()
    for entry in module.bindings(module.tree).get(name, ()):
        if isinstance(entry, ast.alias):
            found.add(entry.name.rpartition(".")[2])
            continue
        parent = module.parents.get(id(entry))
        value = getattr(parent, "value", None)
        if isinstance(value, ast.AST):
            for node in ast.walk(value):
                if isinstance(node, ast.Name):
                    found.add(node.id)
                elif isinstance(node, ast.Attribute):
                    found.add(node.attr)
    return found


# --- the cache ----------------------------------------------------------------------

_INDEXES: OrderedDict[str, tuple[Any, ClassIndex]] = OrderedDict()
_INDEXES_LOCK = threading.Lock()


def clear_indexes() -> None:
    """Forget the cached indexes (tests)."""
    with _INDEXES_LOCK:
        _INDEXES.clear()


def project_index(root: str, cache: Any) -> ClassIndex | str:
    """The class index of the project's indexed Python files, cached per state."""
    files = _python_files(cache)
    if files is None:
        return "the project's Python files could not be listed to find its subclasses"
    stamps, racy = _stamps(root, files)
    from ...resident import snapshot_memo

    state = (snapshot_memo.snapshot_key(cache), stamps)
    with _INDEXES_LOCK:
        hit = _INDEXES.get(root)
        if hit is not None and hit[0] == state:
            _INDEXES.move_to_end(root)
            return hit[1]
    index = build(root, files)
    if not racy:
        with _INDEXES_LOCK:
            _INDEXES[root] = (state, index)
            _INDEXES.move_to_end(root)
            while len(_INDEXES) > _INDEXES_MAX:
                _INDEXES.popitem(last=False)
    return index


def build(root: str, files: list[str]) -> ClassIndex:
    """The word index of every listed file."""
    index = ClassIndex(root)
    for rel in files:
        text = FILE_CACHE.read_text(os.path.join(root, *rel.split("/")))
        if text is None:
            index.unreadable.append(rel)
            continue
        for word in set(_WORD.findall(text)):
            index.by_word.setdefault(word, []).append(rel)
    return index


def _python_files(cache: Any) -> list[str] | None:
    if cache is None:
        return None
    from ...resident import snapshot_memo

    def read() -> list[str] | None:
        try:
            rows = (
                cache.get_conn()
                .execute("SELECT file_path FROM ast_index WHERE language = 'python'")
                .fetchall()
            )
        except Exception:  # noqa: BLE001 — unreadable: cannot list
            return None
        return sorted({str(row[0]).replace("\\", "/") for row in rows})

    found = snapshot_memo.cached(cache, "py_subtypes.files", (), read)
    return None if found is None else list(found)


def _stamps(
    root: str, files: list[str]
) -> tuple[tuple[tuple[str, tuple[int, int, int] | None], ...], bool]:
    now = time.time_ns()
    found: list[tuple[str, tuple[int, int, int] | None]] = []
    racy = False
    for rel in files:
        try:
            info = os.stat(os.path.join(root, *rel.split("/")))
        except OSError:
            found.append((rel, None))
            continue
        found.append((rel, (info.st_size, info.st_mtime_ns, info.st_ctime_ns)))
        racy = racy or now - info.st_mtime_ns < _RACY_NS
    return tuple(found), racy


__all__ = [
    "Base",
    "ClassFacts",
    "ClassIndex",
    "FileFacts",
    "Key",
    "Unknown",
    "build",
    "class_key",
    "clear_indexes",
    "project_index",
]
