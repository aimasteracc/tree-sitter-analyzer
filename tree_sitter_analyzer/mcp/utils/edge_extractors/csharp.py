"""C# edge extractor — using directives, inheritance, and interface implementation."""
from __future__ import annotations

import re

from .base import EdgeExtractor

# System namespace classes — filtered from edges
_SYSTEM_NAMESPACES: frozenset[str] = frozenset(
    {
        "System", "System.Collections", "System.Collections.Generic",
        "System.IO", "System.Linq", "System.Net", "System.Net.Http",
        "System.Text", "System.Threading", "System.Threading.Tasks",
        "System.Json", "System.Xml", "System.Data",
    }
)


def _is_system_type(type_name: str, using_namespaces: set[str]) -> bool:
    """Check if a type reference is from System namespaces."""
    if "." in type_name:
        prefix = type_name.rsplit(".", 1)[0]
        return prefix in _SYSTEM_NAMESPACES or prefix.startswith("System.")
    for ns in using_namespaces:
        if ns in _SYSTEM_NAMESPACES:
            continue
    return False


class CSharpEdgeExtractor(EdgeExtractor):
    """C#: extract using-based references and inheritance edges."""

    def extract(
        self,
        source: str,
        src_name: str,
        project_root: str,
    ) -> list[tuple[str, str]]:
        edges: list[tuple[str, str]] = []

        # Collect using directives for context
        using_namespaces: set[str] = set()
        for m in re.finditer(r"using\s+([\w.]+)\s*;", source):
            using_namespaces.add(m.group(1))

        # Build alias map: using SomeType = Full.Namespace.Type;
        type_aliases: dict[str, str] = {}
        for m in re.finditer(r"using\s+(\w+)\s*=\s*([\w.]+)\s*;", source):
            type_aliases[m.group(1)] = m.group(2)

        # Inheritance: class Foo : Bar, IBaz, IQux
        # Also handles record Foo(string x) : Base
        for m in re.finditer(
            r"(?:class|record|struct)\s+\w+(?:<[^>]*>)?(?:\([^)]*\))?\s*:\s*([^{]+)",
            source,
        ):
            inheritance_part = m.group(1).strip()
            # Remove constraints: where T : ISomething
            inheritance_part = re.sub(r"\bwhere\s+\w+\s*:\s*[\w.,\s]+", "", inheritance_part)
            for item in re.split(r"[,\s]+", inheritance_part):
                item = item.strip()
                if not item or not re.match(r"^[A-Z]\w*$", item):
                    continue
                if item in type_aliases:
                    full = type_aliases[item]
                    if any(ns in _SYSTEM_NAMESPACES for ns in _SYSTEM_NAMESPACES if full.startswith(ns)):
                        continue
                if _is_system_type(item, using_namespaces):
                    continue
                edges.append((src_name, item))

        # Interface: interface IFoo : IBar, IBaz
        for m in re.finditer(
            r"interface\s+(\w+)(?:<[^>]*>)?\s*:\s*([^{]+)",
            source,
        ):
            inheritance_part = m.group(2).strip()
            for item in re.split(r"[,\s]+", inheritance_part):
                item = item.strip()
                if item and re.match(r"^[A-Z]\w*$", item) and not _is_system_type(item, using_namespaces):
                    edges.append((src_name, item))

        return edges
