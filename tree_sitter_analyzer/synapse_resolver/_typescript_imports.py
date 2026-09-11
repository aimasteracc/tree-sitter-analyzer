"""TypeScript/JavaScript ES-module import parsing.

Produces ``ImportEntry`` rows so TS/JS files get ``module:`` import edges,
which is what Pulse's ``imported_by`` context reads. Only static ES-module
``import`` declarations are parsed; ``require()`` and re-exports are out of
scope because they need call-expression and export-graph handling
respectively.

The specifier is recorded verbatim. ``is_relative`` is True only for ``./``
and ``../`` specifiers — the forms that can name a project file. Bare
specifiers (``react``, ``@scope/pkg``, ``node:fs``) are recorded but left
non-relative so module->file resolution never mistakes a package for a
project file.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Iterable

from ._imports import ImportEntry

#: Checked in order, so a source file beside the consumer wins over a
#: directory barrel, and TypeScript wins over emitted JavaScript.
_TS_RESOLUTION_SUFFIXES = (
    "",
    ".ts",
    ".tsx",
    ".mts",
    ".cts",
    ".d.ts",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    "/index.ts",
    "/index.tsx",
    "/index.mts",
    "/index.cts",
    "/index.js",
    "/index.jsx",
)

#: ``import <clause> from '<specifier>'`` — the clause is optional so a
#: side-effect-only ``import './x'`` also matches.
_TS_IMPORT_RE = re.compile(
    r"^import\s+(?:type\s+)?(?:(?P<clause>.+?)\s+from\s+)?"
    r"(?P<quote>['\"])(?P<specifier>[^'\"]+)(?P=quote)\s*;?\s*$",
    re.DOTALL,
)

#: ``{ a, b as c }`` inside an import clause.
_TS_NAMED_BLOCK_RE = re.compile(r"\{(?P<names>[^}]*)\}", re.DOTALL)

#: ``* as ns``
_TS_NAMESPACE_RE = re.compile(r"^\*\s+as\s+(?P<local>[\w$]+)$")

_STRIP_LINE_COMMENTS_RE = re.compile(r"//[^\n]*")


def _strip_line_comments(text: str) -> str:
    return _STRIP_LINE_COMMENTS_RE.sub("", text)


def _split_named_bindings(names: str) -> list[tuple[str, str]]:
    """Return ``(local_name, alias_of)`` for each name in a ``{...}`` block."""
    out: list[tuple[str, str]] = []
    for raw in names.split(","):
        item = raw.strip()
        if item.startswith("type "):
            item = item[len("type ") :].strip()
        if not item:
            continue
        if " as " in item:
            orig, alias = item.split(" as ", 1)
            out.append((alias.strip(), orig.strip()))
        else:
            out.append((item, ""))
    return out


def _is_relative(specifier: str) -> bool:
    return specifier.startswith("./") or specifier.startswith("../")


def resolve_typescript_specifier(
    specifier: str, importer_file: str, indexed_files: Iterable[str]
) -> str:
    """Resolve a relative TS/JS specifier to an indexed project file.

    Returns ``""`` when the specifier is not relative, names nothing indexed,
    or escapes the repository root. Bare package specifiers never resolve —
    binding ``react`` to a project ``react.ts`` would be a false edge.
    """
    if not specifier or not _is_relative(specifier):
        return ""
    importer_dir = posixpath.dirname(importer_file.replace("\\", "/"))
    base = posixpath.normpath(posixpath.join(importer_dir, specifier))
    # normpath collapses '..' but leaves a leading '..' when the specifier
    # climbs above the root; such a path can never name an indexed file.
    if base == ".." or base.startswith("../"):
        return ""
    if base == ".":
        return ""
    known = (
        indexed_files
        if isinstance(indexed_files, (set, frozenset))
        else set(indexed_files)
    )
    for suffix in _TS_RESOLUTION_SUFFIXES:
        candidate = f"{base}{suffix}"
        if candidate in known:
            return candidate
    return ""


def parse_typescript_imports(
    text: str, language: str, file_path: str = "", line: int = 0
) -> list[ImportEntry]:
    """Parse one TS/JS import declaration into one row per bound name."""
    cleaned = _strip_line_comments(text).strip()
    if not cleaned:
        return []
    match = _TS_IMPORT_RE.match(cleaned)
    if not match:
        return []

    specifier = match.group("specifier")
    relative = _is_relative(specifier)

    def row(
        local_name: str, *, is_star: bool = False, alias_of: str = ""
    ) -> ImportEntry:
        return ImportEntry(
            file_path=file_path,
            language=language,
            module_path=specifier,
            local_name=local_name,
            is_relative=relative,
            is_star=is_star,
            alias_of=alias_of,
            line=line,
        )

    clause = (match.group("clause") or "").strip()
    if not clause:
        # Side-effect-only import: the edge exists, nothing is bound.
        return [row("")]

    namespace = _TS_NAMESPACE_RE.match(clause)
    if namespace:
        return [row(namespace.group("local"), is_star=True)]

    rows: list[ImportEntry] = []
    named_block = _TS_NAMED_BLOCK_RE.search(clause)
    # A default binding is whatever precedes the named block (or the whole
    # clause when there is no block): ``parser, { parse }`` -> ``parser``.
    head = clause[: named_block.start()] if named_block else clause
    default_name = head.replace(",", " ").strip()
    if default_name and not default_name.startswith("*"):
        rows.append(row(default_name))
    if named_block:
        for local_name, alias_of in _split_named_bindings(named_block.group("names")):
            rows.append(row(local_name, alias_of=alias_of))
    return rows
