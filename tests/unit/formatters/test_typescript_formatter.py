#!/usr/bin/env python3
"""
Tests for TypeScript table formatter.

Re-exports all tests from focused sub-modules:
- test_typescript_formatter_core: Core formatting, modifiers, method visibility
- test_typescript_formatter_modes: Compact/CSV modes, signatures, format delegation, JSON
"""

from tests.unit.formatters.test_typescript_formatter_core import *  # noqa: F401,F403
from tests.unit.formatters.test_typescript_formatter_modes import *  # noqa: F401,F403

if __name__ == "__main__":
    import pytest

    pytest.main([__file__])
