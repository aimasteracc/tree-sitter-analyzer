"""Java import extractor."""

from typing import Any

from ._shared import _node_text

_JAVA_STD_ROOTS: frozenset[str] = frozenset(
    {
        "java",
        "javax",
        "sun",
        "com.sun",
        "org.w3c",
        "org.xml",
        "org.ietf",
        "org.omg",
    }
)


def _strip_java_import_keywords(raw: str) -> str:
    """Strip ``import`` / ``import static`` prefix, trailing ``;`` and ``.*`` glob."""
    path = raw.rstrip(";").strip()
    if path.startswith("import static "):
        path = path[len("import static ") :]
    elif path.startswith("import "):
        path = path[len("import ") :]
    path = path.strip()
    if path.endswith(".*"):
        path = path[:-2]
    return path


def _is_java_stdlib_path(path: str) -> bool:
    """True if ``path`` is rooted at one of ``_JAVA_STD_ROOTS``."""
    root_pkg = path.split(".")[0]
    return any(root_pkg == r or path.startswith(r + ".") for r in _JAVA_STD_ROOTS)


def _extract_java_imports(
    node: Any, source: str, imports: list[dict[str, Any]]
) -> None:
    """Extract Java import declarations.

    Handles:
        import java.util.List;
        import static org.junit.Assert.*;
        import com.example.MyClass;
    """
    if getattr(node, "type", None) != "import_declaration":
        return

    raw = _node_text(node, source).strip()
    if not raw.startswith("import"):
        return

    path = _strip_java_import_keywords(raw)
    if not path:
        return
    if _is_java_stdlib_path(path):
        return

    imports.append(
        {
            "module_name": path,
            "resolved_path": path.replace(".", "/") + ".java",
            "names": [],
            "is_relative": False,
            "language": "java",
        }
    )
