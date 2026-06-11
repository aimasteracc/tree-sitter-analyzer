# Mis-Wire Audit — pre-seeded results on real repos

Real `miswire-audit` runs on public repos (no CodeGraph install — TSA models the
name-only design from its own index). Reproduce on any tree:
`uvx --from "git+https://github.com/aimasteracc/tree-sitter-analyzer@develop" miswire-audit <path>`.

## Summary

> **Column definitions:**
> - **name-only worst case** — every call whose name has a definition only in another
>   language, including each language's own builtins (`print`, `range`, `Ok`, …). Absolute ceiling.
> - **name-only genuine floor** — same, but excluding each caller language's own builtins.
>   The skeptic-resistant lower bound: a smarter name-only index that special-cased builtins
>   would still get all of these wrong. This is the column reported by `miswire-audit` by default.
> - **TSA mis-wires** — edges in TSA's live index where caller and callee languages are
>   incompatible. A real measurement, not a model.

| repo | languages | call edges | name-only worst case | name-only genuine floor | TSA mis-wires | measured at |
|---|---|---|---|---|---|---|
| huggingface/tokenizers | Rust+Py+JS+TS | 16,329 | — | **1,259** (7.71%) | **0** | v1.21.0 (2026-06-07) — re-run `gauntlet_runner.py --all` before publication <!-- re-measure --> |
| astral-sh/ruff | Rust+Py+TS | 187,418 | — | **7,557** (4.03%) | **0** | v1.21.0 (2026-06-07) — re-run `gauntlet_runner.py --all` before publication <!-- re-measure --> |
| pola-rs/polars | Rust+Py | 267,066 | — | **9,016** (3.38%) | **0** | v1.21.0 (2026-06-07) — re-run `gauntlet_runner.py --all` before publication <!-- re-measure --> |
| tree-sitter-analyzer (this repo) | 14 langs | 116,672 | 3,946 (3.38%) | **680** (0.58%) | **1** | measured 2026-06-10 at v1.22.0 (g6b2a266d) |
| gin-gonic/gin | Go (single) | 9,134 | **0** | **0** | **0** | v1.21.0 (2026-06-07) — re-run `gauntlet_runner.py --all` before publication <!-- re-measure --> |

Across 5 repos TSA resolves **0 or 1 cross-language mis-wires** on the four polyglot
ones (the 1 on its own repo is a single genuine collision — see live head-to-head in
[REPORT-v1.21.0.md](REPORT-v1.21.0.md) for the CodeGraph comparison). A single-language
repo correctly reports **0 and 0** — no false positives.

> **What the name-only counts include.**
>
> **Worst case** (`name-only worst case` column): every call whose name has a definition
> only in another language, including language builtins (`print`, `range`, `Ok`, …) that
> a smarter index could special-case.
>
> **Genuine floor** (`name-only genuine floor` column, default reported by `miswire-audit`):
> same set but excluding each caller language's own builtins — leaving only genuine
> cross-language name collisions no naive index could easily skip. This is the column TSA
> leads with, as it survives a skeptic's "but you could just exclude builtins" objection.
>
> For this repo (measured 2026-06-10 at v1.22.0): 3,946 worst-case but **680 genuine**
> (`sleep()`→Java, `connect()`→Kotlin, `Counter()`→TS, `find()`→PHP, `draw()`→Kotlin).
> TSA resolves **1** of these — a single genuine collision on its own test-corpus files.

## Sample offenders (a name-only resolver would make these; TSA does not)

**huggingface/tokenizers** — `javascript tokenize() → rust def`, `rust format() → python def`, `javascript resolve() → rust def`.

**astral-sh/ruff** — `rust create() → python def`, `rust split() → python def`, `python range() → rust def`.

**pola-rs/polars** — `python iter() → rust def`, `rust f() → python def`, `python wait() → rust def`.
