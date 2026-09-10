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
# => 299      (v1.21.0 index)
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

> **Methodology note (v1.29.0 re-measurement, 2026-07-10).**
> External repo rows (tokenizers, ruff, polars, gin) are from the v1.21.0 run
> (2026-06-07) and are marked for re-measurement. The `tree-sitter-analyzer`
> (this repo) row was re-measured against the v1.29.0-line develop branch on
> 2026-07-10 (commit `6fe62fba`). That re-measurement is not a clean tag checkout
> — see the reproducibility note in
> [GAUNTLET.md](../../benchmarks/codegraph_compare/GAUNTLET.md) for the exact
> protocol. Re-run `gauntlet_runner.py --all` from a clean tag checkout before
> publication to refresh external repo rows.

| repo | languages | call edges | name-only genuine floor | TSA mis-wires | measured at |
|---|---|---|---|---|---|
| huggingface/tokenizers | Rust+Py+JS+TS | 16,329 | **1,259** (7.71%) | **0** | v1.21.0 (2026-06-07) |
| astral-sh/ruff | Rust+Py+TS | 187,418 | **7,557** (4.03%) | **0** | v1.21.0 (2026-06-07) |
| pola-rs/polars | Rust+Py | 267,066 | **9,016** (3.38%) | **0** | v1.21.0 (2026-06-07) |
| tree-sitter-analyzer (this repo) | 14 langs | 133,377 | **724** (0.54%) | **4** | v1.29.0-line (2026-07-10) |
| gin-gonic/gin | Go (single) | 9,134 | **0** | **0** | v1.21.0 (2026-06-07) |

Across all four polyglot repos, TSA resolves **0 cross-language mis-wires**. The
4 on its own repo are genuine collisions on its own test-corpus files (Swift,
Java, Kotlin) — the documented ceiling without receiver-type inference. The
single-language repo (gin) correctly returns 0 and 0 — no false positives.

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
a name-only index would genuinely mis-wire (builtins excluded), 0 that TSA mis-wires.

## The Live Head-to-Head (with Methodology Annotation)

On this repo itself, with both tools' live indexes, the last complete same-session
comparison (both arms measured in the same session, same commit) used v1.21.0:

| tool | cross-language mis-wires | total call edges | mis-wire rate | measured at |
|---|---|---|---|---|
| CodeGraph | **745** | 38,103 | **1.96%** | v1.21.0, same session |
| tree-sitter-analyzer | **6** | 114,160 | **0.005%** | v1.21.0, same session |

**Two ratios, same measurement — choose the one that fits your question:**

- **By mis-wire count: ~124x cleaner.** Raw count ratio: 745 / 6 = 124.2.
  This answers "how many fewer wrong edges are there in absolute terms?"
- **By mis-wire rate: ~390x cleaner.** Rate ratio: 1.96% / 0.005% = 392.
  This answers "how much cleaner is the graph once you normalize for TSA
  resolving 3x more call edges overall?"

Both are honest; they are two different arithmetic operations on the same two raw
numbers, not two different measurements. See
[GAUNTLET.md](../../benchmarks/codegraph_compare/GAUNTLET.md) for the full methodology note.

**Re-verification attempt (2026-07-10).** A fresh same-session CodeGraph + TSA
re-run was attempted against current develop (v1.29.0-line). The CodeGraph arm
could not be completed: the `codegraph` CLI invoked by the harness does not
correspond to any publicly documented, installable package. The closest candidate
(`codegraphcontext` / `cgc`) has a different CLI surface and backend incompatible
with the harness's SQLite-query protocol. Because the CodeGraph arm did not
complete, no new CodeGraph-vs-TSA ratio is claimed this session. The v1.21.0
same-session pair above remains the last valid head-to-head.

## Try It on Your Own Code

The audit requires no CodeGraph install. It runs against TSA's own index:

```bash
uvx --from tree-sitter-analyzer miswire-audit .
```

The output shows your total call edges, how many a name-only resolver would
mis-wire (genuine floor, builtins excluded), how many TSA mis-wires, the
multiplier, and the top offending edges with file:line locations.

Add `--card` to get a self-contained markdown scorecard you can paste to an
issue or PR:

```bash
uvx --from tree-sitter-analyzer miswire-audit . --card
```

Example output:

```
## Mis-wire scorecard: my-project

| metric | value |
|---|---|
| total call edges | 24,831 |
| name-only genuine floor | 1,204 (4.85%) |
| TSA mis-wires | 0 |
| multiplier | infinity (0 TSA vs 1,204 name-only) |

Run: `uvx --from tree-sitter-analyzer miswire-audit . --card`
```

The audit is designed to work on any polyglot repo. If your codebase is
single-language, the expected result is 0 and 0. If it is polyglot and you are
using a name-only index for agent-assisted refactoring, the genuine-floor column
will tell you the scale of the problem on your specific code.

## Conclusion: The Agent Trust Problem

Code-intelligence tools for AI agents face a different success criterion than
tools for human developers. A human reading "sorted [Swift method]" in a call
graph knows immediately that something is wrong — the context makes it obvious.
An AI agent following a refactoring plan does not. It will act on the graph as
given.

That asymmetry makes mis-wires an agent-trust problem, not just a data-quality
problem. An agent that cannot distinguish "unresolved" from "wired-to-wrong-language"
will produce incorrect edits with high confidence. The damage scales with
autonomy: the more the agent is trusted to act without human review, the more
a systematic mis-wire corrupts the output.

TSA's conservative policy — report unknown rather than assert wrong — is
designed for this environment. The Gauntlet numbers demonstrate it works on
real polyglot repos at scale.

---

*Source data: [GAUNTLET.md](../../benchmarks/codegraph_compare/GAUNTLET.md) and
[REPORT-v1.21.0.md](../../benchmarks/codegraph_compare/REPORT-v1.21.0.md).
Methodology: both count-based (~124x) and rate-based (~390x) ratios come from
the same v1.21.0 same-session measurement — see GAUNTLET.md for the full note
on why this project reports both rather than collapsing to a single number.*
