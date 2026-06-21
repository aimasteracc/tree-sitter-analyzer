# Test Architecture Audit

Measured on 2026-06-20 from the current working branch.

## Gates Now Enforced

- New weak assertions are blocked by `scripts/check_loose_assertions.py`.
- CI already invokes the shell wrapper from `.github/workflows/reusable-quality.yml`.
- Local pre-commit now invokes the same Python gate when staged `tests/**/*.py`
  files change.
- Skip governance remains covered by
  `tests/governance/test_postmortem_guards.py::test_skips_have_tracking_references`.

## Current Baselines

| Surface | Baseline |
|---|---:|
| Weak assertion findings | 171 |
| Placeholder `is not None` findings | 130 |
| Loose-bound findings | 30 |
| Tautology findings | 10 |
| `tests/unit/mcp` Python files | 219 |
| `tests/unit/mcp` facade-named files | 11 |
| Test files over 800 lines | 13 |
| Formatter helper files | 48 |
| Formatter helper lines | 7972 |
| Formatter test files | 6 |
| Formatter test lines | 2181 |

## Cleanup Order

1. Replace placeholder assertions with exact result-shape or behavior checks.
2. Replace loose deterministic counts with exact counts or exact sets.
3. Split large files by behavior area when touching them for real changes.
4. Keep formatter helper files only when they are reused by multiple tests or
   hide unavoidable compatibility setup.

## Review Rule

A new test is not acceptable when its only assertion is existence, truthiness,
or "at least one" output. Every new test must prove a behavior that can fail
for a meaningful regression.
