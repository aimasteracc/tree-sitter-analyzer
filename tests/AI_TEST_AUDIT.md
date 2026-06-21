# AI-Generated Test Audit

Measured on 2026-06-20.

## Suspicion Signals

These patterns are treated as AI-slop signals because they create green tests
without protecting behavior:

- `assert result is not None`
- `assert value is not None or value is None`
- `assert len(items) >= 1` for deterministic fixtures
- broad helper-heavy tests whose assertions only prove that something returned

## Current Findings

| Signal | Count |
|---|---:|
| Raw `assert result is not None` matches | 355 |
| AST placeholder findings after paired-behavior filtering | 130 |
| Raw None-check tautology regex matches | 15 |
| AST tautology findings | 10 |

The AST counts are authoritative for gating because they understand expression
shape and ignore placeholder guards that are paired with concrete behavior in
the same test.

## Required Rewrite Pattern

Bad:

```python
result = tool.run(input_data)
assert result is not None
```

Good:

```python
result = tool.run(input_data)
assert result["status"] == "ok"
assert result["items"] == [{"name": "main", "kind": "function"}]
```

When a fixture is intentionally nondeterministic, keep the test but document the
reason with `# ratchet: nondeterministic <reason>` on the assert block.
