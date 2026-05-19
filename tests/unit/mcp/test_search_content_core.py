#!/usr/bin/env python3
"""SearchContentTool core tests — re-export aggregator.

Split from 846 lines into focused modules:
- test_search_content_init_and_def.py: init, path, definition, format (228 lines)
- test_search_content_validation.py: roots, files, arguments validation (155 lines)
- test_search_content_execute.py: async execute paths (442 lines)
"""

from tests.unit.mcp.test_search_content_execute import *  # noqa: F401,F403
from tests.unit.mcp.test_search_content_init_and_def import *  # noqa: F401,F403
from tests.unit.mcp.test_search_content_validation import *  # noqa: F401,F403
