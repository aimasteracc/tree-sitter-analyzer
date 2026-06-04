"""Language-family equivalence + lightweight path→language for resolution gates.

The cross-language callee gates (synapse resolver, unresolved-ref candidate
scoring, the global bare-name fallback, and the nav body inliner) must block a
*known* language mismatch (Python → JavaScript/Swift) without rejecting
legitimate same-family resolution. JavaScript and TypeScript are one interop
family — gradual-migration projects freely cross-import ``.js``/``.ts``/
``.jsx``/``.tsx`` — and ``CrossFileResolver._register_module_path`` already
treats them as one import family, so the gates do too (Codex P2 #301).
"""

from __future__ import annotations

import os

#: Dialects that may legitimately resolve across each other.
_JS_TS_FAMILY = frozenset({"javascript", "typescript", "jsx", "tsx"})


def languages_compatible(a: str, b: str) -> bool:
    """True when two language tags may legitimately resolve across each other.

    Empty/unknown tags are treated as compatible (the gate only blocks on a
    *known* mismatch), identical tags are compatible, and the JS/TS dialects
    form one family.
    """
    if not a or not b or a == b:
        return True
    return a in _JS_TS_FAMILY and b in _JS_TS_FAMILY


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
