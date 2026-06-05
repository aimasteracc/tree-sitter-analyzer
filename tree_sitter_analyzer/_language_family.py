"""Language-family equivalence + lightweight path→language for resolution gates.

The cross-language callee gates (synapse resolver, unresolved-ref candidate
scoring, the global bare-name fallback, and the nav body inliner) must block a
*known* language mismatch (Python → JavaScript/Swift) without rejecting
legitimate same-family resolution. JavaScript and TypeScript are one interop
family — gradual-migration projects freely cross-import ``.js``/``.ts``/
``.jsx``/``.tsx`` — and ``CrossFileResolver._register_module_path`` already
treats them as one import family, so the gates do too (Codex P2 #301).

For C/C++/Objective-C, compatibility is **directional**: a C++ or Objective-C++
caller may resolve symbols defined in C headers (indexed as ``c``), because
``.h`` files are typically indexed as ``c`` even when included from ``.cpp``
translation units. The reverse — a pure-C caller resolving a ``.cpp`` function
— is a foreign binding and should remain blocked (Codex P2 #302).
"""

from __future__ import annotations

import os

#: Groups of dialects that may legitimately resolve across each other
#: in *both* directions. JS/TS projects freely cross-import .js/.ts/.jsx/.tsx
#: files, so the symmetric set is correct here.
_LANGUAGE_FAMILIES: tuple[frozenset[str], ...] = (
    frozenset({"javascript", "typescript", "jsx", "tsx"}),
)

#: Back-compat alias (some imports referenced the JS/TS set directly).
_JS_TS_FAMILY = _LANGUAGE_FAMILIES[0]

#: Directed C-family compat: (caller_lang, callee_lang) pairs that are
#: compatible in ONE direction only. A .cpp caller resolving a .h (indexed
#: as ``c``) is the canonical case; the reverse is a foreign binding.
#:
#: Rules:
#:   cpp → c      : C++ including a C header (common .h pattern)
#:   objc → c     : Objective-C is a superset of C; plain C calls are valid
#:   objcpp → *   : Objective-C++ is a superset of both; all C-family targets ok
_DIRECTED_C_COMPAT: frozenset[tuple[str, str]] = frozenset(
    {
        ("cpp", "c"),
        ("objc", "c"),
        ("objcpp", "c"),
        ("objcpp", "cpp"),
        ("objcpp", "objc"),
    }
)


def languages_compatible(caller: str, callee: str) -> bool:
    """True when *caller* may legitimately resolve a symbol defined in *callee*.

    Empty/unknown tags are treated as compatible (the gate only blocks on a
    *known* mismatch). Identical tags are always compatible. JS/TS dialects are
    a symmetric family. C/C++/ObjC resolution is directional: C++ callers may
    resolve C headers, but pure-C callers must not bind to C++ definitions
    (Codex P2 #302).
    """
    if not caller or not callee or caller == callee:
        return True
    # Symmetric families (JS/TS)
    if any(caller in family and callee in family for family in _LANGUAGE_FAMILIES):
        return True
    # Directed C-family
    return (caller, callee) in _DIRECTED_C_COMPAT


def language_from_path(path: str) -> str:
    """Best-effort language from a file extension; ``""`` when unknown.

    A pure extension lookup (no file stat) so the resolution gates can derive a
    caller file's language even when it has no indexed function symbols — module
    -level calls in a function-less file must still be gated (Codex P2 #301).
    """
    if not path:
        return ""
    from .language_detector import LanguageDetector

    _, ext = os.path.splitext(path)
    return LanguageDetector.EXTENSION_MAPPING.get(ext.lower(), "")
