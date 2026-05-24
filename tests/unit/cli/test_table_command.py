#!/usr/bin/env python3
"""
Re-export aggregator for split TableCommand test modules.

Tests were split from this file into:
- test_table_command_core.py: init, execute, toon format, package name
- test_table_command_conversion.py: structure conversion, element converters, output
"""

from tests.unit.cli.test_table_command_conversion import *  # noqa: F401,F403
from tests.unit.cli.test_table_command_core import *  # noqa: F401,F403
