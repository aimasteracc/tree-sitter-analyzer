"""Tests for platform_compat.fixtures module."""

import pytest

from tree_sitter_analyzer.platform_compat.fixtures import (
    ALL_FIXTURES,
    FIXTURE_PHANTOM_TRIGGER,
    FIXTURE_SIMPLE_TABLE,
    SQLTestFixture,
)


class TestSQLTestFixture:
    """Tests for the SQLTestFixture dataclass."""

    @pytest.mark.unit
    def test_create_fixture(self):
        """Test creating a basic SQLTestFixture."""
        fixture = SQLTestFixture(
            id="test_fixture",
            sql="SELECT 1;",
            description="A test fixture",
            expected_constructs=["table"],
        )
        assert fixture.id == "test_fixture"
        assert fixture.sql == "SELECT 1;"
        assert fixture.description == "A test fixture"
        assert fixture.expected_constructs == ["table"]
        assert fixture.is_edge_case is False
        assert fixture.known_platform_issues is None

    @pytest.mark.unit
    def test_create_edge_case_fixture(self):
        """Test creating an edge case fixture."""
        fixture = SQLTestFixture(
            id="edge_case",
            sql="SELECT 1;",
            description="Edge case test",
            expected_constructs=[],
            is_edge_case=True,
            known_platform_issues=["linux-3.12"],
        )
        assert fixture.is_edge_case is True
        assert fixture.known_platform_issues == ["linux-3.12"]


class TestAllFixtures:
    """Tests for the ALL_FIXTURES list."""

    @pytest.mark.unit
    def test_all_fixtures_not_empty(self):
        """Test that ALL_FIXTURES contains entries."""
        assert len(ALL_FIXTURES) > 0

    @pytest.mark.unit
    def test_all_fixtures_unique_ids(self):
        """Test that all fixtures have unique IDs."""
        ids = [f.id for f in ALL_FIXTURES]
        assert len(ids) == len(set(ids))

    @pytest.mark.unit
    def test_all_fixtures_have_sql(self):
        """Test that all fixtures have non-empty SQL."""
        for fixture in ALL_FIXTURES:
            assert fixture.sql.strip(), f"Fixture {fixture.id} has empty SQL"

    @pytest.mark.unit
    def test_all_fixtures_have_description(self):
        """Test that all fixtures have descriptions."""
        for fixture in ALL_FIXTURES:
            assert fixture.description, f"Fixture {fixture.id} has no description"

    @pytest.mark.unit
    def test_all_fixtures_have_expected_constructs(self):
        """Test that all fixtures have expected_constructs defined."""
        for fixture in ALL_FIXTURES:
            assert isinstance(
                fixture.expected_constructs, list
            ), f"Fixture {fixture.id} has invalid expected_constructs"

    @pytest.mark.unit
    def test_standard_fixtures_exist(self):
        """Test that expected standard fixtures are present."""
        fixture_ids = {f.id for f in ALL_FIXTURES}
        expected_ids = {
            "simple_table",
            "complex_table",
            "view_with_join",
            "stored_procedure",
            "function_with_params",
            "trigger_before_insert",
            "index_unique",
        }
        assert expected_ids.issubset(fixture_ids)

    @pytest.mark.unit
    def test_edge_case_fixtures_exist(self):
        """Test that expected edge case fixtures are present."""
        edge_cases = [f for f in ALL_FIXTURES if f.is_edge_case]
        assert len(edge_cases) > 0
        edge_ids = {f.id for f in edge_cases}
        assert "function_with_select" in edge_ids
        assert "phantom_trigger" in edge_ids

    @pytest.mark.unit
    def test_simple_table_fixture(self):
        """Test FIXTURE_SIMPLE_TABLE content."""
        assert FIXTURE_SIMPLE_TABLE.id == "simple_table"
        assert "CREATE TABLE" in FIXTURE_SIMPLE_TABLE.sql
        assert "table" in FIXTURE_SIMPLE_TABLE.expected_constructs
        assert FIXTURE_SIMPLE_TABLE.is_edge_case is False

    @pytest.mark.unit
    def test_phantom_trigger_fixture(self):
        """Test FIXTURE_PHANTOM_TRIGGER is an edge case."""
        assert FIXTURE_PHANTOM_TRIGGER.is_edge_case is True
        assert "table" in FIXTURE_PHANTOM_TRIGGER.expected_constructs
        assert "trigger" not in FIXTURE_PHANTOM_TRIGGER.expected_constructs
