# Mis-Wire Audit — pre-seeded results

Real `miswire-audit` runs on public repos (no CodeGraph install — TSA models the
name-only design from its own index). Reproduce: `uvx --from tree-sitter-analyzer miswire-audit <path>`.

## huggingface/tokenizers (Rust + Python + JS + TS)

```
    ── TSA Mis-Wire Audit ──────────────────────────────────────
    repo: /tmp/_audit_tok
    languages indexed: javascript:6, python:54, rust:128, typescript:12
    call edges analysed: 16,329
    ❌ a NAME-ONLY resolver would mis-wire up to 1,259 call edges across a language boundary (7.71%) — binding a call to a same-named definition in another language
    ✅ Tree-sitter Analyzer mis-wires 0 (0.00%)
       → TSA is 1259× cleaner on YOUR code.
    (the name-only figure is the worst case for a name-only index — the design CodeGraph and most indexes use. A live head-to-head vs CodeGraph specifically — 745 vs 6 on TSA's repo — is in
     benchmarks/codegraph_compare/REPORT-v1.21.0.md.)
    cross-language mis-wires a name-only index would make here:
      • rust caller `lines()` → python def in bindings/python/tests/test_benchmarks.py (at tokenizers/benches/layout_benchmark.rs:30)
      • rust caller `format()` → python def in bindings/python/tests/bindings/test_tokenizer.py (at tokenizers/benches/llama3_benchmark.rs:61)
      • javascript caller `tokenize()` → rust def in tokenizers/examples/unstable_wasm/src/lib.rs (at tokenizers/examples/unstable_wasm/www/index.js:3)
      • javascript caller `resolve()` → rust def in bindings/node/src/tasks/models.rs (at tokenizers/examples/unstable_wasm/www/webpack.config.js:7)
      • rust caller `run()` → python def in bindings/python/tests/test_benchmarks.py (at bindings/python/tools/stub-gen/src/main.rs:126)
    ────────────────────────────────────────────────────────────
```

## gin-gonic/gin (Go — single language: correctly 0, no false positives)

```
    ── TSA Mis-Wire Audit ──────────────────────────────────────
    repo: /tmp/_audit_gin
    languages indexed: go:99
    call edges analysed: 9,134
    ❌ a NAME-ONLY resolver would mis-wire up to 0 call edges across a language boundary (0.00%) — binding a call to a same-named definition in another language
    ✅ Tree-sitter Analyzer mis-wires 0 (0.00%)
    (the name-only figure is the worst case for a name-only index — the design CodeGraph and most indexes use. A live head-to-head vs CodeGraph specifically — 745 vs 6 on TSA's repo — is in
     benchmarks/codegraph_compare/REPORT-v1.21.0.md.)
    (no cross-language same-name collisions in this repo)
    ────────────────────────────────────────────────────────────
```

## tree-sitter-analyzer (this repo — 13-language corpus)

```
    ── TSA Mis-Wire Audit ──────────────────────────────────────
    repo: .
    languages indexed: c:5, cpp:3, csharp:3, go:6, java:11, javascript:12, kotlin:2, php:2, python:1751, ruby:3, rust:5, swift:2, typescript:5
    call edges analysed: 114,160
    ❌ a NAME-ONLY resolver would mis-wire up to 4,199 call edges across a language boundary (3.68%) — binding a call to a same-named definition in another language
    ✅ Tree-sitter Analyzer mis-wires 6 (0.01%)
       → TSA is 700× cleaner on YOUR code.
    (the name-only figure is the worst case for a name-only index — the design CodeGraph and most indexes use. A live head-to-head vs CodeGraph specifically — 745 vs 6 on TSA's repo — is in
     benchmarks/codegraph_compare/REPORT-v1.21.0.md.)
    cross-language mis-wires a name-only index would make here:
      • python caller `print()` → java def in tests/golden/corpus_java.java (at verify_workflow_structure.py:20)
      • python caller `sorted()` → swift def in tests/golden/corpus_swift.swift (at diagnose_coverage.py:15)
      • python caller `Counter()` → typescript def in tests/golden/corpus_typescript.ts (at check_stability.py:66)
      • python caller `sum()` → typescript def in tests/golden/corpus_typescript.ts (at collect_project_metrics.py:32)
      • python caller `sleep()` → java def in tests/golden/corpus_java.java (at start_mcp_server.py:43)
    ────────────────────────────────────────────────────────────
```

_The name-only figure is the worst case for the name-only design (not CodeGraph's
exact count). The live head-to-head vs CodeGraph specifically — 745 vs 6 — is in
[REPORT-v1.21.0.md](REPORT-v1.21.0.md)._
