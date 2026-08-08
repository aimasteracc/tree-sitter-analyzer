"""Independent-authority validation for E4 claim evidence."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from typing import Any

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
_REPOSITORY_RE = re.compile(r"[A-Za-z0-9]+(?:[._/-][A-Za-z0-9]+)*")
_MODEL_RE = re.compile(r"[A-Za-z0-9]+(?:[._:/-][A-Za-z0-9]+)*")
_BACKEND_RE = re.compile(r"[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*")
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
    rf"repositories {_REPOSITORY_RE.pattern}(?:,{_REPOSITORY_RE.pattern})*; "
    rf"model {_MODEL_RE.pattern}; backend {_BACKEND_RE.pattern}; evidence E4; "
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
            "repositories",
            "model_backend",
            "evidence_level",
            "tsa",
            "competitor",
            "public_artifact_url",
        }
        or benchmark.get("schema_version") != 1
        or benchmark.get("benchmark_version") != provenance["benchmark_version"]
        or benchmark.get("repo_commit") != provenance["repo_commit"]
        or benchmark.get("corpus_revision") != provenance["corpus"]["revision"]
        or benchmark.get("repositories") != claim["repositories"]
        or benchmark.get("model_backend") != claim["model_backend"]
        or benchmark.get("evidence_level") != claim["evidence_level"]
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
            "repositories",
            "model_backend",
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
            "repositories",
            "model_backend",
            "evidence_level",
            "numerator",
            "denominator",
            "unit",
            "public_reproduction_url",
        }
        or reproduction.get("schema_version") != 1
        or reproduction.get("relationship") != "independent-third-party"
        or reproduction.get("benchmark_manifest_sha256") != _digest(benchmark)
        or reproduction.get("claim_sha256") != _digest(claim_payload)
        or reproduction.get("repositories") != claim["repositories"]
        or reproduction.get("model_backend") != claim["model_backend"]
        or reproduction.get("evidence_level") != claim["evidence_level"]
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


def _format_measurement(value: int | float) -> str:
    return json.dumps(value, allow_nan=False, separators=(",", ":"))


def _nested_value(value: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = value
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def unsafe_e4_fields(claim: dict[str, Any]) -> tuple[str, ...]:
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
    repositories = claim.get("repositories")
    if (
        not isinstance(repositories, list)
        or not repositories
        or any(
            not isinstance(repository, str)
            or len(repository) > 96
            or not _REPOSITORY_RE.fullmatch(repository)
            for repository in repositories
        )
        or len(repositories) != len(set(repositories))
    ):
        unsafe.append("repositories")
    model_backend = claim.get("model_backend")
    if not isinstance(model_backend, dict):
        unsafe.append("model_backend")
    else:
        for field, grammar, maximum in (
            ("model", _MODEL_RE, 96),
            ("backend", _BACKEND_RE, 64),
        ):
            value = model_backend.get(field)
            if (
                not isinstance(value, str)
                or len(value) > maximum
                or not grammar.fullmatch(value)
            ):
                unsafe.append(f"model_backend.{field}")
    return tuple(unsafe)


def generated_e4_wording(claim: dict[str, Any]) -> str:
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
        f"repositories {','.join(claim['repositories'])}; "
        f"model {claim['model_backend']['model']}; "
        f"backend {claim['model_backend']['backend']}; "
        f"evidence {claim['evidence_level']}; "
        f"artifact sha256:{artifact['sha256']}."
    )
    if "\r" in wording or "\n" in wording or not _E4_WORDING_RE.fullmatch(wording):
        raise ValueError("generated E4 wording violates the fixed public grammar")
    return wording
