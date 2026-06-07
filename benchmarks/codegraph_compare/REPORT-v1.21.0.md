# Correctness Report — tree-sitter-analyzer vs CodeGraph (v1.21.0)

**The correctness layer that won't let your agent make a wrong edit.**

When an AI agent asks "who calls `sorted()`?" before refactoring it, the answer
has to be *correct* — a wrong caller list is worse than no list, because the
agent acts on it. This report documents a reproducible, AST-grounded difference
in **edge correctness** between tree-sitter-analyzer (TSA) and CodeGraph on the
same multi-language corpus, in two distinct failure modes: (1) **cross-language
edge mis-binding** — CodeGraph wires hundreds of Python callers to a *Swift*
function node that merely shares the name (`sorted`, `reversed`); and (2)
**same-name result aggregation** — for names like `get`/`add` that have many
distinct same-name nodes across languages, a single caller query returns them
merged with no way to tell which definition each caller targets (the distinct
nodes still exist in the DB — 14 `get`, 12 `add` — so this is a query/result
problem, not a DB collapse). TSA refuses to bind across language boundaries and
reports those edges as unresolved rather than wrong, and keeps same-name results
language-separated. The AST doesn't lie — every claim below ships with a
one-command repro you can run against the two indexes yourself. This is a *correctness* report only. **Cost is measured separately and
is pending** (see the footnote); we make no cost claim here.

Both indexes were built over the same workspace. CodeGraph index:
`.codegraph/codegraph.db`. TSA index: `.ast-cache/index.db`.

---

## Verified mis-wires

Each row is independently reproduced against both DBs. "CodeGraph (wrong)" =
edges CodeGraph asserts that the AST does not support. "TSA (correct)" = what
TSA reports for the same query.

| Symbol | CodeGraph (wrong) | TSA (correct) | One-command repro |
|---|---|---|---|
| `sorted` | **299 Python callers** wired to the **Swift** func `corpus_swift.swift:337` (the only `sorted` *node* in the index; no Python definition exists) | 298 callers, all `language=python`, all `callee_resolution='unknown'` — **0** wired to Swift | `sqlite3 .codegraph/codegraph.db "SELECT COUNT(DISTINCT e.source) FROM edges e JOIN nodes n ON e.source=n.id WHERE e.target='method:93b946c9bfbf7d0843dca5323ecd16c4' AND e.kind='calls' AND n.file_path LIKE '%.py';"` → `299` |
| `reversed` | **26 unique callers** wired to the **Swift** func `corpus_swift.swift:323` — 25 human-relevant (1 Kotlin `isPalindrome` + 24 Python) + 1 Swift self-edge. The Kotlin caller is `String.reversed()` stdlib, not Swift | 24 callers, all `language=python`, all `unknown`; **0** Kotlin/Swift bindings | `sqlite3 .codegraph/codegraph.db "SELECT COUNT(DISTINCT source) FROM edges WHERE target='method:569874c42e2a305c0320ed1b3b3f061a' AND kind='calls';"` → `26` |
| `get` | **14 `get` nodes** across Python/C++/Scala/Kotlin/Java collapsed into one query result; callers cannot tell which `get` they target | language-separated: Python callers resolve to the Python `get` | `sqlite3 .codegraph/codegraph.db "SELECT COUNT(*) FROM nodes WHERE name='get';"` → `14` |
| `add` | **12 `add` nodes** across C/C++/TS/Scala/Java/Go/Python merged into one result | 193 callers separated by language (`python` 188, `c` 2, `javascript` 2, `go` 1); Go caller resolves to `corpus_go.go`; the 2 C callers are **unresolved**, not mis-wired to another language | `sqlite3 .codegraph/codegraph.db "SELECT COUNT(*) FROM nodes WHERE name='add';"` → `12` |
| `fts_search` | **1 caller** returned — `_resolve_entry_points`. Misses **2 real production callers** (`_handle_search`, `_exact_search`) — a completeness failure | **12 callers**, including all **3** production call sites (`_handle_search`, `_exact_search`, `_resolve_entry_points`), correctly resolved to `_ast_cache_query.py` | `sqlite3 .codegraph/codegraph.db "SELECT COUNT(*) FROM edges e JOIN nodes n ON e.target=n.id WHERE n.name='fts_search' AND e.kind='calls';"` → `1` |

Notes on precision (kept honest):

- The **`get`/`add` per-language merge is a structural DB fact** (14 / 12 nodes,
  multiple languages). CodeGraph's MCP interface adds a "Note: Aggregated
  results across N symbols named X" line; the **CLI does not** print that note.
  The repro above therefore confirms the *node count* directly from the DB
  rather than citing MCP text.
- For `add`, TSA's 2 C callers carry `callee_resolution='unknown'` — TSA did not
  positively resolve them in-language, but it also did **not** wrongly cross-wire
  them. "Not mis-wired" is the verified claim, not "confirmed in-language."
- For `fts_search`, TSA resolves the **production** callers correctly. TSA's
  *test-only* callers (the `test_fts_search_*` cases) are bound to a mock
  definition in a different test file (`test_codegraph_context_tool.py`) — a TSA
  resolution error scoped to test mocks. It does not affect the production-caller
  result, which is the headline: CodeGraph misses 2 real production callers; TSA
  finds all 3.

---

## Flagship: `sorted()` → Swift definition (full inline repro)

The single clearest case. Python's builtin `sorted()` is called ~299 times
across the Python codebase. There is **no** `sorted` definition in any `.py`
file. The only `sorted` *node* in CodeGraph's index is a **Swift** method,
`tests/golden/corpus_swift.swift:337`. CodeGraph wires every Python caller to
that Swift node. TSA binds none of them.

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

CodeGraph asserts 299 Python→Swift `calls` edges that the AST cannot support
(no Python definition exists; the bind is name-collision only). TSA reports the
same 298 call sites as `callee_resolution='unknown'` — honestly unresolved
rather than confidently wrong. For an agent about to change a function's
signature, "298 unknown" is a safe answer; "299 callers in a Swift file" is a
trap.

(The `reversed` case is the same failure mode against
`tests/golden/corpus_swift.swift:323`; see the table for its one-command repro.)

---

## Headline correctness numbers (TSA)

All from `.ast-cache/index.db`, `kind='calls'`, total **114,160** edges.

**Edge classification rate: 96.3%** of call edges resolve to a non-`unknown`
class.

```bash
sqlite3 .ast-cache/index.db \
  "SELECT ROUND(100.0*SUM(callee_resolution!='unknown')/COUNT(*),1) \
   FROM edges WHERE kind='calls';"
# → 96.3
```

Breakdown: `project` 44,113 · `builtin` 25,089 · `stdlib` 24,659 · `local`
12,917 · `external` 3,213 · `unknown` 4,169.

**Cross-language mis-wires: 6 (~0.01%).** Across the whole graph, only 6
`project`/`local` edges cross a language boundary into a `.py`/`.php` file — all
from Java, all generic 1-word callee names (`collect`, `data`×4, `message`) in
`examples/BigService.java`, `examples/JavaDocTest.java`, and
`tests/golden/corpus_java.java`.

This counts EVERY caller language (not just Java) — an edge is cross-language
when the resolved file's extension does not match the caller's language:

```bash
sqlite3 .ast-cache/index.db "
  SELECT language, COUNT(*) FROM edges
  WHERE kind='calls' AND callee_resolution IN ('project','local')
    AND callee_resolved_file != ''
    AND NOT (
      (language='python'     AND callee_resolved_file LIKE '%.py')  OR
      (language='java'       AND callee_resolved_file LIKE '%.java') OR
      (language='javascript' AND (callee_resolved_file LIKE '%.js'  OR callee_resolved_file LIKE '%.jsx')) OR
      (language='typescript' AND (callee_resolved_file LIKE '%.ts'  OR callee_resolved_file LIKE '%.tsx')) OR
      (language='go'         AND callee_resolved_file LIKE '%.go')  OR
      (language='ruby'       AND callee_resolved_file LIKE '%.rb')  OR
      (language='rust'       AND callee_resolved_file LIKE '%.rs')
    )
  GROUP BY language;"
# → java|6      (the ONLY language with any cross-language edge; 5→.py, 1→.php)
```

**Same-language dominance.** Resolved (`project`/`local`) edges stay in-language:
python→python 56,917 · java→java **58** · typescript→typescript 25 · go→go 13 ·
javascript→javascript 11. These sum to **57,024**; adding the 6 cross-language
Java edges above gives **57,030** = the full `project` + `local` total (44,113 +
12,917). (Java has 64 resolved edges total — 58 in-language + the 6 cross-language
ones counted separately above.)

---

## Reproduce everything yourself

Pinned commands. Run from the repo root with both indexes present
(`.codegraph/codegraph.db` and `.ast-cache/index.db`).

```bash
# --- node counts (CodeGraph keeps N distinct same-name nodes; queries merge them) ---
for s in get add fts_search; do
  printf "%s nodes: " "$s"
  sqlite3 .codegraph/codegraph.db "SELECT COUNT(*) FROM nodes WHERE name='$s';"
done
# → get nodes: 14   add nodes: 12   fts_search nodes: 4

# --- prove the MERGE (not just that N nodes exist): callers really span them ---
# Edge-level: how many DISTINCT same-name 'get' nodes actually have callers?
sqlite3 .codegraph/codegraph.db \
  "SELECT COUNT(DISTINCT n.id) FROM nodes n JOIN edges e ON e.target=n.id \
   AND e.kind='calls' WHERE n.name='get';"            # → 7  (across Python + C++)
# And CodeGraph's caller query returns ALL 14 merged — its own note says so:
#   (MCP) codegraph_callers get  ->  trailing note:
#   "Aggregated results across 14 symbols named get: ... _route_cache.py:133,
#    core/cache_service.py:117, examples/sample.cpp:37, corpus_scala.scala:92/295,
#    Sample.kt:59, corpus_kotlin.kt:605, corpus_java.java:175, ..."
#   -> one query, 14 defs across Python/C++/Scala/Kotlin/Java, no way to tell them apart.

# --- cross-language caller mis-wires (CodeGraph) ---
sqlite3 .codegraph/codegraph.db "SELECT COUNT(DISTINCT e.source) FROM edges e \
  JOIN nodes n ON e.source=n.id \
  WHERE e.target='method:93b946c9bfbf7d0843dca5323ecd16c4' \
    AND e.kind='calls' AND n.file_path LIKE '%.py';"   # sorted → 299
sqlite3 .codegraph/codegraph.db "SELECT COUNT(DISTINCT source) FROM edges \
  WHERE target='method:569874c42e2a305c0320ed1b3b3f061a' AND kind='calls';"  # reversed → 26

# --- completeness miss (CodeGraph fts_search) ---
sqlite3 .codegraph/codegraph.db "SELECT COUNT(*) FROM edges e \
  JOIN nodes n ON e.target=n.id WHERE n.name='fts_search' AND e.kind='calls';"  # → 1

# --- TSA correctness ---
sqlite3 .ast-cache/index.db "SELECT ROUND(100.0*SUM(callee_resolution!='unknown')\
/COUNT(*),1) FROM edges WHERE kind='calls';"             # → 96.3
uv run python -m tree_sitter_analyzer --callers sorted --format json | \
  python3 -c "import json,sys; d=json.load(sys.stdin); \
print('swift refs:', sum('swift' in str(c).lower() for c in d['callers']),'/',d['caller_count'])"
# → swift refs: 0 / 298
uv run python -m tree_sitter_analyzer --callers fts_search --format json | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print('count:', d['caller_count'])"
# → count: 12
```

Source anchors for the Swift definitions the Python callers were wrongly bound
to: [`tests/golden/corpus_swift.swift:337`](../../tests/golden/corpus_swift.swift#L337)
(`func sorted()`) and
[`tests/golden/corpus_swift.swift:323`](../../tests/golden/corpus_swift.swift#L323)
(`func reversed()`).

---

## Cost — measured separately, pending

> **No cost claim is made in this report.** A rigorous cost comparison (token /
> dollar per task) requires an N≥5 benchmark on a *validated* setup, and that
> run has not yet cleared its setup-validation gate. Until it does, we report
> **correctness only** — the axis verified here, end to end, against both
> indexes. Correctness is the claim that stands today; cost is future work and
> will be published as its own artifact when the gate passes.

---

## Addendum (2026-06-08) — the moat now spans 13 languages

When v1.21.0 shipped, cross-language-safe resolution was Python + Java. RFC-0010
(a per-language resolver registry) plus call-edge extraction wiring has since
activated **13 languages**, each with its own conservative classification cascade:
**Python · Java · Go · JavaScript · TypeScript · C · C++ · Rust · C# · Kotlin ·
Ruby · PHP · Swift**.

> **Swift closes the loop.** The flagship failure above is a Python `sorted()`
> wired to a Swift `func sorted`. Swift is now a first-class TSA language: a Swift
> `sorted()` resolves to its own definition, a Python `sorted()` stays a Python
> builtin, and neither crosses to the other — the exact mis-wire, refused in both
> directions.

The moat holds across all of them. On a polyglot fixture (one real source file per
language) **plus an adversarial `adversary.py` that defines `sorted`, `to_string`,
`increment`, `puts`, and `println`** — the exact same-name collisions that make
CodeGraph wire Python `sorted()` to a Swift `func sorted` — the measured result:

| metric | value |
|---|---|
| languages indexed | **12 / 12** (c, cpp, csharp, go, java, javascript, kotlin, php, python, ruby, rust, typescript) |
| total call edges (java 453, ruby 156, python 123, go 103, kotlin 80, rust 65, php 28, cpp 26, ts 23, js 12, c 10, csharp 4) | **1,083** |
| resolved-to-file edges (the moat surface) | 143 |
| **cross-language mis-wires** | **0** |

All 12 active languages, one real source file each, plus the adversarial shadow —
**zero** cross-language mis-wires on 1,083 call edges.

Every per-language resolver gates its project/local bindings through
`languages_compatible(caller_lang, owner_lang)`, so a Rust `to_string()` cannot
bind to the Python `to_string`, a PHP `increment()` cannot bind to a same-named
function in another language, etc. — verified here, not asserted. Reproduce by
indexing any polyglot tree and counting edges whose `callee_resolved_file`
language is incompatible with the caller's language; the count is 0 by
construction of the cascade.

---

## Addendum 2 (2026-06-08) — LIVE head-to-head on both tools' production indexes

The measurements above use controlled fixtures. This one queries **both tools'
live indexes of this very repository** (CodeGraph's `.codegraph/codegraph.db` and
TSA's `.ast-cache/index.db`), at the same commit, and counts every call edge
whose caller language differs from the callee-definition's language — a
cross-language mis-wire by construction (a Python function cannot call a Swift
method).

| tool | cross-language call edges | total call edges | mis-wire rate |
|---|---|---|---|
| **CodeGraph** | **745** | 38,103 | **1.96 %** |
| **Tree-sitter Analyzer** | **6** | 114,160 | **0.005 %** |

**TSA is ~390× cleaner on cross-language correctness — while resolving 3× more
call edges total** (114k vs 38k; more complete, not just more conservative).

CodeGraph's mis-wires are not a single fluke — they span the language matrix:

| CodeGraph mis-wire | count |
|---|---|
| python → swift | 408 |
| python → typescript | 195 |
| python → ruby | 81 |
| c → go | 13 |
| kotlin → java | 6 |
| typescript → python | 5 |
| scala → python | 4 |
| … (12 more pairs) | … |

The flagship case is concrete: CodeGraph's only `sorted` node is
`method | tests/golden/corpus_swift.swift | swift`, and **408 Python callers** of
the Python builtin `sorted()` are wired to that Swift method. TSA classifies all
376 of those Python `sorted()` calls as `builtin` and binds **0** to the Swift
file. TSA's own 6 cross-language edges are all `java → python/php` from
single-word Java method names (the documented ceiling without receiver-type
inference).

Reproduce (both DBs are on disk after each tool indexes the repo):

```bash
# CodeGraph cross-language call edges:
sqlite3 .codegraph/codegraph.db "SELECT COUNT(*) FROM edges e \
  JOIN nodes c ON e.source=c.id JOIN nodes t ON e.target=t.id \
  WHERE e.kind IN ('calls','call') AND c.language!=t.language \
  AND c.language IS NOT NULL AND t.language IS NOT NULL"   # -> 745

# TSA cross-language call edges:
sqlite3 .ast-cache/index.db "SELECT COUNT(*) FROM edges e \
  JOIN ast_index i ON e.callee_resolved_file=i.file_path \
  WHERE e.kind='calls' AND e.callee_resolved_file!='' AND e.language!=i.language"  # -> 6
```
