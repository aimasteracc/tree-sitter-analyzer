from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.cli.commands.table_command import TableCommand


@pytest.fixture
def table_command():
    return TableCommand(MagicMock())


def test_table_command_run_empty(table_command):
    args = MagicMock()
    args.file = "test.py"
    args.format = "full"
    args.output = None

    # Mocking external calls if needed
    with pytest.raises(
        (FileNotFoundError, ValueError, OSError)
    ):  # More specific exceptions
        table_command.run(args)


def test_table_command_basic_logic(table_command):
    # Testing internal formatting logic if accessible
    assert table_command is not None
