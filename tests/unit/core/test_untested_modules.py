#!/usr/bin/env python3
"""Tests for previously untested core modules."""

from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.cli.argument_validator import CLIArgumentValidator
from tree_sitter_analyzer.constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_MAPPING,
    ELEMENT_TYPE_SQL_TABLE,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)
from tree_sitter_analyzer.core.engine_manager import EngineManager
from tree_sitter_analyzer.mcp.tools.output_format_validator import OutputFormatValidator


class TestCLIArgumentValidator:
    def test_init(self):
        assert isinstance(CLIArgumentValidator(), CLIArgumentValidator)

    def test_validate_no_conflicts(self):
        v = CLIArgumentValidator()
        args = MagicMock()
        args.table = "full"
        args.query_key = None
        assert v.validate_arguments(args) is None

    def test_validate_table_and_query_key_conflict(self):
        v = CLIArgumentValidator()
        args = MagicMock()
        args.table = "full"
        args.query_key = "methods"
        result = v.validate_arguments(args)
        assert result is not None
        assert "cannot" in result.lower()


class TestConstants:
    def test_element_types(self):
        assert ELEMENT_TYPE_CLASS == "class"
        assert ELEMENT_TYPE_FUNCTION == "function"
        assert ELEMENT_TYPE_VARIABLE == "variable"
        assert ELEMENT_TYPE_IMPORT == "import"

    def test_sql_element_types(self):
        assert ELEMENT_TYPE_SQL_TABLE == "table"

    def test_mapping(self):
        assert ELEMENT_TYPE_MAPPING == {
            "Class": "class",
            "Function": "function",
            "Variable": "variable",
            "Import": "import",
            "Package": "package",
            "Annotation": "annotation",
            "Lambda": "lambda",
            "Comprehension": "comprehension",
            "Expression": "expression",
        }

    def test_is_element_of_type(self):
        elem = MagicMock()
        elem.element_type = "class"
        assert is_element_of_type(elem, ELEMENT_TYPE_CLASS) is True
        assert is_element_of_type(elem, ELEMENT_TYPE_FUNCTION) is False


class TestEngineManager:
    def test_singleton_same_root(self):
        EngineManager.reset_instances()
        inst1 = EngineManager.get_instance(MagicMock, "/p1")
        inst2 = EngineManager.get_instance(MagicMock, "/p1")
        assert inst1 is inst2

    def test_different_roots(self):
        EngineManager.reset_instances()
        inst1 = EngineManager.get_instance(MagicMock, "/pa")
        inst2 = EngineManager.get_instance(MagicMock, "/pb")
        assert inst1 is not None and inst2 is not None

    def test_reset(self):
        first = EngineManager.get_instance(MagicMock, "/t")
        EngineManager.reset_instances()
        second = EngineManager.get_instance(MagicMock, "/t")
        assert first is not second
        assert list(EngineManager._instances) == ["/t"]


class TestOutputFormatValidator:
    def test_init(self):
        assert isinstance(OutputFormatValidator(), OutputFormatValidator)

    def test_no_conflict_passes(self):
        v = OutputFormatValidator()
        assert v.validate_output_format_exclusion({"query": "test"}) is None

    def test_mutual_exclusion_raises(self):
        v = OutputFormatValidator()
        with pytest.raises(ValueError):
            v.validate_output_format_exclusion(
                {"total_only": True, "count_only_matches": True}
            )

    def test_single_format_passes(self):
        v = OutputFormatValidator()
        assert v.validate_output_format_exclusion({"total_only": True}) is None

    def test_format_params(self):
        v = OutputFormatValidator()
        assert "total_only" in v.OUTPUT_FORMAT_PARAMS
        assert v.OUTPUT_FORMAT_PARAMS == [
            "total_only",
            "count_only_matches",
            "summary_only",
            "group_by_file",
            "suppress_output",
        ]
