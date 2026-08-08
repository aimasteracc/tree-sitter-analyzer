# fmt: off
"""Behavioral tests for the quantitative claim registry subsystem."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from benchmarks.codegraph_compare import claim_registry as claim_registry_module
from benchmarks.codegraph_compare.claim_registry import (
    ClaimRegistryVerdict,
    canonical_json_bytes,
    load_and_validate,
    main,
    readme_claim_violations,
    render_readme_claims,
    validate_registry,
)
from scripts.generate_language_support_inventory import render_markdown

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "benchmarks/codegraph_compare/claim_registry.schema.json"
EMPTY_CLAIMS = (
    "<!-- BEGIN GENERATED QUANTITATIVE CLAIMS -->\n"
    "<!-- END GENERATED QUANTITATIVE CLAIMS -->"
)

@pytest.fixture
def schema():
    return json.loads(SCHEMA_PATH.read_text())

@pytest.fixture
def blocked_verdict():
    return ClaimRegistryVerdict("BLOCKED", True, False, 1, 0, 1, (), ())

@pytest.fixture
def readme_fixture():
    def build(body="", claim_body=""):
        claims = (
            "<!-- BEGIN GENERATED QUANTITATIVE CLAIMS -->\n"
            f"{claim_body}<!-- END GENERATED QUANTITATIVE CLAIMS -->"
        )
        return "\n".join(filter(None, (claims, body, render_markdown(compact=True).rstrip())))
    return build

@pytest.fixture
def claim_factory(tmp_path):
    def build(evidence_level="E2"):
        claim = {
            "claim_id": "fixture-latency-ratio", "status": "verified",
            "metric": "warm answer latency", "numerator": 8.0,
            "denominator": 10.0, "unit": "seconds",
            "tsa": {"name": "tree-sitter-analyzer", "version": "1.29.0"},
            "competitor": {"name": "FixtureGraph", "version": "2.0.0"},
            "provenance": {
                "benchmark_version": "fixture-v1", "repo_commit": "a" * 40,
                "corpus": {"name": "fixture corpus", "revision": "b" * 40},
                "measurement_date": "2026-07-17",
            },
            "repositories": ["django", "tokio"],
            "model_backend": {"model": "gpt-5-codex", "backend": "codex"},
            "evidence_level": evidence_level, "artifact": None,
        }
        synchronize_artifact(claim, tmp_path)
        return claim
    return build

def synchronize_artifact(claim, root):
    keys = (
        "claim_id", "metric", "numerator", "denominator", "unit", "tsa",
        "competitor", "provenance", "repositories", "model_backend",
        "evidence_level",
    )
    artifact = root / "evidence.json"
    artifact.write_bytes(canonical_json_bytes({
        "schema_version": 1, "claim": {key: claim[key] for key in keys}
    }))
    claim["artifact"] = {
        "path": "evidence.json", "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()
    }

def synchronize_e4_artifact(claim, root):
    benchmark = {
        "schema_version": 1,
        "benchmark_version": claim["provenance"]["benchmark_version"],
        "repo_commit": claim["provenance"]["repo_commit"],
        "corpus_revision": claim["provenance"]["corpus"]["revision"],
        "repositories": claim["repositories"], "model_backend": claim["model_backend"],
        "evidence_level": claim["evidence_level"],
        "tsa": claim["tsa"], "competitor": claim["competitor"],
        "public_artifact_url": "https://evidence.example/benchmark.json",
    }
    claim_payload = {key: claim[key] for key in (
        "claim_id", "metric", "numerator", "denominator", "unit", "tsa",
        "competitor", "provenance", "repositories", "model_backend",
        "evidence_level",
    )}
    reproduction = {
        "schema_version": 1, "authority_id": "independent-lab",
        "relationship": "independent-third-party",
        "benchmark_manifest_sha256": hashlib.sha256(canonical_json_bytes(benchmark)).hexdigest(),
        "claim_sha256": hashlib.sha256(canonical_json_bytes(claim_payload)).hexdigest(),
        "repositories": claim["repositories"], "model_backend": claim["model_backend"],
        "evidence_level": claim["evidence_level"],
        "numerator": claim["numerator"], "denominator": claim["denominator"],
        "unit": claim["unit"],
        "public_reproduction_url": "https://independent.example/reproduction.json",
    }
    artifact = root / "evidence.json"
    artifact.write_bytes(canonical_json_bytes({
        "schema_version": 2, "claim": claim_payload,
        "benchmark_manifest": benchmark, "reproduction_manifest": reproduction,
    }))
    claim["artifact"] = {
        "path": "evidence.json", "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()
    }
    digest = hashlib.sha256(canonical_json_bytes(reproduction)).hexdigest()
    return {"independent-lab": frozenset({digest})}

def validate(claims, schema, root, trusted_reproductions=None):
    previous = claim_registry_module._TRUSTED_E4_REPRODUCTIONS
    claim_registry_module._TRUSTED_E4_REPRODUCTIONS = trusted_reproductions or {}
    try:
        return validate_registry(
            {"schema_version": 1, "claims": claims}, schema=schema, artifacts_root=root,
        )
    finally:
        claim_registry_module._TRUSTED_E4_REPRODUCTIONS = previous

def set_nested(mapping, field, value):
    parts = field.split(".")
    for part in parts[:-1]:
        mapping = mapping[part]
    mapping[parts[-1]] = value

def without_public_string_grammars(schema):
    schema = deepcopy(schema)
    paths = (
        ("claim", "metric"), ("claim", "unit"), ("tool", "name"),
        ("tool", "version"), ("provenance", "benchmark_version"),
        ("provenance", "repo_commit"), ("corpus", "name"), ("corpus", "revision"),
    )
    for definition, field in paths:
        target = schema["$defs"][definition]["properties"][field]
        for keyword in ("enum", "pattern", "minLength", "maxLength"):
            target.pop(keyword, None)
    return schema

def test_checked_in_registry_is_blocked_and_emits_no_wording():
    result = load_and_validate(ROOT / "benchmarks/codegraph_compare/claim_registry.json", schema_path=SCHEMA_PATH)
    assert result.to_dict() == {
        "blocked_count": 1, "claim_count": 1, "emittable_wording": [],
        "publishable": False, "schema_valid": True, "status": "BLOCKED",
        "verified_count": 0, "violations": [],
    }

@pytest.mark.parametrize("evidence_level", ("E0", "E1", "E2", "E3"))
def test_every_sub_e4_level_emits_no_wording(tmp_path, schema, claim_factory, evidence_level):
    result = validate([claim_factory(evidence_level)], schema, tmp_path)
    assert (result.emittable_wording, result.publishable) == ((), False)

@pytest.mark.parametrize("wording", (
    "Other 1.0 beats Rival 2.0 on fixture-v1 fixture corpus, 2026-07-17.",
    "TSA is superior to CodeGraph.", "TSA has 2x the accuracy of CodeGraph.",
    "TSA dominates CodeGraph.", "TSA delivers lower latency than CodeGraph.",
))
def test_arbitrary_wording_property_is_never_emittable(tmp_path, schema, claim_factory, wording):
    claim = claim_factory("E4")
    claim["permitted_wording"] = [wording]
    result = validate([claim], schema, tmp_path)
    assert (result.schema_valid, result.emittable_wording, result.publishable) == (False, (), False)

def test_verified_e4_wording_is_exactly_generated_from_all_bound_fields(tmp_path, schema, claim_factory):
    claim = claim_factory("E4")
    authority = synchronize_e4_artifact(claim, tmp_path)
    result = validate([claim], schema, tmp_path, authority)
    digest = claim["artifact"]["sha256"]
    wording = (
        "tree-sitter-analyzer 1.29.0: warm answer latency = 8.0 seconds; "
        "FixtureGraph 2.0.0: warm answer latency = 10.0 seconds; "
        "benchmark fixture-v1; measured 2026-07-17; "
        f"repository commit {'a' * 40}; corpus fixture corpus@{'b' * 40}; "
        "repositories django,tokio; model gpt-5-codex; backend codex; evidence E4; "
        f"artifact sha256:{digest}."
    )
    assert (result.emittable_wording, result.publishable) == ((("fixture-latency-ratio", (wording,)),), True)

def test_permissive_override_cannot_publish_empty_registry(tmp_path):
    result = validate_registry({"schema_version": 1, "claims": []}, schema={}, artifacts_root=tmp_path)
    assert (result.status, result.publishable, result.violations) == (
        "INVALID", False, ("REGISTRY_RELEASE_EMPTY",),
    )

def test_permissive_override_cannot_bypass_measurement_invariant(tmp_path, claim_factory):
    claim = claim_factory("E4")
    claim["denominator"] = -1
    result = validate([claim], {}, tmp_path)
    assert result.violations == ("DENOMINATOR_NONPOSITIVE:fixture-latency-ratio",)


@pytest.mark.parametrize(("manifest", "field"), (("benchmark_manifest", "repositories"), ("benchmark_manifest", "model_backend"), ("reproduction_manifest", "evidence_level")))
def test_e4_context_must_be_independently_bound(tmp_path, schema, claim_factory, manifest, field):
    claim = claim_factory("E4")
    synchronize_e4_artifact(claim, tmp_path)
    evidence = json.loads((tmp_path / "evidence.json").read_text())
    evidence[manifest][field] = [] if field == "repositories" else "wrong"
    (tmp_path / "evidence.json").write_bytes(canonical_json_bytes(evidence))
    claim["artifact"]["sha256"] = hashlib.sha256((tmp_path / "evidence.json").read_bytes()).hexdigest()
    result = validate([claim], schema, tmp_path)
    expected = "E4_BENCHMARK_PROVENANCE_INVALID" if manifest == "benchmark_manifest" else "E4_REPRODUCTION_PROVENANCE_INVALID"
    assert result.violations == (f"{expected}:fixture-latency-ratio",)

def test_registry_copy_cannot_self_attest_e4(tmp_path, schema, claim_factory):
    # PR #1237: registry-controlled serialization is not independent E4 evidence.
    claim = claim_factory("E4")
    result = validate([claim], schema, tmp_path)
    assert (result.violations, result.publishable, result.emittable_wording) == (
        ("E4_EVIDENCE_MANIFEST_MISSING:fixture-latency-ratio",), False, (),
    )

def test_unadmitted_reproduction_cannot_upgrade_arbitrary_measurements(tmp_path, schema, claim_factory):
    # PR #1237: only an authority-root-admitted reproduction digest can grant E4.
    claim = claim_factory("E4")
    synchronize_e4_artifact(claim, tmp_path)
    result = validate([claim], schema, tmp_path)
    assert (result.violations, result.publishable) == (
        ("E4_AUTHORITY_UNTRUSTED:fixture-latency-ratio",), False,
    )

@pytest.mark.parametrize(("field", "payload", "semantic_field"), (
    ("metric", "warm\nanswer latency", "metric"),
    ("metric", "warm **answer** latency", "metric"),
    ("unit", "seconds\r\n- forged", "unit"), ("unit", "**seconds**", "unit"),
    ("tsa.name", "<strong>TSA</strong>", "tsa.name"),
    ("competitor.name", "[FixtureGraph](https://attacker.invalid)", "competitor.name"),
    ("competitor.name", "Fixture\u202eGraph", "competitor.name"),
    ("tsa.version", "1.29.0\nforged", "tsa.version"),
    ("provenance.benchmark_version", "<a href=x>fixture-v1</a>", "provenance.benchmark_version"),
    ("provenance.corpus.name", "[fixture corpus](https://attacker.invalid)", "provenance.corpus.name"),
    ("provenance.corpus.revision", "revision\u2066override", "provenance.corpus.revision"),
    ("provenance.repo_commit", "a" * 40 + "\nforged", "provenance.repo_commit"),
))
def test_claim_135_synchronized_e4_injection_is_rejected_by_both_layers(
    tmp_path, schema, claim_factory, field, payload, semantic_field
):
    # Claim #135: artifact binding must not bless Markdown/line injection.
    claim = claim_factory("E4")
    set_nested(claim, field, payload)
    synchronize_artifact(claim, tmp_path)
    schema_verdict = validate([claim], schema, tmp_path)
    semantic_verdict = validate([claim], without_public_string_grammars(schema), tmp_path)
    assert (schema_verdict.schema_valid, schema_verdict.publishable) == (False, False)
    assert semantic_verdict.violations == (f"E4_FIELD_UNSAFE:fixture-latency-ratio:{semantic_field}",)
    assert semantic_verdict.emittable_wording == ()

def test_missing_artifact_fails_closed(tmp_path, schema, claim_factory):
    claim = claim_factory()
    (tmp_path / "evidence.json").unlink()
    result = validate([claim], schema, tmp_path)
    assert (result.violations, result.emittable_wording) == (("ARTIFACT_MISSING:fixture-latency-ratio",), ())

def test_stale_artifact_provenance_fails_closed(tmp_path, schema, claim_factory):
    claim = claim_factory()
    claim["provenance"]["repo_commit"] = "c" * 40
    result = validate([claim], schema, tmp_path)
    assert (result.violations, result.publishable) == (("STALE_OR_MIXED_PROVENANCE:fixture-latency-ratio",), False)

@pytest.mark.parametrize("measurement", (float("nan"), float("inf"), float("-inf")))
def test_nonfinite_measurement_fails_closed(tmp_path, schema, claim_factory, measurement):
    claim = claim_factory()
    claim["numerator"] = measurement
    result = validate([claim], schema, tmp_path)
    assert (result.violations, result.publishable) == (("MEASUREMENT_NONFINITE:fixture-latency-ratio:numerator",), False)

@pytest.mark.parametrize("readme", ("README.md", "README_ja.md", "README_zh.md"))
def test_readme_claim_section_and_whole_document_coverage_are_current(readme):
    verdict = load_and_validate(ROOT / "benchmarks/codegraph_compare/claim_registry.json", schema_path=SCHEMA_PATH)
    assert readme_claim_violations((ROOT / readme).read_text(), verdict) == ()

@pytest.mark.parametrize(("readme", "probe"), (
    ("README.md", "TSA processes hundreds of files."),
    ("README_ja.md", "TSA は数百ファイルを処理します。"),
    ("README_zh.md", "TSA 可处理数百个文件。"),
))
def test_each_public_readme_scan_rejects_localized_unregistered_claim(readme, probe):
    verdict = load_and_validate(ROOT / "benchmarks/codegraph_compare/claim_registry.json", schema_path=SCHEMA_PATH)
    text = probe + "\n" + (ROOT / readme).read_text()
    assert readme_claim_violations(text, verdict) == ("README_UNREGISTERED_QUANTITATIVE_CLAIM:1",)

def test_readme_generated_claim_drift_is_rejected(blocked_verdict, readme_fixture):
    assert readme_claim_violations(readme_fixture(claim_body="manual\n"), blocked_verdict) == ("README_CLAIM_SECTION_DRIFT",)

@pytest.mark.parametrize("claim", (
    "Other is superior to Rival with 2x accuracy.", "TSA dominates Rival with 50% fewer call edges.",
    "TSA has lower latency: 10 ms.", "TSA processes 500 files in 2 seconds.",
))
def test_readme_manual_quantitative_marketing_is_rejected(claim, blocked_verdict, readme_fixture):
    assert readme_claim_violations(readme_fixture(claim), blocked_verdict) == ("README_UNREGISTERED_QUANTITATIVE_CLAIM:3",)

def test_readme_contract_excludes_commands_versions_and_language_inventory(blocked_verdict, readme_fixture):
    body = "Requires Python 3.10+; check python --version.\n```bash\ntool --timeout-seconds 120 --limit 5\n```"
    assert readme_claim_violations(readme_fixture(body), blocked_verdict) == ()

def test_mixed_e4_and_blocked_registry_emits_nothing(tmp_path, schema, claim_factory):
    verified = claim_factory("E4")
    authority = synchronize_e4_artifact(verified, tmp_path)
    blocked = verified | {"claim_id": "blocked-fixture", "status": "blocked", "numerator": None, "denominator": None, "artifact": None}
    result = validate([verified, blocked], schema, tmp_path, authority)
    assert (result.status, result.publishable, result.emittable_wording) == ("BLOCKED", False, ())
    assert render_readme_claims(result) == EMPTY_CLAIMS

def test_mixed_e4_and_e3_registry_emits_nothing(tmp_path, schema, claim_factory):
    e4 = claim_factory("E4")
    authority = synchronize_e4_artifact(e4, tmp_path)
    (tmp_path / "evidence.json").rename(tmp_path / "e4.json")
    e4["artifact"]["path"] = "e4.json"
    e3 = claim_factory("E3")
    e3["claim_id"] = "fixture-e3"
    evidence = json.loads((tmp_path / "evidence.json").read_text())
    evidence["claim"]["claim_id"] = "fixture-e3"
    (tmp_path / "e3.json").write_bytes(canonical_json_bytes(evidence))
    e3["artifact"] = {"path": "e3.json", "sha256": hashlib.sha256((tmp_path / "e3.json").read_bytes()).hexdigest()}
    result = validate([e4, e3], schema, tmp_path, authority)
    assert (result.status, result.publishable, result.emittable_wording) == ("VALID", False, ())

def test_nonpublishable_verdict_cannot_be_rendered():
    verdict = ClaimRegistryVerdict("VALID", True, False, 1, 1, 0, (), (("bad", ("must not leak",)),))
    assert render_readme_claims(verdict) == EMPTY_CLAIMS

@pytest.mark.parametrize(("level", "status"), (("E3", "VALID"), ("E4", "INVALID")))
def test_cli_requires_admitted_authority_for_e4_registry(tmp_path, capsys, claim_factory, level, status):
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"schema_version": 1, "claims": [claim_factory(level)]}))
    actual_code = main([str(registry), "--schema", str(SCHEMA_PATH), "--artifacts-root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)
    assert (actual_code, payload["status"], payload["publishable"], payload["emittable_wording"]) == (2, status, False, [])

NORMALIZATION_PROBES = (
    "Success rate reaches 96.3 percent.", "TSA delivers a 390-fold speedup.",
    "TSA is twice as fast as Rival.", "TSA handles 500 **files** in 2 **seconds**.",
    "TSA is [390× faster](https://example.invalid).", "TSA answers in 2 seconds.",
    "TSA provides sub-second answers.", "Success rate is 96.3&#37;.",
    "Success rate is 96.3\npercent.", "TSA is 390 倍 faster.",
    "TSA has half the latency.", "TSA finishes in 2 minutes with lower latency.",
    "TSA has 50% higher accuracy and fewer errors.", "TSA handles 500 files in 0.5 seconds.",
)
FINAL_REVIEW_PROBES = (
    "TSA resolves 1,259 files on the benchmark corpus.", "TSA supports 100 languages.",
    "TSA processes 500 files per hour.", "TSA answers in two seconds.",
    "Success rate is ninety-six percent.", r"Success rate is 96.3\%.",
    "Success rate is 96<span>.</span>3<span>%</span>.", "[![TSA is 390× faster](badge)](url)",
    "TSA handles a hundred files.", "TSA handles a dozen repositories.",
    "TSA handles a million files.", "TSA delivers threefold speedup.",
    "TSA delivers millionfold speedup.", "TSA delivers dozen倍 speedup.",
    "TSA uses a quarter the latency.", "One-shot analysis finds the answer.",
    "TSA は半秒でインデックスを完了します。", "TSA 可在半秒内完成索引。",
    "TSA handles five widgets per hour.", "TSA handles 8 MCP tools per second.",
    "TSA answers in Step 2 seconds.", "TSA is ³⁹⁰× faster.", "TSA is Ⅻ× faster.", "TSA is 三倍 faster.",
)
WORD_NUMBERS = tuple("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million billion trillion dozen score couple pair hundreds thousands millions billions trillions dozens scores couples pairs several many few half quarter third single double triple quadruple".split())
CAMOUFLAGE = (
    "Python version 3.10; TSA is 390× faster than Rival.", "8 MCP tools and TSA is 390× faster than Rival.",
    "323 CLI flags; TSA is 390× faster than Rival.", "`python3 --version`; TSA is 390× faster than Rival.",
    "version 1.2.3; TSA is 390× faster than Rival.",
    "2026-07-17; TSA is 390× faster than Rival.", "RFC-0018; TSA is 390× faster than Rival.",
    "issue #123; TSA is 390× faster than Rival.", "Step 2; TSA is 390× faster than Rival.",
    f"commit {'a' * 40}; TSA is 390× faster than Rival.", "[![x](badge)](url) TSA is 390× faster than Rival.",
)

@pytest.mark.parametrize("claim", NORMALIZATION_PROBES)
def test_readme_normalization_cannot_bypass_claim_scanner(claim, blocked_verdict, readme_fixture):
    assert readme_claim_violations(readme_fixture(claim), blocked_verdict) == ("README_UNREGISTERED_QUANTITATIVE_CLAIM:3",)

@pytest.mark.parametrize("probe", FINAL_REVIEW_PROBES)
def test_final_review_fail_closed_probes_are_rejected(probe, blocked_verdict, readme_fixture):
    # Incident 2026-08-08: B1 whole-README scanner bypasses.
    assert readme_claim_violations(readme_fixture(probe), blocked_verdict) == ("README_UNREGISTERED_QUANTITATIVE_CLAIM:3",)

@pytest.mark.parametrize("word_number", WORD_NUMBERS)
def test_spelled_out_number_vocabulary_is_fail_closed(word_number, blocked_verdict, readme_fixture):
    assert readme_claim_violations(readme_fixture(f"TSA answers in {word_number} seconds."), blocked_verdict) == ("README_UNREGISTERED_QUANTITATIVE_CLAIM:3",)

@pytest.mark.parametrize("probe", (
    "TSA processes hundreds of files.", "TSA indexes thousands of repositories.",
    "TSA supports scores of languages.", "TSA analyzes a pair of repositories.",
))
def test_plural_and_pair_quantity_phrases_are_fail_closed(probe, blocked_verdict, readme_fixture):
    assert readme_claim_violations(readme_fixture(probe), blocked_verdict) == ("README_UNREGISTERED_QUANTITATIVE_CLAIM:3",)

@pytest.mark.parametrize("noun", ("seconds", "percent", "files", "languages"))
def test_required_measurement_nouns_are_fail_closed(noun, blocked_verdict, readme_fixture):
    assert readme_claim_violations(readme_fixture(f"TSA reports two {noun}."), blocked_verdict) == ("README_UNREGISTERED_QUANTITATIVE_CLAIM:3",)

@pytest.mark.parametrize("camouflage", CAMOUFLAGE)
def test_exact_span_exclusions_do_not_hide_surrounding_claims(camouflage, blocked_verdict, readme_fixture):
    assert readme_claim_violations(readme_fixture(camouflage), blocked_verdict) == ("README_UNREGISTERED_QUANTITATIVE_CLAIM:3",)

def test_badge_destination_numbers_are_ignored_but_alt_is_scanned(blocked_verdict, readme_fixture):
    badge = "[![Python](https://img.shields.io/badge/python-3.10-blue.svg)](url)"
    assert readme_claim_violations(readme_fixture(badge), blocked_verdict) == ()

@pytest.mark.parametrize(("mutation", "expected"), (
    ("duplicate-claim", ("README_CLAIM_MARKERS_INVALID",)),
    ("duplicate-language", ("README_LANGUAGE_MARKERS_INVALID",)),
    ("reverse-claim", ("README_CLAIM_MARKERS_ORDER", "README_UNREGISTERED_QUANTITATIVE_CLAIM:1")),
    ("nested", ("README_GENERATED_MARKERS_NESTED", "README_UNREGISTERED_QUANTITATIVE_CLAIM:1")),
))
def test_generated_markers_fail_closed(mutation, expected, blocked_verdict, readme_fixture):
    readme = readme_fixture()
    cb, ce = "<!-- BEGIN GENERATED QUANTITATIVE CLAIMS -->", "<!-- END GENERATED QUANTITATIVE CLAIMS -->"
    lb, le = "<!-- BEGIN GENERATED LANGUAGE SUPPORT INVENTORY -->", "<!-- END GENERATED LANGUAGE SUPPORT INVENTORY -->"
    if mutation == "duplicate-claim":
        readme += "\n" + cb
    elif mutation == "duplicate-language":
        readme += "\n" + lb + "\n" + le
    elif mutation == "reverse-claim":
        readme = readme.replace(cb + "\n" + ce, ce + "\n" + cb)
    else:
        language = readme[readme.index(lb):]
        readme = cb + "\n" + lb + "\n" + ce + language[len(lb):language.index(le)] + le
    assert readme_claim_violations(readme, blocked_verdict) == expected

@pytest.mark.parametrize(("body", "expected"), (
    ("```\nhidden 390× faster", ("README_FENCE_UNBALANCED", "README_UNREGISTERED_QUANTITATIVE_CLAIM:4")),
    ("```\nexample\n``` TSA is 390× faster", ("README_FENCE_UNBALANCED",)),
    ("```\nexample 390× faster\n```", ("README_UNREGISTERED_QUANTITATIVE_CLAIM:4",)),
    ("```bash\ntool --timeout-seconds 120 --limit 5\n```", ()),
    ("```bash\ntool --limit 390 files processed\n```", ("README_UNREGISTERED_QUANTITATIVE_CLAIM:4",)),
))
def test_fence_handling_fails_closed(body, expected, blocked_verdict, readme_fixture):
    # PR #1237: rendered claim prose must not disappear inside Markdown fences.
    assert readme_claim_violations(readme_fixture(body), blocked_verdict) == expected

@pytest.mark.parametrize("claim", (
    "TSA has the fastest indexing.", "TSA has the slowest indexing.",
    "TSA has the highest throughput.", "TSA has the lowest latency.",
    "TSA uses the most efficient index.", "TSA has the least memory use.",
    "TSA delivers the best performance.", "TSA has the worst latency.",
))
def test_quantitative_superlatives_are_fail_closed(claim, blocked_verdict, readme_fixture):
    # PR #1237: numeral-free superiority claims still require governed evidence.
    assert readme_claim_violations(readme_fixture(claim), blocked_verdict) == ("README_UNREGISTERED_QUANTITATIVE_CLAIM:3",)

@pytest.mark.parametrize("prose", (
    "Follow best practices.", "Most users should start here.",
    "Choose the least surprising configuration.", "Use the highest-level API.",
))
def test_nonquantitative_superlative_context_remains_accepted(prose, blocked_verdict, readme_fixture):
    assert readme_claim_violations(readme_fixture(prose), blocked_verdict) == ()

@pytest.mark.parametrize("claim", (
    "390. files processed", "390) requests handled", "## 390. files processed",
    "100. repositories indexed", "## 100: requests handled",
))
def test_large_claim_bearing_markers_are_fail_closed(claim, blocked_verdict, readme_fixture):
    # PR #1237: large quantities must not be mistaken for structural numbering.
    assert readme_claim_violations(readme_fixture(claim), blocked_verdict) == ("README_UNREGISTERED_QUANTITATIVE_CLAIM:3",)

@pytest.mark.parametrize("prose", (
    "1. Install the package.", "99) Read the migration notes.", "## 12: Configuration",
))
def test_controlled_small_structural_markers_remain_accepted(prose, blocked_verdict, readme_fixture):
    assert readme_claim_violations(readme_fixture(prose), blocked_verdict) == ()

def test_language_region_requires_canonical_generator_output(blocked_verdict, readme_fixture):
    readme = readme_fixture().replace("Generated from runtime registries;", "TSA is 390× faster;")
    assert readme_claim_violations(readme, blocked_verdict) == ("README_LANGUAGE_SECTION_UNVERIFIED", "README_UNREGISTERED_QUANTITATIVE_CLAIM:3")

@pytest.mark.parametrize(("text", "violation"), (
    ('{"schema_version":1,"claims":[],"x":Infinity}', "INPUT:non-finite JSON constant: Infinity"),
    ('{"schema_version":1,"schema_version":1,"claims":[]}', "INPUT:duplicate JSON key: schema_version"),
))
def test_invalid_json_is_rejected(tmp_path, text, violation):
    registry = tmp_path / "registry.json"
    registry.write_text(text)
    assert load_and_validate(registry, schema_path=SCHEMA_PATH).violations == (violation,)

def test_cli_json_is_byte_deterministic_for_blocked_registry(capsys):
    registry = ROOT / "benchmarks/codegraph_compare/claim_registry.json"
    first_code = main([str(registry)])
    first = capsys.readouterr().out
    second_code = main([str(registry)])
    second = capsys.readouterr().out
    assert (first_code, second_code, second) == (2, 2, first)
