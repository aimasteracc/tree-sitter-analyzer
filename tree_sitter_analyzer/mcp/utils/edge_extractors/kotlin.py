"""Kotlin edge extractor — import and inheritance analysis."""
from __future__ import annotations

import re

from .base import EdgeExtractor

# Kotlin stdlib / common classes to filter
_KOTLIN_STDLIB: frozenset[str] = frozenset(
    {
        "String", "Int", "Long", "Double", "Float", "Boolean", "Byte",
        "Short", "Char", "Array", "List", "Map", "Set", "MutableList",
        "MutableMap", "MutableSet", "Collection", "Sequence", "Pair",
        "Triple", "Unit", "Nothing", "Any", "Throwable", "Exception",
        "RuntimeException", "IllegalArgumentException",
        "IllegalStateException", "NullPointerException",
        "IndexOutOfBoundsException", "ClassCastException",
        "ArithmeticException", "Comparable", "Iterable", "Iterator",
        "StringBuilder", "Regex", "Range", "IntRange", "LongRange",
    }
)

# Kotlin standard library packages
_STDLIB_PACKAGES: frozenset[str] = frozenset(
    {
        "kotlin", "kotlin.collections", "kotlin.sequences",
        "kotlin.text", "kotlin.math", "kotlin.io",
        "kotlin.coroutines", "kotlin.concurrent", "kotlin.system",
        "kotlin.reflect", "kotlin.time",
    }
)


def _is_stdlib_import(import_path: str) -> bool:
    """Check if import is from Kotlin stdlib."""
    top = import_path.split(".")[0]
    return top in _STDLIB_PACKAGES or top == "kotlinx"


class KotlinEdgeExtractor(EdgeExtractor):
    """Kotlin: extract import and inheritance edges."""

    def extract(
        self,
        source: str,
        src_name: str,
        project_root: str,
    ) -> list[tuple[str, str]]:
        edges: list[tuple[str, str]] = []

        # Build import map for package resolution
        import_map: dict[str, str] = {}
        for m in re.finditer(r"import\s+([\w.]+\.(\w+))", source):
            import_map[m.group(2)] = m.group(1).rsplit(".", 1)[0]

        # Class inheritance: class Foo : Bar()
        for m in re.finditer(
            r"(?:class|interface|object)\s+\w+(?:<[^>]*>)?\s*(?::\s*([^{=(]+))?",
            source,
        ):
            if not m.group(1):
                continue
            inheritance_part = m.group(1).strip()
            for item in re.split(r"[,\s]+", inheritance_part):
                # Remove generic args and constructor call parens
                item = re.sub(r"<[^>]*>", "", item)
                item = re.sub(r"\(\)", "", item)
                item = item.strip()
                if not item or not re.match(r"^[A-Z]\w*$", item):
                    continue
                if item in _KOTLIN_STDLIB:
                    continue
                if item in import_map and _is_stdlib_import(import_map[item]):
                    continue
                edges.append((src_name, item))

        return edges
