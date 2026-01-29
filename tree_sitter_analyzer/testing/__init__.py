#!/usr/bin/env python3
"""
Testing Utilities Package

This package provides utilities for regression testing and golden master management
for the tree-sitter-analyzer project.
"""

from .golden_master import (
    generate_diff,
    load_golden_master,
    save_golden_master,
)
from .normalizer import MCPOutputNormalizer

__all__ = [
    "MCPOutputNormalizer",
    "load_golden_master",
    "save_golden_master",
    "generate_diff",
]
