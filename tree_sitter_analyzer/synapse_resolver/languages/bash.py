"""Bash resolver registration (RFC-0010).

A SAFE, deliberately minimal callee resolver for Bash/shell scripts. Its ONLY
job is to claim the ``bash`` language slot in the registry so that the Python
cascade CANNOT mis-classify Bash command names (``print``, ``list``, ``map``,
``type``, etc.) as Python builtins or stdlib symbols.

Design decisions:
- ``resolve_bash_callee`` always returns ``(None, "unknown", "")`` — Bash call
  targets cannot be statically resolved without full shell expansion semantics,
  and guessing would introduce cross-language false-positives (the moat).
- ``build_bash_resolver_context`` returns ``None`` when no Bash file is present
  (zero cost for non-shell projects) and a ``BashResolverContext`` otherwise.
- No stdlib tier, no local-symbol lookup, no import tracking.

THE MOAT: by registering ``bash``, the language-dispatch in the outer resolve
loop will call ``resolve_bash_callee`` instead of falling through to the Python
cascade for ``.sh`` caller files. This prevents a Bash ``print`` or ``list``
call from ever being classified as a Python builtin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .._registry import register_language


@dataclass
class BashResolverContext:
    """Per-index Bash resolution context (built once per pass).

    Currently empty: Bash resolution is always ``unknown``. The class exists
    so that ``build_bash_resolver_context`` can return a typed non-``None``
    sentinel and the registry contract (``Any | None``) is satisfied.
    """


def build_bash_resolver_context(
    *,
    imports_by_file: dict[str, Any],
    file_languages: dict[str, str],
    file_symbols: dict[str, Any],
    global_name_table: dict[str, Any],
    file_class_methods: Any,  # zero-arg thunk -> class->method map (lazy; unused)
    **_ignored: Any,
) -> BashResolverContext | None:
    """Build the Bash context, or ``None`` when no Bash file is indexed.

    Zero cost for non-shell projects (gated on ``file_languages``). When at
    least one ``.sh``/Bash file is present the returned context acts as a
    sentinel: the registry dispatches to ``resolve_bash_callee`` instead of the
    Python cascade, preventing false-positive builtin/stdlib classifications.
    """
    if not any(lang == "bash" for lang in file_languages.values()):
        return None
    return BashResolverContext()


def resolve_bash_callee(
    callee_name: str,
    callee_full: str,
    caller_file: str,
    ctx: BashResolverContext,
) -> tuple[int | None, str, str]:
    """Resolve a Bash call edge — always returns ``unknown``.

    Bash command targets (builtins, aliases, functions, external programs)
    cannot be statically resolved without full shell-expansion semantics. This
    resolver claims the language slot to prevent cross-language mis-binding and
    conservatively returns ``unknown`` for every call.

    Returns ``(symbol_id, resolution, resolved_file)``.
    """
    return (None, "unknown", "")


register_language("bash", build_bash_resolver_context, resolve_bash_callee)


__all__ = [
    "BashResolverContext",
    "build_bash_resolver_context",
    "resolve_bash_callee",
]
