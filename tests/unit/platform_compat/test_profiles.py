#!/usr/bin/env python3
"""Unit tests for platform_compat profiles - validate_profile, migrate_profile_schema, migrate_to_1_0_0."""

import jsonschema
import pytest

from tree_sitter_analyzer.platform_compat.profiles import (
    migrate_profile_schema,
    migrate_to_1_0_0,
    validate_profile,
)


class TestValidateProfile:
    """Tests for validate_profile function."""

    def test_valid_profile_passes(self) -> None:
        """Valid profile data passes validation."""
        data = {
            "schema_version": "1.0.0",
            "platform_key": "windows-3.12",
            "behaviors": {
                "simple_table": {
                    "construct_id": "simple_table",
                    "node_type": "program",
                    "element_count": 1,
                    "attributes": [],
                    "has_error": False,
                    "known_issues": [],
                }
            },
            "adaptation_rules": [],
        }
        validate_profile(data)  # Should not raise

    def test_invalid_profile_raises(self) -> None:
        """Invalid profile data raises ValidationError."""
        data = {"platform_key": "test"}  # Missing required fields
        with pytest.raises(jsonschema.ValidationError):
            validate_profile(data)

    def test_missing_platform_key_raises(self) -> None:
        """Profile without platform_key raises."""
        data = {
            "schema_version": "1.0.0",
            "behaviors": {},
            "adaptation_rules": [],
        }
        # platform_key is required
        with pytest.raises(jsonschema.ValidationError):
            validate_profile(data)


class TestMigrateTo1_0_0:
    """Tests for migrate_to_1_0_0 function."""

    def test_adds_schema_version(self) -> None:
        """Sets schema_version to 1.0.0."""
        data = {}
        result = migrate_to_1_0_0(data)
        assert result["schema_version"] == "1.0.0"

    def test_adds_behaviors_if_missing(self) -> None:
        """Adds empty behaviors dict if missing."""
        data = {}
        result = migrate_to_1_0_0(data)
        assert "behaviors" in result
        assert result["behaviors"] == {}

    def test_adds_adaptation_rules_if_missing(self) -> None:
        """Adds empty adaptation_rules list if missing."""
        data = {}
        result = migrate_to_1_0_0(data)
        assert "adaptation_rules" in result
        assert result["adaptation_rules"] == []

    def test_preserves_existing_behaviors(self) -> None:
        """Does not overwrite existing behaviors."""
        data = {
            "behaviors": {
                "x": {
                    "construct_id": "x",
                    "node_type": "p",
                    "element_count": 0,
                    "attributes": [],
                    "has_error": False,
                }
            }
        }
        result = migrate_to_1_0_0(data)
        assert result["behaviors"]["x"]["construct_id"] == "x"


class TestMigrateProfileSchema:
    """Tests for migrate_profile_schema function."""

    def test_current_version_returns_unchanged(self) -> None:
        """Profile already at 1.0.0 is returned unchanged."""
        data = {
            "schema_version": "1.0.0",
            "platform_key": "test",
            "behaviors": {},
            "adaptation_rules": [],
        }
        result = migrate_profile_schema(data)
        assert result is data

    def test_version_0_0_0_migrates_to_1_0_0(self) -> None:
        """Profile with 0.0.0 is migrated to 1.0.0."""
        data = {"schema_version": "0.0.0"}
        result = migrate_profile_schema(data)
        assert result["schema_version"] == "1.0.0"
        assert "behaviors" in result
        assert "adaptation_rules" in result

    def test_no_version_treated_as_0_0_0(self) -> None:
        """Profile without schema_version defaults to 0.0.0 and migrates."""
        data = {}
        result = migrate_profile_schema(data)
        assert result["schema_version"] == "1.0.0"
