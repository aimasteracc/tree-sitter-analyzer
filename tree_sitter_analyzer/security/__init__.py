#!/usr/bin/env python3
"""
Security module for Tree-sitter Analyzer

This module provides unified security validation and protection mechanisms
for file path validation, regex pattern safety, and project boundary control.

Architecture:
- SecurityValidator: Unified validation framework
- ProjectBoundaryManager: Project access control
- RegexSafetyChecker: ReDoS attack prevention
"""

from .boundary_manager import ProjectBoundaryManager
from .regex_checker import RegexSafetyChecker
from .validator import SecurityValidator

__all__ = [
    "SecurityValidator",
    "ProjectBoundaryManager",
    "RegexSafetyChecker",
]
