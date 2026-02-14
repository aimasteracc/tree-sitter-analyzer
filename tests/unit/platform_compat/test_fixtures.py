#!/usr/bin/env python3
"""Unit tests for platform_compat fixtures - SQLTestFixture."""

from tree_sitter_analyzer.platform_compat.fixtures import (
    ALL_FIXTURES,
    FIXTURE_SIMPLE_TABLE,
    SQLTestFixture,
)


class TestSQLTestFixture:
    """Tests for SQLTestFixture dataclass."""

    def test_instantiation(self) -> None:
        """SQLTestFixture can be instantiated with required fields."""
        fixture = SQLTestFixture(
            id="test_fixture",
            sql="CREATE TABLE t (id INT);",
            description="Test table",
            expected_constructs=["table"],
        )
        assert fixture.id == "test_fixture"
        assert "CREATE TABLE" in fixture.sql
        assert fixture.description == "Test table"
        assert fixture.expected_constructs == ["table"]
        assert fixture.is_edge_case is False
        assert fixture.known_platform_issues is None

    def test_instantiation_with_defaults(self) -> None:
        """SQLTestFixture optional fields have correct defaults."""
        fixture = SQLTestFixture(
            id="edge",
            sql="SELECT 1;",
            description="Edge case",
            expected_constructs=[],
            is_edge_case=True,
            known_platform_issues=["windows"],
        )
        assert fixture.is_edge_case is True
        assert fixture.known_platform_issues == ["windows"]

    def test_fixture_simple_table_has_expected_fields(self) -> None:
        """FIXTURE_SIMPLE_TABLE constant has expected structure."""
        assert FIXTURE_SIMPLE_TABLE.id == "simple_table"
        assert "CREATE TABLE" in FIXTURE_SIMPLE_TABLE.sql
        assert "table" in FIXTURE_SIMPLE_TABLE.expected_constructs

    def test_all_fixtures_non_empty(self) -> None:
        """ALL_FIXTURES contains at least one fixture."""
        assert len(ALL_FIXTURES) > 0

    def test_all_fixtures_have_unique_ids(self) -> None:
        """All fixtures in ALL_FIXTURES have unique ids."""
        ids = [f.id for f in ALL_FIXTURES]
        assert len(ids) == len(set(ids))
