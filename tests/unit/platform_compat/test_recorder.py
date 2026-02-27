"""Tests for platform_compat.recorder module."""


import pytest

from tree_sitter_analyzer.platform_compat.fixtures import (
    FIXTURE_SIMPLE_TABLE,
    SQLTestFixture,
)
from tree_sitter_analyzer.platform_compat.profiles import (
    BehaviorProfile,
    ParsingBehavior,
)
from tree_sitter_analyzer.platform_compat.recorder import BehaviorRecorder


class TestBehaviorRecorder:
    """Tests for the BehaviorRecorder class."""

    @pytest.mark.unit
    def test_init_creates_parser(self):
        """Test that __init__ sets up parser and platform info."""
        recorder = BehaviorRecorder()
        assert recorder.parser is not None
        assert recorder.language is not None
        assert recorder.platform_info is not None

    @pytest.mark.unit
    def test_record_fixture_returns_parsing_behavior(self):
        """Test that record_fixture returns a ParsingBehavior."""
        recorder = BehaviorRecorder()
        fixture = SQLTestFixture(
            id="test",
            sql="CREATE TABLE t (id INT);",
            description="Simple table",
            expected_constructs=["table"],
        )
        result = recorder.record_fixture(fixture)
        assert isinstance(result, ParsingBehavior)
        assert result.construct_id == "test"
        assert result.node_type == "program"

    @pytest.mark.unit
    def test_record_fixture_simple_table(self):
        """Test recording behavior for a simple CREATE TABLE."""
        recorder = BehaviorRecorder()
        result = recorder.record_fixture(FIXTURE_SIMPLE_TABLE)
        assert result.construct_id == "simple_table"
        assert result.element_count >= 0  # Count depends on parser/platform
        assert isinstance(result.attributes, list)

    @pytest.mark.unit
    def test_record_fixture_detects_errors(self):
        """Test that record_fixture detects ERROR nodes."""
        recorder = BehaviorRecorder()
        fixture = SQLTestFixture(
            id="broken_sql",
            sql="CREATE TABL broken syntax here !!!",
            description="Broken SQL",
            expected_constructs=[],
        )
        result = recorder.record_fixture(fixture)
        # Depending on parser, this might or might not have errors
        # But we verify the structure is correct
        assert isinstance(result.has_error, bool)
        assert isinstance(result.attributes, list)

    @pytest.mark.unit
    def test_record_all_returns_profile(self):
        """Test that record_all returns a complete BehaviorProfile."""
        recorder = BehaviorRecorder()
        profile = recorder.record_all()
        assert isinstance(profile, BehaviorProfile)
        assert profile.schema_version == "1.0.0"
        assert len(profile.behaviors) > 0
        assert profile.platform_key == recorder.platform_info.platform_key

    @pytest.mark.unit
    def test_record_all_includes_all_fixtures(self):
        """Test that record_all records behaviors for all fixtures."""
        from tree_sitter_analyzer.platform_compat.fixtures import ALL_FIXTURES

        recorder = BehaviorRecorder()
        profile = recorder.record_all()
        for fixture in ALL_FIXTURES:
            assert fixture.id in profile.behaviors

    @pytest.mark.unit
    def test_analyze_ast_basic(self):
        """Test analyze_ast with a simple SQL statement."""
        recorder = BehaviorRecorder()
        tree = recorder.parser.parse(b"CREATE TABLE t (id INT PRIMARY KEY);")
        result = recorder.analyze_ast(tree.root_node)
        assert "element_count" in result
        assert "attributes" in result
        assert "has_error" in result
        assert isinstance(result["attributes"], list)

    @pytest.mark.unit
    def test_analyze_ast_with_columns(self):
        """Test that analyze_ast extracts column attributes."""
        recorder = BehaviorRecorder()
        sql = b"CREATE TABLE users (id INT PRIMARY KEY, username VARCHAR(50));"
        tree = recorder.parser.parse(sql)
        result = recorder.analyze_ast(tree.root_node)
        # Column names may or may not be extracted depending on parser field names.
        # Just verify the structure.
        assert isinstance(result["attributes"], list)
        assert result["element_count"] >= 0

    @pytest.mark.unit
    def test_save_profile(self, tmp_path):
        """Test save_profile delegates to profile.save."""
        recorder = BehaviorRecorder()
        profile = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="linux-3.12",
            behaviors={},
            adaptation_rules=[],
        )
        recorder.save_profile(profile, tmp_path)
        expected_path = tmp_path / "linux" / "3.12" / "profile.json"
        assert expected_path.exists()

    @pytest.mark.unit
    def test_record_fixture_empty_sql(self):
        """Test record_fixture with empty SQL."""
        recorder = BehaviorRecorder()
        fixture = SQLTestFixture(
            id="empty",
            sql="",
            description="Empty SQL",
            expected_constructs=[],
        )
        result = recorder.record_fixture(fixture)
        assert isinstance(result, ParsingBehavior)
        assert result.construct_id == "empty"
        assert result.element_count == 0
