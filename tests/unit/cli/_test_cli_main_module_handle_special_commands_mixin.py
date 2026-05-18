#!/usr/bin/env python3
"""Shared mixin tests for handle_special_commands.

Keeps the large "TestHandleSpecialCommands" suite out of the primary module
for faster review and safer local refactoring.
"""

from tests.unit.cli._test_cli_main_module_handle_special_commands_batch_mixin import (
    TestHandleSpecialCommandsBatchMixin,
)
from tests.unit.cli._test_cli_main_module_handle_special_commands_profile_mixin import (
    TestHandleSpecialCommandsProfileMixin,
)


class TestHandleSpecialCommandsTestMixin(
    TestHandleSpecialCommandsProfileMixin,
    TestHandleSpecialCommandsBatchMixin,
):
    """Mixin aggregating all handle_special_commands test groups."""

    __test__ = False
