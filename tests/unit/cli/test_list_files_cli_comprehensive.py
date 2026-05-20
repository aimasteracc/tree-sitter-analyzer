"""list_files_cli comprehensive test entry point — placeholder.

Split into:
- test_list_files_cli_comprehensive_execution.py
- test_list_files_cli_comprehensive_parser.py

Pytest collects them directly; the ``import *`` re-exports that used to
live here caused every test class to be collected twice under xdist's
``--dist=loadfile`` and produced flaky cross-worker collisions.

Run the full list-files-CLI suite with::

    uv run pytest tests/unit/cli/test_list_files_cli_comprehensive_*.py
"""
