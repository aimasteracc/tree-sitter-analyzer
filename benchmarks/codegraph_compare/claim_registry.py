"""Fail-closed validator for provenance-bound quantitative claims.

This is an internal benchmark CLI, not a TSA public CLI or MCP surface.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

_LEVELS = {"E0": 0, "E1": 1, "E2": 2, "E3": 3, "E4": 4}
_README_CLAIMS_BEGIN = "<!-- BEGIN GENERATED QUANTITATIVE CLAIMS -->"
_README_CLAIMS_END = "<!-- END GENERATED QUANTITATIVE CLAIMS -->"

# Public E4 wording is deliberately less expressive than arbitrary Markdown.
# Keep these grammars synchronized with claim_registry.schema.json.
_METRIC_RE = re.compile(r"[a-z][a-z0-9]*(?: [a-z0-9]+){0,7}")
_UNIT_VALUES = frozenset(
    {
        "bytes",
        "files",
        "milliseconds",
        "operations",
        "percent",
        "ratio",
        "requests",
        "seconds",
    }
)
_TOOL_NAME_RE = re.compile(r"[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*")
_VERSION_RE = re.compile(
    r"v?[0-9]+(?:\.[0-9]+){0,3}(?:-[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)?"
)
_BENCHMARK_RE = re.compile(r"[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*")
_CORPUS_NAME_RE = re.compile(r"[A-Za-z0-9]+(?:[ -][A-Za-z0-9]+)*")
_REVISION_RE = re.compile(r"[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*")
_COMMIT_RE = re.compile(r"[0-9a-f]{40,64}")
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_NUMBER_PATTERN = r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?"
_E4_WORDING_RE = re.compile(
    rf"{_TOOL_NAME_RE.pattern} {_VERSION_RE.pattern}: "
    rf"{_METRIC_RE.pattern} = {_NUMBER_PATTERN} (?:{'|'.join(sorted(_UNIT_VALUES))}); "
    rf"{_TOOL_NAME_RE.pattern} {_VERSION_RE.pattern}: "
    rf"{_METRIC_RE.pattern} = {_NUMBER_PATTERN} (?:{'|'.join(sorted(_UNIT_VALUES))}); "
    rf"benchmark {_BENCHMARK_RE.pattern}; measured {_DATE_RE.pattern}; "
    rf"repository commit {_COMMIT_RE.pattern}; "
    rf"corpus {_CORPUS_NAME_RE.pattern}@{_REVISION_RE.pattern}; "
    rf"artifact sha256:{_SHA256_RE.pattern}\."
)

_E4_STRING_FIELDS = (
    ("metric", ("metric",), _METRIC_RE, 64),
    ("unit", ("unit",), None, 16),
    ("tsa.name", ("tsa", "name"), _TOOL_NAME_RE, 64),
    ("tsa.version", ("tsa", "version"), _VERSION_RE, 32),
    ("competitor.name", ("competitor", "name"), _TOOL_NAME_RE, 64),
    ("competitor.version", ("competitor", "version"), _VERSION_RE, 32),
    (
        "provenance.benchmark_version",
        ("provenance", "benchmark_version"),
        _BENCHMARK_RE,
        64,
    ),
    (
        "provenance.measurement_date",
        ("provenance", "measurement_date"),
        _DATE_RE,
        10,
    ),
    ("provenance.repo_commit", ("provenance", "repo_commit"), _COMMIT_RE, 64),
    (
        "provenance.corpus.name",
        ("provenance", "corpus", "name"),
        _CORPUS_NAME_RE,
        96,
    ),
    (
        "provenance.corpus.revision",
        ("provenance", "corpus", "revision"),
        _REVISION_RE,
        64,
    ),
    ("artifact.sha256", ("artifact", "sha256"), _SHA256_RE, 64),
)


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
    }
    return tuple(name for name, value in fields.items() if value is None)


def _format_measurement(value: int | float) -> str:
    return json.dumps(value, allow_nan=False, separators=(",", ":"))


def _nested_value(value: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = value
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _unsafe_e4_fields(claim: dict[str, Any]) -> tuple[str, ...]:
    """Apply a second, code-owned grammar after the externally supplied schema."""
    unsafe: list[str] = []
    for field, path, grammar, maximum in _E4_STRING_FIELDS:
        value = _nested_value(claim, path)
        if not isinstance(value, str):
            unsafe.append(field)
            continue
        has_control = any(
            unicodedata.category(character).startswith("C") for character in value
        )
        lexical_match = (
            value in _UNIT_VALUES
            if field == "unit"
            else bool(grammar and grammar.fullmatch(value))
        )
        if (
            not value
            or value != value.strip()
            or len(value) > maximum
            or has_control
            or not lexical_match
        ):
            unsafe.append(field)
    return tuple(unsafe)


def _generated_e4_wording(claim: dict[str, Any]) -> str:
    """Generate public wording from evidence fields bound to the artifact payload."""
    provenance = claim["provenance"]
    corpus = provenance["corpus"]
    artifact = claim["artifact"]
    wording = (
        f"{claim['tsa']['name']} {claim['tsa']['version']}: "
        f"{claim['metric']} = {_format_measurement(claim['numerator'])} {claim['unit']}; "
        f"{claim['competitor']['name']} {claim['competitor']['version']}: "
        f"{claim['metric']} = {_format_measurement(claim['denominator'])} {claim['unit']}; "
        f"benchmark {provenance['benchmark_version']}; "
        f"measured {provenance['measurement_date']}; "
        f"repository commit {provenance['repo_commit']}; "
        f"corpus {corpus['name']}@{corpus['revision']}; "
        f"artifact sha256:{artifact['sha256']}."
    )
    if "\r" in wording or "\n" in wording or not _E4_WORDING_RE.fullmatch(wording):
        raise ValueError("generated E4 wording violates the fixed public grammar")
    return wording


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
    claim: dict[str, Any], artifacts_root: Path, violations: list[str]
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
    if (
        type(evidence) is not dict
        or set(evidence) != {"schema_version", "claim"}
        or evidence.get("schema_version") != 1
        or evidence.get("claim") != _evidence_payload(claim)
    ):
        violations.append(f"STALE_OR_MIXED_PROVENANCE:{claim_id}")


def validate_registry(
    registry: Any, *, schema: dict[str, Any], artifacts_root: Path
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

    claims = registry["claims"]
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
            missing = _missing_verified_provenance(claim)
            if missing:
                claim_violations.append(
                    f"PROVENANCE_MISSING:{claim_id}:" + ",".join(missing)
                )
            if _LEVELS[claim["evidence_level"]] < 2:
                claim_violations.append(f"QUANTITATIVE_EVIDENCE_TOO_LOW:{claim_id}")
            if claim["evidence_level"] == "E4":
                unsafe_fields = _unsafe_e4_fields(claim)
                if unsafe_fields:
                    claim_violations.append(
                        f"E4_FIELD_UNSAFE:{claim_id}:" + ",".join(unsafe_fields)
                    )
            if claim["artifact"] is None:
                claim_violations.append(f"ARTIFACT_MISSING:{claim_id}")
            elif not measurement_invalid:
                _validate_artifact(claim, artifacts_root, claim_violations)
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
            safe_wording.append((claim_id, (_generated_e4_wording(claim),)))

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
