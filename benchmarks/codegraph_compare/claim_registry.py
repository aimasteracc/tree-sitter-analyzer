"""Fail-closed validator for provenance-bound quantitative claims.

This is an internal benchmark CLI, not a TSA public CLI or MCP surface.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

from benchmarks.codegraph_compare.e4_evidence import (
    generated_e4_wording,
    unsafe_e4_fields,
    validate_e4_evidence,
)

_LEVELS = {"E0": 0, "E1": 1, "E2": 2, "E3": 3, "E4": 4}
# E4 trust roots are deliberately outside claim-controlled artifacts.  A future
# authority is admitted only by adding its independently supplied reproduction
# manifest digest here through normal code review; registry edits cannot create
# or expand this trust set.
_TRUSTED_E4_REPRODUCTIONS: Mapping[str, frozenset[str]] = {}
_README_CLAIMS_BEGIN = "<!-- BEGIN GENERATED QUANTITATIVE CLAIMS -->"
_README_CLAIMS_END = "<!-- END GENERATED QUANTITATIVE CLAIMS -->"

_CLAIM_ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_CLAIM_FIELDS = frozenset(
    {
        "claim_id",
        "status",
        "metric",
        "numerator",
        "denominator",
        "unit",
        "tsa",
        "competitor",
        "provenance",
        "repositories",
        "model_backend",
        "evidence_level",
        "artifact",
    }
)


def _release_shape_violation(registry: Any) -> str | None:
    """Protect release invariants even when a caller supplies a weak schema."""
    if type(registry) is not dict or set(registry) != {"schema_version", "claims"}:
        return "REGISTRY_RELEASE_SHAPE"
    if registry.get("schema_version") != 1:
        return "REGISTRY_RELEASE_SCHEMA_VERSION"
    claims = registry.get("claims")
    if type(claims) is not list or not claims:
        return "REGISTRY_RELEASE_EMPTY"
    for claim in claims:
        if type(claim) is not dict or set(claim) != _CLAIM_FIELDS:
            return "CLAIM_RELEASE_SHAPE"
        if not isinstance(claim.get("claim_id"), str) or not _CLAIM_ID_RE.fullmatch(
            claim["claim_id"]
        ):
            return "CLAIM_RELEASE_ID"
        if claim.get("status") not in {"verified", "unverified", "blocked"}:
            return "CLAIM_RELEASE_STATUS"
        if claim.get("evidence_level") not in _LEVELS:
            return "CLAIM_RELEASE_EVIDENCE_LEVEL"
        for tool_name in ("tsa", "competitor"):
            tool = claim.get(tool_name)
            if type(tool) is not dict or set(tool) != {"name", "version"}:
                return "CLAIM_RELEASE_TOOL_SHAPE"
        model_backend = claim.get("model_backend")
        if model_backend is not None and (
            type(model_backend) is not dict
            or set(model_backend) != {"model", "backend"}
        ):
            return "CLAIM_RELEASE_MODEL_BACKEND_SHAPE"
        provenance = claim.get("provenance")
        if type(provenance) is not dict or set(provenance) != {
            "benchmark_version",
            "repo_commit",
            "corpus",
            "measurement_date",
        }:
            return "CLAIM_RELEASE_PROVENANCE_SHAPE"
        corpus = provenance.get("corpus")
        if type(corpus) is not dict or set(corpus) != {"name", "revision"}:
            return "CLAIM_RELEASE_CORPUS_SHAPE"
        artifact = claim.get("artifact")
        if artifact is not None and (
            type(artifact) is not dict
            or set(artifact) != {"path", "sha256"}
            or not isinstance(artifact.get("path"), str)
            or not isinstance(artifact.get("sha256"), str)
        ):
            return "CLAIM_RELEASE_ARTIFACT_SHAPE"
    return None


@dataclass(frozen=True)
class ClaimRegistryVerdict:
    status: str
    schema_valid: bool
    publishable: bool
    claim_count: int
    verified_count: int
    blocked_count: int
    violations: tuple[str, ...]
    emittable_wording: tuple[tuple[str, tuple[str, ...]], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocked_count": self.blocked_count,
            "claim_count": self.claim_count,
            "emittable_wording": [
                {"claim_id": claim_id, "wording": list(wording)}
                for claim_id, wording in self.emittable_wording
            ],
            "publishable": self.publishable,
            "schema_valid": self.schema_valid,
            "status": self.status,
            "verified_count": self.verified_count,
            "violations": list(self.violations),
        }


def _reject_nonfinite_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json_loads(value: str | bytes) -> Any:
    """Decode standards-compliant JSON without non-finite values or duplicate keys."""
    return json.loads(
        value,
        parse_constant=_reject_nonfinite_constant,
        object_pairs_hook=_reject_duplicate_keys,
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic JSON bytes and reject NaN/non-JSON values."""
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("value is not canonical JSON") from error
    return encoded.encode("utf-8")


def _evidence_payload(claim: dict[str, Any]) -> dict[str, Any]:
    return {
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
            "repositories",
            "model_backend",
            "evidence_level",
        )
    }


def _safe_artifact_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("artifact path must be relative and cannot traverse parents")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError("artifact path escapes artifacts root")
    return resolved


def _missing_verified_provenance(claim: dict[str, Any]) -> tuple[str, ...]:
    provenance = claim["provenance"]
    fields = {
        "tsa.version": claim["tsa"]["version"],
        "competitor.version": claim["competitor"]["version"],
        "provenance.benchmark_version": provenance["benchmark_version"],
        "provenance.repo_commit": provenance["repo_commit"],
        "provenance.corpus.revision": provenance["corpus"]["revision"],
        "provenance.measurement_date": provenance["measurement_date"],
        "repositories": claim["repositories"],
        "model_backend": claim["model_backend"],
    }
    return tuple(name for name, value in fields.items() if value is None)


def render_readme_claims(verdict: ClaimRegistryVerdict) -> str:
    """Render only a whole-registry publishable verdict."""
    lines = [_README_CLAIMS_BEGIN]
    if verdict.publishable:
        for _, wording in verdict.emittable_wording:
            lines.extend(f"- {claim}" for claim in wording)
    lines.append(_README_CLAIMS_END)
    return "\n".join(lines)


def readme_claim_violations(
    readme: str, verdict: ClaimRegistryVerdict
) -> tuple[str, ...]:
    """Reject malformed exclusions and unregistered quantitative marketing."""
    from benchmarks.codegraph_compare.readme_claim_scanner import scan_readme_claims

    return scan_readme_claims(readme, render_readme_claims(verdict))


def _validate_artifact(
    claim: dict[str, Any],
    artifacts_root: Path,
    violations: list[str],
    trusted_reproductions: Mapping[str, frozenset[str]],
) -> None:
    claim_id = claim["claim_id"]
    artifact = claim["artifact"]
    try:
        path = _safe_artifact_path(artifacts_root, artifact["path"])
    except ValueError as error:
        violations.append(f"ARTIFACT_PATH_INVALID:{claim_id}:{error}")
        return
    if not path.is_file():
        violations.append(f"ARTIFACT_MISSING:{claim_id}")
        return
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
        violations.append(f"ARTIFACT_SHA256_MISMATCH:{claim_id}")
        return
    try:
        evidence = strict_json_loads(raw)
    except (UnicodeDecodeError, ValueError):
        violations.append(f"ARTIFACT_JSON_INVALID:{claim_id}")
        return
    if type(evidence) is not dict or evidence.get("claim") != _evidence_payload(claim):
        violations.append(f"STALE_OR_MIXED_PROVENANCE:{claim_id}")
        return
    if claim["evidence_level"] == "E4":
        validate_e4_evidence(claim, evidence, trusted_reproductions, violations)
    elif (
        set(evidence) != {"schema_version", "claim"}
        or evidence.get("schema_version") != 1
    ):
        violations.append(f"STALE_OR_MIXED_PROVENANCE:{claim_id}")


def validate_registry(
    registry: Any,
    *,
    schema: dict[str, Any],
    artifacts_root: Path,
) -> ClaimRegistryVerdict:
    """Validate a registry and release wording only after every gate passes."""
    try:
        Draft202012Validator.check_schema(schema)
        schema_errors = sorted(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
                registry
            ),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
    except SchemaError as error:
        return ClaimRegistryVerdict(
            "INVALID",
            False,
            False,
            0,
            0,
            0,
            (f"SCHEMA_DEFINITION:{error.message}",),
            (),
        )
    if schema_errors:
        schema_violations = tuple(
            "SCHEMA:"
            + "/".join(str(part) for part in error.absolute_path)
            + ":"
            + error.message
            for error in schema_errors
        )
        return ClaimRegistryVerdict(
            "INVALID", False, False, 0, 0, 0, schema_violations, ()
        )

    release_violation = _release_shape_violation(registry)
    if release_violation is not None:
        claim_count = (
            len(registry.get("claims", [])) if isinstance(registry, dict) else 0
        )
        return ClaimRegistryVerdict(
            "INVALID",
            True,
            False,
            claim_count,
            0,
            0,
            (release_violation,),
            (),
        )

    claims = registry["claims"]
    authority_roots = _TRUSTED_E4_REPRODUCTIONS
    violations: list[str] = []
    identifiers = [claim["claim_id"] for claim in claims]
    if len(identifiers) != len(set(identifiers)):
        violations.append("DUPLICATE_CLAIM_ID")

    verified = 0
    blocked = 0
    safe_wording: list[tuple[str, tuple[str, ...]]] = []
    for claim in claims:
        claim_id = claim["claim_id"]
        status = claim["status"]
        claim_violations: list[str] = []
        if status == "verified":
            verified += 1
            measurement_invalid = False
            if claim["numerator"] is None or claim["denominator"] is None:
                claim_violations.append(f"MEASUREMENT_MISSING:{claim_id}")
                measurement_invalid = True
            else:
                for field in ("numerator", "denominator"):
                    value = claim[field]
                    if type(value) not in (int, float) or not math.isfinite(value):
                        claim_violations.append(
                            f"MEASUREMENT_NONFINITE:{claim_id}:{field}"
                        )
                        measurement_invalid = True
                if not measurement_invalid and claim["denominator"] <= 0:
                    claim_violations.append(f"DENOMINATOR_NONPOSITIVE:{claim_id}")
                    measurement_invalid = True
            missing = _missing_verified_provenance(claim)
            if missing:
                claim_violations.append(
                    f"PROVENANCE_MISSING:{claim_id}:" + ",".join(missing)
                )
            if _LEVELS[claim["evidence_level"]] < 2:
                claim_violations.append(f"QUANTITATIVE_EVIDENCE_TOO_LOW:{claim_id}")
            unsafe_fields: tuple[str, ...] = ()
            if claim["evidence_level"] == "E4":
                unsafe_fields = unsafe_e4_fields(claim)
                if unsafe_fields:
                    claim_violations.append(
                        f"E4_FIELD_UNSAFE:{claim_id}:" + ",".join(unsafe_fields)
                    )
            if claim["artifact"] is None:
                claim_violations.append(f"ARTIFACT_MISSING:{claim_id}")
            elif not measurement_invalid and not unsafe_fields:
                _validate_artifact(
                    claim, artifacts_root, claim_violations, authority_roots
                )
        else:
            blocked += 1
            if claim["numerator"] is not None or claim["denominator"] is not None:
                claim_violations.append(f"UNVERIFIED_MEASUREMENT_PRESENT:{claim_id}")
            if claim["artifact"] is not None:
                claim_violations.append(f"UNVERIFIED_ARTIFACT_PRESENT:{claim_id}")
        violations.extend(claim_violations)
        if (
            not claim_violations
            and status == "verified"
            and claim["evidence_level"] == "E4"
        ):
            safe_wording.append((claim_id, (generated_e4_wording(claim),)))

    if violations:
        status = "INVALID"
    elif blocked:
        status = "BLOCKED"
    else:
        status = "VALID"
    publishable = (
        status == "VALID"
        and verified == len(claims)
        and all(claim["evidence_level"] == "E4" for claim in claims)
    )
    return ClaimRegistryVerdict(
        status,
        True,
        publishable,
        len(claims),
        verified,
        blocked,
        tuple(violations),
        tuple(safe_wording) if publishable else (),
    )


def load_and_validate(
    registry_path: Path, *, schema_path: Path, artifacts_root: Path | None = None
) -> ClaimRegistryVerdict:
    try:
        registry = strict_json_loads(registry_path.read_text(encoding="utf-8"))
        schema = strict_json_loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        return ClaimRegistryVerdict(
            "INVALID", False, False, 0, 0, 0, (f"INPUT:{error}",), ()
        )
    return validate_registry(
        registry,
        schema=schema,
        artifacts_root=artifacts_root or registry_path.parent,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    module_dir = Path(__file__).resolve().parent
    parser.add_argument("registry", type=Path)
    parser.add_argument(
        "--schema", type=Path, default=module_dir / "claim_registry.schema.json"
    )
    parser.add_argument("--artifacts-root", type=Path)
    args = parser.parse_args(argv)
    verdict = load_and_validate(
        args.registry, schema_path=args.schema, artifacts_root=args.artifacts_root
    )
    print(canonical_json_bytes(verdict.to_dict()).decode("ascii"))
    return 0 if verdict.publishable else 2


if __name__ == "__main__":
    raise SystemExit(main())
