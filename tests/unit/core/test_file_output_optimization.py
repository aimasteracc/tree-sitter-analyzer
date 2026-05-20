"""File-output optimisation test entry point — placeholder.

The split modules (``test_file_output_search_content.py``,
``test_file_output_find_and_grep.py``, ``test_file_output_list_files.py``)
are picked up directly by pytest. This file used to ``import *`` from
each split module, which made every test class get collected twice under
xdist's ``--dist=loadfile`` and caused flaky cross-worker collisions on
shared module-level state.

The re-imports were removed so each test class is collected exactly
once. To run all file-output-optimisation tests, use::

    uv run pytest tests/unit/core/test_file_output_*.py
"""
