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

# Pre-compiled patterns — avoid re-compiling on every call.
_POM_GROUP_PATTERN: re.Pattern[str] = re.compile(r"<groupId>([^<]+)</groupId>")
_GRADLE_GROUP_PATTERN: re.Pattern[str] = re.compile(r"""group\s*=\s*['"]([^'"]+)['"]""")
_EXTENDS_RE: re.Pattern[str] = re.compile(r"\bextends\s+(\w+)")
_IMPLEMENTS_RE: re.Pattern[str] = re.compile(r"\bimplements\s+([\w\s,<>]+?)(?:\{|$)")
_IMPORT_RE: re.Pattern[str] = re.compile(r"import\s+(?:static\s+)?([\w.]+\.(\w+))\s*;")


def _read_group_id(pattern: re.Pattern[str], text: str) -> str | None:
    """Extract a groupId/group value from text; return stripped value or None."""
    m = pattern.search(text)
    if not m:
        return None
    raw = m.group(1)
    return raw.strip()


def _any_prefix_match(pkg: str, root_packages: frozenset[str]) -> bool:
    """Return True if pkg starts with any root package prefix."""
    return any(pkg.startswith(rp) for rp in root_packages)


def _scan_pom_file(pom: Path, roots: set[str]) -> None:
    """Extract groupId from a pom.xml file and add to roots."""
    try:
        text = pom.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    gid = _read_group_id(_POM_GROUP_PATTERN, text)
    if gid:
        roots.add(gid)


def _scan_gradle_file(gradle: Path, roots: set[str]) -> None:
    """Extract group from a build.gradle / build.gradle.kts file and add to roots."""
    try:
        text = gradle.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    gid = _read_group_id(_GRADLE_GROUP_PATTERN, text)
    if gid:
        roots.add(gid)


def _detect_java_root_packages(project_root: str) -> frozenset[str]:
    """Read project root packages from pom.xml/build.gradle."""
    if project_root in _root_cache:
        return _root_cache[project_root]
    root_path = Path(project_root)
    roots: set[str] = set()
    for pom in root_path.rglob("pom.xml"):
        _scan_pom_file(pom, roots)
    for gf_name in ("build.gradle", "build.gradle.kts"):
        for gradle in root_path.rglob(gf_name):
            _scan_gradle_file(gradle, roots)
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
    r38a: uses ``_any_prefix_match`` to eliminate inline generator depth.
    """
    if not cls or not re.match(r"^[A-Z]\w*$", cls):
        return False
    if len(cls) <= 2 and cls.isupper():
        return False
    if cls in _JAVA_LANG_CLASSES:
        return False
    if cls in import_map:
        pkg = import_map[cls]
        if root_packages and not _any_prefix_match(pkg, root_packages):
            return False
    return True


def _is_extends_target_keep(
    cls: str,
    import_map: dict[str, str],
    root_packages: frozenset[str],
) -> bool:
    """Decide whether ``cls`` should appear as an ``extends`` edge target.

    Mirrors ``_is_implements_target_keep`` but omits the CamelCase check
    (extends targets are always a single class name, not a list of interfaces).

    r38a: extracted from ``JavaEdgeExtractor.extract`` extends loop to flatten
    the nested if/any structure and eliminate depth-16 nodes.
    """
    if len(cls) <= 2 and cls.isupper():
        return False
    if cls in _JAVA_LANG_CLASSES:
        return False
    if cls in import_map:
        pkg = import_map[cls]
        if root_packages and not _any_prefix_match(pkg, root_packages):
            return False
    return True


def _build_import_map(source: str) -> dict[str, str]:
    """Build class-name → package map from Java import statements."""
    result: dict[str, str] = {}
    for m in _IMPORT_RE.finditer(source):
        cls_name = m.group(2)
        full_pkg = m.group(1)
        result[cls_name] = full_pkg.rsplit(".", 1)[0]
    return result


def _scan_extends_edges(
    source: str,
    src_name: str,
    import_map: dict[str, str],
    root_packages: frozenset[str],
) -> list[tuple[str, str]]:
    """Return (src_name, cls) pairs for every ``extends`` relationship in source."""
    edges: list[tuple[str, str]] = []
    for m in _EXTENDS_RE.finditer(source):
        cls = m.group(1)
        if _is_extends_target_keep(cls, import_map, root_packages):
            _edge = (src_name, cls)
            edges.append(_edge)
    return edges


def _scan_implements_edges(
    source: str,
    src_name: str,
    import_map: dict[str, str],
    root_packages: frozenset[str],
) -> list[tuple[str, str]]:
    """Return (src_name, cls) pairs for every ``implements`` relationship in source."""
    edges: list[tuple[str, str]] = []
    for m in _IMPLEMENTS_RE.finditer(source):
        group1 = m.group(1)
        raw = re.split(r"[,\s]+", group1)
        for cls in raw:
            if not cls:
                continue
            if not _is_implements_target_keep(cls, import_map, root_packages):
                continue
            _edge = (src_name, cls)
            edges.append(_edge)
    return edges


class JavaEdgeExtractor(EdgeExtractor):
    """Java: only extends/implements edges. Import map used for package resolution."""

    def extract(
        self,
        source: str,
        src_name: str,
        project_root: str,
    ) -> list[tuple[str, str]]:
        root_packages = _detect_java_root_packages(project_root)
        import_map = _build_import_map(source)
        extends_edges = _scan_extends_edges(source, src_name, import_map, root_packages)
        impl_edges = _scan_implements_edges(source, src_name, import_map, root_packages)
        return extends_edges + impl_edges

    def detect_root_packages(self, project_root: str) -> frozenset[str]:
        return _detect_java_root_packages(project_root)
