"""Issue #1376：setup_schema 行为组，原测试 AST 保持不变。"""

from __future__ import annotations

import json

import pytest

from tests.unit._benchmark_harness_matrix_helpers import (
    TestCodeGraphCompareSetupGate as _TestCodeGraphCompareSetupGate,
)
from tests.unit._benchmark_harness_matrix_helpers import _v1_manifest, _v1_run


class TestCodeGraphCompareSetupGate(_TestCodeGraphCompareSetupGate):
    """Model-backed matrix work must be fail-closed behind setup validation."""

    def test_index_evidence_schema_version_requires_integer_one(self):
        from benchmarks.codegraph_compare.setup_validation import (
            parse_index_evidence_v1,
        )

        with pytest.raises(
            ValueError,
            match="Index evidence schema_version must be the integer 1",
        ):
            parse_index_evidence_v1({"schema_version": True, "cells": []})

    @pytest.mark.parametrize(
        ("field", "value"),
        (
            ("repo_id", 1),
            ("repo_id", ""),
            ("arm_id", 1),
            ("arm_id", ""),
        ),
    )
    def test_index_evidence_cell_ids_require_nonempty_strings(
        self,
        field: str,
        value: object,
    ):
        with pytest.raises(
            ValueError,
            match="Index evidence repo_id and arm_id must be strings",
        ):
            self._parse_v1_index_evidence(cell_overrides={field: value})

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        (
            (
                "eligible_source_files",
                "10",
                "Index evidence count and size fields must be integers",
            ),
            (
                "build_seconds",
                "1.0",
                "Index evidence build_seconds must be a finite number",
            ),
            (
                "build_seconds",
                float("nan"),
                "Index evidence build_seconds must be a finite number",
            ),
        ),
    )
    def test_index_evidence_numeric_fields_reject_strings(
        self,
        field: str,
        value: object,
        message: str,
    ):
        with pytest.raises(ValueError, match=message):
            self._parse_v1_index_evidence(stats_overrides={field: value})

    def test_index_evidence_rejects_integer_duration_too_large_for_float(self):
        with pytest.raises(
            ValueError,
            match="Index evidence build_seconds must be a finite number",
        ):
            self._parse_v1_index_evidence(stats_overrides={"build_seconds": 10**400})

    def test_index_evidence_provenance_fields_require_strings(self):
        with pytest.raises(
            ValueError,
            match="Index evidence provenance fields must be strings",
        ):
            self._parse_v1_index_evidence(stats_overrides={"repo_fingerprint": 1})

    @pytest.mark.parametrize(
        ("field", "value"),
        (
            ("indexed_paths", "main.go"),
            ("readiness_oracles", [1]),
        ),
    )
    def test_index_evidence_tuple_fields_require_string_lists(
        self,
        field: str,
        value: object,
    ):
        with pytest.raises(
            ValueError,
            match="Index evidence path and oracle fields must be string lists",
        ):
            self._parse_v1_index_evidence(stats_overrides={field: value})


class TestBenchmarkExperimentIntegrity:
    def test_manifest_id_is_stable_across_mapping_order(self):
        first = _v1_manifest(
            tool_fingerprints={"codegraph-warm": "cg141", "tsa-warm": "tsa130"}
        )
        second = _v1_manifest(
            tool_fingerprints={"tsa-warm": "tsa130", "codegraph-warm": "cg141"}
        )

        assert first.experiment_id == second.experiment_id

    def test_manifest_survives_real_json_round_trip(self):
        from dataclasses import asdict

        from benchmarks.codegraph_compare.integrity import parse_manifest_v1

        manifest = _v1_manifest()
        payload = json.loads(json.dumps(asdict(manifest)))

        parsed = parse_manifest_v1(payload)

        assert parsed == manifest

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        (
            (
                "benchmark_git_sha",
                1,
                "Manifest scalar fields do not match the V1 schema",
            ),
            (
                "seed",
                True,
                "Manifest integer fields do not match the V1 schema",
            ),
            (
                "retry_session_ids",
                "RS",
                "Manifest sequence fields do not match the V1 schema",
            ),
            (
                "expected_cells",
                {},
                "Manifest expected cells do not match the V1 schema",
            ),
            (
                "tool_fingerprints",
                {},
                "Manifest mapping fields do not match the V1 schema",
            ),
            (
                "eligible_paths",
                [["gin", "src/main.py"]],
                "Manifest nested fields do not match the V1 schema",
            ),
        ),
    )
    def test_manifest_parser_rejects_noncanonical_json_shapes(
        self,
        field: str,
        value: object,
        message: str,
    ):
        from dataclasses import asdict

        from benchmarks.codegraph_compare.integrity import parse_manifest_v1

        payload = json.loads(json.dumps(asdict(_v1_manifest())))
        payload[field] = value

        with pytest.raises(ValueError, match=message):
            parse_manifest_v1(payload)

    def test_manifest_constructor_requires_string_provenance(self):
        with pytest.raises(
            ValueError,
            match=("Manifest identity and provenance fields must be non-empty strings"),
        ):
            _v1_manifest(benchmark_git_sha=1)

    @pytest.mark.parametrize(
        ("field", "message"),
        (
            ("seed", "seed must be an integer"),
            ("timeout_seconds", "timeout_seconds must be a positive integer"),
        ),
    )
    def test_manifest_integer_fields_reject_booleans(self, field: str, message: str):
        with pytest.raises(ValueError, match=message):
            _v1_manifest(**{field: True})

    def test_expected_cell_repeat_rejects_boolean(self):
        from benchmarks.codegraph_compare.integrity import ExpectedCellV1

        with pytest.raises(
            ValueError,
            match="Expected cell repeat must be a non-negative integer",
        ):
            ExpectedCellV1(
                repo="gin",
                question_id="q1",
                arm="native-only",
                repeat=True,
                agent_backend="codex",
                run_id="q1__native-only__codex__01",
            )

    def test_expected_cell_identity_requires_strings(self):
        from benchmarks.codegraph_compare.integrity import ExpectedCellV1

        with pytest.raises(
            ValueError,
            match="Expected cell identity fields must be non-empty strings",
        ):
            ExpectedCellV1(
                repo=1,
                question_id="q1",
                arm="native-only",
                repeat=0,
                agent_backend="codex",
                run_id="q1__native-only__codex__00",
            )

    def test_manifest_rejects_required_arm_without_expected_cell(self):
        with pytest.raises(
            ValueError, match="Required arms must exactly match expected cell arms"
        ):
            _v1_manifest(
                expected_run_ids=("q1__tsa-warm__codex__00",),
                required_arms=("codegraph-warm", "tsa-warm"),
            )

    def test_manifest_rejects_empty_required_readiness_oracle(self):
        with pytest.raises(
            ValueError,
            match="Readiness oracles must exactly cover indexed arms",
        ):
            _v1_manifest(
                required_readiness_oracles={
                    "codegraph-warm": ("",),
                    "tsa-warm": ("known-symbol",),
                }
            )

    def test_index_stats_rejects_empty_supplied_readiness_oracle(self):
        from dataclasses import replace

        manifest = _v1_manifest()
        stats = _v1_run(
            manifest,
            "q1__codegraph-warm__codex__00",
        ).index_stats
        if stats is None:
            pytest.fail("indexed fixture must include V1 index statistics")

        with pytest.raises(
            ValueError,
            match=("Readiness oracle identifiers must be non-empty canonical strings"),
        ):
            replace(stats, readiness_oracles=("",))
