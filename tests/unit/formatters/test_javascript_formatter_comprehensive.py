#!/usr/bin/env python3
"""
Comprehensive tests for JavaScript formatter — split into focused modules.

All test classes are imported from the split modules below so this file
remains a single entry point for running the full suite.
"""

from tests.unit.formatters.test_javascript_formatter_integration import (  # noqa: F401
    TestJavaScriptFormatterIntegration,
)
from tests.unit.formatters.test_javascript_formatter_robustness import (  # noqa: F401
    TestJavaScriptFormatterRobustness,
)
from tests.unit.formatters.test_js_formatter_init_and_types import (  # noqa: F401
    TestJavaScriptFormatterInit,
    TestJavaScriptFunctionTypes,
    TestJavaScriptMethodHelpers,
    TestJavaScriptParamCreation,
    TestJavaScriptTypeInference,
)
from tests.unit.formatters.test_js_formatter_table_output import (  # noqa: F401
    TestJavaScriptCompactSignatureMixin,
    TestJavaScriptCompactTableFormatting,
    TestJavaScriptFullTableFormatting,
    TestJavaScriptSectionAbsence,
)
