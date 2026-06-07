"""Language resolver registry (RFC-0010).

A language plugs into the callee-resolution cascade by calling
:func:`register_language` from its own module under ``languages/`` — no edits to
``_context.py`` or ``__init__.py``. ``build_resolver_context`` iterates the
registry to build each language's context; ``resolve_callee`` looks up the
registered resolver by the caller file's language and falls back to the Python
cascade when none is registered (or no per-language context was built).

Contract per language:

- ``build_context(**common) -> Any | None`` — receives the common derived inputs
  (``imports_by_file``, ``file_languages``, ``file_symbols``,
  ``global_name_table``, ``file_class_methods``, ``conn``, ``line_idx``) and
  returns a per-language context, or ``None`` to opt out (e.g. no file of that
  language is indexed — zero cost for absent languages).
- ``resolve_callee(bare_name, full_name, caller_file, lang_context)
  -> (symbol_id, resolution, resolved_file)`` — the per-language resolution.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, NamedTuple

# (symbol_id, resolution, resolved_file)
ResolveResult = tuple[int | None, str, str]

BuildContextFn = Callable[..., Any | None]
ResolveCalleeFn = Callable[[str, str, str, Any], ResolveResult]


class LanguageResolver(NamedTuple):
    """One registered language's build + resolve hooks."""

    language: str
    build_context: BuildContextFn
    resolve_callee: ResolveCalleeFn


_REGISTRY: dict[str, LanguageResolver] = {}


def register_language(
    language: str,
    build_context: BuildContextFn,
    resolve_callee: ResolveCalleeFn,
) -> None:
    """Register (or replace) the resolver hooks for ``language``."""
    _REGISTRY[language] = LanguageResolver(language, build_context, resolve_callee)


def get_language_resolver(language: str | None) -> LanguageResolver | None:
    """Return the registered resolver for ``language``, or ``None``."""
    if not language:
        return None
    return _REGISTRY.get(language)


def registered_languages() -> list[str]:
    """Return the list of registered language names (registration order)."""
    return list(_REGISTRY)
