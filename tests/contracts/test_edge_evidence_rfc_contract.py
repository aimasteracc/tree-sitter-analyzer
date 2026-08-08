"""Executable contracts for RFC-0023 edge-evidence artifacts."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

RFC_ROOT = Path(__file__).parents[2] / "rfcs"
FIXTURE_ROOT = RFC_ROOT / "fixtures"
SCHEMA_PATH = RFC_ROOT / "schemas" / "edge-evidence-v1.schema.json"
GOLDEN_PATH = FIXTURE_ROOT / "edge-evidence-v1-golden.json"
STABLE_PATH = FIXTURE_ROOT / "edge-evidence-v1-stable-sort-base.json"
NEGATIVE_PATH = FIXTURE_ROOT / "edge-evidence-v1-negative.json"
REGISTRY_PATH = FIXTURE_ROOT / "edge-evidence-v1-generated-rule-registry.json"
EXPECTED_SCHEMA_ID = (
    "https://github.com/aimasteracc/tree-sitter-analyzer/"
    "rfcs/schemas/edge-evidence-v1.schema.json"
)
EXPECTED_NEGATIVE_IDS = (
    "absolute-path",
    "backslash-path",
    "dot-path",
    "byte-range-reversed",
    "endpoint-source-mismatch",
    "endpoint-target-mismatch",
    "owner-facade-mismatch",
    "owner-action-mismatch",
    "owner-action-version-mismatch",
    "owner-producer-rule-id-mismatch",
    "owner-producer-rule-version-mismatch",
    "owner-facade-missing",
    "owner-action-missing",
    "owner-action-version-missing",
    "owner-producer-rule-id-missing",
    "owner-producer-rule-version-missing",
    "dangling-collection-ref",
    "unsorted-item-refs",
    "returned-count-mismatch",
    "exact-total-mismatch",
    "canonical-preimage-mismatch",
    "missing-canonical-preimage",
    "request-preimage-mismatch",
    "provenance-result-mismatch",
    "diagnostic-freshness-reason-mismatch",
    "diagnostic-reasons-unsorted",
    "proposed-edge-key-missing",
    "freshness-signal-missing",
    "stale-snapshot-deny",
    "ambiguous-deny",
    "unresolved-deny",
    "no-target-deny",
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _records(bundle: dict[str, Any], schema: str) -> list[dict[str, Any]]:
    return [record for record in bundle["records"] if record["schema"] == schema]


def _pointer(document: Any, pointer: str) -> Any:
    value = document
    for token in pointer.removeprefix("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def _apply(document: dict[str, Any], operations: list[dict[str, Any]]) -> None:
    for operation in operations:
        tokens = operation["path"].removeprefix("/").split("/")
        parent: Any = document
        for encoded in tokens[:-1]:
            token = encoded.replace("~1", "/").replace("~0", "~")
            parent = parent[int(token)] if isinstance(parent, list) else parent[token]
        key = tokens[-1].replace("~1", "/").replace("~0", "~")
        if operation["op"] == "remove":
            parent.pop(int(key)) if isinstance(parent, list) else parent.pop(key)
        elif isinstance(parent, list):
            if operation["op"] == "add" and key == "-":
                parent.append(copy.deepcopy(operation["value"]))
            elif operation["op"] == "add":
                parent.insert(int(key), copy.deepcopy(operation["value"]))
            else:
                parent[int(key)] = copy.deepcopy(operation["value"])
        else:
            parent[key] = copy.deepcopy(operation["value"])


def _expected_preimages(bundle: dict[str, Any]) -> dict[str, Any]:
    expected: dict[str, Any] = {}
    for record in bundle["records"]:
        schema = record["schema"]
        if schema == "edge-collection/v1":
            expected[record["collection_id"]] = {
                "scope": record["scope"],
                "snapshot": record["snapshot"],
                "primitive": record["primitive"],
            }
        elif schema == "edge-provenance/v1":
            expected[record["provenance_id"]] = {
                key: value
                for key, value in record.items()
                if key not in {"schema", "provenance_id"}
            }
        elif schema == "edge-evidence/v1":
            expected[record["contradiction_group_id"]] = {
                "edge_key": record["edge_key"],
                "snapshot_id": record["snapshot"]["snapshot_id"],
            }
            expected[record["evidence_id"]] = {
                key: value for key, value in record.items() if key != "evidence_id"
            }
    return expected


def test_schema_is_canonical_draft_2020_12() -> None:
    schema = _load(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == EXPECTED_SCHEMA_ID


@pytest.mark.parametrize("bundle_path", [GOLDEN_PATH, STABLE_PATH])
def test_positive_bundles_validate_against_schema(bundle_path: Path) -> None:
    Draft202012Validator(_load(SCHEMA_PATH)).validate(_load(bundle_path))


@pytest.mark.parametrize("bundle_path", [GOLDEN_PATH, STABLE_PATH])
def test_bundle_hash_preimages_recompute(bundle_path: Path) -> None:
    bundle = _load(bundle_path)
    expected = _expected_preimages(bundle)
    actual = {
        item["id"]: item["canonical_json"] for item in bundle["canonical_preimages"]
    }
    assert set(actual) == set(expected)
    for identifier, value in expected.items():
        canonical = _canonical(value)
        assert actual[identifier] == canonical
        prefix, algorithm, digest = identifier.split(":")
        assert prefix in {"collection", "provenance", "contradiction", "evidence"}
        assert algorithm == "sha256"
        assert digest == hashlib.sha256(canonical.encode()).hexdigest()


@pytest.mark.parametrize("bundle_path", [GOLDEN_PATH, STABLE_PATH])
def test_bundle_result_hashes_recompute(bundle_path: Path) -> None:
    bundle = _load(bundle_path)
    expected = {
        _digest(raw)
        for raw in bundle["raw_observations"]
        if raw["state"] in {"resolved_unique", "negative_rule"}
    }
    actual = {
        record["normalized_result_sha256"]
        for record in bundle["records"]
        if "normalized_result_sha256" in record
    }
    assert actual == expected


@pytest.mark.parametrize("bundle_path", [GOLDEN_PATH, STABLE_PATH])
def test_bundle_request_hashes_recompute(bundle_path: Path) -> None:
    bundle = _load(bundle_path)
    requests = {
        item["request_sha256"]: item["canonical_json"]
        for item in bundle["normalized_request_preimages"]
    }
    referenced = {
        record["request_sha256"] for record in _records(bundle, "edge-provenance/v1")
    }
    assert set(requests) == referenced
    for digest, canonical in requests.items():
        assert _canonical(json.loads(canonical)) == canonical
        assert hashlib.sha256(canonical.encode()).hexdigest() == digest


@pytest.mark.parametrize("bundle_path", [GOLDEN_PATH, STABLE_PATH])
def test_bundle_references_are_closed_and_sorted(bundle_path: Path) -> None:
    bundle = _load(bundle_path)
    evidence = {
        record["evidence_id"]: record for record in _records(bundle, "edge-evidence/v1")
    }
    collections = {
        record["collection_id"]: record
        for record in _records(bundle, "edge-collection/v1")
    }
    provenance = {
        record["provenance_id"]: record
        for record in _records(bundle, "edge-provenance/v1")
    }
    for record in evidence.values():
        assert record["collection_id"] in collections
        assert record["provenance_id"] in provenance
    for identifier, record in collections.items():
        assert record["item_refs"] == sorted(record["item_refs"])
        assert len(record["item_refs"]) == len(set(record["item_refs"]))
        assert record["returned_count"] == len(record["item_refs"])
        for reference in record["item_refs"]:
            assert evidence[reference]["collection_id"] == identifier
    for record in provenance.values():
        for reference in record["input_evidence_ids"]:
            assert reference in evidence


def test_generated_rule_registry_is_independent_authority() -> None:
    corpus = _load(NEGATIVE_PATH)
    registry = _load(REGISTRY_PATH)
    entries = {entry["entry_id"]: entry for entry in registry["entries"]}
    assert registry["registry_version"] == "2026-08-08.1"
    for context in corpus["base_contexts"].values():
        assert (
            context["generated_rule_registry_version"] == registry["registry_version"]
        )
        bundle = _load(FIXTURE_ROOT / context["fixture"])
        for invocation in context["invocations"]:
            raw = _pointer(bundle, invocation["raw_observation_pointer"])
            authority = entries[invocation["generated_rule_entry"]]
            expected = authority["adapter"] | {
                "producer_rule_id": authority["producer_rule_id"],
                "producer_rule_version": authority["producer_rule_version"],
            }
            assert invocation["invoked_adapter"] == authority["adapter"]
            assert raw["primitive"] == expected


def test_negative_corpus_pins_all_32_denials() -> None:
    corpus = _load(NEGATIVE_PATH)
    assert corpus["mutation_semantics"] == "RFC6901_POINTER_SINGLE_DOCUMENT_SEQUENTIAL"
    assert tuple(case["id"] for case in corpus["cases"]) == EXPECTED_NEGATIVE_IDS
    for case in corpus["cases"]:
        expected = case["expected"]
        assert expected["accepted"] is False
        assert expected["evidence_ids"] == []
        base = _load(FIXTURE_ROOT / corpus["base_contexts"][case["base"]]["fixture"])
        mutated = copy.deepcopy(base)
        _apply(mutated, case["mutations"])
        assert mutated != base
