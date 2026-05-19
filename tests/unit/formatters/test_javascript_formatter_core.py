#!/usr/bin/env python3
"""Re-export aggregator — tests split into focused modules for readability.

Original 982-line file split into:
- test_js_formatter_init_and_types.py: initialization, params, type detection
- test_js_formatter_table_output.py: full/compact table formatting output
"""

from tests.unit.formatters.test_js_formatter_init_and_types import *  # noqa: F401,F403
from tests.unit.formatters.test_js_formatter_table_output import *  # noqa: F401,F403
