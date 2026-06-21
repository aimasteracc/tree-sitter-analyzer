# Formatter Helper Audit

Measured on 2026-06-20 under `tests/integration/formatters`.

| Surface | Count |
|---|---:|
| Helper files | 48 |
| Helper lines | 7972 |
| Test files | 6 |
| Test lines | 2181 |

## Policy

Formatter helpers are acceptable only when they remove real duplication across
multiple tests or isolate unavoidable compatibility setup. A helper that only
wraps one assertion or hides one fixture should be inlined into the test.

## Cleanup Order

1. Identify helpers imported by exactly one test file.
2. Inline helpers that merely call a formatter and return the result.
3. Keep helpers that build shared golden data or normalize cross-version output.
4. Move behavior assertions out of helpers and into test bodies so failures
   point at the behavior being protected.

## Review Rule

New formatter helpers must include at least two call sites or a comment that
names the compatibility concern they isolate.
