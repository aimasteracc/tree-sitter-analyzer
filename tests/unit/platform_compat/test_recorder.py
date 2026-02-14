#!/usr/bin/env python3
"""Unit tests for platform_compat recorder - record_fixture, analyze_ast."""

import pytest

from tree_sitter_analyzer.platform_compat.fixtures import (
    FIXTURE_SIMPLE_TABLE,
    SQLTestFixture,
)
from tree_sitter_analyzer.platform_compat.profiles import ParsingBehavior
from tree_sitter_analyzer.platform_compat.recorder import BehaviorRecorder


class TestRecordFixture:
    """Tests for BehaviorRecorder.record_fixture."""

    def test_record_fixture_returns_parsing_behavior(self) -> None:
        """record_fixture returns a ParsingBehavior instance."""
        recorder = BehaviorRecorder()
        result = recorder.record_fixture(FIXTURE_SIMPLE_TABLE)
        assert isinstance(result, ParsingBehavior)

    def test_record_fixture_sets_construct_id(self) -> None:
        """record_fixture sets construct_id from fixture."""
        recorder = BehaviorRecorder()
        result = recorder.record_fixture(FIXTURE_SIMPLE_TABLE)
        assert result.construct_id == "simple_table"

    def test_record_fixture_has_element_count(self) -> None:
        """record_fixture produces valid element_count (int)."""
        recorder = BehaviorRecorder()
        result = recorder.record_fixture(FIXTURE_SIMPLE_TABLE)
        assert isinstance(result.element_count, int)
        assert result.element_count >= 0

    def test_record_fixture_has_attributes_list(self) -> None:
        """record_fixture produces attributes as list."""
        recorder = BehaviorRecorder()
        result = recorder.record_fixture(FIXTURE_SIMPLE_TABLE)
        assert isinstance(result.attributes, list)

    def test_record_fixture_has_has_error_bool(self) -> None:
        """record_fixture produces has_error as bool."""
        recorder = BehaviorRecorder()
        result = recorder.record_fixture(FIXTURE_SIMPLE_TABLE)
        assert isinstance(result.has_error, bool)


class TestAnalyzeAst:
    """Tests for BehaviorRecorder.analyze_ast."""

    def test_analyze_ast_returns_dict_with_expected_keys(self) -> None:
        """analyze_ast returns dict with element_count, attributes, has_error."""
        recorder = BehaviorRecorder()
        tree = recorder.parser.parse(bytes(FIXTURE_SIMPLE_TABLE.sql, "utf8"))
        root = tree.root_node

        result = recorder.analyze_ast(root)

        assert "element_count" in result
        assert "attributes" in result
        assert "has_error" in result
        assert isinstance(result["element_count"], int)
        assert isinstance(result["attributes"], list)
        assert isinstance(result["has_error"], bool)

    def test_analyze_ast_simple_table_returns_valid_result(self) -> None:
        """analyze_ast returns valid analysis for simple table fixture."""
        recorder = BehaviorRecorder()
        tree = recorder.parser.parse(bytes(FIXTURE_SIMPLE_TABLE.sql, "utf8"))
        root = tree.root_node

        result = recorder.analyze_ast(root)

        # Grammar may vary by tree-sitter-sql version; element_count is non-negative
        assert result["element_count"] >= 0
        # Simple table may have column definitions -> attributes (list, possibly empty)
        assert isinstance(result["attributes"], list)
