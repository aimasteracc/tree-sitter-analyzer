"""Unit tests for platform_compat/report.py — compatibility matrix report generation."""

import json
from pathlib import Path

from tree_sitter_analyzer.platform_compat.profiles import ParsingBehavior
from tree_sitter_analyzer.platform_compat.report import generate_compatibility_matrix


def _make_profile(
    tmp_path: Path,
    platform_key: str,
    behaviors: dict[str, ParsingBehavior],
) -> Path:
    """Create a profile.json under the expected directory structure."""
    parts = platform_key.split("-")
    os_name = parts[0]
    version = parts[1] if len(parts) > 1 else "default"
    profile_dir = tmp_path / os_name / version
    profile_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": "1.0.0",
        "platform_key": platform_key,
        "behaviors": {
            k: {
                "construct_id": v.construct_id,
                "node_type": v.node_type,
                "element_count": v.element_count,
                "attributes": v.attributes,
                "has_error": v.has_error,
                "known_issues": v.known_issues,
            }
            for k, v in behaviors.items()
        },
        "adaptation_rules": [],
    }
    profile_file = profile_dir / "profile.json"
    profile_file.write_text(json.dumps(data))
    return profile_file


class TestGenerateCompatibilityMatrix:
    """Tests for generate_compatibility_matrix."""

    def test_empty_dir_returns_no_profiles(self, tmp_path: Path) -> None:
        result = generate_compatibility_matrix(tmp_path)
        assert result == "No profiles found."

    def test_single_profile_no_errors(self, tmp_path: Path) -> None:
        behaviors = {
            "simple_table": ParsingBehavior(
                construct_id="simple_table",
                node_type="create_table_statement",
                element_count=1,
                attributes=[],
                has_error=False,
            ),
        }
        _make_profile(tmp_path, "linux-3.12", behaviors)
        result = generate_compatibility_matrix(tmp_path)
        assert "# SQL Compatibility Matrix" in result
        assert "linux-3.12" in result
        assert "✅ OK" in result

    def test_profile_with_error_shows_warning(self, tmp_path: Path) -> None:
        behaviors = {
            "complex_table": ParsingBehavior(
                construct_id="complex_table",
                node_type="create_table_statement",
                element_count=1,
                attributes=[],
                has_error=True,
            ),
        }
        _make_profile(tmp_path, "macos-3.11", behaviors)
        result = generate_compatibility_matrix(tmp_path)
        assert "⚠️ Error" in result

    def test_missing_construct_shows_missing(self, tmp_path: Path) -> None:
        b1 = {
            "simple_table": ParsingBehavior(
                construct_id="simple_table",
                node_type="create_table_statement",
                element_count=1,
                attributes=[],
                has_error=False,
            ),
        }
        b2 = {
            "view_with_join": ParsingBehavior(
                construct_id="view_with_join",
                node_type="create_view_statement",
                element_count=1,
                attributes=[],
                has_error=False,
            ),
        }
        _make_profile(tmp_path, "linux-3.12", b1)
        _make_profile(tmp_path, "windows-3.11", b2)
        result = generate_compatibility_matrix(tmp_path)
        assert "❌ Missing" in result
        assert "linux-3.12" in result
        assert "windows-3.11" in result

    def test_profiles_sorted_by_platform_key(self, tmp_path: Path) -> None:
        behaviors = {
            "simple_table": ParsingBehavior(
                construct_id="simple_table",
                node_type="create_table_statement",
                element_count=1,
                attributes=[],
                has_error=False,
            ),
        }
        _make_profile(tmp_path, "z-platform-1.0", behaviors)
        _make_profile(tmp_path, "a-platform-1.0", behaviors)
        result = generate_compatibility_matrix(tmp_path)
        a_pos = result.index("a-platform-1.0")
        z_pos = result.index("z-platform-1.0")
        assert a_pos < z_pos

    def test_invalid_json_skipped(self, tmp_path: Path) -> None:
        bad_dir = tmp_path / "bad" / "1.0"
        bad_dir.mkdir(parents=True)
        (bad_dir / "profile.json").write_text("{invalid json")
        behaviors = {
            "simple_table": ParsingBehavior(
                construct_id="simple_table",
                node_type="create_table_statement",
                element_count=1,
                attributes=[],
                has_error=False,
            ),
        }
        _make_profile(tmp_path, "linux-3.12", behaviors)
        result = generate_compatibility_matrix(tmp_path)
        assert "linux-3.12" in result
        assert "bad" not in result

    def test_json_without_platform_key_skipped(self, tmp_path: Path) -> None:
        bad_dir = tmp_path / "nokey" / "1.0"
        bad_dir.mkdir(parents=True)
        (bad_dir / "profile.json").write_text(json.dumps({"behaviors": {}}))
        behaviors = {
            "simple_table": ParsingBehavior(
                construct_id="simple_table",
                node_type="create_table_statement",
                element_count=1,
                attributes=[],
                has_error=False,
            ),
        }
        _make_profile(tmp_path, "linux-3.12", behaviors)
        result = generate_compatibility_matrix(tmp_path)
        assert "linux-3.12" in result
        assert "nokey" not in result

    def test_markdown_table_format(self, tmp_path: Path) -> None:
        behaviors = {
            "simple_table": ParsingBehavior(
                construct_id="simple_table",
                node_type="create_table_statement",
                element_count=1,
                attributes=[],
                has_error=False,
            ),
        }
        _make_profile(tmp_path, "linux-3.12", behaviors)
        result = generate_compatibility_matrix(tmp_path)
        lines = result.split("\n")
        assert lines[0].startswith("#")
        assert "|" in lines[2]
        assert "---" in lines[3]
