#!/usr/bin/env python3
"""
Comprehensive tests for JavaScript formatter — split into focused modules.

All test classes are imported from the split modules below so this file
remains a single entry point for running the full suite.
"""

from tests.unit.formatters.test_javascript_formatter_core import (  # noqa: F401
    TestJavaScriptTableFormatterCore,
)
from tests.unit.formatters.test_javascript_formatter_integration import (  # noqa: F401
    TestJavaScriptFormatterIntegration,
)
from tests.unit.formatters.test_javascript_formatter_robustness import (  # noqa: F401
    TestJavaScriptFormatterRobustness,
)
