"""Import extraction functions for Python, JS/TS, Go, Rust, C/C++, Java, C#, Kotlin, Swift, Ruby, PHP.

Public API — all symbols importable from ``tree_sitter_analyzer.import_extractors``:

    from tree_sitter_analyzer.import_extractors import walk_imports
    from tree_sitter_analyzer.import_extractors import extract_python_import_simple
    from tree_sitter_analyzer.import_extractors import _node_text
    # ... etc.
"""

from types import MappingProxyType
from typing import Any

from ._cpp import (
    _cpp_import_entry,
    _extract_cpp_imports,
)
from ._go import (
    _collect_go_specs,
    _extract_go_imports,
    _parse_go_spec,
)
from ._java import (
    _extract_java_imports,
    _is_java_stdlib_path,
    _strip_java_import_keywords,
)
from ._javascript import (
    _collect_require_call_imports,
    _extract_js_imports,
    _js_import_module_path,
    extract_js_imports,
)
from ._other_langs import (
    _csharp_qualified_name_parts,
    _extract_csharp_imports,
    _extract_kotlin_imports,
    _extract_php_imports,
    _extract_ruby_imports,
    _extract_swift_imports,
    _ruby_call_function_name,
    _ruby_call_string_arg,
)
from ._python import (
    _collect_aliased_import_names,
    _emit_python_from_import,
    _emit_relative_submodule_imports,
    _extract_import_names,
    _extract_python_imports,
    _parse_python_from_children,
    _parse_relative_import,
    extract_python_import_from,
    extract_python_import_simple,
)
from ._rust import (
    _extract_rust_imports,
    _parse_rust_use_path,
)
from ._shared import _node_text

__all__ = [
    "SUPPORTED_LANGUAGES",
    "walk_imports",
    "_node_text",
    # Python
    "extract_python_import_simple",
    "extract_python_import_from",
    "_extract_python_imports",
    "_parse_python_from_children",
    "_parse_relative_import",
    "_emit_relative_submodule_imports",
    "_emit_python_from_import",
    "_extract_import_names",
    "_collect_aliased_import_names",
    # JavaScript
    "extract_js_imports",
    "_extract_js_imports",
    "_js_import_module_path",
    "_collect_require_call_imports",
    # Go
    "_extract_go_imports",
    "_parse_go_spec",
    "_collect_go_specs",
    # Rust
    "_extract_rust_imports",
    "_parse_rust_use_path",
    # C/C++
    "_extract_cpp_imports",
    "_cpp_import_entry",
    # Java
    "_extract_java_imports",
    "_strip_java_import_keywords",
    "_is_java_stdlib_path",
    # C#, Kotlin, Swift, Ruby, PHP
    "_extract_csharp_imports",
    "_csharp_qualified_name_parts",
    "_extract_kotlin_imports",
    "_extract_swift_imports",
    "_extract_ruby_imports",
    "_ruby_call_function_name",
    "_ruby_call_string_arg",
    "_extract_php_imports",
]


# Canonical import dispatch. Inventory and execution derive from this single
# registry, so support claims cannot drift from ``walk_imports`` behavior.
IMPORT_DISPATCH = MappingProxyType(
    {
        "c": _extract_cpp_imports,
        "cpp": _extract_cpp_imports,
        "csharp": _extract_csharp_imports,
        "go": _extract_go_imports,
        "java": _extract_java_imports,
        "javascript": _extract_js_imports,
        "kotlin": _extract_kotlin_imports,
        "php": _extract_php_imports,
        "python": _extract_python_imports,
        "ruby": _extract_ruby_imports,
        "rust": _extract_rust_imports,
        "swift": _extract_swift_imports,
        "typescript": _extract_js_imports,
    }
)
IMPORT_LANGUAGE_ALIASES = {"c_sharp": "csharp", "cs": "csharp"}
SUPPORTED_LANGUAGES = frozenset(IMPORT_DISPATCH)


def _extract_imports_for_language(
    node: Any, source: str, language: str, imports: list[dict[str, Any]]
) -> None:
    """Dispatch one node through the canonical language extractor registry."""
    extractor = IMPORT_DISPATCH.get(language)
    if extractor is not None:
        extractor(node, source, imports)


def walk_imports(
    node: Any, source: str, language: str, imports: list[dict[str, Any]]
) -> None:
    """Walk the AST to collect import statements."""
    canonical_language = IMPORT_LANGUAGE_ALIASES.get(language, language)
    try:
        _extract_imports_for_language(node, source, canonical_language, imports)
    except Exception:  # nosec B110
        pass

    children = getattr(node, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            walk_imports(child, source, canonical_language, imports)
