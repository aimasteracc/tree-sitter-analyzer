"""Per-language corpus data for grammar coverage auto-discovery.

Each sub-module exposes:
  CORPUS: str          — UTF-8 source code covering the language's major syntax constructs
  CORPUS_EXTRA: list[bytes]  — (optional) byte-level snippets for non-UTF-8 / legacy syntax

This package assembles them into the flat dicts expected by discovery_corpus.
"""

from . import (
    c,
    cpp,
    csharp,
    go,
    java,
    javascript,
    kotlin,
    php,
    python,
    ruby,
    rust,
    sql,
    typescript,
    yaml,
)

# Ordered mapping: language name → corpus string
BUILTIN_CORPUS: dict[str, str] = {
    "python": python.CORPUS,
    "javascript": javascript.CORPUS,
    "typescript": typescript.CORPUS,
    "java": java.CORPUS,
    "go": go.CORPUS,
    "rust": rust.CORPUS,
    "c": c.CORPUS,
    "cpp": cpp.CORPUS,
    "csharp": csharp.CORPUS,
    "ruby": ruby.CORPUS,
    "php": php.CORPUS,
    "kotlin": kotlin.CORPUS,
    "yaml": yaml.CORPUS,
    "sql": sql.CORPUS,
}

# Byte-level extra snippets (only for languages that need them)
BUILTIN_CORPUS_EXTRA: dict[str, list[bytes]] = {
    lang: mod.CORPUS_EXTRA
    for lang, mod in [("python", python)]
    if hasattr(mod, "CORPUS_EXTRA")
}

__all__ = ["BUILTIN_CORPUS", "BUILTIN_CORPUS_EXTRA"]
