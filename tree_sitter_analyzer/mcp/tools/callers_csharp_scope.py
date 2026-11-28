"""#1953: ``global using`` directives apply to every C# file of a project.

.. code-block:: csharp

    // GlobalUsings.cs
    global using IShape = Ext.IThing;

    // Square.cs
    using P;                                   // declares P.IShape
    public class Square : IShape { public int Area() => 4; }

The alias wins over the type ``using P`` imports, so ``Square`` implements
``Ext.IThing``. Name resolution of :mod:`.callers_csharp_overrides` reads the
global directives of every project C# file, and the ``<Using>`` items of the
MSBuild files (``*.csproj``, ``*.props``, ``*.targets``) next to them or above
them (the SDK turns those into global directives), as directives of each file's
compilation unit. A global directive that could not be read leaves an alias of
every name (fail closed).
"""

from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Callable
from typing import Any

from .callers_override_common import walk
from .evidence_file_cache import FILE_CACHE

#: Alias value standing for "any name": the global directives are unknown.
ANY_ALIAS = "*"
_GLOBAL = re.compile(r"^[ \t]*global[ \t]+using\b", re.MULTILINE)
_MSBUILD_SUFFIXES = (".csproj", ".props", ".targets")
_USING_ITEM = re.compile(r"<Using\b([^>]*)>", re.IGNORECASE)
_ATTRIBUTE = re.compile(r"(\w+)\s*=\s*\"([^\"]*)\"")


def csharp_files(cache: Any) -> list[str] | str:
    """The project's C# files, or why they could not be listed."""
    try:
        rows = cache.get_conn().execute(
            "SELECT file_path FROM ast_index WHERE language = 'csharp'"
        )
        return sorted(str(row[0]) for row in rows)
    except (sqlite3.Error, AttributeError):
        return "the project's C# files could not be listed"


def global_usings(
    cache: Any, project_root: str, parse_file: Callable[[str], Any]
) -> list[Any]:
    """``_Using`` entries of every global directive of the project."""
    from .callers_csharp_overrides import _Using, _usings

    files = csharp_files(cache)
    if isinstance(files, str):
        return [_Using("alias", ANY_ALIAS)]
    found: list[Any] = []
    for rel in files:
        text = FILE_CACHE.read_text(os.path.join(project_root, rel))
        if text is None:
            return [_Using("alias", ANY_ALIAS)]
        expected = len(_GLOBAL.findall(text))
        if not expected:
            continue
        parsed = parse_file(rel)
        directives = (
            []
            if parsed is None
            else [
                node
                for node in walk(parsed.root)
                if node.type == "using_directive"
                and any(c.type == "global" for c in node.children)
            ]
        )
        if len(directives) != expected or any(d.has_error for d in directives):
            return [_Using("alias", ANY_ALIAS)]
        found.extend(_usings(parsed, directives))
    msbuild = _msbuild_usings(project_root, files)
    if msbuild is None:
        return [_Using("alias", ANY_ALIAS)]
    return found + [_Using(kind, value) for kind, value in msbuild]


def _msbuild_usings(
    project_root: str, files: list[str]
) -> list[tuple[str, str]] | None:
    """``(kind, value)`` of the ``<Using>`` items in MSBuild files at or above
    the C# files' directories; None when one could not be read."""
    root = os.path.normpath(project_root)
    dirs: set[str] = set()
    for rel in files:
        current = os.path.normpath(os.path.dirname(os.path.join(root, rel)))
        while current.startswith(root) and current not in dirs:
            dirs.add(current)
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
    found: list[tuple[str, str]] = []
    for directory in sorted(dirs):
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            continue
        for name in names:
            if not name.lower().endswith(_MSBUILD_SUFFIXES):
                continue
            text = FILE_CACHE.read_text(os.path.join(directory, name))
            if text is None:
                return None
            found.extend(_items(text))
    return found


def _items(text: str) -> list[tuple[str, str]]:
    found = []
    for match in _USING_ITEM.finditer(text):
        attributes = {k.lower(): v for k, v in _ATTRIBUTE.findall(match.group(1))}
        include = attributes.get("include", "")
        if not include:
            continue  # `<Using Remove="...">` and the like
        alias = attributes.get("alias", "")
        if alias:
            found.append(("alias", alias))
        elif attributes.get("static", "").lower() == "true":
            found.append(("static", include.replace(" ", "")))
        else:
            found.append(("ns", include.replace(" ", "")))
    return found


__all__ = ["ANY_ALIAS", "csharp_files", "global_usings"]
