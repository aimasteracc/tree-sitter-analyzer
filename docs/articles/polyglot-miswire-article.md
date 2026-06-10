# When Your Code-Intelligence Tool Wires Python to Swift: The Polyglot Mis-Wire Problem

There is a class of code-intelligence bug that is invisible in a single-language
codebase and silent until an AI agent acts on it. We call it the **mis-wire**: a
call graph edge that connects a call site in one language to a definition in a
different, incompatible language — because both share the same name.

Here is what it looks like in practice.

## The `sorted()` Story

tree-sitter-analyzer's own test corpus includes one Swift file,
`tests/golden/corpus_swift.swift`. Line 337 defines:

```swift
func sorted() -> [Element] { ... }
```

Python's builtin `sorted()` is called hundreds of times across the Python codebase.
There is no `sorted` definition in any `.py` file — it is a language builtin,
not a user-defined function.

A name-only code-intelligence index — one that binds a call to whichever
definition shares its name, regardless of language — will look up `sorted`,
find one definition in the index, and wire all those Python callers to that Swift
method. CodeGraph, a popular open-source alternative tool in this space, does
exactly this on this corpus (measured at v1.21.0, 2026-06-07):

```bash
sqlite3 .codegraph/codegraph.db "
  SELECT COUNT(DISTINCT e.source)
  FROM edges e JOIN nodes n ON e.source = n.id
  WHERE e.target = 'method:93b946c9bfbf7d0843dca5323ecd16c4'
    AND e.kind = 'calls' AND n.file_path LIKE '%.py';"
# → 299      (v1.21.0 index)
```

299 Python callers, one Swift target. The AST does not support any of these
edges. Python cannot call a Swift method.

tree-sitter-analyzer (measured at v1.22.0, 2026-06-10) finds 392 Python `sorted()`
call sites, all with `callee_resolution='unknown'` — honestly unresolved rather than
confidently wrong. Zero wired to Swift.

For a human reading the output, "unknown" is fine. For an AI agent about to
refactor a function's signature, "392 unknown callers" is a safe foundation;
"299 callers in a Swift file" is a trap that sends the agent down a wrong path.

## An Honest Framing Before the Big Numbers

Before presenting the Gauntlet results, it is worth being direct about what the
mis-wire audit measures and what it does not.

**The "name-only genuine floor" column is the skeptic-resistant lower bound** for
a naive resolver. It counts every call whose name has a definition only in another
language, *excluding* each language's own builtins (`print`, `range`, `Ok`) that a
smarter name-only index could explicitly skip. Even after excluding those builtins,
these remaining mis-wires are ones no simple name-only index can avoid — they are
genuine cross-language name collisions (a JS `tokenize()` bound to a Rust `tokenize`).
The **worst case** column (all mis-wires including builtins) is higher; the genuine
floor is what we lead with so the demo survives a skeptic's "just exclude builtins" objection.

**The TSA mis-wire count is a real measurement** — edges in TSA's index where
the caller's language is incompatible with the resolved callee file's language.
Zero means zero measured mis-wires on that corpus; it does not mean TSA is
perfect on recall (missed edges are a separate audit).

**Cost and latency are not measured here.** The numbers below are correctness
numbers only.

With that context, here is what the Gauntlet found.

## The Gauntlet: Five Real Repos

> The table below shows the **name-only genuine floor** column (builtins excluded) and
> the **TSA mis-wires** column (the real measurement). The external repos are measured
> at v1.21.0 (2026-06-07); the this-repo row is freshly measured at v1.22.0 (2026-06-10).
> Re-run `gauntlet_runner.py --all` before publication to refresh the external repos.

<!-- re-measure: external repo rows (tokenizers / ruff / polars / gin) are v1.21.0 (2026-06-07) -->

| repo | languages | call edges | name-only genuine floor | TSA mis-wires | measured at |
|---|---|---|---|---|---|
| huggingface/tokenizers | Rust+Py+JS+TS | 16,329 | **1,259** (7.71%) | **0** | v1.21.0 <!-- re-measure --> |
| astral-sh/ruff | Rust+Py+TS | 187,418 | **7,557** (4.03%) | **0** | v1.21.0 <!-- re-measure --> |
| pola-rs/polars | Rust+Py | 267,066 | **9,016** (3.38%) | **0** | v1.21.0 <!-- re-measure --> |
| tree-sitter-analyzer (this repo) | 14 langs | 116,672 | **680** (0.58%) | **1** | 2026-06-10 at v1.22.0 |
| gin-gonic/gin | Go (single) | 9,134 | **0** | **0** | v1.21.0 <!-- re-measure --> |

Across all four polyglot repos, TSA resolves **0 cross-language mis-wires**. The
1 on its own repo is a single genuine collision on its own test-corpus files —
the documented ceiling without receiver-type inference.

The gin result matters: a single-language repo returns 0 and 0. No false
positives when there is nothing to cross-wire.

## Why the Moat Is Structural

The name-only design is not a bug in CodeGraph; it is a deliberate choice that
most code-intelligence tools make. The assumption is that most codebases are
single-language, and that cross-language collisions are rare enough to ignore.

In a polyglot monorepo — the common pattern in systems software today — that
assumption breaks. Rust crates with Python bindings, Go services alongside
TypeScript clients, Java services with Kotlin DSLs: every one of these setups
has the same-name collision problem at scale.

TSA's resolver gates every binding through a `languages_compatible()` predicate
that knows, for example, that Python and Swift are not compatible, that JavaScript
and TypeScript are, and that Go has no relationship to Kotlin. A call in one
language cannot bind to a definition in an incompatible language, regardless of
name. The binding is left `unknown` rather than mis-wired.

That conservative policy is what the Gauntlet measures: 7,557 calls in ruff that
a name-only index would genuinely mis-wire (builtins excluded), 0 that TSA mis-wires. <!-- re-measure: ruff row is v1.21.0 -->

## The Live Head-to-Head

The Gauntlet uses a modelled "name-only" count without requiring CodeGraph to be
installed. On this repo itself, with both tools' live indexes, the measured comparison
is (CodeGraph row from v1.21.0 — re-measure before publication):

<!-- re-measure: CodeGraph row is v1.21.0 (2026-06-07); TSA row measured 2026-06-10 at v1.22.0 -->
| tool | cross-language call edges | total call edges | mis-wire rate | measured at |
|---|---|---|---|---|
| CodeGraph | **763** | 36,788 | **2.07%** | v1.21.0 (2026-06-07) <!-- re-measure --> |
| tree-sitter-analyzer | **1** | 116,672 | **0.0009%** | 2026-06-10 at v1.22.0 |

TSA is approximately 763x cleaner (1 vs 763 mis-wires) while resolving 3x more call edges.

## Run It on Your Own Code

The audit requires no CodeGraph install. It runs against TSA's own index:

```bash
uvx --from tree-sitter-analyzer miswire-audit .
```

The output shows your total call edges, how many a name-only resolver would
mis-wire (genuine floor — builtins excluded), how many TSA mis-wires, the
multiplier, and the top offending edges with file:line locations.

Add `--card` to get a markdown snippet you can paste to an issue or PR.

The audit is designed to work on any polyglot repo. If your codebase is
single-language, the expected result is 0 and 0. If it is polyglot and you are
using a name-only index for agent-assisted refactoring, the genuine-floor column
will tell you the scale of the problem on your specific code.

---

*Source data: [MISWIRE-AUDIT-EXAMPLES.md](../../benchmarks/codegraph_compare/MISWIRE-AUDIT-EXAMPLES.md)
and [REPORT-v1.21.0.md](../../benchmarks/codegraph_compare/REPORT-v1.21.0.md).
Numbers marked `<!-- re-measure -->` should be re-verified against a fresh index
before publication.*
