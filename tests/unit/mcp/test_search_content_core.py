"""SearchContentTool core test entry point — placeholder.

Split into:
- test_search_content_init_and_def.py:    init, path, definition, format
- test_search_content_validation.py:      roots, files, arguments validation
- test_search_content_execute.py:         async execute paths

Pytest collects them directly; the ``import *`` re-exports that used to
live here caused every test class to be collected twice under xdist's
``--dist=loadfile`` and produced flaky cross-worker collisions.

Run the full SearchContent suite with::

    uv run pytest tests/unit/mcp/test_search_content_*.py
"""
