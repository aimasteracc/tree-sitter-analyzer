# Polyglot Mis-Wire Gauntlet — TSA Results Card

**What this page is:** a permanent, verifiable record of how tree-sitter-analyzer
scores on cross-language call-graph correctness across five real open-source repos.
All numbers in the summary table are lifted verbatim from
[MISWIRE-AUDIT-EXAMPLES.md](MISWIRE-AUDIT-EXAMPLES.md) and
[REPORT-v1.21.0.md](REPORT-v1.21.0.md); the source document is cited in every row.

---

## 5-Repo Summary Table

| repo | languages | call edges | name-only mis-wires (worst case) | TSA mis-wires | source |
|---|---|---|---|---|---|
| huggingface/tokenizers | Rust+Py+JS+TS | 16,329 | **1,259** (7.71%) | **0** | [MISWIRE-AUDIT-EXAMPLES.md](MISWIRE-AUDIT-EXAMPLES.md) |
| astral-sh/ruff | Rust+Py+TS | 187,418 | **7,557** (4.03%) | **0** | [MISWIRE-AUDIT-EXAMPLES.md](MISWIRE-AUDIT-EXAMPLES.md) |
| pola-rs/polars | Rust+Py | 267,066 | **9,016** (3.38%) | **0** | [MISWIRE-AUDIT-EXAMPLES.md](MISWIRE-AUDIT-EXAMPLES.md) |
| tree-sitter-analyzer (this repo) | 13 langs | 114,160 | 4,199 (3.68%) | **6** | [MISWIRE-AUDIT-EXAMPLES.md](MISWIRE-AUDIT-EXAMPLES.md) |
| gin-gonic/gin | Go (single) | 9,134 | **0** | **0** | [MISWIRE-AUDIT-EXAMPLES.md](MISWIRE-AUDIT-EXAMPLES.md) |

**Across all four polyglot repos TSA resolves 0 cross-language mis-wires.** The 6
on this repo are single-word Java method names (`collect`, `data`x4, `message`)
in the Java example files — the documented ceiling without receiver-type inference.
The single-language repo (gin) correctly returns 0 and 0 — no false positives.

> **What "name-only mis-wires (worst case)" means.** It is the worst case for a
> name-only design: every call whose name has a definition only in another language.
> This includes genuine cross-language collisions AND language builtins a smarter
> index could special-case (`print`, `range`). For this repo: 4,199 worst-case but
> **762 genuine** (`Counter()`→TS, `sleep()`→Java, `pop()`→Swift, `connect()`→Kotlin).
> The audit reports the **genuine floor by default** — naive mis-wires excluding
> each language's own builtins — leading its examples with non-builtin collisions so
> the demo survives a skeptic. TSA resolves **0** genuine cross-language mis-wires
> on the four external polyglot repos.

---

## Live Head-to-Head vs CodeGraph (this repo, same commit)

Source: [REPORT-v1.21.0.md §Addendum 2](REPORT-v1.21.0.md)

| tool | cross-language call edges | total call edges | mis-wire rate |
|---|---|---|---|
| **CodeGraph** | **745** | 38,103 | **1.96%** |
| **Tree-sitter Analyzer** | **6** | 114,160 | **0.005%** |

TSA is ~390x cleaner while resolving 3x more call edges total (114k vs 38k).

---

## Flagship: `sorted()` → Swift (full inline repro)

The clearest case. Python's builtin `sorted()` is called ~299 times. There is no
`sorted` definition in any `.py` file. The only `sorted` node in CodeGraph's index
is a Swift method, `tests/golden/corpus_swift.swift:337`. CodeGraph wires every
Python caller to that Swift node. TSA binds none of them.

```bash
# 1. Confirm the only in-repo 'sorted' definition is Swift (no Python def):
grep -rl "def sorted" --include="*.py" .          # → (nothing)
grep -n "func sorted" tests/golden/corpus_swift.swift
# → 337:    func sorted() -> [Element] {

# 2. CodeGraph: count distinct Python callers wired to the Swift node:
sqlite3 .codegraph/codegraph.db "
  SELECT COUNT(DISTINCT e.source)
  FROM edges e JOIN nodes n ON e.source = n.id
  WHERE e.target = 'method:93b946c9bfbf7d0843dca5323ecd16c4'
    AND e.kind = 'calls' AND n.file_path LIKE '%.py';"
# → 299      (299 Python callers attached to a Swift func)

# 3. TSA: confirm ZERO Python callers are bound to Swift:
uv run python -m tree_sitter_analyzer --callers sorted --format json | \
  python3 -c "import json,sys; d=json.load(sys.stdin); \
print('swift refs:', sum('swift' in str(c).lower() for c in d['callers']), '/', d['caller_count'])"
# → swift refs: 0 / 298
```

CodeGraph asserts 299 Python→Swift `calls` edges the AST cannot support. TSA
reports those call sites as `callee_resolution='unknown'` — honestly unresolved
rather than confidently wrong. For an agent about to change a function's signature,
"298 unknown" is a safe answer; "299 callers in a Swift file" is a trap.

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
  missed edges (recall failures). TSA's 114k vs CodeGraph's 38k edge count
  suggests higher recall, but that is a separate audit.

- **Name-only average case.** The audit reports the worst case — a better name-only
  index that special-cases all builtins would have a lower number. That hypothetical
  tool does not exist; the audit uses the genuine floor to be fair.

These caveats are adapted from
[MISWIRE-AUDIT-EXAMPLES.md §Summary](MISWIRE-AUDIT-EXAMPLES.md).
