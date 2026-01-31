#!/usr/bin/env python3
"""
Tree-sitter Analyzer Package Main Entry Point.

Allows the package to be executed with `python -m tree_sitter_analyzer`.

Version: 1.10.5
Date: 2026-01-28
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cli_main import main
else:
    try:
        from .cli_main import main
    except ImportError as e:
        import logging

        logging.warning(f"Import fallback triggered in __main__: {e}")
        raise

if __name__ == "__main__":
    main()
