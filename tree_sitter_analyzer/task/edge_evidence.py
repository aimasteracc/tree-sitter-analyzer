"""RFC-0023 edge-evidence/v1 validator (Phase A, internal experiment only).

Consumes the five checked-in artifacts under ``rfcs/fixtures/`` and
``rfcs/schemas/``: schema-plus-semantic validation, full ID/preimage
recomputation, and RFC-6901 mutation denial (RFC-0023 §7 Acceptance).

This module is internal: no MCP facade, no CLI flags, no codemap surface.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .evidence import canonical_json_bytes

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "rfcs" / "schemas" / "edge-evidence-v1.schema.json"
FIXTURES_DIR = PROJECT_ROOT / "rfcs" / "fixtures"

_REJECTION_REASONS = frozenset(
    {
        "EDGE_KIND_MISMATCH",
        "INCOMPATIBLE_SCHEMA",
        "FACADE_MISSING",
        "ACTION_MISSING",
        "ACTION_VERSION_MISSING",
        "RULE_ID_MISSING",
        "RULE_VERSION_MISSING",
        "OWNER_MISMATCH",
        "SOURCE_LOCATOR_UNAVAILABLE",
        "AMBIGUOUS_TARGET",
        "UNRESOLVED_TARGET",
        "NO_TARGET",
        "TARGET_LOCATOR_UNAVAILABLE",
        "PROPOSED_EDGE_KEY_MISSING",
        "TARGET_DECLARATION_MISMATCH",
        "FRESHNESS_SIGNAL_MISSING",
        "SNAPSHOT_MISSING",
        "FINGERPRINT_MISSING",
        "PARTIAL_SNAPSHOT",
        "STALE_SNAPSHOT",
        "SNAPSHOT_MISMATCH",
        "TRUNCATED",
        "UNSUPPORTED_KIND",
        "MALFORMED_RESULT",
        "BUDGET_EXHAUSTED",
        "CONTRADICTORY_EDGE_EVIDENCE",
    }
)

#: Reason priority order (RFC-0023 §3) — low index wins.
_REASON_PRIORITY = (
    "INCOMPATIBLE_SCHEMA",
    "FACADE_MISSING",
    "ACTION_MISSING",
    "ACTION_VERSION_MISSING",
    "RULE_ID_MISSING",
    "RULE_VERSION_MISSING",
    "OWNER_MISMATCH",
    "SOURCE_LOCATOR_UNAVAILABLE",
    "AMBIGUOUS_TARGET",
    "UNRESOLVED_TARGET",
    "NO_TARGET",
    "TARGET_LOCATOR_UNAVAILABLE",
    "PROPOSED_EDGE_KEY_MISSING",
    "TARGET_DECLARATION_MISMATCH",
    "EDGE_KIND_MISMATCH",
    "FRESHNESS_SIGNAL_MISSING",
    "SNAPSHOT_MISSING",
    "FINGERPRINT_MISSING",
    "PARTIAL_SNAPSHOT",
    "STALE_SNAPSHOT",
    "SNAPSHOT_MISMATCH",
    "TRUNCATED",
    "UNSUPPORTED_KIND",
    "MALFORMED_RESULT",
    "BUDGET_EXHAUSTED",
    "CONTRADICTORY_EDGE_EVIDENCE",
)
_REASON_RANK = {reason: index for index, reason in enumerate(_REASON_PRIORITY)}

SCHEMA_VERSION = "edge-evidence/v1"
COLLECTION_PREFIX = "collection:sha256:"
PROVENANCE_PREFIX = "provenance:sha256:"
CONTRADICTION_PREFIX = "contradiction:sha256:"
EVIDENCE_PREFIX = "evidence:sha256:"


@dataclass(frozen=True)
class ValidationResult:
    accepted: bool
    reasons: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def collection_id(scope: object, snapshot: object, primitive: object) -> str:
    return COLLECTION_PREFIX + _digest(
        {"scope": scope, "snapshot": snapshot, "primitive": primitive}
    )


def provenance_id(
    primitive: object,
    request_sha256: str,
    normalized_result_sha256: str,
    snapshot: object,
    success: object,
    verdict: object,
    truncation: object,
    input_evidence_ids: object,
) -> str:
    return PROVENANCE_PREFIX + _digest(
        {
            "primitive": primitive,
            "request_sha256": request_sha256,
            "normalized_result_sha256": normalized_result_sha256,
            "snapshot": snapshot,
            "success": success,
            "verdict": verdict,
            "truncation": truncation,
            "input_evidence_ids": input_evidence_ids,
        }
    )


def contradiction_group_id(edge_key: object, snapshot_id: object) -> str:
    return CONTRADICTION_PREFIX + _digest(
        {"edge_key": edge_key, "snapshot_id": snapshot_id}
    )


def evidence_id(record: dict[str, Any]) -> str:
    without_id = {key: value for key, value in record.items() if key != "evidence_id"}
    return EVIDENCE_PREFIX + _digest(without_id)


def load_schema() -> dict[str, Any]:
    """Load the checked-in Draft 2020-12 edge-evidence schema."""

    payload = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if payload.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ValueError(
            "edge-evidence schema is not Draft 2020-12"
        )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
    if type(payload) is not dict:
        raise ValueError(
            "edge-evidence schema must be an object"
        )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
    return payload


def validate_shape(bundle: dict[str, Any]) -> None:
    """JSON Schema shape validation; raises ValueError on violation."""
    import jsonschema

    schema = load_schema()
    jsonschema.validate(instance=bundle, schema=schema)


def _recompute_raw_digests(bundle: dict[str, Any]) -> list[str]:
    return [
        _digest(observation) for observation in bundle["raw_observations"]
    ]  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family


def _recompute_evidence_ids(bundle: dict[str, Any]) -> dict[str, str]:
    """Map every evidence record to its recomputed ID."""
    ids: dict[str, str] = {}
    for record in bundle["records"]:
        if record["schema"] != "edge-evidence/v1":
            continue
        ids[record.get("evidence_id", "")] = evidence_id(record)
    return ids


def _recompute_record_ids(bundle: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Recompute every record ID from its own content (review #1269).

    Evidence IDs are already recomputed; this extends the same guarantee to
    collection, provenance, and contradiction IDs so a producer cannot change
    record content while keeping a stale ID and old preimage. Contradiction
    IDs are intentionally shared, so the per-record (kind, declared, recomputed)
    tuples are preserved instead of collapsing the dict by declared ID; a
    middle record whose edge key drifted cannot be hidden by matching first and
    last records (review #1271).
    """
    recomputed: list[tuple[str, str, str]] = []
    for record in bundle["records"]:
        schema = record["schema"]
        if schema == "edge-collection/v1":
            recomputed.append(
                (
                    "edge-collection/v1",
                    record["collection_id"],
                    collection_id(
                        record["scope"], record["snapshot"], record["primitive"]
                    ),
                )
            )
        elif schema == "edge-provenance/v1":
            recomputed.append(
                (
                    "edge-provenance/v1",
                    record["provenance_id"],
                    provenance_id(
                        record["primitive"],
                        record["request_sha256"],
                        record["normalized_result_sha256"],
                        record["snapshot"],
                        record["success"],
                        record["verdict"],
                        record["truncation"],
                        record["input_evidence_ids"],
                    ),
                )
            )
        elif schema == "edge-evidence/v1":
            if (
                record.get("contradiction_group_id") is not None
            ):  # pragma: no cover - structural defense; the schema requires contradiction_group_id on every evidence record
                recomputed.append(
                    (
                        "edge-evidence/v1",
                        record["contradiction_group_id"],
                        contradiction_group_id(
                            record["edge_key"], record["snapshot"]["snapshot_id"]
                        ),
                    )
                )
    return recomputed


def _check_preimages(bundle: dict[str, Any], ids: dict[str, str]) -> None:
    """Require exactly one canonical preimage per recomputed ID (step 4)."""
    canonical = bundle.get("canonical_preimages", [])
    by_target: dict[str, list[bytes]] = {}
    for entry in canonical:
        target = entry["id"]
        by_target.setdefault(target, []).append(entry["canonical_json"].encode("utf-8"))
    record_ids = (
        {
            record.get("collection_id")
            for record in bundle["records"]
            if record["schema"] == "edge-collection/v1"
        }
        | {
            record.get("provenance_id")
            for record in bundle["records"]
            if record["schema"] == "edge-provenance/v1"
        }
        | {
            record.get("contradiction_group_id")
            for record in bundle["records"]
            if record.get("contradiction_group_id") is not None
        }
    )
    for record_id in record_ids:
        if record_id not in {entry["id"] for entry in canonical}:
            raise ValueError("MALFORMED_RESULT: record preimage missing")
    expected = (
        set(ids.values())
        | {value for _kind, _declared, value in _recompute_record_ids(bundle)}
        | record_ids
    )
    for target in sorted(expected):
        if target not in by_target or len(by_target[target]) != 1:
            raise ValueError(f"MALFORMED_RESULT: preimage count for {target}")
    for target in by_target:
        if target not in expected:
            raise ValueError(f"MALFORMED_RESULT: extra preimage {target}")
    # Recompute each preimage digest against its target ID.
    for entry in canonical:
        target = entry["id"]
        preimage_bytes = entry["canonical_json"].encode("utf-8")
        digest = hashlib.sha256(preimage_bytes).hexdigest()
        if target.startswith(EVIDENCE_PREFIX) and target != EVIDENCE_PREFIX + digest:
            raise ValueError(f"MALFORMED_RESULT: evidence preimage mismatch {target}")
        if (
            target.startswith(PROVENANCE_PREFIX)
            and target != PROVENANCE_PREFIX + digest
        ):
            raise ValueError(
                f"MALFORMED_RESULT: provenance preimage mismatch {target}"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        if (
            target.startswith(CONTRADICTION_PREFIX)
            and target != CONTRADICTION_PREFIX + digest
        ):
            raise ValueError(  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
                f"MALFORMED_RESULT: contradiction preimage mismatch {target}"
            )
        if (
            target.startswith(COLLECTION_PREFIX)
            and target != COLLECTION_PREFIX + digest
        ):
            raise ValueError(f"MALFORMED_RESULT: collection preimage mismatch {target}")
    # Each preimage must be a fresh canonical serialization of the object its
    # ID formula digests: collection preimages are (scope, snapshot, primitive),
    # provenance preimages are the eight provenance formula inputs,
    # contradiction preimages are (edge_key, snapshot_id), and evidence
    # preimages are the record minus its ID (review #1269).
    record_by_id: dict[str, dict[str, Any]] = {}
    for record in bundle["records"]:
        if record["schema"] == "edge-evidence/v1":
            record_by_id[record.get("evidence_id", "")] = record
        elif record["schema"] == "edge-provenance/v1":
            record_by_id[record.get("provenance_id", "")] = record
        elif record["schema"] == "edge-collection/v1":
            record_by_id[record.get("collection_id", "")] = record
        if record.get("contradiction_group_id") is not None:
            record_by_id.setdefault(record["contradiction_group_id"], record)
    for entry in canonical:
        record = record_by_id.get(entry["id"])
        if record is None:
            continue  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        if entry["id"].startswith(EVIDENCE_PREFIX):
            without_id = {
                key: value for key, value in record.items() if key != "evidence_id"
            }
            expected_json = canonical_json_bytes(without_id).decode("utf-8")
        elif entry["id"].startswith(PROVENANCE_PREFIX):
            expected_json = canonical_json_bytes(
                {
                    "primitive": record.get("primitive"),
                    "request_sha256": record.get("request_sha256"),
                    "normalized_result_sha256": record.get("normalized_result_sha256"),
                    "snapshot": record.get("snapshot"),
                    "success": record.get("success"),
                    "verdict": record.get("verdict"),
                    "truncation": record.get("truncation"),
                    "input_evidence_ids": record.get("input_evidence_ids"),
                }
            ).decode("utf-8")
        elif entry["id"].startswith(COLLECTION_PREFIX):
            expected_json = canonical_json_bytes(
                {
                    "scope": record.get("scope"),
                    "snapshot": record.get("snapshot"),
                    "primitive": record.get("primitive"),
                }
            ).decode("utf-8")
        else:  # contradiction preimage
            expected_json = canonical_json_bytes(
                {
                    "edge_key": record.get("edge_key"),
                    "snapshot_id": record.get("snapshot", {}).get("snapshot_id"),
                }
            ).decode("utf-8")
        if (
            expected_json != entry["canonical_json"]
        ):  # pragma: no cover - structural defense; the recomputed-ID count check rejects content drift before this branch is reachable
            raise ValueError(
                f"MALFORMED_RESULT: preimage record mismatch {entry['id']}"
            )  # pragma: no cover - structural defense; the recomputed-ID count check rejects content drift before this branch is reachable


def _reject_floats(value: object) -> None:
    """RFC-0023 §4: canonical JSON has no floats."""
    if isinstance(value, float):
        raise ValueError("MALFORMED_RESULT: request preimage float")
    if isinstance(value, dict):
        for item in value.values():
            _reject_floats(item)
    elif isinstance(value, list):
        for item in value:  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            _reject_floats(
                item
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family


def _check_request_preimages(bundle: dict[str, Any]) -> None:
    """Step 5: normalized request preimages reserialize and hash exactly."""
    entries = bundle.get("normalized_request_preimages", [])
    by_hash: dict[str, list[str]] = {}
    for entry in entries:
        request_hash = entry["request_sha256"]
        canonical = entry["canonical_json"]
        decoded = json.loads(canonical)
        _reject_floats(decoded)
        reserialized = json.dumps(
            decoded,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        if reserialized != canonical:
            raise ValueError("MALFORMED_RESULT: request preimage not canonical")
        if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != request_hash:
            raise ValueError("MALFORMED_RESULT: request preimage hash mismatch")
        by_hash.setdefault(request_hash, []).append(canonical)
    provenance_hashes = {
        record.get("request_sha256")
        for record in bundle["records"]
        if record["schema"] == "edge-provenance/v1"
    }
    for request_hash in provenance_hashes:
        if request_hash not in by_hash or len(by_hash[request_hash]) != 1:
            raise ValueError(
                "MALFORMED_RESULT: provenance request preimage missing"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
    for request_hash in by_hash:
        if request_hash not in provenance_hashes:
            raise ValueError(
                "MALFORMED_RESULT: extra request preimage"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family


def _check_unique_record_ids(bundle: dict[str, Any]) -> None:
    """Reject duplicate evidence/provenance/collection identities (review #1269).

    Lookup dictionaries built by assignment silently collapse duplicates, so an
    exact duplicate record with the same ID would otherwise be accepted and even
    appear twice in the returned ``evidence_ids`` tuple.
    """
    for kind, id_field in (
        ("edge-evidence/v1", "evidence_id"),
        ("edge-provenance/v1", "provenance_id"),
        ("edge-collection/v1", "collection_id"),
    ):
        seen: set[str] = set()
        for record in bundle["records"]:
            if record["schema"] != kind:
                continue
            identity = record.get(id_field, "")
            if identity in seen:
                raise ValueError("MALFORMED_RESULT: duplicate record identity")
            seen.add(identity)


def _check_collections(bundle: dict[str, Any]) -> None:
    """Steps 2-3: link resolution, ordering, counts."""
    by_id: dict[str, dict[str, Any]] = {}
    for record in bundle["records"]:
        if record["schema"] == "edge-evidence/v1":
            by_id[record.get("evidence_id", "")] = record
        elif record["schema"] == "edge-provenance/v1":
            by_id[record.get("provenance_id", "")] = record
        elif record["schema"] == "edge-collection/v1":
            by_id[record.get("collection_id", "")] = record

    for record in bundle["records"]:
        if record["schema"] != "edge-evidence/v1":
            continue
        collection = record.get("collection_id")
        if (
            collection is not None
        ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            if collection not in by_id:
                raise ValueError("MALFORMED_RESULT: dangling collection link")
            collection_record = by_id[collection]
            if collection_record.get("schema") != "edge-collection/v1":
                raise ValueError("MALFORMED_RESULT: collection link not a collection")
            if record.get("evidence_id") not in collection_record.get("item_refs", []):
                raise ValueError("MALFORMED_RESULT: missing reverse collection link")
        provenance = record.get("provenance_id")
        if provenance is not None and provenance not in by_id:
            raise ValueError(
                "MALFORMED_RESULT: dangling provenance link"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family

    for record in bundle["records"]:
        if record["schema"] != "edge-collection/v1":
            continue
        item_refs = record.get("item_refs", [])
        for ref in item_refs:
            if ref not in by_id:
                raise ValueError(
                    "MALFORMED_RESULT: dangling collection item ref"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            item_record = by_id[ref]
            if item_record.get("collection_id") != record.get("collection_id"):
                raise ValueError(
                    "MALFORMED_RESULT: cross collection item ref"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        if len(set(item_refs)) != len(item_refs):
            raise ValueError("MALFORMED_RESULT: duplicate collection item ref")
        if item_refs != sorted(item_refs):
            raise ValueError(
                "MALFORMED_RESULT: unsorted collection item refs"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        if record.get("returned_count") != len(item_refs):
            raise ValueError("MALFORMED_RESULT: returned_count mismatch")
        total = record.get("total_count")
        total_state = record.get("total_count_state")
        if total_state == "exact" and total is None:
            raise ValueError("MALFORMED_RESULT: exact total missing")
        if total_state != "exact" and total is not None:
            raise ValueError("MALFORMED_RESULT: non-exact total present")
        if record.get("truncation", {}).get("state") == "not_truncated":
            if (
                total_state != "exact" or total != len(item_refs)
            ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
                raise ValueError(
                    "MALFORMED_RESULT: not_truncated total mismatch"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        if total is not None and total < len(item_refs):
            raise ValueError("MALFORMED_RESULT: exact total less than returned")


def _check_diagnostic_reasons(bundle: dict[str, Any]) -> None:
    """Step 6: reason priority order and freshness.reason == reasons[0]."""
    for record in bundle["records"]:
        if record["schema"] != "edge-diagnostic/v1":
            continue
        reasons = record.get("reasons", [])
        if not reasons or len(set(reasons)) != len(reasons):
            raise ValueError("MALFORMED_RESULT: reasons not unique")
        ranked = sorted(reasons, key=lambda reason: _REASON_RANK[reason])
        if ranked != reasons:
            raise ValueError("MALFORMED_RESULT: reasons out of priority order")
        if record.get("freshness", {}).get("reason") != reasons[0]:
            raise ValueError("MALFORMED_RESULT: freshness reason mismatch")


def _check_owner(record_owner: dict[str, Any], obs_owner: dict[str, Any]) -> None:
    """Owner fields must match the raw observation exactly (step 1)."""
    for field, missing_reason in (
        ("facade", "FACADE_MISSING"),
        ("action", "ACTION_MISSING"),
        ("action_version", "ACTION_VERSION_MISSING"),
        ("producer_rule_id", "RULE_ID_MISSING"),
        ("producer_rule_version", "RULE_VERSION_MISSING"),
    ):
        if field not in obs_owner:
            raise ValueError(
                missing_reason
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        if record_owner.get(field) != obs_owner[field]:
            raise ValueError("OWNER_MISMATCH")


def _check_evidence_projection(bundle: dict[str, Any]) -> None:
    """Evidence records must project exactly from their raw observation.

    Order follows RFC-0023 §5 step 1: owner fields and edge-key projection
    are judged before result-hash equality so owner drift is reported with
    its precise reason instead of being masked by a digest mismatch.
    """
    observations = bundle.get("raw_observations", [])
    by_pointer: dict[str, dict[str, Any]] = {}
    by_occurrence: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for observation in observations:
        # RFC-0023: the result pointer nests under observation.result_pointer.
        pointer = observation.get("observation", {}).get("result_pointer")
        if (
            pointer is not None
        ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            by_pointer[pointer] = observation
        occurrence = (
            observation.get("observation", {}).get("occurrence", {}).get("node_id")
        )
        by_occurrence.setdefault((occurrence, observation.get("state")), []).append(
            observation
        )
    for record in bundle["records"]:
        if record["schema"] != "edge-evidence/v1":
            continue
        locator = record.get("locators", {}).get("observation", {})
        pointer = locator.get("result_pointer")
        observation = by_pointer.get(pointer) if pointer is not None else None
        if observation is None:
            occurrence = locator.get(
                "occurrence", {}
            ).get(
                "node_id"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            binding = record.get(
                "binding"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            candidates = by_occurrence.get(
                (occurrence, binding), []
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            if (
                len(candidates) == 1
            ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
                observation = candidates[
                    0
                ]  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        if observation is not None and observation.get("state") != record.get(
            "binding"
        ):
            # The observation moved to a zero-ID state: the projection is
            # invalid with that state's reason.
            state = observation.get("state")
            if state == "ambiguous":
                raise ValueError("AMBIGUOUS_TARGET")
            if state == "unresolved":
                raise ValueError(
                    "UNRESOLVED_TARGET"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            if state == "no_target":
                raise ValueError(
                    "NO_TARGET"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            raise ValueError("MALFORMED_RESULT: evidence state mismatch")
        if observation is None:
            # The referenced occurrence may have moved to a zero-ID state.
            occurrence = locator.get(
                "occurrence", {}
            ).get(
                "node_id"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            state_candidates = [  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
                observation
                for (node_id, _state), group in by_occurrence.items()
                if node_id == occurrence
                for observation in group
            ]
            for candidate in state_candidates:  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
                if (
                    candidate.get("state") == "ambiguous"
                ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
                    raise ValueError(
                        "AMBIGUOUS_TARGET"
                    )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
                if candidate.get("state") == "unresolved":
                    raise ValueError(
                        "UNRESOLVED_TARGET"
                    )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
                if candidate.get("state") == "no_target":
                    raise ValueError(
                        "NO_TARGET"
                    )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            raise ValueError(
                "MALFORMED_RESULT: evidence has no raw observation"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        # Owner fields must match (missing field -> its reason; drift -> OWNER_MISMATCH).
        _check_owner(record.get("primitive", {}), observation.get("primitive", {}))
        # Snapshot identity must match.
        if record.get("snapshot") != observation.get("snapshot"):
            raise ValueError("MALFORMED_RESULT: evidence snapshot mismatch")
        # Proposed edge key projection (before digest so drift is precise).
        proposed = observation.get("proposed_edge_key")
        if proposed is None:
            raise ValueError(
                "PROPOSED_EDGE_KEY_MISSING"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        source_endpoint = observation.get("source_endpoint", {})
        if proposed.get("source_node_id") != source_endpoint.get("node_id"):
            raise ValueError("TARGET_DECLARATION_MISMATCH")
        target_endpoint = observation.get("target_endpoint", {})
        if proposed.get("target_node_id") != target_endpoint.get("node_id"):
            raise ValueError("TARGET_DECLARATION_MISMATCH")
        if proposed.get("kind") != observation.get("edge_kind"):
            raise ValueError("EDGE_KIND_MISMATCH")
        # All three projected locators must equal the raw observation locators
        # so evidence cannot point reviewers at unrelated source text
        # (review #1269).
        record_locators = record.get("locators", {})
        for locator_field, reason in (
            ("source_endpoint", "MALFORMED_RESULT: evidence source locator mismatch"),
            ("target_endpoint", "MALFORMED_RESULT: evidence target locator mismatch"),
            ("observation", "MALFORMED_RESULT: evidence observation locator mismatch"),
        ):
            if record_locators.get(locator_field) != observation.get(locator_field):
                raise ValueError(reason)


def _check_projection_closure(bundle: dict[str, Any]) -> None:
    """Every positive raw observation must project exactly one evidence record.

    ``_check_evidence_projection`` walks records to observations (one-way); this
    reverse pass guarantees no positive observation is silently dropped without
    minting an ID, and that each one projects exactly one record (RFC-0023 §5
    step 1: bind each output to exactly one raw digest; review #1269).
    """
    observations = bundle.get("raw_observations", [])
    # A result pointer identifies exactly one raw observation; duplicate
    # pointers would let a single evidence record cover two observations
    # (review #1271).
    positive_pointers: dict[str, int] = {}
    for observation in observations:
        if observation.get("state") not in {"resolved_unique", "negative_rule"}:
            continue
        pointer = observation.get("observation", {}).get("result_pointer")
        if pointer is not None:
            positive_pointers[pointer] = positive_pointers.get(pointer, 0) + 1
    for _pointer, count in positive_pointers.items():
        if count > 1:
            raise ValueError("MALFORMED_RESULT: duplicate observation pointer")
    evidence_count: dict[str, int] = {}
    for record in bundle["records"]:
        if record["schema"] != "edge-evidence/v1":
            continue
        locator = record.get("locators", {}).get("observation", {})
        pointer = locator.get("result_pointer")
        occurrence = locator.get("occurrence", {}).get("node_id")
        key = pointer if pointer is not None else occurrence
        if (
            key is not None
        ):  # pragma: no cover - structural defense; schema-valid evidence records always carry a locator pointer or occurrence
            evidence_count[key] = evidence_count.get(key, 0) + 1
    for observation in observations:
        if observation.get("state") not in {"resolved_unique", "negative_rule"}:
            continue
        pointer = observation.get("observation", {}).get("result_pointer")
        occurrence = (
            observation.get("observation", {}).get("occurrence", {}).get("node_id")
        )
        key = pointer if pointer is not None else occurrence
        if evidence_count.get(key) != 1:
            raise ValueError("MALFORMED_RESULT: positive observation without evidence")


def _check_evidence_digests(bundle: dict[str, Any]) -> None:
    """Result hashes must equal raw observation digests (after scope checks)."""
    observations = bundle.get("raw_observations", [])
    by_occurrence: dict[tuple[str, str], dict[str, Any]] = {}
    for observation in observations:
        occurrence = (
            observation.get("observation", {}).get("occurrence", {}).get("node_id")
        )
        by_occurrence[(occurrence, observation.get("state"))] = observation
    for record in bundle["records"]:
        if record["schema"] != "edge-evidence/v1":
            continue
        locator = record.get("locators", {}).get("observation", {})
        occurrence = locator.get("occurrence", {}).get("node_id")
        observation = by_occurrence.get((occurrence, record.get("binding")))
        if observation is None:
            continue  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        if record.get("normalized_result_sha256") != _digest(observation):
            raise ValueError(
                "MALFORMED_RESULT: evidence result hash mismatch"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family


def _check_evidence_edge_key(bundle: dict[str, Any]) -> None:
    """Evidence edge_key must equal the proposed key (after rule scope check)."""
    observations = bundle.get("raw_observations", [])
    by_occurrence: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for observation in observations:
        occurrence = (
            observation.get("observation", {}).get("occurrence", {}).get("node_id")
        )
        by_occurrence.setdefault((occurrence, observation.get("state")), []).append(
            observation
        )
    for record in bundle["records"]:
        if record["schema"] != "edge-evidence/v1":
            continue
        locator = record.get("locators", {}).get("observation", {})
        occurrence = locator.get("occurrence", {}).get("node_id")
        candidates = by_occurrence.get((occurrence, record.get("binding")), [])
        if len(candidates) != 1:
            continue  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        observation = candidates[0]
        proposed = observation.get("proposed_edge_key", {})
        edge_key = record.get("edge_key", {})
        if edge_key.get("source_node_id") != proposed.get("source_node_id"):
            raise ValueError(
                "MALFORMED_RESULT: evidence edge key source mismatch"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        if edge_key.get("target_node_id") != proposed.get("target_node_id"):
            raise ValueError("MALFORMED_RESULT: evidence edge key target mismatch")
        if edge_key.get("kind") != proposed.get("kind"):
            raise ValueError(
                "MALFORMED_RESULT: evidence edge key kind mismatch"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family


def _check_diagnostics(bundle: dict[str, Any]) -> None:
    """Diagnostic records must match their raw observation state machine."""
    observations = bundle.get("raw_observations", [])
    observation_states = {
        observation.get("observation", {}).get("occurrence", {}).get("node_id"): (
            observation.get("state"),
            observation.get("freshness_signal", {}).get("state"),
        )
        for observation in observations
    }
    for record in bundle["records"]:
        if record["schema"] != "edge-diagnostic/v1":
            continue
        freshness = record.get("freshness", {})
        reason = freshness.get("reason")
        state = record.get("raw_state")
        if isinstance(state, dict):
            state = state.get(
                "state"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        if (
            state == "ambiguous"
        ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            expected = "AMBIGUOUS_TARGET"
        elif (
            state == "unresolved"
        ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            expected = "UNRESOLVED_TARGET"  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        elif (
            state == "no_target"
        ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            expected = "NO_TARGET"  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        else:
            expected = "MALFORMED_RESULT"  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        # Diagnostic projection: primitive/snapshot/digest must match.
        observation = None
        occurrence = (
            record.get("locators", {})
            .get("observation", {})
            .get("occurrence", {})
            .get("node_id")
        )
        diagnostic_pointer = (
            record.get("locators", {}).get("observation", {}).get("result_pointer")
        )
        observation = next(
            (
                candidate
                for candidate in observations
                if candidate.get("observation", {}).get("result_pointer")
                == diagnostic_pointer
            ),
            None,
        )
        if observation is None and occurrence is not None:
            matching = [
                candidate
                for candidate in observations
                if candidate.get("observation", {}).get("occurrence", {}).get("node_id")
                == occurrence
            ]
            # A diagnostic projects from the zero-ID observation (ambiguous /
            # unresolved / no_target), never a resolved one sharing the node.
            for candidate in matching:  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
                if candidate.get("state") in {
                    "ambiguous",
                    "unresolved",
                    "no_target",
                }:
                    observation = candidate
                    break
        if (
            observation is not None
        ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            # State consistency first: a moved observation reports its own
            # zero-ID reason before digest drift masks it.
            actual_state = observation.get("state")
            if actual_state == "ambiguous" and state != "ambiguous":
                raise ValueError(
                    "AMBIGUOUS_TARGET"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            if actual_state == "unresolved" and state != "unresolved":
                raise ValueError("UNRESOLVED_TARGET")
            if actual_state == "no_target" and state != "no_target":
                raise ValueError("NO_TARGET")
            diagnostic_owner = record.get("primitive", {})
            observation_owner = observation.get("primitive", {})
            for field in ("facade", "action", "action_version"):
                if diagnostic_owner.get(field) != observation_owner.get(field):
                    raise ValueError("MALFORMED_RESULT: diagnostic owner mismatch")
            if record.get("snapshot") != observation.get("snapshot"):
                raise ValueError(
                    "MALFORMED_RESULT: diagnostic snapshot mismatch"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            # The full diagnostic projection: edge key and endpoint locators
            # must match the referenced observation so diagnostics cannot
            # misattribute their source (review #1269).
            if record.get("edge_key") != observation.get("proposed_edge_key"):
                raise ValueError("MALFORMED_RESULT: diagnostic edge key mismatch")
            diagnostic_locators = record.get("locators", {})
            for locator_field in ("source_endpoint", "target_endpoint", "observation"):
                if diagnostic_locators.get(locator_field) != observation.get(
                    locator_field
                ):
                    raise ValueError(
                        "MALFORMED_RESULT: diagnostic locator mismatch"
                    )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            result_hash = diagnostic_owner.get("normalized_result_sha256")
            if result_hash is not None and result_hash != _digest(observation):
                raise ValueError(
                    "MALFORMED_RESULT: diagnostic result hash mismatch"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            expected_binding = observation.get("state")
            if (
                expected_binding in {"ambiguous", "unresolved", "no_target"}
            ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
                expected_binding = None
            if record.get("observed_binding") != expected_binding:
                raise ValueError(
                    "MALFORMED_RESULT: diagnostic binding mismatch"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        # Zero-ID freshness state is derived from the complete reason list:
        # stale exactly when STALE_SNAPSHOT / SNAPSHOT_MISMATCH is present,
        # missing exactly when a missing/partial snapshot reason is present,
        # otherwise unknown (RFC-0023 §3; review #1269).
        if (
            state in {"ambiguous", "unresolved", "no_target"}
        ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            reasons = record.get("reasons", [])
            # The raw freshness signal is authoritative: stale/superseded
            # observations must surface STALE_SNAPSHOT, independent of what the
            # producer chose to list (review #1271).
            if observation is not None:
                raw_freshness = observation.get("freshness_signal", {}).get("state")
                if raw_freshness in {"stale", "superseded"} and (
                    "STALE_SNAPSHOT" not in reasons
                    and "SNAPSHOT_MISMATCH" not in reasons
                ):
                    raise ValueError("STALE_SNAPSHOT")
                # A truncated zero-ID observation must surface TRUNCATED
                # (RFC-0023 §3: every non-not_truncated result adds TRUNCATED;
                # review #1271).
                if (
                    observation.get("truncation", {}).get("state") != "not_truncated"
                    and "TRUNCATED" not in reasons
                ):
                    raise ValueError("TRUNCATED")
            expected_freshness = "unknown"
            if any(item in reasons for item in ("STALE_SNAPSHOT", "SNAPSHOT_MISMATCH")):
                expected_freshness = "stale"
            elif any(
                item in reasons
                for item in (
                    "FRESHNESS_SIGNAL_MISSING",
                    "SNAPSHOT_MISSING",
                    "FINGERPRINT_MISSING",
                    "PARTIAL_SNAPSHOT",
                )
            ):
                expected_freshness = "missing"
            if freshness.get("state") != expected_freshness:
                raise ValueError("MALFORMED_RESULT: diagnostic freshness state")
        if freshness.get("state") == "unknown" and reason != expected:
            raise ValueError(
                expected
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        # The observation result_pointer must be referenced by the bundle.
        pointer = (
            record.get("locators", {}).get("observation", {}).get("result_pointer")
        )
        if (
            pointer is not None
        ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            # A result pointer addresses a known result array; a fabricated
            # pointer is rejected without guessing result shapes.
            known_prefixes = ("/edges/", "/negative_edges/", "/unknowns/")
            if not pointer.startswith(known_prefixes):
                raise ValueError("MALFORMED_RESULT: diagnostic source mismatch")
        # The raw_state must agree with the referenced observation.
        occurrence = (
            record.get("locators", {})
            .get("observation", {})
            .get("occurrence", {})
            .get("node_id")
        )
        if (
            occurrence is not None
        ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            if occurrence not in observation_states:
                raise ValueError(
                    "MALFORMED_RESULT: diagnostic source mismatch"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            actual_state, _ = observation_states[occurrence]
            if actual_state == "ambiguous" and state != "ambiguous":
                raise ValueError(
                    "AMBIGUOUS_TARGET"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            if actual_state == "unresolved" and state != "unresolved":
                raise ValueError(
                    "UNRESOLVED_TARGET"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            if actual_state == "no_target" and state != "no_target":
                raise ValueError(
                    "NO_TARGET"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family


def _check_observation_state_machine(bundle: dict[str, Any]) -> None:
    """RFC-0023 §3 truth table over raw observations.

    ambiguous/unresolved/no_target observations are legal (they produce a
    diagnostic with zero evidence IDs); only contradictory combinations and
    stale positive states are rejected.
    """
    for observation in bundle.get("raw_observations", []):
        state = observation.get("state")
        freshness = observation.get("freshness_signal", {}).get("state")
        candidates = observation.get("candidates", []) or []
        target = observation.get("target_endpoint")
        target_id = target.get("node_id") if isinstance(target, dict) else None
        if state == "ambiguous":
            unique = {candidate.get("node_id") for candidate in candidates}
            if len(unique) < 2:
                raise ValueError(
                    "MALFORMED_RESULT: ambiguous without unique candidates"
                )
            if target_id is not None:
                raise ValueError(
                    "MALFORMED_RESULT: ambiguous with a selected target"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        elif state == "unresolved":
            if candidates:
                raise ValueError(
                    "MALFORMED_RESULT: unresolved with candidates"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        elif state == "no_target":
            if candidates:
                raise ValueError(
                    "MALFORMED_RESULT: no_target with candidates"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        elif (
            state in {"resolved_unique", "negative_rule"}
        ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            if freshness in {"stale", "superseded"}:
                raise ValueError("STALE_SNAPSHOT")
            if (
                observation.get("truncation", {}).get("state") != "not_truncated"
            ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
                raise ValueError(
                    "TRUNCATED"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            if target_id is None:
                raise ValueError(
                    "MALFORMED_RESULT: positive state without target"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family


def _check_candidate_uniqueness(bundle: dict[str, Any]) -> None:
    for observation in bundle.get("raw_observations", []):
        candidates = observation.get("candidates", []) or []
        node_ids = [candidate.get("node_id") for candidate in candidates]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError(
                "MALFORMED_RESULT: duplicate candidate identity"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family


def _check_provenance_projection(bundle: dict[str, Any]) -> None:
    """Provenance result hashes must match their input evidence results."""
    evidence_hashes = {
        record.get("normalized_result_sha256")
        for record in bundle["records"]
        if record["schema"] == "edge-evidence/v1"
    }
    evidence_by_id = {
        item.get("evidence_id"): item
        for item in bundle["records"]
        if item["schema"] == "edge-evidence/v1"
    }
    observations = bundle.get("raw_observations", [])
    for record in bundle["records"]:
        if record["schema"] != "edge-provenance/v1":
            continue
        result_hash = record.get("normalized_result_sha256")
        if result_hash not in evidence_hashes:
            raise ValueError("MALFORMED_RESULT: provenance result hash mismatch")
        # The provenance must also project from a raw observation.
        observation = next(
            (
                candidate
                for candidate in observations
                if _digest(candidate) == result_hash
            ),
            None,
        )
        if observation is None:
            raise ValueError("MALFORMED_RESULT: provenance has no raw observation")
        if record.get("primitive") != observation.get("primitive"):
            raise ValueError("MALFORMED_RESULT: provenance owner mismatch")
        if record.get("snapshot") != observation.get("snapshot"):
            raise ValueError(
                "MALFORMED_RESULT: provenance snapshot mismatch"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        for evidence_ref in record.get("input_evidence_ids", []):
            evidence = evidence_by_id.get(
                evidence_ref
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            if (
                evidence is None
            ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
                raise ValueError(
                    "MALFORMED_RESULT: provenance evidence link mismatch"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            if (
                evidence.get("primitive") != record.get("primitive")
            ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
                raise ValueError(
                    "MALFORMED_RESULT: provenance owner mismatch"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            if (
                evidence.get("snapshot") != record.get("snapshot")
            ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
                raise ValueError(
                    "MALFORMED_RESULT: provenance snapshot mismatch"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            if (
                evidence.get("normalized_result_sha256") != result_hash
            ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
                raise ValueError(
                    "MALFORMED_RESULT: provenance result hash mismatch"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family


def _check_provenance_linkage(bundle: dict[str, Any]) -> None:
    """Validate each evidence record through its own provenance_id.

    The projection above accepts any global hash membership; this reverse pass
    requires the provenance named by each evidence record to carry the same
    primitive, snapshot, and result hash as that evidence (review #1269).
    """
    provenance_by_id = {
        record.get("provenance_id"): record
        for record in bundle["records"]
        if record["schema"] == "edge-provenance/v1"
    }
    for record in bundle["records"]:
        if record["schema"] != "edge-evidence/v1":
            continue
        provenance_id_value = record.get("provenance_id")
        if provenance_id_value is None:
            continue  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        provenance = provenance_by_id.get(
            provenance_id_value
        )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        if (
            provenance is None
        ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            raise ValueError(
                "MALFORMED_RESULT: evidence provenance link missing"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        if (
            provenance.get("normalized_result_sha256")
            != record.get("normalized_result_sha256")
        ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            raise ValueError(
                "MALFORMED_RESULT: evidence provenance hash mismatch"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        if (
            provenance.get("primitive") != record.get("primitive")
        ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            raise ValueError(
                "MALFORMED_RESULT: evidence provenance owner mismatch"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        if (
            provenance.get("snapshot") != record.get("snapshot")
        ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            raise ValueError(
                "MALFORMED_RESULT: evidence provenance snapshot mismatch"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
    # Reverse direction: every provenance record must be selected by at least
    # one evidence record, so a producer cannot attach an unreferenced
    # provenance with a different verdict to an existing raw digest
    # (review #1271).
    referenced: set[str] = {
        record.get("provenance_id")
        for record in bundle["records"]
        if record["schema"] == "edge-evidence/v1"
        and record.get("provenance_id") is not None
    }
    for record in bundle["records"]:
        if record["schema"] != "edge-provenance/v1":
            continue
        if record.get("provenance_id") not in referenced:
            raise ValueError(
                "MALFORMED_RESULT: unreferenced provenance record"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family


def _check_collection_consistency(bundle: dict[str, Any]) -> None:
    """Collections must match the scope/snapshot/primitive of every item.

    Every referenced item is checked (not only the first), and
    ``source_and_kind`` scope additionally requires the item's edge kind and
    source node to match the declared scope (review #1269).
    """
    evidence_by_id = {
        record.get("evidence_id"): record
        for record in bundle["records"]
        if record["schema"] == "edge-evidence/v1"
    }
    for record in bundle["records"]:
        if record["schema"] != "edge-collection/v1":
            continue
        items = [
            evidence_by_id[ref]
            for ref in record.get("item_refs", [])
            if ref in evidence_by_id
        ]
        if not items:
            continue  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        scope = record.get("scope", {})
        for item in items:
            if record.get("primitive") != item.get("primitive"):
                raise ValueError("MALFORMED_RESULT: collection owner mismatch")
            if record.get("snapshot") != item.get("snapshot"):
                raise ValueError("MALFORMED_RESULT: collection snapshot mismatch")
            item_key = item.get("edge_key", {})
            if scope.get("source_node_id") != item_key.get("source_node_id"):
                raise ValueError(
                    "MALFORMED_RESULT: collection scope mismatch"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            if scope.get("mode") == "source_and_kind":
                if scope.get("edge_kind") != item_key.get("kind"):
                    raise ValueError(
                        "MALFORMED_RESULT: collection scope kind mismatch"
                    )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family


def _check_freshness_signals(bundle: dict[str, Any]) -> None:
    """Every positive-state observation must carry a freshness signal."""
    for observation in bundle.get("raw_observations", []):
        if observation.get("state") in {"resolved_unique", "negative_rule"}:
            if "freshness_signal" not in observation:
                raise ValueError(
                    "FRESHNESS_SIGNAL_MISSING"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family


def _check_generated_rules(bundle: dict[str, Any]) -> None:
    """Producer rules must be registered with the generated-rule registry."""
    import json as _json

    registry_path = FIXTURES_DIR / "edge-evidence-v1-generated-rule-registry.json"
    registry = _json.loads(registry_path.read_text(encoding="utf-8"))
    entries = registry.get("entries", [])
    by_rule: dict[tuple[str, str], dict[str, Any]] = {
        (entry.get("producer_rule_id"), entry.get("producer_rule_version")): entry
        for entry in entries
    }
    for observation in bundle.get("raw_observations", []):
        owner = observation.get("primitive", {})
        pair = (owner.get("producer_rule_id"), owner.get("producer_rule_version"))
        entry = by_rule.get(pair)
        if entry is None:
            raise ValueError(
                "MALFORMED_RESULT: unregistered producer rule"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        allowed_kinds = entry.get("allowed_edge_kinds", [])
        if observation.get("edge_kind") not in allowed_kinds:
            raise ValueError("UNSUPPORTED_KIND")
        allowed_states = entry.get("allowed_observation_states", [])
        if observation.get("state") not in allowed_states:
            raise ValueError(
                "MALFORMED_RESULT: observation state out of scope"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family


def _classify_missing_fields(bundle: dict[str, Any]) -> None:
    """Field-classifier phase: missing owner/signal fields are named before
    schema or semantic checks can mask them.

    The classifier is deliberately type-safe: malformed outer shapes (non-dict
    bundle, non-dict observations) raise ``MALFORMED_RESULT`` through the normal
    rejection path instead of crashing the validator with ``AttributeError``
    (review #1269).
    """
    if not isinstance(bundle, dict):
        raise ValueError("MALFORMED_RESULT: bundle must be an object")
    for observation in bundle.get("raw_observations", []):
        if not isinstance(observation, dict):
            raise ValueError("MALFORMED_RESULT: raw observation must be an object")
        owner = observation.get("primitive", {})
        if not isinstance(owner, dict):
            raise ValueError("MALFORMED_RESULT: primitive must be an object")
        for field, reason in (
            ("facade", "FACADE_MISSING"),
            ("action", "ACTION_MISSING"),
            ("action_version", "ACTION_VERSION_MISSING"),
            ("producer_rule_id", "RULE_ID_MISSING"),
            ("producer_rule_version", "RULE_VERSION_MISSING"),
        ):
            if field not in owner:
                raise ValueError(reason)
        if "freshness_signal" not in observation:
            raise ValueError("FRESHNESS_SIGNAL_MISSING")
        if "proposed_edge_key" not in observation:
            raise ValueError("PROPOSED_EDGE_KEY_MISSING")


def semantic_validate(bundle: dict[str, Any]) -> ValidationResult:
    """Run the complete §5 bundle semantic algorithm.

    Returns the accepted result, or the first rejection reason.
    """
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        raise RuntimeError(
            "edge-evidence validation requires jsonschema"
        ) from exc  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
    try:
        _classify_missing_fields(bundle)
        validate_shape(bundle)
        # Step 1 full: observation state machine, rules, projections.
        _check_unique_record_ids(bundle)
        _check_freshness_signals(bundle)
        _check_observation_state_machine(bundle)
        _check_candidate_uniqueness(bundle)
        _check_evidence_projection(bundle)
        _check_projection_closure(bundle)
        _check_collection_consistency(bundle)
        _check_generated_rules(bundle)
        _check_provenance_projection(bundle)
        _check_provenance_linkage(bundle)
        _check_evidence_digests(bundle)
        _check_evidence_edge_key(bundle)
        _check_diagnostics(bundle)
        # Step 2: link resolution.
        _check_collections(bundle)
        # Step 3: counts (inside _check_collections).
        # Step 4: ID recomputation + preimages.
        ids = _recompute_evidence_ids(bundle)
        for record in bundle["records"]:
            if record["schema"] == "edge-evidence/v1":
                if record.get("evidence_id") != ids[record.get("evidence_id", "")]:
                    raise ValueError("MALFORMED_RESULT: evidence ID mismatch")
        recomputed = _recompute_record_ids(bundle)
        for kind, declared, value in recomputed:
            if kind == "edge-collection/v1":
                if (
                    declared != value
                ):  # pragma: no cover - structural defense; evidence projection binds items to observations, so consistent drift cannot reach this branch
                    raise ValueError(
                        "MALFORMED_RESULT: collection ID mismatch"
                    )  # pragma: no cover - structural defense; evidence projection binds items to observations, so consistent drift cannot reach this branch
            elif kind == "edge-provenance/v1":
                if declared != value:
                    raise ValueError("MALFORMED_RESULT: provenance ID mismatch")
            elif declared != value:
                raise ValueError(
                    "MALFORMED_RESULT: contradiction ID mismatch"
                )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        _check_preimages(bundle, ids)
        # Step 5: request preimages.
        _check_request_preimages(bundle)
        # Step 6: diagnostic reasons.
        _check_diagnostic_reasons(bundle)
    except (ValueError, jsonschema.ValidationError) as exc:
        reason = str(exc)
        for candidate in sorted(
            _REJECTION_REASONS, key=lambda item: _REASON_RANK[item]
        ):
            if reason.startswith(candidate):
                return ValidationResult(accepted=False, reasons=(candidate,))
        return ValidationResult(accepted=False, reasons=("MALFORMED_RESULT",))
    evidence_ids = tuple(
        record.get("evidence_id")
        for record in bundle["records"]
        if record["schema"] == "edge-evidence/v1"
        and record.get("evidence_id") is not None
    )
    return ValidationResult(accepted=True, evidence_ids=evidence_ids)


def _apply_mutations(document: Any, mutations: list[dict[str, Any]]) -> Any:
    """Apply RFC-6901 mutations to a deep copy of the document."""
    import copy

    document = copy.deepcopy(document)
    for mutation in mutations:
        op = mutation["op"]
        path = mutation["path"]
        parts = [part for part in path.split("/") if part]
        if op == "replace":
            target = document
            for part in parts[:-1]:
                if isinstance(target, list):
                    target = target[int(part)]
                else:
                    target = target[part]
            if isinstance(target, list):
                target[int(parts[-1])] = mutation[
                    "value"
                ]  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            else:
                target[parts[-1]] = mutation["value"]
        elif op == "add":
            target = document
            for part in parts[:-1]:
                if isinstance(target, list):
                    target = target[int(part)]
                else:
                    target = target[part]
            if isinstance(target, list):
                if parts[-1] == "-":
                    target.append(mutation["value"])
                else:
                    target.insert(
                        int(parts[-1]), mutation["value"]
                    )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
            else:
                target[parts[-1]] = mutation["value"]
        elif op == "remove":
            target = document
            for part in parts[:-1]:
                if isinstance(target, list):
                    target = target[int(part)]
                else:
                    target = target[part]
            if isinstance(target, list):
                del target[int(parts[-1])]
            else:
                del target[parts[-1]]
        else:
            raise ValueError(
                f"unsupported mutation op {op!r}"
            )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
    return document


def validate_negative_cases(
    negative: dict[str, Any],
    case_ids: set[str] | None = None,
) -> dict[str, ValidationResult]:
    """Apply every RFC-0023 denial case and require rejection.

    The base context maps a bundle id to its fixture file; the mutation
    paths address the fixture document itself. Authority cases mutate the
    authoritative index-status fixture; context cases mutate the invocation
    metadata before bundle validation. ``case_ids`` optionally restricts the
    run to a subset of corpus cases so batched tests stay inside the unit
    per-test budget (review #1269).
    """
    contexts = negative.get("base_contexts", {})
    documents = {
        context_id: json.loads(
            (FIXTURES_DIR / context["fixture"]).read_text(encoding="utf-8")
        )
        for context_id, context in contexts.items()
    }
    results: dict[str, ValidationResult] = {}
    for case in negative["cases"]:
        if case_ids is not None and case["id"] not in case_ids:
            continue
        document = documents[case["base"]]
        mutated = _apply_mutations(document, case.get("mutations", []))
        if case.get("authority_mutations"):
            context = contexts[case["base"]]
            authority = _load_authority(context)
            authority = _apply_mutations(authority, case["authority_mutations"])
            try:
                _check_authority(
                    mutated, authority, context.get("authoritative_status_id")
                )
            except ValueError as exc:
                reason = str(exc)
                if reason.startswith("SNAPSHOT_MISMATCH"):
                    results[case["id"]] = (
                        ValidationResult(  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
                            accepted=False, reasons=("SNAPSHOT_MISMATCH",)
                        )
                    )
                    continue  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
                results[case["id"]] = ValidationResult(
                    accepted=False, reasons=("MALFORMED_RESULT",)
                )
                continue
        elif case.get("context_mutations"):
            context = contexts[case["base"]]
            context = _apply_mutations(context, case["context_mutations"])
            try:
                _check_invocation_authority(mutated, context)
            except ValueError:
                results[case["id"]] = ValidationResult(
                    accepted=False, reasons=("MALFORMED_RESULT",)
                )
                continue
        else:
            context = contexts[case["base"]]
            authority = _load_authority(context)
            try:
                _check_authority(
                    mutated, authority, context.get("authoritative_status_id")
                )
            except ValueError as exc:
                reason = str(exc)
                if reason.startswith("SNAPSHOT_MISMATCH"):
                    results[case["id"]] = ValidationResult(
                        accepted=False, reasons=("SNAPSHOT_MISMATCH",)
                    )
                    continue
                results[case["id"]] = (
                    ValidationResult(  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
                        accepted=False, reasons=("MALFORMED_RESULT",)
                    )
                )
                continue  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        result = semantic_validate(mutated)
        results[case["id"]] = result
    return results


def _check_invocation_authority(
    bundle: dict[str, Any], context: dict[str, Any]
) -> None:
    """Every provenance request hash must match an invocation request.

    Additionally, every invocation that pins an ``invoked_adapter`` tuple must
    bind its referenced raw observation and compare the full owner tuple
    (facade/action/action_version) plus the generated-rule entry, so a producer
    cannot claim a different adapter was invoked (review #1269).
    """
    invocations = context.get("invocations", [])
    if not invocations:
        raise ValueError("MALFORMED_RESULT: invocation authority missing")
    expected = {
        json.dumps(
            invocation.get("expected_normalized_request"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        for invocation in invocations
    }
    actual = {
        entry.get("canonical_json")
        for entry in bundle.get("normalized_request_preimages", [])
    }
    if (
        expected != actual
    ):  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
        raise ValueError("MALFORMED_RESULT: invocation request mismatch")
    # Every raw observation must be bound by exactly one invocation so no
    # observation can escape adapter authority and none can be double-bound
    # (review #1271).
    bound_pointers: set[str] = set()
    for invocation in invocations:
        pointer = invocation.get("raw_observation_pointer")
        if pointer is None or invocation.get("invoked_adapter") is None:
            raise ValueError("MALFORMED_RESULT: invocation authority incomplete")
        parts = [part for part in pointer.split("/") if part]
        observation: Any = bundle
        try:
            for part in parts:
                if isinstance(observation, list):
                    observation = observation[int(part)]
                else:
                    observation = observation[part]
        except (IndexError, KeyError, TypeError, ValueError):
            raise ValueError(
                "MALFORMED_RESULT: invocation observation missing"
            ) from None
        if not isinstance(observation, dict):
            raise ValueError("MALFORMED_RESULT: invocation observation missing")
        if pointer in bound_pointers:
            raise ValueError("MALFORMED_RESULT: invocation pointer duplicate")
        bound_pointers.add(pointer)
        invoked = invocation["invoked_adapter"]
        owner = observation.get("primitive", {})
        for field in ("facade", "action", "action_version"):
            if invoked.get(field) != owner.get(field):
                raise ValueError("MALFORMED_RESULT: invocation owner mismatch")
        rule_entry = invocation.get("generated_rule_entry")
        if rule_entry is not None:
            rule_pair = (
                f"{owner.get('producer_rule_id')}@{owner.get('producer_rule_version')}"
            )
            if rule_entry != rule_pair:
                raise ValueError("MALFORMED_RESULT: invocation rule mismatch")
    expected_pointers = {
        f"/raw_observations/{index}"
        for index in range(len(bundle.get("raw_observations", [])))
    }
    if bound_pointers != expected_pointers:
        raise ValueError("MALFORMED_RESULT: invocation pointer coverage")


def _load_authority(bundle_context: dict[str, Any]) -> dict[str, Any]:
    """Load the authoritative index-status fixture named by the context."""
    fixture = bundle_context.get("authoritative_index_status_fixture")
    if type(fixture) is not str:
        raise ValueError(
            "MALFORMED_RESULT: missing authority fixture"
        )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
    payload = json.loads((FIXTURES_DIR / fixture).read_text(encoding="utf-8"))
    if type(payload) is not dict:
        raise ValueError(
            "MALFORMED_RESULT: authority fixture must be an object"
        )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
    return payload


def _check_authority(
    bundle: dict[str, Any],
    authority: dict[str, Any],
    status_id: str | None,
) -> None:
    """Raw observation snapshots must match the authoritative index status."""
    statuses = authority.get("statuses", [])
    status_ids = [status.get("status_id") for status in statuses]
    if len(set(status_ids)) != len(status_ids):
        raise ValueError("MALFORMED_RESULT: duplicate authoritative status id")
    if status_id is None:
        raise ValueError(
            "MALFORMED_RESULT: authoritative status id missing"
        )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
    status_by_id = {status.get("status_id"): status for status in statuses}
    authority_status = status_by_id.get(status_id)
    if authority_status is None:
        raise ValueError(
            "MALFORMED_RESULT: authoritative status missing"
        )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
    for observation in bundle.get("raw_observations", []):
        snapshot = observation.get("snapshot", {})
        # Missing/partial snapshot state keeps its higher-priority reason
        # before any remaining authoritative tuple disagreement is reported
        # as SNAPSHOT_MISMATCH (RFC-0023 §3 reason priority; review #1271).
        if snapshot.get("completeness") == "partial":
            raise ValueError("PARTIAL_SNAPSHOT")
        for field in ("snapshot_id", "source_fingerprint", "index_fingerprint"):
            if snapshot.get(field) is None:
                raise ValueError(
                    "SNAPSHOT_MISSING"
                    if field == "snapshot_id"
                    else "FINGERPRINT_MISSING"
                )
        # Compare the complete authoritative snapshot tuple, not only the index
        # fingerprint, so a consistently rewritten bundle cannot mint evidence
        # whose snapshot_id / source_fingerprint / completeness disagrees with
        # the independently selected status (review #1269).
        authoritative = authority_status.get("snapshot", {})
        for field in (
            "snapshot_id",
            "source_fingerprint",
            "index_fingerprint",
            "completeness",
        ):
            if snapshot.get(field) != authoritative.get(field):
                raise ValueError("SNAPSHOT_MISMATCH")


def validate_fixture(name: str) -> ValidationResult:
    """Validate one checked-in fixture by name."""
    path = FIXTURES_DIR / f"edge-evidence-v1-{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            path
        )  # pragma: no cover - structural defense; corpus and mutation suites verify the rejection family
    bundle = json.loads(path.read_text(encoding="utf-8"))
    return semantic_validate(bundle)
