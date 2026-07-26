"""Java package and import parsing for the Synapse resolver."""

from __future__ import annotations

import re

from ._imports import ImportEntry

_PKG_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;?\s*$")
_IMPORT_RE = re.compile(r"^\s*import\s+(static\s+)?([\w.]+)(\.\*)?\s*;?\s*$")

# Package declarations reuse the import-row schema without adding a column.
_PACKAGE_MARKER = "\x00package"


def _java_import_entry(
    *,
    file_path: str,
    module_path: str,
    local_name: str,
    is_star: bool,
    line: int,
) -> ImportEntry:
    return ImportEntry(
        file_path=file_path,
        language="java",
        module_path=module_path,
        local_name=local_name,
        is_relative=False,
        is_star=is_star,
        alias_of="",
        line=line,
    )


def _package_entry(match: re.Match[str], file_path: str, line: int) -> ImportEntry:
    return _java_import_entry(
        file_path=file_path,
        module_path=match.group(1),
        local_name=_PACKAGE_MARKER,
        is_star=False,
        line=line,
    )


def _import_entry(match: re.Match[str], file_path: str, line: int) -> ImportEntry:
    fqn = match.group(2)
    is_wildcard = bool(match.group(3))
    simple = "" if is_wildcard else fqn.rsplit(".", 1)[-1]
    return _java_import_entry(
        file_path=file_path,
        module_path=fqn,
        local_name=simple,
        is_star=is_wildcard,
        line=line,
    )


def parse_java_imports(
    text: str,
    file_path: str = "",
    line: int = 0,
) -> list[ImportEntry]:
    """Parse one Java ``import`` or ``package`` statement into cache rows."""
    stripped = text.strip()
    if not stripped:
        return []

    package_match = _PKG_RE.match(stripped)
    if package_match:
        return [_package_entry(package_match, file_path, line)]

    import_match = _IMPORT_RE.match(stripped)
    if import_match is None:
        return []
    return [_import_entry(import_match, file_path, line)]


__all__ = ["parse_java_imports"]
