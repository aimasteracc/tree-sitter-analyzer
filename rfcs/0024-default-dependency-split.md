# RFC-0024: Default dependency split, measured before design

- **Status**: draft
- **Author(s)**: Runtime Lead
- **Created**: 2026-08-08
- **Last updated**: 2026-08-08
- **Tracking**: roadmap NO1-006B
- **Affected paths**: `pyproject.toml` (future only), `scripts/collect_no1_006b_baseline.py`, `schemas/no1-006b-baseline.schema.json`

## Summary

Define a reversible candidate split between the default install and optional capabilities. This RFC does **not** change dependencies. It first records an auditable E0 measurement of unmodified `origin/develop` commit `7e0e8f6e03270fcbf4025d717415ef69c9354145`; NO1-011A may implement a split only after native measurements and compatibility gates pass.

## Measured current baseline (before recommendations)

The raw, schema-validated receipt is [`docs/baselines/no1-006b-macos-e0.json`](../docs/baselines/no1-006b-macos-e0.json), report SHA-256 `894cad430c847a5f0a653fb3c32d4c8796723a374b5d9342ff0edc6ee6d46a06`. It was produced on the actual checkout, not inferred from `pyproject.toml`.

| Axis | Measured value |
|---|---:|
| source | `7e0e8f6e03270fcbf4025d717415ef69c9354145` |
| wheel SHA-256 / bytes | `c1cb3520542fd14dad60ddec55dfac6afbdaa424e7a4a39d875be1801d98f9e8` / 2,209,032 |
| root-wheel download payload | 2,209,032 bytes |
| installed distribution files | 106,916,217 bytes |
| direct / transitive / total distributions | 33 / 38 / 72 |
| CLI cold; warm samples (ms) | 1437.014; 146.212, 149.725, 149.838, 141.008, 149.877 |
| MCP cold; warm samples (ms) | 1612.283; 289.217, 289.244, 292.211, 292.481, 293.373 |

Environment: macOS 26.4.1 arm64, CPython 3.14.3, uv 0.12.3. “Cold” is the first newly-installed-environment process; it is not an OS page-cache flush. CLI ends at a successful `--show-supported-languages`; MCP ends at the first successful `initialize` JSON-RPC response. Five warm repeats are retained individually, not summarized away.

The root wheel byte count is the only offline-reproducible download measure. Dependency network-transfer bytes are explicitly **unknown**, rather than reconstructed from mutable uv cache internals. Installed size is the sum of unique non-pyc, non-`direct_url.json` regular files named by installed distribution metadata, excluding the interpreter. All build/install resolution used `uv --offline`. Exact commands, versions, scopes, samples, and hashes are in the receipt.

This is a **macOS-only E0** observation. Linux and Windows are `unknown`; it makes no cross-platform or user-visible performance claim.

### Reproduction

From the pinned commit with the required wheels already present in the uv cache:

```bash
NO1_006B_PYTHON=3.14 uv run python scripts/collect_no1_006b_baseline.py \
  --repo . --repeats 5 --output /tmp/no1-006b-macos-e0.json
uv run python -c 'import json,jsonschema; jsonschema.validate(json.load(open("/tmp/no1-006b-macos-e0.json")),json.load(open("schemas/no1-006b-baseline.schema.json")))'
```

The collector allows 3–20 repeats, has 30/120/180-second operation timeouts, refuses non-macOS hosts for this receipt version, pins the commit by default, uses temporary isolation, and never enables network access.

## Candidate design (not implemented here)

Only after the baseline above exists, NO1-011A may prototype:

* **default/core candidate**: CLI/MCP protocol, shared models/security/formatters, the tree-sitter runtime, and one explicitly documented minimal language capability;
* **language option groups**: existing per-language extras, plus convenience `popular`, `web`, `systems`, and `all-languages` groups;
* **advanced-analysis group**: graph/numeric, secret scanning, and other capabilities not necessary to start the default CLI/MCP process;
* **full compatibility group**: one `full` extra reproducing the current default capability set exactly.

Names and membership are candidates, not decisions. Import tracing and native-axis measurements must decide which imports are genuinely on startup paths. Missing optional capabilities must return a deterministic installation hint, never an import traceback, silent feature loss, or false “supported” result. Console entry points and locked defaults (CLI JSON, MCP TOON) do not change.

## Compatibility, admission, and rollback gates

A proposed split is admitted only if one exact wheel passes NO1-006A fresh-install qualification on native macOS, Linux, and Windows, existing CLI/MCP contract suites pass, every currently advertised language succeeds with `full`, and default-install unavailable features have exact diagnostic tests. Each native axis must supply the same schema fields and its own pre/post receipt. `unknown` cannot pass a gate.

For default/core on **each** native axis: wheel bytes, installed bytes, direct count, transitive count, CLI cold and median warm startup, and MCP cold and median warm startup must all be no worse than that axis’s pinned pre-split baseline; at least wheel bytes, installed bytes, and total dependency count must improve. Timing comparisons use identical hardware/tool/Python/commands and raw repeats. No mac result substitutes for Linux or Windows.

Rollback is metadata-only: restore the prior default dependency list and republish; users can immediately select the `full` extra during a staged rollout. The implementation must not couple the split to package moves, engine rewrites, schema migrations, or entry-point changes. A default behavior regression, ambiguous optional-import error, NO1-006A failure, or worse qualified axis blocks release and triggers rollback.

## Alternatives and drawbacks

* **Big-bang modular rewrite**: rejected; it mixes packaging evidence with architectural change and makes rollback unsafe.
* **Keep the current default forever**: safest compatibility, but leaves measured footprint/startup costs unaddressed.
* **Dynamic auto-download**: rejected; violates offline operation and makes installs unauditable.

A split increases support combinations and may surprise users who relied on an undeclared language. The `full` compatibility path, explicit diagnostics, staged rollout, and native gates are therefore mandatory.

## Test plan and acceptance

- [x] Current commit measured before recommendations; raw samples and unfavorable values retained.
- [x] Bounded offline collector, strict schema, and same-named subsystem contract tests added.
- [x] macOS E0 recorded; Linux/Windows honestly unknown.
- [x] No dependency split or big-bang rewrite implemented.
- [ ] NO1-011A gathers native pre/post receipts and passes all admission gates.

## Deferred

Actual `pyproject.toml` changes, lazy imports, feature diagnostics, native Linux/Windows baselines, and any release claim belong to NO1-011A. This E0 receipt cannot support marketing or “faster/lighter” wording.
