#!/usr/bin/env python3
"""
Platform Compatibility.

Platform detection and compatibility utilities.

Version: 1.10.5
Date: 2026-01-28
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .detector import PlatformDetector, PlatformInfo
else:
    try:
        from .detector import PlatformDetector, PlatformInfo
    except ImportError as e:
        import logging

        logging.warning(f"Import fallback triggered in platform_compat: {e}")

__all__ = ["PlatformDetector", "PlatformInfo"]
