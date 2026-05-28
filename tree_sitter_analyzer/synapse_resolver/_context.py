"""Build the project-wide resolver context — one DB pass per index run."""

from __future__ import annotations

import json
import os
from collections import OrderedDict
from typing import TYPE_CHECKING, Any

from ..callee_resolution import CalleeResolver
from ._constants import BUILTINS_PY, STDLIB_NAMES_PY
from ._imports import ImportEntry

if TYPE_CHECKING:
    from ..ast_cache import ASTCache


class ResolverContext:
    """Project-wide indices the resolver consults per call edge.

    Two construction modes:

    * ``ResolverContext(project_root=..., cache=...)`` — convenience form;
      ``__post_init__`` auto-populates the maps from the cache on first
      construction. This is what callers of the public API typically use.
    * Pre-built form: pass all maps in directly (used by the hot index
      path so the build is shared across thousands of edge resolutions).

    All maps are caller-file-keyed where applicable.
    """

    def __init__(
        self,
        project_root: str,
        cache: ASTCache | None,
        *,
        file_symbols: dict[str, list[tuple[str, str, int]]] | None = None,
        name_to_source: dict[str, dict[str, str]] | None = None,
        file_class_methods: dict[str, dict[str, dict[str, int]]] | None = None,
        global_name_table: dict[str, list[tuple[str, int]]] | None = None,
        import_alias_target: dict[str, dict[str, str]] | None = None,
        imports_by_file: dict[str, list[ImportEntry]] | None = None,
        builtins: dict[str, frozenset[str]] | None = None,
        stdlib_modules: dict[str, frozenset[str]] | None = None,
        callee_resolver: CalleeResolver | None = None,
    ) -> None:
        self.project_root = project_root
        self.cache = cache
        self._file_symbols = file_symbols or {}
        self._name_to_source = name_to_source or {}
        self._file_class_methods = file_class_methods or {}
        self._file_class_methods_loaded = file_class_methods is not None
        self._global_name_table = global_name_table or {}
        self._import_alias_target = import_alias_target or {}
        self._imports_by_file = imports_by_file or {}
        self._builtins = builtins or {}
        self._stdlib_modules = stdlib_modules or {}
        self._callee_resolver = callee_resolver
        self._loaded = any(
            value is not None
            for value in (
                file_symbols,
                name_to_source,
                file_class_methods,
                global_name_table,
                import_alias_target,
                imports_by_file,
                builtins,
                stdlib_modules,
                callee_resolver,
            )
        )

    @property
    def file_symbols(self) -> dict[str, list[tuple[str, str, int]]]:
        self._ensure_loaded()
        return self._file_symbols

    @property
    def name_to_source(self) -> dict[str, dict[str, str]]:
        self._ensure_loaded()
        return self._name_to_source

    @property
    def file_class_methods(self) -> dict[str, dict[str, dict[str, int]]]:
        self._ensure_loaded()
        if not self._file_class_methods_loaded and self.cache is not None:
            self._file_class_methods = _build_file_class_methods_from_cache(self.cache)
            self._file_class_methods_loaded = True
        return self._file_class_methods

    @property
    def global_name_table(self) -> dict[str, list[tuple[str, int]]]:
        self._ensure_loaded()
        return self._global_name_table

    @property
    def import_alias_target(self) -> dict[str, dict[str, str]]:
        self._ensure_loaded()
        return self._import_alias_target

    @property
    def imports_by_file(self) -> dict[str, list[ImportEntry]]:
        self._ensure_loaded()
        return self._imports_by_file

    @property
    def builtins(self) -> dict[str, frozenset[str]]:
        self._ensure_loaded()
        return self._builtins

    @property
    def stdlib_modules(self) -> dict[str, frozenset[str]]:
        self._ensure_loaded()
        return self._stdlib_modules

    @property
    def callee_resolver(self) -> CalleeResolver | None:
        self._ensure_loaded()
        return self._callee_resolver

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        if self.cache is None:
            self._loaded = True
            return
        built = build_resolver_context(self.cache)
        self._file_symbols = built.file_symbols
        self._name_to_source = built.name_to_source
        self._file_class_methods = built._file_class_methods
        self._file_class_methods_loaded = built._file_class_methods_loaded
        self._global_name_table = built.global_name_table
        self._import_alias_target = built.import_alias_target
        self._imports_by_file = built.imports_by_file
        self._builtins = built.builtins
        self._stdlib_modules = built.stdlib_modules
        self._callee_resolver = built.callee_resolver
        self._loaded = True


_CONTEXT_CACHE_MAX = 8
_CONTEXT_CACHE: OrderedDict[tuple[str, int, int], ResolverContext] = OrderedDict()


def clear_resolver_context_cache() -> None:
    _CONTEXT_CACHE.clear()


def is_enabled() -> bool:
    """``TSA_SYNAPSE=0`` disables; anything else enables."""
    val = os.environ.get("TSA_SYNAPSE")
    if val is None:
        return True
    return val.strip().lower() not in ("0", "false", "no", "off", "")


def _build_module_to_file(file_paths: list[str]) -> dict[str, str]:
    """Map every indexed Python file to its module-dotted-name."""
    out: dict[str, str] = {}
    for fp in file_paths:
        parts = fp.replace(os.sep, "/")
        if parts.endswith("/__init__.py"):
            mod = parts[: -len("/__init__.py")].replace("/", ".")
            out[mod] = fp
        elif parts.endswith(".py"):
            mod = parts[:-3].replace("/", ".")
            out[mod] = fp
    return out


def _resolve_relative_module(
    module_path: str, caller_file: str, module_to_file: dict[str, str]
) -> str:
    """Resolve a relative ``.x.y`` import to a concrete file path."""
    caller_dir = os.path.dirname(caller_file).replace(os.sep, "/")
    leading_dots = 0
    for ch in module_path:
        if ch == ".":
            leading_dots += 1
        else:
            break
    rel = module_path[leading_dots:]
    anchor = caller_dir
    for _ in range(leading_dots - 1):
        if "/" in anchor:
            anchor = anchor.rsplit("/", 1)[0]
        else:
            anchor = ""
    if not rel:
        candidate = f"{anchor}/__init__.py" if anchor else "__init__.py"
        if candidate in set(module_to_file.values()):
            return candidate
        return ""
    base = f"{anchor}/{rel.replace('.', '/')}" if anchor else rel.replace(".", "/")
    candidates = (f"{base}.py", f"{base}/__init__.py")
    by_path = set(module_to_file.values())
    for cand in candidates:
        if cand in by_path:
            return cand
    return ""


def _resolve_absolute_module(module_path: str, module_to_file: dict[str, str]) -> str:
    if module_path in module_to_file:
        return module_to_file[module_path]
    parts = module_path.split(".")
    for i in range(len(parts), 0, -1):
        partial = ".".join(parts[:i])
        if partial in module_to_file:
            return module_to_file[partial]
    return ""


def _resolve_module_to_file(
    module_path: str,
    is_relative: bool,
    caller_file: str,
    module_to_file: dict[str, str],
) -> str:
    if is_relative:
        return _resolve_relative_module(module_path, caller_file, module_to_file)
    return _resolve_absolute_module(module_path, module_to_file)


def _local_name_as_submodule(
    local_name: str,
    alias_of: str,
    module_path: str,
    caller_file: str,
    module_to_file: dict[str, str],
) -> str:
    """For ``from <pkg> import <name>``, check if ``<name>`` is itself a
    submodule. Returns target file path or ``""``.

    Concrete cases:
    * ``from . import b``        — local_name='b',  alias_of=''   → caller_dir/b.py
    * ``from . import b as bb``  — local_name='bb', alias_of='b'  → caller_dir/b.py
    * ``from .pkg import b``     — local_name='b',  alias_of=''   → caller_dir/pkg/b.py

    The lookup module name is ``alias_of`` when present, else ``local_name``.
    """
    if not local_name:
        return ""
    lookup_name = alias_of or local_name
    caller_dir = os.path.dirname(caller_file).replace(os.sep, "/")
    leading_dots = 0
    for ch in module_path:
        if ch == ".":
            leading_dots += 1
        else:
            break
    anchor = caller_dir
    for _ in range(max(leading_dots - 1, 0)):
        if "/" in anchor:
            anchor = anchor.rsplit("/", 1)[0]
        else:
            anchor = ""
    rel = module_path[leading_dots:]
    base = anchor
    if rel:
        base = f"{anchor}/{rel.replace('.', '/')}" if anchor else rel.replace(".", "/")
    candidates = (
        f"{base}/{lookup_name}.py" if base else f"{lookup_name}.py",
        f"{base}/{lookup_name}/__init__.py" if base else f"{lookup_name}/__init__.py",
    )
    by_path = set(module_to_file.values())
    for cand in candidates:
        if cand in by_path:
            return cand
    return ""


def _build_file_class_methods(
    conn: Any, line_idx: dict[tuple[str, str, int], int]
) -> dict[str, dict[str, dict[str, int]]]:
    """Pull class→method maps from ``symbols_json``.

    ``ast_symbol_rows`` does not store the parent class. We pull it from
    the per-file ``symbols_json`` blob (where ``class`` is captured), then
    cross-reference back to the symbol id via (file, name, line).
    """
    out: dict[str, dict[str, dict[str, int]]] = {}
    rows = conn.execute("SELECT file_path, symbols_json FROM ast_index").fetchall()
    for row in rows:
        fp = row["file_path"]
        try:
            symbols = json.loads(row["symbols_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        per_class: dict[str, dict[str, int]] = {}
        for sym in symbols.get("symbols", []):
            if sym.get("kind") != "function":
                continue
            cls_name = sym.get("class")
            if not cls_name:
                continue
            method_name = sym.get("name", "")
            method_line = sym.get("line", 0)
            sym_id = line_idx.get((fp, method_name, method_line))
            if sym_id is None:
                continue
            per_class.setdefault(cls_name, {})[method_name] = sym_id
        if per_class:
            out[fp] = per_class
    return out


def _build_file_class_methods_from_cache(
    cache: ASTCache,
) -> dict[str, dict[str, dict[str, int]]]:
    conn = cache.get_conn()
    line_idx: dict[tuple[str, str, int], int] = {}
    try:
        rows = conn.execute(
            "SELECT id, name, file_path, line FROM ast_symbol_rows"
        ).fetchall()
    except Exception:  # nosec B110
        rows = []
    for row in rows:
        line_idx[(row["file_path"], row["name"], row["line"])] = row["id"]
    return _build_file_class_methods(conn, line_idx)


def _build_import_maps(
    imports_by_file: dict[str, list[ImportEntry]],
    module_to_file: dict[str, str],
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    """Derive (name_to_source, alias_target) from per-file import entries."""
    name_to_source: dict[str, dict[str, str]] = {}
    alias_target: dict[str, dict[str, str]] = {}
    for caller_file, entries in imports_by_file.items():
        name_map: dict[str, str] = {}
        alias_map: dict[str, str] = {}
        for entry in entries:
            if entry.is_star:
                continue
            target = _resolve_module_to_file(
                entry.module_path, entry.is_relative, caller_file, module_to_file
            )
            if entry.local_name:
                # Is this a `from <pkg> import <submodule>`? If so the
                # binding is a module alias, not a name binding. Use the
                # original module name (``alias_of``) for the lookup so
                # ``from . import b as bb`` correctly resolves ``bb`` to b.py.
                submod = _local_name_as_submodule(
                    entry.local_name,
                    entry.alias_of,
                    entry.module_path,
                    caller_file,
                    module_to_file,
                )
                if submod:
                    alias_map[entry.local_name] = submod
                elif target:
                    name_map[entry.local_name] = target
            # Bare ``import X`` and ``import a.b as c`` rows: register the
            # binding as a module alias for ``c.foo()`` style calls.
            if not entry.is_relative and entry.local_name and target:
                alias_map.setdefault(entry.local_name, target)
        if name_map:
            name_to_source[caller_file] = name_map
        if alias_map:
            alias_target[caller_file] = alias_map
    return name_to_source, alias_target


def _cache_identity(cache: ASTCache) -> tuple[str, int, int]:
    db_path = str(getattr(cache, "db_path", ""))
    if not db_path:
        return (str(id(cache)), 0, 0)
    try:
        stat = os.stat(db_path)
    except OSError:
        return (db_path, 0, 0)
    return (db_path, int(stat.st_mtime_ns), int(stat.st_size))


def build_resolver_context(cache: ASTCache) -> ResolverContext:
    """Return a loaded resolver context, reusing recent cache snapshots."""
    key = _cache_identity(cache)
    cached = _CONTEXT_CACHE.get(key)
    if cached is not None:
        _CONTEXT_CACHE.move_to_end(key)
        return cached
    built = _build_resolver_context_uncached(cache)
    _CONTEXT_CACHE[key] = built
    if len(_CONTEXT_CACHE) > _CONTEXT_CACHE_MAX:
        _CONTEXT_CACHE.popitem(last=False)
    return built


def _build_resolver_context_uncached(cache: ASTCache) -> ResolverContext:
    """One DB pass; populates every map the resolver needs."""
    conn = cache.get_conn()

    file_symbols: dict[str, list[tuple[str, str, int]]] = {}
    global_name_table: dict[str, list[tuple[str, int]]] = {}
    line_idx: dict[tuple[str, str, int], int] = {}
    try:
        sym_rows = conn.execute(
            "SELECT id, name, kind, file_path, line FROM ast_symbol_rows "
            "WHERE kind IN ('function', 'method', 'class')"
        ).fetchall()
    except Exception:  # nosec B110 — fts5/table-missing tolerance.
        sym_rows = []
    for row in sym_rows:
        sid = row["id"]
        name = row["name"]
        kind = row["kind"]
        fp = row["file_path"]
        file_symbols.setdefault(fp, []).append((name, kind, sid))
        global_name_table.setdefault(name, []).append((fp, sid))
        line_idx[(fp, name, row["line"])] = sid

    imports_by_file: dict[str, list[ImportEntry]] = {}
    try:
        imp_rows = conn.execute(
            "SELECT file_path, language, module_path, local_name, "
            "is_relative, is_star, alias_of, line FROM ast_imports"
        ).fetchall()
    except Exception:  # nosec B110
        imp_rows = []
    for r in imp_rows:
        entry = ImportEntry(
            file_path=r["file_path"],
            language=r["language"],
            module_path=r["module_path"],
            local_name=r["local_name"],
            is_relative=bool(r["is_relative"]),
            is_star=bool(r["is_star"]),
            alias_of=r["alias_of"],
            line=r["line"],
        )
        imports_by_file.setdefault(entry.file_path, []).append(entry)

    file_paths = [
        r["file_path"]
        for r in conn.execute("SELECT file_path FROM ast_index").fetchall()
    ]
    module_to_file = _build_module_to_file(file_paths)
    name_to_source, alias_target = _build_import_maps(imports_by_file, module_to_file)
    callee_resolver = _build_callee_resolver(
        file_symbols=file_symbols,
        global_name_table=global_name_table,
        name_to_source=name_to_source,
        alias_target=alias_target,
    )

    return ResolverContext(
        project_root=cache.project_root,
        cache=cache,
        file_symbols=file_symbols,
        name_to_source=name_to_source,
        global_name_table=global_name_table,
        import_alias_target=alias_target,
        imports_by_file=imports_by_file,
        builtins={"python": BUILTINS_PY},
        stdlib_modules={"python": STDLIB_NAMES_PY},
        callee_resolver=callee_resolver,
    )


def _build_callee_resolver(
    *,
    file_symbols: dict[str, list[tuple[str, str, int]]],
    global_name_table: dict[str, list[tuple[str, int]]],
    name_to_source: dict[str, dict[str, str]],
    alias_target: dict[str, dict[str, str]],
) -> CalleeResolver:
    functions_by_file: dict[str, list[dict[str, Any]]] = {}
    for file_path, symbols in file_symbols.items():
        for name, kind, sym_id in symbols:
            if kind not in ("function", "method", "class"):
                continue
            functions_by_file.setdefault(file_path, []).append(
                {
                    "name": name,
                    "kind": kind,
                    "file": file_path,
                    "id": sym_id,
                }
            )

    functions_by_name: dict[str, list[dict[str, Any]]] = {}
    for name, entries in global_name_table.items():
        for file_path, sym_id in entries:
            functions_by_name.setdefault(name, []).append(
                {
                    "name": name,
                    "file": file_path,
                    "id": sym_id,
                }
            )

    combined_sources: dict[str, dict[str, str]] = {}
    for file_path, sources in name_to_source.items():
        combined_sources.setdefault(file_path, {}).update(sources)
    for file_path, aliases in alias_target.items():
        combined_sources.setdefault(file_path, {}).update(aliases)

    return CalleeResolver(
        functions_by_name=functions_by_name,
        functions_by_file=functions_by_file,
        name_to_source=combined_sources,
    )


__all__ = ["ResolverContext", "build_resolver_context", "is_enabled"]
