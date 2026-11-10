"""#1937 / #1938: shared pieces of the C#, PHP and Swift override gates.

Each language module (:mod:`.callers_csharp_overrides`,
:mod:`.callers_php_overrides`, :mod:`.callers_swift_overrides`) reads the
target's declaration from source and returns a :class:`SupertypeFinding` when a
call that names no project symbol may still reach it: through a supertype
declared outside the project, through a supertype in the project (a call edge
named like it that is not bound to this declaration), or from the language /
a test framework (PHP magic methods, XCTest ``test*`` methods). The problem
code is ``OVERRIDE_DISPATCH``, as for Java and Kotlin; anything that cannot be
read or parsed leaves the check not run.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from .callers_java_overrides import (
    OVERRIDE_REASON,
    OverrideProof,
    _bound_here_or_outside,
    _describe,
)
from .callers_supertypes import SupertypeFinding

#: Types visited in one supertype closure before giving up (fail closed).
MAX_TYPES = 64


@dataclass(frozen=True)
class Parsed:
    """A parsed source file."""

    source: bytes
    root: Any

    def text(self, node: Any) -> str:
        return self.source[node.start_byte : node.end_byte].decode("utf-8", "replace")


def parse(language: str, text: str) -> Parsed | None:
    """The tree of ``text``; None when the grammar is missing or fails."""
    from ...language_loader import create_parser_safely

    try:
        parser = create_parser_safely(language)
        if parser is None:
            return None
        source = text.encode("utf-8")
        tree = parser.parse(source)
    except Exception:  # noqa: BLE001 — a grammar failure is "cannot prove"
        return None
    return Parsed(source, tree.root_node)


def walk(root: Any) -> list[Any]:
    found: list[Any] = []
    stack = [root]
    while stack:
        node = stack.pop()
        found.append(node)
        stack.extend(reversed(node.children))
    return found


def same(a: Any, b: Any) -> bool:
    return (a.type, a.start_byte, a.end_byte) == (b.type, b.start_byte, b.end_byte)


def ancestors(node: Any) -> list[Any]:
    found: list[Any] = []
    current = node.parent
    while current is not None:
        found.append(current)
        current = current.parent
    return found


def fail(detail: str) -> OverrideProof:
    return OverrideProof(False, detail)


def unchecked(rel: str, why: str) -> SupertypeFinding:
    return SupertypeFinding("", rel, 0, "", why, unchecked=True)


def finding(
    bare: str,
    rel: str,
    line: int,
    owner: str | None,
    detail: str,
    *,
    verb: str,
    lead: str,
) -> SupertypeFinding:
    return SupertypeFinding(
        bare,
        rel,
        line,
        owner or "<anonymous>",
        detail,
        verb=verb,
        reason=OVERRIDE_REASON,
        lead=lead,
    )


def class_files(
    cache: Any, language: str, name: str, *, nocase: bool = False
) -> list[str] | str:
    """Project files of ``language`` declaring a type named ``name``, or why not."""
    where = "lower(name) = lower(?)" if nocase else "name = ?"
    try:
        rows = cache.get_conn().execute(
            "SELECT DISTINCT file_path FROM ast_symbol_rows WHERE "
            + where
            + " AND kind IN ('class', 'enum') AND language = ?",
            (name, language),
        )
        return sorted(str(row[0]) for row in rows)
    except (sqlite3.Error, AttributeError):
        return "the project's types could not be read"


def dispatch_proof(
    cache: Any,
    bare: str,
    rel: str,
    line: int,
    owner: str | None,
    *,
    nocase: bool = False,
) -> OverrideProof:
    """Proved when every call edge named like ``bare`` is bound here or outside."""
    sites = _dispatch_sites(cache, bare, rel, line, owner, nocase)
    if sites is None:
        return fail("the call edges named like it could not be read")
    if sites:
        return OverrideProof(
            False,
            "call(s) named like it are not bound to this declaration and may "
            "dispatch here through a supertype: " + _describe(sites),
            tuple(sites),
        )
    return OverrideProof(True)


def _dispatch_sites(
    cache: Any, bare: str, rel: str, line: int, owner: str | None, nocase: bool
) -> list[dict[str, Any]] | None:
    """The Java gate's site check; ``nocase`` matches names case-insensitively
    (PHP method names are)."""
    match = "lower(name) = lower(?)" if nocase else "name = ?"
    callee = "lower(callee_name) = lower(?)" if nocase else "callee_name = ?"
    try:
        conn = cache.get_conn()
        same_file = int(
            conn.execute(
                "SELECT count(*) FROM ast_symbol_rows WHERE "
                + match
                + " AND file_path = ? AND kind IN ('method', 'function')",
                (bare, rel),
            ).fetchone()[0]
        )
        rows = list(
            conn.execute(
                "SELECT file_path, line, callee_resolution, callee_resolved_file, "
                "metadata FROM edges WHERE kind = 'calls' AND " + callee,
                (bare,),
            )
        )
    except (sqlite3.Error, AttributeError, TypeError):
        return None
    sites = [
        {"file": str(file), "line": int(call_line or 0)}
        for file, call_line, resolution, resolved_file, metadata in rows
        if not _bound_here_or_outside(
            str(resolution or ""),
            str(resolved_file or ""),
            metadata,
            rel,
            line,
            owner,
            same_file,
        )
    ]
    sites.sort(key=lambda site: (site["file"], site["line"]))
    return sites


__all__ = [
    "MAX_TYPES",
    "OVERRIDE_REASON",
    "OverrideProof",
    "Parsed",
    "ancestors",
    "class_files",
    "dispatch_proof",
    "fail",
    "finding",
    "parse",
    "same",
    "unchecked",
    "walk",
]
