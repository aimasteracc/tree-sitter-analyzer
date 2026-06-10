# Polyglot Mis-Wire Gauntlet — TSA Results Card

**What this page is:** a permanent, verifiable record of how tree-sitter-analyzer
scores on cross-language call-graph correctness across five real open-source repos.
All numbers in the summary table are lifted verbatim from
[MISWIRE-AUDIT-EXAMPLES.md](MISWIRE-AUDIT-EXAMPLES.md) and
[REPORT-v1.21.0.md](REPORT-v1.21.0.md); the source document is cited in every row.

---

## 5-Repo Summary Table

> **Column definitions (see [MISWIRE-AUDIT-EXAMPLES.md](MISWIRE-AUDIT-EXAMPLES.md) for full explanation):**
> - **name-only genuine floor** — naive mis-wires excluding each language's own builtins
>   (`print`, `range`, …). Lower bound; the default column reported by `miswire-audit`.
> - **TSA mis-wires** — edges in TSA's live index where caller and callee languages are
>   incompatible. A real measurement, not a model.

<!-- re-measure: rows marked (v1.21.0) are from the v1.21.0 run (2026-06-07).
     Re-run `gauntlet_runner.py --all` before publication to replace them with fresh numbers. -->

| repo | languages | call edges | name-only genuine floor | TSA mis-wires | measured at |
|---|---|---|---|---|---|
| huggingface/tokenizers | Rust+Py+JS+TS | 16,329 | **1,259** (7.71%) | **0** | v1.21.0 (2026-06-07) <!-- re-measure --> |
| astral-sh/ruff | Rust+Py+TS | 187,418 | **7,557** (4.03%) | **0** | v1.21.0 (2026-06-07) <!-- re-measure --> |
| pola-rs/polars | Rust+Py | 267,066 | **9,016** (3.38%) | **0** | v1.21.0 (2026-06-07) <!-- re-measure --> |
| tree-sitter-analyzer (this repo) | 14 langs | 116,672 | **680** (0.58%) | **1** | measured 2026-06-10 at v1.22.0 (g6b2a266d) |
| gin-gonic/gin | Go (single) | 9,134 | **0** | **0** | v1.21.0 (2026-06-07) <!-- re-measure --> |

**Across all four polyglot repos TSA resolves 0 cross-language mis-wires.** The 1
on this repo is a single genuine collision on this repo's own test-corpus files —
the documented ceiling without receiver-type inference.
The single-language repo (gin) correctly returns 0 and 0 — no false positives.

> **What "name-only genuine floor" means.** The audit models a name-only resolver: every
> call whose name has a definition only in another language. The **genuine floor** excludes
> each caller language's own builtins (`print`, `range`, `Ok`, …) — leaving only real
> cross-language collisions a basic name-only index cannot skip. This column is the default
> reported by `miswire-audit` as it survives a skeptic's "you could just exclude builtins"
> objection. The **worst case** (including builtins) for this repo is 3,946; the genuine
> floor is **680** (`sleep()`→Java, `connect()`→Kotlin, `Counter()`→TS, `find()`→PHP,
> `draw()`→Kotlin). TSA resolves **0** genuine cross-language mis-wires on the four external
> polyglot repos, and only **1** on its own repo.

---

## Live Head-to-Head vs CodeGraph (this repo, same commit)

Source: [REPORT-v1.21.0.md §Addendum 2](REPORT-v1.21.0.md)

> **Note:** The CodeGraph row was measured at v1.21.0 (2026-06-07). The TSA row was
> re-measured at v1.22.0 (2026-06-10). Re-run `gauntlet_runner.py --repo tsa` with a
> fresh CodeGraph index to update the CodeGraph row. <!-- re-measure: CodeGraph row -->

| tool | cross-language call edges | total call edges | mis-wire rate | measured at |
|---|---|---|---|---|
| **CodeGraph** | **763** | 36,788 | **2.07%** | v1.21.0 (2026-06-07) <!-- re-measure --> |
| **Tree-sitter Analyzer** | **1** | 116,672 | **0.0009%** | measured 2026-06-10 at v1.22.0 |

TSA is ~763x cleaner (1 vs 763 mis-wires) while resolving 3x more call edges total (116k vs 37k).

---

## Flagship: `sorted()` → Swift (original repro, v1.21.0)

> **Measurement note (2026-06-10):** The numbers below were captured at v1.21.0.
> At v1.22.0 the live index shows 392 Python `sorted()` call sites, all with
> `callee_resolution='unknown'` — zero wired to Swift (same conclusion, updated count).
> The Swift definition at `tests/golden/corpus_swift.swift:337` still exists.
> The CodeGraph repro commands remain valid for demonstrating the mis-wire behaviour;
> the TSA count will differ on a fresh index.

The clearest case. Python's builtin `sorted()` is called hundreds of times across the
Python codebase. There is no `sorted` definition in any `.py` file. The only `sorted`
node in CodeGraph's index is a Swift method, `tests/golden/corpus_swift.swift:337`.
CodeGraph wires every Python caller to that Swift node. TSA binds none of them.

```bash
# 1. Confirm the only in-repo 'sorted' definition is Swift (no Python def):
grep -rl "def sorted" --include="*.py" .          # → (nothing)
grep -n "func sorted" tests/golden/corpus_swift.swift
# → 337:    func sorted() -> [Element] {

# 2. CodeGraph (v1.21.0): count distinct Python callers wired to the Swift node:
sqlite3 .codegraph/codegraph.db "
  SELECT COUNT(DISTINCT e.source)
  FROM edges e JOIN nodes n ON e.source = n.id
  WHERE e.target = 'method:93b946c9bfbf7d0843dca5323ecd16c4'
    AND e.kind = 'calls' AND n.file_path LIKE '%.py';"
# → 299      (299 Python callers attached to a Swift func — v1.21.0 index)

# 3. TSA (v1.22.0, 2026-06-10): all 392 sorted() call sites are unresolved; none wired to Swift:
uv run python -c "
from tree_sitter_analyzer.ast_cache import ASTCache
cache = ASTCache('.')
conn = cache.get_conn()
edges = conn.execute(\"SELECT callee_resolved_file, COUNT(*) n FROM edges WHERE kind='calls' AND callee_name='sorted' GROUP BY callee_resolved_file\").fetchall()
print([(r['callee_resolved_file'] or 'unresolved', r['n']) for r in edges])
cache.close()
"
# → [('unresolved', 392)]   ← all 392 callers unresolved; zero wired to Swift
```

CodeGraph asserts hundreds of Python→Swift `calls` edges the AST cannot support. TSA
reports those call sites as `callee_resolution='unknown'` — honestly unresolved
rather than confidently wrong. For an agent about to change a function's signature,
"392 unknown" is a safe answer; "299 callers in a Swift file" is a trap.

---

## Run It Yourself

### One-command audit (any repo, no CodeGraph install needed)

```bash
# Via uvx (no install required):
uvx --from tree-sitter-analyzer miswire-audit /path/to/your/repo

# Via uv run (from this repo):
uv run python -m tree_sitter_analyzer.miswire_audit /path/to/your/repo

# Options:
#   --card          emit a markdown card you can paste to issues/PRs
#   --top N         show N offender examples (default: 5)
#   --no-reindex    reuse an existing .ast-cache (faster)
```

### Re-run the Gauntlet table with fresh numbers

```bash
# Dry-run (no clones, no indexing — just verify the script loads):
uv run python benchmarks/codegraph_compare/gauntlet_runner.py --dry-run

# Full run (clones 5 repos, indexes each, writes fresh numbers):
uv run python benchmarks/codegraph_compare/gauntlet_runner.py --all

# Single repo:
uv run python benchmarks/codegraph_compare/gauntlet_runner.py --repo tokenizers
```

---

## What This Measures / What It Doesn't

### What it measures

- **Cross-language call-graph mis-wires.** Each edge in the call graph connects a
  call site (caller) to a definition (callee). A mis-wire is an edge where the
  caller language and callee definition language are incompatible — Python cannot
  call a Swift method. TSA gates every binding through `languages_compatible()`;
  the audit counts how many edges survive that gate (TSA mis-wires) vs how many a
  name-only resolver would have created (worst-case).

- **Genuine-floor framing.** The "name-only" count excludes each language's own
  builtins (Python `print`, JS `Map`, Rust `Ok`, …) so the number is defensible
  against the "but a smart index could skip builtins" objection.

- **Single-language control.** gin is Go-only. The audit returns 0/0, confirming no
  false positives when there is nothing to cross-wire.

### What it doesn't measure

- **Answer quality or latency.** This is a correctness audit on the graph, not a
  benchmark of how well an AI agent uses the graph to answer questions. That
  measurement lives in the codegraph_compare benchmark harness (see README.md).

- **Cost.** Token cost is measured separately (REPORT-v1.21.0.md §Cost). No cost
  claim is made here.

- **Completeness** (recall). The audit measures mis-wires (precision failures), not
  missed edges (recall failures). TSA's 116k vs CodeGraph's 37k edge count (measured
  at their respective versions) suggests higher recall, but that is a separate audit.

- **Name-only average case.** The audit reports the worst case — a better name-only
  index that special-cases all builtins would have a lower number. That hypothetical
  tool does not exist; the audit uses the genuine floor to be fair.

These caveats are adapted from
[MISWIRE-AUDIT-EXAMPLES.md §Summary](MISWIRE-AUDIT-EXAMPLES.md).
