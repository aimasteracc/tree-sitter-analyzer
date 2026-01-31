#!/usr/bin/env python3
"""
Security Module.

Unified security validation and protection mechanisms.

Version: 1.10.5
Date: 2026-01-28
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .boundary_manager import ProjectBoundaryManager
    from .regex_checker import RegexSafetyChecker
    from .validator import SecurityValidator
else:
    try:
        from .boundary_manager import ProjectBoundaryManager
        from .regex_checker import RegexSafetyChecker
        from .validator import SecurityValidator
    except ImportError as e:
        import logging

        logging.warning(f"Import fallback triggered in security: {e}")

__all__ = [
    "SecurityValidator",
    "ProjectBoundaryManager",
    "RegexSafetyChecker",
]
