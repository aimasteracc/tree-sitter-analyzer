#!/usr/bin/env python3
"""
Testing Utilities.

Regression testing and golden master management utilities.

Version: 1.10.5
Date: 2026-01-28
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .golden_master import (
        generate_diff,
        load_golden_master,
        save_golden_master,
    )
    from .normalizer import MCPOutputNormalizer
else:
    try:
        from .golden_master import (
            generate_diff,
            load_golden_master,
            save_golden_master,
        )
        from .normalizer import MCPOutputNormalizer
    except ImportError as e:
        import logging

        logging.warning(f"Import fallback triggered in testing: {e}")

__all__ = [
    "MCPOutputNormalizer",
    "load_golden_master",
    "save_golden_master",
    "generate_diff",
]
