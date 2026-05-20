"""Tests for the compatibility difference analyzer script."""

import json

from compatibility_test.scripts._analyze_differences_json import (
    compare_json_structure,
    determine_field_severity,
)
from compatibility_test.scripts.analyze_differences import DifferenceAnalyzer


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_analyzer(tmp_path, version_a="1.0.0", version_b="1.0.1"):
    return DifferenceAnalyzer(
        version_a=version_a,
        version_b=version_b,
        project_root=str(tmp_path),
    )


def _make_version_dirs(tmp_path, version_a="1.0.0", version_b="1.0.1"):
    version_a_dir = tmp_path / "compatibility_test" / "results" / f"v{version_a}"
    version_b_dir = tmp_path / "compatibility_test" / "results" / f"v{version_b}"
    version_a_dir.mkdir(parents=True)
    version_b_dir.mkdir(parents=True)
    return version_a_dir, version_b_dir


def test_compare_json_structure_reports_nested_key_and_value_changes():
    differences = compare_json_structure(
        {
            "name": "old",
            "metadata": {"removed": True, "stable": 1},
            "items": [1, 2],
        },
        {
            "name": "new",
            "metadata": {"added": True, "stable": 1},
            "items": [1, 3, 4],
        },
        "",
        determine_field_severity,
    )

    by_type = {difference["type"] for difference in differences}
    assert {
        "value_changed",
        "key_added",
        "key_removed",
        "list_length_changed",
    } <= by_type
    assert any(
        difference["path"] == "metadata.removed" and difference["severity"] == "high"
        for difference in differences
    )
    assert any(
        difference["path"] == "metadata.added" and difference["severity"] == "low"
        for difference in differences
    )


def test_determine_field_severity_preserves_empty_string_breaking_change():
    assert determine_field_severity("description", "present", "") == "high"


def test_analyze_all_differences_summarizes_json_text_and_missing_files(tmp_path):
    analyzer = _make_analyzer(tmp_path)
    version_a_dir, version_b_dir = _make_version_dirs(tmp_path)

    _write_json(version_a_dir / "structure.json", {"name": "old", "elapsed_ms": 100})
    _write_json(version_b_dir / "structure.json", {"name": "new", "elapsed_ms": 90})
    (version_a_dir / "notes.txt").write_text("same\n", encoding="utf-8")
    (version_b_dir / "notes.txt").write_text("same\n", encoding="utf-8")
    (version_a_dir / "removed.txt").write_text("only in old\n", encoding="utf-8")
    (version_b_dir / "added.txt").write_text("only in new\n", encoding="utf-8")

    results = analyzer.analyze_all_differences()

    assert results["summary"]["total_files"] == 2
    assert results["summary"]["identical_files"] == 1
    assert results["summary"]["different_files"] == 1
    assert results["summary"]["breaking_changes"] == 1
    assert results["summary"]["performance_changes"] == 1
    assert results["missing_files"] == {
        "missing_in_b": ["removed.txt"],
        "missing_in_a": ["added.txt"],
    }


def test_generate_analysis_report_writes_expected_sections(tmp_path):
    analyzer = _make_analyzer(tmp_path)
    analysis_results = {
        "analysis_date": "2026-05-17T00:00:00",
        "version_a": "1.0.0",
        "version_b": "1.0.1",
        "summary": {
            "total_files": 1,
            "identical_files": 0,
            "different_files": 1,
            "breaking_changes": 1,
            "non_breaking_changes": 0,
            "performance_changes": 0,
        },
        "missing_files": {"missing_in_b": [], "missing_in_a": []},
        "file_analysis": {
            "structure.json": {
                "type": "json_comparison",
                "differences": [
                    {
                        "type": "key_removed",
                        "path": "name",
                        "old_value": "old",
                        "new_value": "new",
                        "severity": "high",
                    }
                ],
            }
        },
    }

    report_path = analyzer.generate_analysis_report(analysis_results)

    report_content = tmp_path.joinpath(report_path).read_text(encoding="utf-8")
    assert "差分分析レポート: v1.0.0 vs v1.0.1" in report_content
    assert "## 分析サマリー" in report_content
    assert "### structure.json" in report_content
    assert "#### 🚨 高重要度の変更:" in report_content
