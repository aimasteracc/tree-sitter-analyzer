"""List Files MCP tool test entry point — placeholder.

Split into:
- test_list_files_tool_init_and_def.py: init, definition, validation, summary
- test_list_files_tool_execute.py:      async execute paths

Pytest collects them directly; the ``import *`` re-exports that used to
live here caused every test class to be collected twice under xdist's
``--dist=loadfile`` and produced flaky cross-worker collisions.

Run the full List-Files suite with::

    uv run pytest tests/unit/mcp/test_list_files_tool_*.py
"""
