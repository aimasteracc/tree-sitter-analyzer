# Mis-Wire Audit — pre-seeded results on real repos

Real `miswire-audit` runs on public repos (no CodeGraph install — TSA models the
name-only design from its own index). Reproduce on any tree:
`uvx --from "tree-sitter-analyzer" miswire-audit <path>`.

## Summary

| repo | languages | call edges | name-only would mis-wire | TSA mis-wires |
|---|---|---|---|---|
| huggingface/tokenizers | Rust+Py+JS+TS | 16,329 | **1,259** (7.71%) | **0** |
| astral-sh/ruff | Rust+Py+TS | 187,418 | **7,557** (4.03%) | **0** |
| pola-rs/polars | Rust+Py | 267,066 | **9,016** (3.38%) | **0** |
| tree-sitter-analyzer (this repo) | 13 langs | 114,160 | 4,199 (3.68%) | 6 |
| gin-gonic/gin | Go (single) | 9,134 | **0** | **0** |

Across 5 repos TSA resolves **0 cross-language mis-wires** on the four polyglot
ones (and the 6 on its own repo are single-word Java method names — see the live
head-to-head in [REPORT-v1.21.0.md](REPORT-v1.21.0.md)). A single-language repo
correctly reports **0 and 0** — no false positives.

> **What the name-only count includes.** It is the *worst case for the name-only
> design*: every call whose name has a definition only in another language. That
> set includes both genuine cross-language collisions (e.g. a JS `tokenize()` bound
> to a Rust `tokenize`) AND language builtins a smarter name-only index could
> special-case (`print`, `range`). The honest takeaway is not the exact upper bound
> but that **TSA resolves every one of them correctly (0)** by gating on language
> family — and the live, CodeGraph-specific figure is 745 vs 6 (REPORT-v1.21.0).
> A `--exclude-builtins` floor is tracked in RFC-0011.

## Sample offenders (a name-only resolver would make these; TSA does not)

**huggingface/tokenizers** — `javascript tokenize() → rust def`, `rust format() → python def`, `javascript resolve() → rust def`.

**astral-sh/ruff** — `rust create() → python def`, `rust split() → python def`, `python range() → rust def`.

**pola-rs/polars** — `python iter() → rust def`, `rust f() → python def`, `python wait() → rust def`.
