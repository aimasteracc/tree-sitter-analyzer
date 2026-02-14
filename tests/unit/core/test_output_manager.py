#!/usr/bin/env python3
"""Unit tests for output_manager module - get_output_manager and OutputManager."""

from tree_sitter_analyzer.output_manager import (
    OutputManager,
    get_output_manager,
    set_output_mode,
)


class TestGetOutputManager:
    """Tests for get_output_manager function."""

    def test_get_output_manager_returns_output_manager_instance(self) -> None:
        """get_output_manager returns an OutputManager instance."""
        manager = get_output_manager()
        assert isinstance(manager, OutputManager)

    def test_get_output_manager_returns_same_instance_by_default(self) -> None:
        """Default get_output_manager returns the same global instance."""
        manager1 = get_output_manager()
        manager2 = get_output_manager()
        assert manager1 is manager2

    def test_set_output_mode_changes_returned_manager(self) -> None:
        """set_output_mode creates a new OutputManager with specified options."""
        set_output_mode(quiet=True, json_output=False)
        manager = get_output_manager()
        assert manager.quiet is True
        assert manager.json_output is False
        # Restore default for other tests
        set_output_mode(quiet=False, json_output=False)
