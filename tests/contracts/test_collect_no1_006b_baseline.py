"""Contracts for the NO1-006B bounded baseline collector."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

from scripts import collect_no1_006b_baseline as collector

REPO = Path(__file__).parents[2]
BASELINE = REPO / "docs/baselines/no1-006b-macos-e0.json"
SCHEMA = REPO / "schemas/no1-006b-baseline.schema.json"


def _baseline() -> dict[str, object]:
    return json.loads(BASELINE.read_text())


def test_checked_in_baseline_matches_strict_schema() -> None:
    jsonschema.validate(_baseline(), json.loads(SCHEMA.read_text()))


def test_checked_in_baseline_hash_covers_canonical_report() -> None:
    report = _baseline()
    expected = report.pop("report_sha256")
    actual = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert actual == expected


def test_baseline_is_bound_to_measured_origin_develop_commit() -> None:
    assert _baseline()["source"]["commit"] == collector.EXPECTED_COMMIT


def test_baseline_dependency_counts_are_exact() -> None:
    measurements = _baseline()["measurements"]
    assert [
        measurements["direct_dependency_count"],
        measurements["transitive_dependency_count"],
        measurements["installed_distribution_count"],
    ] == [33, 38, 72]


def test_baseline_cross_platform_axes_remain_unknown() -> None:
    assert _baseline()["platform_axes"] == {
        "linux": "unknown",
        "macos": "measured_e0",
        "windows": "unknown",
    }


def test_baseline_retains_exact_number_of_warm_samples() -> None:
    report = _baseline()
    measurements = report["measurements"]
    assert [
        len(measurements["cli_startup"]["warm_ms"]),
        len(measurements["mcp_startup"]["warm_ms"]),
    ] == [report["repeats"], report["repeats"]]


def test_collector_rejects_unbounded_repeat_count(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="repeats must be between 3 and 20"):
        collector.collect(REPO, tmp_path / "report.json", 21, collector.EXPECTED_COMMIT)


def test_collector_canonical_hash_ignores_existing_hash_field() -> None:
    report = {"schema_version": 1, "report_sha256": "stale"}
    assert collector.canonical_hash(report) == collector.canonical_hash(
        {"schema_version": 1}
    )
