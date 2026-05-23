"""Import-statement parsing for the Synapse resolver.

Produces structured ``ImportEntry`` rows (one per bound name) that land
in the ``ast_imports`` table. Phase 3a supports Python only; other
languages return an empty list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PY_FROM_IMPORT_RE = re.compile(
    r"^from\s+(\.*)([\w.]*)\s+import\s+(.+)$", re.MULTILINE | re.DOTALL
)
_PY_IMPORT_RE = re.compile(r"^import\s+([\w.,\s]+)$", re.MULTILINE | re.DOTALL)


@dataclass(frozen=True)
class ImportEntry:
    """One row in ``ast_imports`` — a single imported name binding."""

    file_path: str
    language: str
    module_path: str
    local_name: str = ""
    is_relative: bool = False
    is_star: bool = False
    alias_of: str = ""
    line: int = 0


def _split_names_clause(clause: str) -> list[tuple[str, str]]:
    """Parse ``"a, b as c, *"`` into ``[(local_name, alias_of), ...]``."""
    clause = clause.strip()
    if clause.startswith("("):
        clause = clause.lstrip("(")
    if clause.endswith(")"):
        clause = clause.rstrip(")")
    out: list[tuple[str, str]] = []
    for raw in clause.split(","):
        item = raw.strip()
        if not item:
            continue
        if " as " in item:
            orig, alias = item.split(" as ", 1)
            out.append((alias.strip(), orig.strip()))
        else:
            out.append((item, ""))
    return out


def parse_imports(
    text: str, language: str, file_path: str = "", line: int = 0
) -> list[ImportEntry]:
    """Parse one import statement into structured rows.

    ``from .b import x, y`` -> 2 rows with module_path='.b' (relative).
    ``from . import b as bb`` -> 1 row with local_name='bb', alias_of='b'.
    ``from M import *`` -> 1 row with is_star=True, local_name=''.
    ``import a.b as c`` -> 1 row with module_path='a.b', local_name='c'.
    Non-python languages: empty (Phase 3a focuses on Python).
    """
    if language != "python":
        return []
    text = text.strip()
    if not text:
        return []

    m_from = _PY_FROM_IMPORT_RE.match(text)
    if m_from:
        dots = m_from.group(1) or ""
        module_tail = m_from.group(2) or ""
        names_clause = (m_from.group(3) or "").split("#", 1)[0]
        module_path = dots + module_tail
        is_relative = bool(dots)
        entries: list[ImportEntry] = []
        for local_name, alias_of in _split_names_clause(names_clause):
            if local_name == "*":
                entries.append(
                    ImportEntry(
                        file_path=file_path,
                        language=language,
                        module_path=module_path,
                        local_name="",
                        is_relative=is_relative,
                        is_star=True,
                        alias_of="",
                        line=line,
                    )
                )
            else:
                entries.append(
                    ImportEntry(
                        file_path=file_path,
                        language=language,
                        module_path=module_path,
                        local_name=local_name,
                        is_relative=is_relative,
                        is_star=False,
                        alias_of=alias_of,
                        line=line,
                    )
                )
        return entries

    m_imp = _PY_IMPORT_RE.match(text)
    if m_imp:
        body = m_imp.group(1).split("#", 1)[0]
        entries = []
        for item, alias_of in _split_names_clause(body):
            if alias_of:
                # ``import a.b as c`` — module_path = "a.b", local_name = "c"
                module_path = alias_of
                local_name = item
                stored_alias = alias_of
            else:
                module_path = item
                local_name = item.split(".")[0]
                stored_alias = ""
            entries.append(
                ImportEntry(
                    file_path=file_path,
                    language=language,
                    module_path=module_path,
                    local_name=local_name,
                    is_relative=False,
                    is_star=False,
                    alias_of=stored_alias,
                    line=line,
                )
            )
        return entries

    return []


__all__ = ["ImportEntry", "parse_imports"]
