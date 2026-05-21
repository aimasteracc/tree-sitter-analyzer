#!/usr/bin/env python3
"""Shared output-format detection for CLI commands.

r37am (dogfood): three identical ``_wants_json`` /
``_wants_json_output`` helpers were scattered across
``cli/info_commands.py``, ``cli/special_commands.py``, and an inline
check in ``cli_main.py::_print_filter_help``. The duplication made it
easy to drift (each copy had slightly different parameter naming
``args``/``Namespace``/``Any``). This module owns the single source
of truth — every CLI command that branches on output format imports
:func:`wants_json_output` from here.
"""

from __future__ import annotations

from typing import Any


def wants_json_output(args: Any) -> bool:
    """Return ``True`` when the caller asked for JSON output.

    Reads ``args.format`` first (the user-facing ``--format`` flag), and
    falls back to ``args.output_format`` (the legacy
    ``--output-format`` flag, which currently defaults to ``"json"``).

    Used by every CLI command that supports both text and JSON
    rendering paths. Centralising the check ensures consistent
    detection — e.g. one helper bug, one fix site, not three.
    """
    fmt = getattr(args, "format", None) or getattr(args, "output_format", None)
    return fmt == "json"
