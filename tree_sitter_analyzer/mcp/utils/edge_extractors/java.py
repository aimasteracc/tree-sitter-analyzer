"""Java edge extractor — extends/implements + Spring DI + Stream method refs."""

from __future__ import annotations

import re
from pathlib import Path

from .base import EdgeExtractor

# java.lang auto-imported classes — filtered from extends/implements
_JAVA_LANG_CLASSES: frozenset[str] = frozenset(
    {
        "Object", "String", "Integer", "Long", "Double", "Float",
        "Boolean", "Byte", "Short", "Character", "Number", "Void",
        "RuntimeException", "Exception", "Error", "Throwable",
        "IllegalArgumentException", "IllegalStateException",
        "NullPointerException", "UnsupportedOperationException",
        "IndexOutOfBoundsException", "ClassNotFoundException",
        "ClassCastException", "ArithmeticException",
        "Comparable", "Iterable", "AutoCloseable", "Cloneable",
        "Serializable", "Runnable", "Thread", "Class", "ClassLoader",
        "Override", "Deprecated", "SuppressWarnings",
        "FunctionalInterface", "Annotation",
        "StringBuilder", "StringBuffer", "Math", "System", "Enum",
        "List", "Map", "Set", "Collection", "ArrayList", "HashMap",
        "HashSet", "LinkedList", "Optional", "Stream", "Collectors",
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


class JavaEdgeExtractor(EdgeExtractor):
    """Java: extends/implements + Spring DI + Stream method ref edges."""

    _DI_FIELD_PATTERN = re.compile(
        r"@(?:Autowired|Inject|Resource)(?:\([^)]*\))?\s+"
        r"(?:private\s+|protected\s+|public\s+)?"
        r"(\w+)(?:<[^>]+>)?\s+\w+\s*[;=]",
        re.MULTILINE,
    )

    _METHOD_REF_PATTERN = re.compile(r"(\w+)::(\w+)")

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
        for m in re.finditer(
            r"import\s+(?:static\s+)?([\w.]+\.(\w+))\s*;", source
        ):
            import_map[m.group(2)] = m.group(1).rsplit(".", 1)[0]

        def _is_third_party(cls: str) -> bool:
            if cls in _JAVA_LANG_CLASSES:
                return True
            if cls in import_map:
                pkg = import_map[cls]
                if root_packages and not any(
                    pkg.startswith(rp) for rp in root_packages
                ):
                    return True
            return False

        # extends
        for m in re.finditer(r"\bextends\s+(\w+)", source):
            cls = m.group(1)
            if len(cls) <= 2 and cls.isupper():
                continue
            if _is_third_party(cls):
                continue
            edges.append((src_name, cls))

        # implements
        for m in re.finditer(
            r"\bimplements\s+([\w\s,<>]+?)(?:\{|$)", source
        ):
            for cls in re.split(r"[,\s]+", m.group(1)):
                cls = cls.strip()
                if not cls or not re.match(r"^[A-Z]\w*$", cls):
                    continue
                if _is_third_party(cls):
                    continue
                edges.append((src_name, cls))

        # Spring DI field edges
        for di_m in self._DI_FIELD_PATTERN.finditer(source):
            field_type = di_m.group(1)
            if not field_type[0].isupper():
                continue
            if _is_third_party(field_type):
                continue
            edges.append((src_name, field_type))

        # Stream method reference edges (Type::method)
        for ref_m in self._METHOD_REF_PATTERN.finditer(source):
            ref_type = ref_m.group(1)
            if not ref_type[0].isupper():
                continue
            if _is_third_party(ref_type):
                continue
            edges.append((src_name, ref_type))

        return edges

    def detect_root_packages(self, project_root: str) -> frozenset[str]:
        return _detect_java_root_packages(project_root)
