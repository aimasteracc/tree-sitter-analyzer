"""Independent-authority validation for E4 claim evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def _digest(value: Any) -> str | None:
    try:
        raw = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(raw).hexdigest()


def validate_e4_evidence(
    claim: dict[str, Any],
    evidence: Any,
    trusted_reproductions: Mapping[str, frozenset[str]],
    violations: list[str],
) -> None:
    """Require an externally admitted independent reproduction manifest for E4."""
    claim_id = claim["claim_id"]
    if (
        type(evidence) is not dict
        or set(evidence)
        != {"schema_version", "claim", "benchmark_manifest", "reproduction_manifest"}
        or evidence.get("schema_version") != 2
    ):
        violations.append(f"E4_EVIDENCE_MANIFEST_MISSING:{claim_id}")
        return
    benchmark = evidence.get("benchmark_manifest")
    provenance = claim["provenance"]
    if (
        type(benchmark) is not dict
        or set(benchmark)
        != {
            "schema_version",
            "benchmark_version",
            "repo_commit",
            "corpus_revision",
            "tsa",
            "competitor",
            "public_artifact_url",
        }
        or benchmark.get("schema_version") != 1
        or benchmark.get("benchmark_version") != provenance["benchmark_version"]
        or benchmark.get("repo_commit") != provenance["repo_commit"]
        or benchmark.get("corpus_revision") != provenance["corpus"]["revision"]
        or benchmark.get("tsa") != claim["tsa"]
        or benchmark.get("competitor") != claim["competitor"]
        or not isinstance(benchmark.get("public_artifact_url"), str)
        or not benchmark["public_artifact_url"].startswith("https://")
    ):
        violations.append(f"E4_BENCHMARK_PROVENANCE_INVALID:{claim_id}")
        return
    claim_payload = {
        key: claim[key]
        for key in (
            "claim_id",
            "metric",
            "numerator",
            "denominator",
            "unit",
            "tsa",
            "competitor",
            "provenance",
            "evidence_level",
        )
    }
    reproduction = evidence.get("reproduction_manifest")
    if (
        type(reproduction) is not dict
        or set(reproduction)
        != {
            "schema_version",
            "authority_id",
            "relationship",
            "benchmark_manifest_sha256",
            "claim_sha256",
            "numerator",
            "denominator",
            "unit",
            "public_reproduction_url",
        }
        or reproduction.get("schema_version") != 1
        or reproduction.get("relationship") != "independent-third-party"
        or reproduction.get("benchmark_manifest_sha256") != _digest(benchmark)
        or reproduction.get("claim_sha256") != _digest(claim_payload)
        or reproduction.get("numerator") != claim["numerator"]
        or reproduction.get("denominator") != claim["denominator"]
        or reproduction.get("unit") != claim["unit"]
        or not isinstance(reproduction.get("public_reproduction_url"), str)
        or not reproduction["public_reproduction_url"].startswith("https://")
    ):
        violations.append(f"E4_REPRODUCTION_PROVENANCE_INVALID:{claim_id}")
        return
    authority_id = reproduction.get("authority_id")
    digest = _digest(reproduction)
    if (
        not isinstance(authority_id, str)
        or digest is None
        or digest not in trusted_reproductions.get(authority_id, frozenset())
    ):
        violations.append(f"E4_AUTHORITY_UNTRUSTED:{claim_id}")
