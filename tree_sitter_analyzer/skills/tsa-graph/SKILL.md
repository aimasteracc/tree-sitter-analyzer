---
name: tsa-graph
version: 2.1.0
description: |
  Code archaeology via call graph + symbol resolution. Answer "who calls X",
  "what does Y call", "where is Z defined", "what's the path from A to B" in
  one MCP call instead of multi-step grep + read. Uses persisted cross-file
  resolution (Synapse) so cross-module edges are precise, not regex-guessed.
  Multi-hop questions ("who calls X and which tests cover them", "untested
  callers of Y in M", "impact of X") are ONE `search action=uql` call.

  Use when:
  - User asks "what calls this function" / "what does this function call"
  - "Which tests cover the callers of X" / "which callers are untested"
  - Tracing a bug through layers (impact → caller chain)
  - Planning refactor of a function/class (need full fanout)
  - "Where is this symbol defined" / "find all references to X"
  - "Show me the path from handler → DB"
  - "Draw a UML class/package/component/sequence diagram"

  Replaces: grep + read + manual chain-following (~10-30k tokens) with
  2-4 MCP calls (~1-3k tokens).
allowed-tools:
  - mcp__tree-sitter-analyzer__nav
  - mcp__tree-sitter-analyzer__search
  - mcp__tree-sitter-analyzer__structure
  - mcp__tree-sitter-analyzer__health
  - mcp__tree-sitter-analyzer__viz
  - Bash
  - Read
---

# tsa-graph — Code archaeology, one call deep

> This skill exposes the graph-focused tools that answer "who is connected to
> what" — the questions agents waste the most tokens on when they fall back to
> grep.

## When to use

Pick the right tool by question shape:

| Question                              | Tool                              |
|---------------------------------------|-----------------------------------|
| Who calls X **and** which tests cover those callers? | `search action=uql query="symbol('X').callers().tests()"` |
| Which callers of Y in module M have no tests? | `search action=uql query="symbol('Y').callers().filter(file='M').untested()"` |
| Callers of X to depth N, only under `src/`? | `search action=uql query="symbol('X').callers(depth=2).filter(path='src/')"` |
| Impact of changing X (transitive callers + tests + files)? | `search action=uql query="symbol('X').impact()"` |
| Need search + snippets + callers/callees together? | `search action=chain` |
| What does FUNCTION call?              | `nav action=callees`              |
| What calls FUNCTION? (one hop)        | `nav action=callers`              |
| Which tests exercise FUNCTION? (one symbol) | `nav action=test_map`       |
| Where is SYMBOL defined?              | `search action=symbol`            |
| What references SYMBOL anywhere?      | `nav action=xref`                 |
| Path from CALLER to CALLEE?           | `nav action=call_path`            |
| Resolve "Path" in file X (project or stdlib?) | `nav action=resolve`    |
| Need architecture diagram output?     | `viz action=uml`                  |

**Don't use** when:
- You need the actual *body* of the function → use `structure action=read`
- You're hunting a string literal in non-source files → use Grep

## Procedure

### Single-question case (90% of uses)

Pick the matching tool, call once. Read the response. Done.

Example: "what calls `score_file`?"

```
nav action=callers function_name="score_file" language="python" limit=20
```

Returns: `callers: [{name, file, line, callee_resolution, callee_resolved_file}, ...]`.
The `callee_resolution` field tells you `local` / `project` / `stdlib` /
`unknown` so you can filter out noise.

### Multi-hop case: one `uql` call, not one call per caller

If the answer to the first call would make you call `nav` again **for each
row** (test_map per caller, callers of each caller, a path filter you would
apply by hand), ask the whole question as one `search action=uql` query:

```
search action=uql query="symbol('score_file').callers().tests()"
```

Measured on the 8 RFC-0041 benchmark questions (TSA + rich): 1 call instead
of up to 13, about half the tokens per task, and every stage carries its own
completeness (`stages[].c` = complete / incomplete / unknown, with reason
codes) — `test_map`, `caller_tree` and TQL make no claim at all. Grammar: one
`search action=help target_action=uql` call. Read the total `completeness`
before saying "all" or "none"; `untested()` rows marked ` ?` are undecided,
not untested. Call-graph tests are not coverage (CLAUDE.md rule 5).

**Stay on the single tools when** the question is one hop and you do not
need a claim: `nav action=callers` (carries its own completeness), `nav
action=test_map` for one symbol's tests and `nav action=callees` are faster
and, for tests/callees, smaller than the uql answer. uql pays ~0.5–1.5 s more
tool time per question for the per-input proof.

For search plus source snippets (`explore`, `include`), keep the chain
surface — uql has no snippet stages:

```
search action=chain query="search('score_file').explore(max_files=3).callers(depth=1).callees(depth=1)"
```

### Multi-step case (refactor planning)

Fan out 3 in parallel:
1. `search action=uql query="symbol('X').impact()"` (who depends on this,
   transitively, with the tests and files to re-check — blast radius)
2. `nav action=callees` (what this depends on — what may need updating)
3. `search action=symbol` with the symbol name (find aliases / shadows)

Then if you need a specific reachability path:
```
nav action=call_path from_function="X" to_function="Y" max_depth=10
```

## Reading the new resolution fields (Synapse)

Each callee entry now carries:

```yaml
name: "Path"
file: ".../health_scorer.py"
line: 366
callee_resolution: stdlib | local | project | third_party | dynamic | unknown
callee_resolved_file: "" | "<file the callee lives in>"
callee_symbol_id: null | <int FK to ast_symbol_rows>
```

Filter rules of thumb:
- `resolution=stdlib` → ignore for change-impact (won't be in this repo)
- `resolution=local|project` with non-null `callee_symbol_id` → trustworthy edge
- `resolution=unknown` → may need re-index: `uv run tree-sitter-analyzer --ast-cache --ast-cache-mode index --ast-cache-force`

## CLI equivalents

```bash
uv run tree-sitter-analyzer --callees <FUNC> --output-format toon
uv run tree-sitter-analyzer --callers <FUNC> --output-format toon
uv run tree-sitter-analyzer --uql "symbol('<FUNC>').callers().tests()"
uv run tree-sitter-analyzer --symbol-search <NAME> --output-format toon
uv run tree-sitter-analyzer --codegraph-xref <SYMBOL> --output-format toon
uv run tree-sitter-analyzer --call-path --call-path-source X --call-path-target Y
uv run tree-sitter-analyzer --uml class --output-format toon
```

## Anti-patterns

- Don't `grep -rn "def X" tree_sitter_analyzer/` — use `search action=symbol` (10x faster, precise)
- Don't read 5 files to trace a call chain — use `nav action=call_path`
- Don't loop `nav action=test_map` / `nav action=callers` over the rows of a
  callers answer — that is one `search action=uql` query (nav appends this
  hint when it sees the loop)
- Don't ignore `callee_resolution` — `unknown` entries are noise, filter them

## Decision surface

```yaml
function: <queried name>
callee_count | caller_count: <int>
callees | callers: [
  {name, file, line, language, callee_resolution, callee_resolved_file}
]
verdict: INFO   # graph queries are observational, not actionable
```
