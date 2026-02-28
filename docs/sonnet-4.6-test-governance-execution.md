# Sonnet 4.6 Test Governance Execution

## Review Result

Current governance plan is **executable** and aligned with professional testing goals:

- Function-level source-to-test traceability is defined.
- Duplicate / invalid / missing test detection is automated.
- YAML over-sharding policy is explicitly defined.
- CI gate thresholds are staged for safe adoption.

## Before Full Autopilot (Required Safety Guards)

To avoid deleting valuable tests by mistake, Sonnet should apply these safeguards first:

1. Add **invalid-test allowlist** for tests that intentionally validate side effects without explicit assertions.
2. Add **duplicate-test allowlist** for deliberate contract conformance tests across multiple tool implementations.
3. Never delete tests directly in first pass; perform `migrate unique -> run tests -> delete redundant`.

## Execution Scope for Sonnet 4.6

### Phase A - Governance Baseline

1. Run:

```bash
uv run python scripts/audit_test_governance.py
```

2. Read outputs:

- `comprehensive_test_results/test_governance_audit.json`
- `comprehensive_test_results/test_governance_audit.md`

3. Create/update allowlist config:

- `tests/governance_allowlist.json`

Suggested schema:

```json
{
  "invalid_tests_allowlist": [],
  "duplicate_clusters_allowlist": []
}
```

### Phase B - Duplicate Cleanup (Safe)

For each duplicate cluster:

1. Keep one canonical file.
2. Migrate unique scenarios from others.
3. Run focused tests.
4. Delete redundant tests only after passing.

### Phase C - Invalid Test Cleanup

For each invalid candidate test:

1. Add explicit assertions, or
2. Convert to `pytest.raises`, or
3. Add mock call assertions (`assert_called_once_with`), or
4. Put into allowlist if intentionally assertion-free.

### Phase D - YAML Re-sharding

Consolidate YAML property tests to 2-4 files:

- `test_yaml_properties_syntax.py`
- `test_yaml_properties_semantics.py`
- `test_yaml_properties_resilience.py`
- `test_yaml_properties_io.py` (optional)

Keep compatibility wrappers only if required temporarily.

### Phase E - Gate Hardening

Apply staged gates:

1. `--fail-on-invalid 50 --fail-on-duplicates 50`
2. `--fail-on-invalid 10 --fail-on-duplicates 20`
3. `--fail-on-invalid 0 --fail-on-duplicates 0`

## Ready-to-Paste Prompt for Sonnet 4.6

```text
You are operating in the tree-sitter-analyzer repository.

Goal:
Implement docs/test-governance-framework.md fully with safe autonomous execution.

Constraints:
1) No broad risky deletions in one step.
2) For duplicate tests: migrate unique scenarios first, then delete redundant tests.
3) For invalid tests: add explicit assertions or pytest.raises; if intentionally assertion-free, add to allowlist.
4) Keep project behavior unchanged.
5) Run focused tests after each cluster change.

Execution steps:
A. Run `uv run python scripts/audit_test_governance.py` and parse JSON report.
B. Add allowlist file `tests/governance_allowlist.json` and update auditor to respect allowlists.
C. Resolve top 10 duplicate clusters safely (migrate -> test -> delete).
D. Resolve top 30 invalid tests (assertions/raises/mock asserts).
E. Re-shard YAML property tests to 2-4 files with consistent naming.
F. Run `uv run pytest tests/unit/ -q` and governance audit again.
G. Update docs with exact command examples and final metrics delta.

Definition of done:
- Duplicate clusters significantly reduced.
- Invalid tests significantly reduced.
- No test regressions.
- Governance audit report regenerated.

Output format:
- Short summary
- Files changed
- Before/after metrics from governance audit
- Remaining risks and next steps
```

## Notes

- `pytest.ini` currently includes `-n auto`, `--maxfail=10`, and coverage defaults. Sonnet should avoid changing this unless explicitly requested by owner.
- Prefer surgical changes in test files and preserve existing test intent.
