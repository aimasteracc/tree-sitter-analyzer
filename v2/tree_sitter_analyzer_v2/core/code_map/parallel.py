"""
Parallel file parsing infrastructure — thread-safe parser management.

Extracted from __init__.py to follow SRP (Fowler P0 #1).
Provides thread-local parser instances for safe concurrent parsing.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.core.code_map.decorators import extract_decorated_entries
from tree_sitter_analyzer_v2.core.code_map.types import ModuleInfo

logger = logging.getLogger(__name__)

_thread_local = threading.local()


def get_thread_parsers() -> dict[str, Any]:
    """Get or create parser instances for the current thread.

    Uses ParserRegistry to resolve parsers (DIP compliant).
    Each thread gets its own parser instances for thread safety.
    """
    if not hasattr(_thread_local, "parsers"):
        from tree_sitter_analyzer_v2.core.parser_registry import get_all_parsers
        # Create new instances for this thread by getting classes from registry
        # and instantiating fresh copies for thread safety
        registry_parsers = get_all_parsers()
        thread_parsers: dict[str, Any] = {}
        for lang, parser in registry_parsers.items():
            try:
                thread_parsers[lang] = type(parser)()
            except TypeError:
                # GenericLanguageParser requires profile argument for construction
                if hasattr(parser, "_profile"):
                    try:
                        thread_parsers[lang] = type(parser)(parser._profile)
                    except Exception as e:
                        logger.warning("Skipping language %s in thread: %s", lang, e)
                else:
                    logger.warning("Skipping language %s in thread: cannot clone parser", lang)
            except Exception as e:
                logger.warning("Skipping language %s in thread: %s", lang, e)
        _thread_local.parsers = thread_parsers
    return _thread_local.parsers


def parse_file_standalone(
    root_str: str,
    file_path_str: str,
    rel_path: str,
    ext_lang_map: dict[str, str],
) -> ModuleInfo | None:
    """Thread-safe file parser — creates per-thread parser instances.

    Designed for use with ThreadPoolExecutor. Each thread gets its own
    parser instances via thread-local storage to avoid shared state.
    """
    try:
        file_path = Path(file_path_str)
        content = file_path.read_text(encoding="utf-8", errors="replace")

        language = ext_lang_map.get(file_path.suffix.lower())
        if not language:
            return None

        parsers = get_thread_parsers()
        parser = parsers.get(language)
        if not parser:
            return None

        parsed = parser.parse(content, file_path_str)
        lines = len(content.splitlines())
        functions = parsed.get("functions", [])
        classes = parsed.get("classes", [])

        # Extract call sites from AST (shared implementation in call_index)
        from tree_sitter_analyzer_v2.core.code_map.call_index import extract_call_sites
        call_sites = extract_call_sites(
            parsed.get("ast"), language, functions, classes
        )

        # Extract decorated entries (shared implementation)
        decorated_entries = extract_decorated_entries(functions, classes)

        return ModuleInfo(
            path=rel_path,
            language=language,
            lines=lines,
            classes=classes,
            functions=functions,
            imports=parsed.get("imports", []),
            call_sites=call_sites,
            decorated_entries=decorated_entries,
        )
    except Exception as e:
        logger.warning("Failed to parse %s: %s", file_path_str, e)
        return None
