---
name: tsa-graph
version: 2.0.0
description: |
  Code archaeology via call graph + symbol resolution. Answer "who calls X",
  "what does Y call", "where is Z defined", "what's the path from A to B" in
  one MCP call instead of multi-step grep + read. Uses persisted cross-file
  resolution (Synapse) so cross-module edges are precise, not regex-guessed.

  Use when:
  - User asks "what calls this function" / "what does this function call"
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
| Need search + snippets + callers/callees together? | `search action=chain` |
| What does FUNCTION call?              | `nav action=callees`              |
| What calls FUNCTION?                  | `nav action=callers`              |
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

When a question needs several graph hops plus source snippets, prefer the
chain surface:

```
search action=chain query="search('score_file').explore(max_files=3).callers(depth=1).callees(depth=1)"
```

### Multi-step case (refactor planning)

Fan out 3 in parallel:
1. `nav action=callers` (who depends on this — blast radius)
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
- `resolution=unknown` → may need re-index: `uv run tree-sitter-analyzer --ast-cache --ast-cache-mode force`

## CLI equivalents

```bash
uv run tree-sitter-analyzer --callees <FUNC> --output-format toon
uv run tree-sitter-analyzer --callers <FUNC> --output-format toon
uv run tree-sitter-analyzer --symbol-search <NAME> --output-format toon
uv run tree-sitter-analyzer --codegraph-xref <SYMBOL> --output-format toon
uv run tree-sitter-analyzer --call-path --call-path-source X --call-path-target Y
uv run tree-sitter-analyzer --uml class --output-format toon
```

## Anti-patterns

- Don't `grep -rn "def X" tree_sitter_analyzer/` — use `search action=symbol` (10x faster, precise)
- Don't read 5 files to trace a call chain — use `nav action=call_path`
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
