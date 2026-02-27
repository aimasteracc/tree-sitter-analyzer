"""Tests for platform_compat.profiles module."""

import json
import threading

import jsonschema
import pytest

from tree_sitter_analyzer.platform_compat.profiles import (
    PROFILE_SCHEMA_VERSION,
    BehaviorProfile,
    ParsingBehavior,
    ProfileCache,
    migrate_profile_schema,
    migrate_to_1_0_0,
    validate_profile,
)


class TestParsingBehavior:
    """Tests for the ParsingBehavior dataclass."""

    @pytest.mark.unit
    def test_create_basic_behavior(self):
        """Test creating a ParsingBehavior with required fields."""
        behavior = ParsingBehavior(
            construct_id="simple_table",
            node_type="program",
            element_count=1,
            attributes=["col:id"],
            has_error=False,
        )
        assert behavior.construct_id == "simple_table"
        assert behavior.node_type == "program"
        assert behavior.element_count == 1
        assert behavior.attributes == ["col:id"]
        assert behavior.has_error is False
        assert behavior.known_issues == []

    @pytest.mark.unit
    def test_create_behavior_with_known_issues(self):
        """Test creating a ParsingBehavior with known_issues."""
        behavior = ParsingBehavior(
            construct_id="function_with_select",
            node_type="program",
            element_count=0,
            attributes=[],
            has_error=True,
            known_issues=["ubuntu-3.12", "windows-3.11"],
        )
        assert behavior.has_error is True
        assert len(behavior.known_issues) == 2
        assert "ubuntu-3.12" in behavior.known_issues


class TestBehaviorProfile:
    """Tests for the BehaviorProfile dataclass."""

    @pytest.mark.unit
    def test_create_profile(self, sample_behavior):
        """Test creating a BehaviorProfile."""
        profile = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="linux-3.12",
            behaviors={"simple_table": sample_behavior},
            adaptation_rules=[],
        )
        assert profile.schema_version == "1.0.0"
        assert profile.platform_key == "linux-3.12"
        assert "simple_table" in profile.behaviors

    @pytest.mark.unit
    def test_post_init_converts_dicts_to_parsing_behavior(self):
        """Test that __post_init__ converts dict behaviors to ParsingBehavior."""
        profile = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="linux-3.12",
            behaviors={
                "test": {
                    "construct_id": "test",
                    "node_type": "program",
                    "element_count": 1,
                    "attributes": [],
                    "has_error": False,
                }
            },
            adaptation_rules=[],
        )
        assert isinstance(profile.behaviors["test"], ParsingBehavior)
        assert profile.behaviors["test"].construct_id == "test"

    @pytest.mark.unit
    def test_post_init_leaves_parsing_behavior_untouched(self, sample_behavior):
        """Test that __post_init__ does not re-wrap ParsingBehavior objects."""
        profile = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="linux-3.12",
            behaviors={"test": sample_behavior},
            adaptation_rules=[],
        )
        assert profile.behaviors["test"] is sample_behavior

    @pytest.mark.unit
    def test_post_init_empty_behaviors(self):
        """Test __post_init__ with empty behaviors dict."""
        profile = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="linux-3.12",
            behaviors={},
            adaptation_rules=[],
        )
        assert profile.behaviors == {}

    @pytest.mark.unit
    def test_save_creates_directory_and_file(self, tmp_path, sample_profile):
        """Test that save() creates the profile directory and JSON file."""
        sample_profile.save(tmp_path)

        expected_path = tmp_path / "linux" / "3.12" / "profile.json"
        assert expected_path.exists()

        with open(expected_path, encoding="utf-8") as f:
            data = json.load(f)

        assert data["platform_key"] == "linux-3.12"
        assert data["schema_version"] == "1.0.0"
        assert "simple_table" in data["behaviors"]

    @pytest.mark.unit
    def test_load_returns_none_for_invalid_key(self, tmp_path):
        """Test that load() returns None for an invalid platform key."""
        result = BehaviorProfile.load("invalidkey", base_path=tmp_path)
        assert result is None

    @pytest.mark.unit
    def test_load_returns_none_for_missing_profile(self, tmp_path):
        """Test that load() returns None when profile file does not exist."""
        result = BehaviorProfile.load("linux-3.99", base_path=tmp_path)
        assert result is None

    @pytest.mark.unit
    def test_load_valid_profile(self, profiles_dir):
        """Test that load() correctly reads a saved profile."""
        result = BehaviorProfile.load("linux-3.12", base_path=profiles_dir)
        assert result is not None
        assert result.platform_key == "linux-3.12"
        assert "simple_table" in result.behaviors
        assert isinstance(result.behaviors["simple_table"], ParsingBehavior)

    @pytest.mark.unit
    def test_load_returns_none_for_corrupt_json(self, tmp_path):
        """Test that load() returns None for corrupt JSON."""
        profile_dir = tmp_path / "linux" / "3.12"
        profile_dir.mkdir(parents=True)
        (profile_dir / "profile.json").write_text("not valid json", encoding="utf-8")

        result = BehaviorProfile.load("linux-3.12", base_path=tmp_path)
        assert result is None


class TestValidateProfile:
    """Tests for the validate_profile function."""

    @pytest.mark.unit
    def test_valid_profile_passes(self):
        """Test that a valid profile passes validation."""
        data = {
            "schema_version": "1.0.0",
            "platform_key": "linux-3.12",
            "behaviors": {},
            "adaptation_rules": [],
        }
        # Should not raise
        validate_profile(data)

    @pytest.mark.unit
    def test_invalid_profile_missing_key(self):
        """Test that missing required keys raise validation error."""
        data = {
            "schema_version": "1.0.0",
            # missing platform_key
            "behaviors": {},
            "adaptation_rules": [],
        }
        with pytest.raises((jsonschema.ValidationError, KeyError, ValueError, TypeError)):
            validate_profile(data)

    @pytest.mark.unit
    def test_invalid_behavior_type(self):
        """Test that invalid behavior property types raise validation error."""
        data = {
            "schema_version": "1.0.0",
            "platform_key": "linux-3.12",
            "behaviors": {
                "test": {
                    "construct_id": "test",
                    "node_type": "program",
                    "element_count": "not_an_int",  # Should be integer
                    "attributes": [],
                    "has_error": False,
                }
            },
            "adaptation_rules": [],
        }
        with pytest.raises((jsonschema.ValidationError, KeyError, ValueError, TypeError)):
            validate_profile(data)


class TestMigrateProfileSchema:
    """Tests for schema migration functions."""

    @pytest.mark.unit
    def test_migrate_current_version_is_noop(self):
        """Test that migrating data already at current version returns it unchanged."""
        data = {"schema_version": PROFILE_SCHEMA_VERSION, "behaviors": {}}
        result = migrate_profile_schema(data)
        assert result is data

    @pytest.mark.unit
    def test_migrate_from_0_0_0(self):
        """Test migration from version 0.0.0 to 1.0.0."""
        data = {"schema_version": "0.0.0", "platform_key": "linux-3.12"}
        result = migrate_profile_schema(data)
        assert result["schema_version"] == "1.0.0"
        assert "behaviors" in result
        assert "adaptation_rules" in result

    @pytest.mark.unit
    def test_migrate_unknown_version_returns_data(self):
        """Test that an unknown version returns data as-is."""
        data = {"schema_version": "99.99.99", "behaviors": {}}
        result = migrate_profile_schema(data)
        assert result["schema_version"] == "99.99.99"

    @pytest.mark.unit
    def test_migrate_to_1_0_0_adds_missing_fields(self):
        """Test migrate_to_1_0_0 adds behaviors and adaptation_rules if missing."""
        data = {"platform_key": "linux-3.12"}
        result = migrate_to_1_0_0(data)
        assert result["schema_version"] == "1.0.0"
        assert result["behaviors"] == {}
        assert result["adaptation_rules"] == []

    @pytest.mark.unit
    def test_migrate_to_1_0_0_preserves_existing_behaviors(self):
        """Test that migrate_to_1_0_0 preserves existing behaviors."""
        data = {
            "platform_key": "linux-3.12",
            "behaviors": {"test": {"construct_id": "test"}},
            "adaptation_rules": ["rule1"],
        }
        result = migrate_to_1_0_0(data)
        assert result["schema_version"] == "1.0.0"
        assert "test" in result["behaviors"]
        assert "rule1" in result["adaptation_rules"]

    @pytest.mark.unit
    def test_migrate_missing_schema_version(self):
        """Test migration when schema_version key is missing entirely."""
        data = {"platform_key": "linux-3.12"}
        result = migrate_profile_schema(data)
        # Missing schema_version defaults to "0.0.0" which triggers migration
        assert result["schema_version"] == "1.0.0"


class TestProfileCache:
    """Tests for the ProfileCache class."""

    @pytest.mark.unit
    def test_get_returns_none_for_missing_key(self):
        """Test that get() returns None for a key not in cache."""
        cache = ProfileCache()
        assert cache.get("nonexistent") is None

    @pytest.mark.unit
    def test_put_and_get(self, sample_profile):
        """Test that put() stores and get() retrieves a profile."""
        cache = ProfileCache()
        cache.put("linux-3.12", sample_profile)
        result = cache.get("linux-3.12")
        assert result is sample_profile

    @pytest.mark.unit
    def test_cache_stats_initial(self):
        """Test that initial cache stats are all zero."""
        cache = ProfileCache()
        stats = cache.stats
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0

    @pytest.mark.unit
    def test_cache_stats_after_operations(self, sample_profile):
        """Test that cache stats track hits and misses."""
        cache = ProfileCache()
        cache.get("miss1")  # miss
        cache.get("miss2")  # miss
        cache.put("linux-3.12", sample_profile)
        cache.get("linux-3.12")  # hit

        stats = cache.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 2
        assert stats["size"] == 1

    @pytest.mark.unit
    def test_cache_clear(self, sample_profile):
        """Test that clear() empties the cache and resets stats."""
        cache = ProfileCache()
        cache.put("linux-3.12", sample_profile)
        cache.get("linux-3.12")  # hit
        cache.get("missing")  # miss

        cache.clear()
        stats = cache.stats
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0

    @pytest.mark.unit
    def test_cache_thread_safety(self, sample_profile):
        """Test that cache operations are thread-safe."""
        cache = ProfileCache(maxsize=100)
        errors = []

        def writer(key_prefix, count):
            try:
                for i in range(count):
                    profile = BehaviorProfile(
                        schema_version="1.0.0",
                        platform_key=f"{key_prefix}-{i}",
                        behaviors={},
                        adaptation_rules=[],
                    )
                    cache.put(f"{key_prefix}-{i}", profile)
            except Exception as e:
                errors.append(e)

        def reader(key_prefix, count):
            try:
                for i in range(count):
                    cache.get(f"{key_prefix}-{i}")
            except Exception as e:
                errors.append(e)

        threads = []
        for prefix in ["a", "b", "c"]:
            threads.append(threading.Thread(target=writer, args=(prefix, 20)))
            threads.append(threading.Thread(target=reader, args=(prefix, 20)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    @pytest.mark.unit
    def test_cache_maxsize(self):
        """Test that cache respects maxsize."""
        cache = ProfileCache(maxsize=2)
        for i in range(5):
            profile = BehaviorProfile(
                schema_version="1.0.0",
                platform_key=f"test-{i}",
                behaviors={},
                adaptation_rules=[],
            )
            cache.put(f"key-{i}", profile)

        stats = cache.stats
        assert stats["size"] <= 2
