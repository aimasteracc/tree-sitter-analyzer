"""Java edge extractor — architecture-only (extends/implements)."""

from __future__ import annotations

import re
from pathlib import Path

from .base import EdgeExtractor

# java.lang auto-imported classes — filtered from extends/implements
_JAVA_LANG_CLASSES: frozenset[str] = frozenset(
    {
        "Object",
        "String",
        "Integer",
        "Long",
        "Double",
        "Float",
        "Boolean",
        "Byte",
        "Short",
        "Character",
        "Number",
        "Void",
        "RuntimeException",
        "Exception",
        "Error",
        "Throwable",
        "IllegalArgumentException",
        "IllegalStateException",
        "NullPointerException",
        "UnsupportedOperationException",
        "IndexOutOfBoundsException",
        "ClassNotFoundException",
        "ClassCastException",
        "ArithmeticException",
        "Comparable",
        "Iterable",
        "AutoCloseable",
        "Cloneable",
        "Serializable",
        "Runnable",
        "Thread",
        "Class",
        "ClassLoader",
        "Override",
        "Deprecated",
        "SuppressWarnings",
        "FunctionalInterface",
        "Annotation",
        "StringBuilder",
        "StringBuffer",
        "Math",
        "System",
        "Enum",
    }
)

# Cache root packages per project_root to avoid re-scanning build files
_root_cache: dict[str, frozenset[str]] = {}


def _detect_java_root_packages(project_root: str) -> frozenset[str]:
    """Read project root packages from pom.xml/build.gradle."""
    if project_root in _root_cache:
        return _root_cache[project_root]

    root_path = Path(project_root)
    roots: set[str] = set()

    for pom in root_path.rglob("pom.xml"):
        try:
            text = pom.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.search(r"<groupId>([^<]+)</groupId>", text)
        if m:
            roots.add(m.group(1).strip())

    for gf_name in ("build.gradle", "build.gradle.kts"):
        for gradle in root_path.rglob(gf_name):
            try:
                text = gradle.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            m = re.search(r"""group\s*=\s*['"]([^'"]+)['"]""", text)
            if m:
                roots.add(m.group(1).strip())

    result = frozenset(roots)
    _root_cache[project_root] = result
    return result


def _is_implements_target_keep(
    cls: str,
    import_map: dict[str, str],
    root_packages: frozenset[str],
) -> bool:
    """Decide whether ``cls`` should appear as an ``implements`` edge target.

    Returns ``False`` (drop edge) when:
    - ``cls`` is empty or not a CamelCase identifier (regex ``^[A-Z]\\w*$``)
    - ``cls`` is a short all-caps name (likely a 1-2 letter generic / type var)
    - ``cls`` is a standard ``java.lang`` class (no architectural signal)
    - ``cls`` resolves via ``import_map`` to a package OUTSIDE the project's
      ``root_packages`` (third-party interface — skip cross-project noise)

    r37e5 (dogfood): lifted from ``JavaEdgeExtractor.extract`` to flatten
    the for-implements inner block from depth 6 to 3.
    """
    if not cls or not re.match(r"^[A-Z]\w*$", cls):
        return False
    if len(cls) <= 2 and cls.isupper():
        return False
    if cls in _JAVA_LANG_CLASSES:
        return False
    if cls in import_map:
        pkg = import_map[cls]
        if root_packages and not any(pkg.startswith(rp) for rp in root_packages):
            return False
    return True


class JavaEdgeExtractor(EdgeExtractor):
    """Java: only extends/implements edges. Import map used for package resolution."""

    def extract(
        self,
        source: str,
        src_name: str,
        project_root: str,
    ) -> list[tuple[str, str]]:
        root_packages = _detect_java_root_packages(project_root)
        edges: list[tuple[str, str]] = []

        # Build import map for package resolution (no edges from imports)
        import_map: dict[str, str] = {}
        for m in re.finditer(r"import\s+(?:static\s+)?([\w.]+\.(\w+))\s*;", source):
            import_map[m.group(2)] = m.group(1).rsplit(".", 1)[0]

        # extends
        for m in re.finditer(r"\bextends\s+(\w+)", source):
            cls = m.group(1)
            if len(cls) <= 2 and cls.isupper():
                continue
            if cls in _JAVA_LANG_CLASSES:
                continue
            if cls in import_map:
                pkg = import_map[cls]
                if root_packages and not any(
                    pkg.startswith(rp) for rp in root_packages
                ):
                    continue
            edges.append((src_name, cls))

        # r37e5 (dogfood): flatten nesting 6 → 3 via _is_implements_target_keep.
        for m in re.finditer(r"\bimplements\s+([\w\s,<>]+?)(?:\{|$)", source):
            for cls in re.split(r"[,\s]+", m.group(1)):
                cls = cls.strip()
                if not _is_implements_target_keep(cls, import_map, root_packages):
                    continue
                edges.append((src_name, cls))

        return edges

    def detect_root_packages(self, project_root: str) -> frozenset[str]:
        return _detect_java_root_packages(project_root)
