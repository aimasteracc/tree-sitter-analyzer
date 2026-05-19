#!/usr/bin/env python3
"""
Re-export aggregator for split MCP tools integration tests.

Original file (857 lines) split into:
- test_mcp_tools_integration_workflows.py — multi-step workflow tests
- test_mcp_tools_integration_consistency.py — consistency/error/performance tests
"""

from test_mcp_tools_integration_consistency import *  # noqa: F401,F403
from test_mcp_tools_integration_workflows import *  # noqa: F401,F403
