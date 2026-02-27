"""Tests for platform_compat.report module."""

import json

import pytest

from tree_sitter_analyzer.platform_compat.report import generate_compatibility_matrix


class TestGenerateCompatibilityMatrix:
    """Tests for the generate_compatibility_matrix function."""

    @pytest.mark.unit
    def test_no_profiles_returns_message(self, tmp_path):
        """Test that empty directory returns 'No profiles found.' message."""
        result = generate_compatibility_matrix(tmp_path)
        assert result == "No profiles found."

    @pytest.mark.unit
    def test_single_profile(self, profiles_dir):
        """Test matrix generation with a single profile."""
        result = generate_compatibility_matrix(profiles_dir)
        assert "linux-3.12" in result
        assert "simple_table" in result
        assert "SQL Compatibility Matrix" in result

    @pytest.mark.unit
    def test_single_profile_ok_status(self, profiles_dir):
        """Test that a behavior without errors shows OK status."""
        result = generate_compatibility_matrix(profiles_dir)
        # The simple_table has has_error=False so should show OK
        assert "OK" in result

    @pytest.mark.unit
    def test_profile_with_error_shows_error_status(self, tmp_path):
        """Test that a behavior with has_error=True shows Error status."""
        profile_data = {
            "schema_version": "1.0.0",
            "platform_key": "linux-3.12",
            "behaviors": {
                "broken_construct": {
                    "construct_id": "broken_construct",
                    "node_type": "program",
                    "element_count": 0,
                    "attributes": [],
                    "has_error": True,
                    "known_issues": [],
                }
            },
            "adaptation_rules": [],
        }
        profile_dir = tmp_path / "linux" / "3.12"
        profile_dir.mkdir(parents=True)
        (profile_dir / "profile.json").write_text(
            json.dumps(profile_data), encoding="utf-8"
        )

        result = generate_compatibility_matrix(tmp_path)
        assert "Error" in result

    @pytest.mark.unit
    def test_multiple_profiles(self, tmp_path):
        """Test matrix generation with multiple profiles."""
        for platform_key, os_name, py_ver in [
            ("linux-3.12", "linux", "3.12"),
            ("macos-3.12", "macos", "3.12"),
        ]:
            profile_data = {
                "schema_version": "1.0.0",
                "platform_key": platform_key,
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
            profile_dir = tmp_path / os_name / py_ver
            profile_dir.mkdir(parents=True)
            (profile_dir / "profile.json").write_text(
                json.dumps(profile_data), encoding="utf-8"
            )

        result = generate_compatibility_matrix(tmp_path)
        assert "linux-3.12" in result
        assert "macos-3.12" in result
        assert "simple_table" in result

    @pytest.mark.unit
    def test_missing_construct_shows_missing_status(self, tmp_path):
        """Test that a construct missing in one profile shows Missing status."""
        # Profile A has construct, Profile B does not
        for platform_key, os_name, py_ver, behaviors in [
            (
                "linux-3.12",
                "linux",
                "3.12",
                {
                    "common": {
                        "construct_id": "common",
                        "node_type": "program",
                        "element_count": 1,
                        "attributes": [],
                        "has_error": False,
                        "known_issues": [],
                    },
                    "only_linux": {
                        "construct_id": "only_linux",
                        "node_type": "program",
                        "element_count": 1,
                        "attributes": [],
                        "has_error": False,
                        "known_issues": [],
                    },
                },
            ),
            (
                "macos-3.12",
                "macos",
                "3.12",
                {
                    "common": {
                        "construct_id": "common",
                        "node_type": "program",
                        "element_count": 1,
                        "attributes": [],
                        "has_error": False,
                        "known_issues": [],
                    }
                },
            ),
        ]:
            profile_data = {
                "schema_version": "1.0.0",
                "platform_key": platform_key,
                "behaviors": behaviors,
                "adaptation_rules": [],
            }
            profile_dir = tmp_path / os_name / py_ver
            profile_dir.mkdir(parents=True)
            (profile_dir / "profile.json").write_text(
                json.dumps(profile_data), encoding="utf-8"
            )

        result = generate_compatibility_matrix(tmp_path)
        assert "Missing" in result

    @pytest.mark.unit
    def test_corrupt_profile_skipped(self, tmp_path):
        """Test that corrupt profile files are skipped gracefully."""
        profile_dir = tmp_path / "linux" / "3.12"
        profile_dir.mkdir(parents=True)
        (profile_dir / "profile.json").write_text("not valid json", encoding="utf-8")

        result = generate_compatibility_matrix(tmp_path)
        assert result == "No profiles found."

    @pytest.mark.unit
    def test_profile_without_platform_key_skipped(self, tmp_path):
        """Test that profile without platform_key is skipped."""
        profile_dir = tmp_path / "linux" / "3.12"
        profile_dir.mkdir(parents=True)
        data = {"schema_version": "1.0.0", "behaviors": {}}
        (profile_dir / "profile.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

        result = generate_compatibility_matrix(tmp_path)
        assert result == "No profiles found."

    @pytest.mark.unit
    def test_profiles_sorted_by_platform_key(self, tmp_path):
        """Test that profiles are sorted by platform_key in output."""
        for platform_key, os_name, py_ver in [
            ("windows-3.12", "windows", "3.12"),
            ("linux-3.12", "linux", "3.12"),
            ("macos-3.12", "macos", "3.12"),
        ]:
            profile_data = {
                "schema_version": "1.0.0",
                "platform_key": platform_key,
                "behaviors": {},
                "adaptation_rules": [],
            }
            profile_dir = tmp_path / os_name / py_ver
            profile_dir.mkdir(parents=True)
            (profile_dir / "profile.json").write_text(
                json.dumps(profile_data), encoding="utf-8"
            )

        result = generate_compatibility_matrix(tmp_path)
        linux_pos = result.index("linux-3.12")
        macos_pos = result.index("macos-3.12")
        windows_pos = result.index("windows-3.12")
        assert linux_pos < macos_pos < windows_pos
