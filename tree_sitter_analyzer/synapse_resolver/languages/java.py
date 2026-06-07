"""Java resolver registration (RFC-0010, migrated from the inline dispatch).

Wraps the existing ``_java`` machinery behind the registry contract. Behaviour is
identical to the pre-registry ``if language == "java"`` branch (asserted by the
Java byte-parity test); this module only changes HOW Java is wired in, not WHAT
it resolves.
"""

from __future__ import annotations

from typing import Any

from .._java import build_java_context, resolve_java_callee
from .._registry import register_language


def build_java_resolver_context(
    *,
    imports_by_file: dict[str, Any],
    file_languages: dict[str, str],
    file_symbols: dict[str, Any],
    global_name_table: dict[str, Any],
    file_class_methods: Any,  # zero-arg thunk -> class->method map (lazy)
    **_ignored: Any,
) -> Any | None:
    """Build the Java context, or ``None`` when no Java file is indexed.

    Zero cost for non-Java projects (gated on ``file_languages``). Java-only
    import rows are passed through, matching the previous
    ``_maybe_build_java_context`` behaviour exactly.
    """
    if not any(lang == "java" for lang in file_languages.values()):
        return None
    java_imports = {
        fp: entries
        for fp, entries in imports_by_file.items()
        if file_languages.get(fp) == "java"
    }
    fcm = file_class_methods() if callable(file_class_methods) else file_class_methods
    return build_java_context(
        imports_by_file=java_imports,
        file_symbols=file_symbols,
        file_class_methods=fcm,
        global_name_table=global_name_table,
        file_languages=file_languages,
    )


register_language("java", build_java_resolver_context, resolve_java_callee)
