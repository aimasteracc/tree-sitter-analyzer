# Four Tools, One File, One Neutral Oracle: An AST Shootout

Benchmark claims are easy to dismiss when the benchmark is run by the tool
that wins it. So here is a different design: instead of measuring
tree-sitter-analyzer against a competitor's own numbers, we pick a referee
neither tool controls — Python's standard-library `ast` module, CPython's own
parser — and ask four tools the same question about the same file.

**Method.** Use Python's own stdlib `ast` as a neutral oracle. It is not a
product of tree-sitter-analyzer, CodeGraphContext, wrale/mcp-server-tree-sitter,
or grep-ast — it is CPython's own parser, so it cannot be structured to favor
any of them.

**Fixture file:** `tree_sitter_analyzer/health_scorer.py` (891 lines, includes
non-ASCII `≤` characters in a docstring — a small but real Unicode-handling
test).

**Date:** 2026-05-23.

## Summary

| Tool | Classes | Functions | Imports | Status |
|---|---|---|---|---|
| Python stdlib `ast` (**ORACLE**) | 2 | 21 | 10 | ground truth |
| **tree-sitter-analyzer** | **2** | **21** | **10** | **100% match** |
| wrale/mcp-server-tree-sitter | 2 | 21 | 14 | imports over-counted by 4 |
| CodeGraphContext (`cgc`) | **0** | **0** | **0** | silent index failure |
| grep-ast (Aider) | — | — | — | crashes on Python 3.14 |

Of four tools measured against the same file and the same oracle, only one —
tree-sitter-analyzer — matched the oracle exactly on all three counts.

## Finding 1: CodeGraphContext's KuzuDB backend fails silently

```console
$ cgc --db kuzudb --db-path /tmp/cgc_compare/.kuzu index /tmp/cgc_compare
Starting indexing for: /private/tmp/cgc_compare
Successfully finished indexing: /tmp/cgc_compare in 1.94 seconds

$ cgc --db kuzudb --db-path /tmp/cgc_compare/.kuzu stats
Overall Database Statistics
┏━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Metric       ┃ Count ┃
┡━━━━━━━━━━━━━━╇━━━━━━━┩
│ Repositories │     1 │
│ Files        │     0 │   <- indexing reports "success" but 0 files landed
│ Functions    │     0 │
│ Classes      │     0 │
│ Modules      │     0 │
└──────────────┴───────┘
```

It reports "Successfully finished" and then shows zero files, zero functions,
zero classes in the same breath. A user — or worse, an agent acting
unattended — reading a 0-result query has no way to tell "the project
genuinely has no functions" from "the tool silently failed to index anything."
That distinction is exactly the kind of failure mode we keep fixing in our own
tool: an agent needs to be able to tell `NOT_FOUND` apart from `ERROR` apart
from `INFO`. We carry a `verdict: "ERROR"` path for this; `cgc`'s default
KuzuDB backend does not surface one here — you have to fall back to FalkorDB
or a Neo4j server to get a working index, which raises the setup bar
considerably for a quick trust check.

## Finding 2: grep-ast (Aider) crashes outright on Python 3.14

```console
$ grep-ast "HealthScorer" tree_sitter_analyzer/health_scorer.py
Traceback (most recent call last):
  File ".../grep_ast/grep_ast.py", line 47, in __init__
    tree = parser.parse(bytes(code, "utf8"))
TypeError: argument 'source': 'bytes' object is not an instance of 'str'
```

Newer tree-sitter (>= 0.25) changed its parsing API; grep-ast 0.9.0 still calls
the old signature. Python 3.14 shipped 2025-10 — this is a real
"new-runtime-breaks-an-old-dependency" failure, not an edge case nobody will
hit. tree-sitter-analyzer runs the same underlying tree-sitter release without
this crash — the fault-tolerance work happens at the API-compatibility layer,
not as an afterthought.

## Finding 3: wrale/mcp-server-tree-sitter over-counts imports by 4

```
tree-sitter-analyzer: 10 imports
wrale/mcp-server-tree-sitter: 14 imports
Python ast (oracle):  10 imports
```

wrale counts multi-name imports like `from typing import Any, Optional` as
multiple imports (one per imported name), while Python's own `ast` counts the
whole `ImportFrom` statement once — one AST node, one import, regardless of
how many names it binds. This is not a "bug" in the sense of a crash; it is a
definitional choice that happens to disagree with the language's own parser.
That disagreement matters downstream: an agent doing dead-import analysis or
dependency counting on wrale's numbers will over-count by however many
multi-name import statements the file has.

## Finding 4: four fault-tolerance properties, side by side

| Scenario | cgc | grep-ast | wrale | tree-sitter-analyzer |
|---|---|---|---|---|
| Runs on Python 3.14 | yes | **crashes** | yes | yes |
| Query returns data after indexing | **silent 0** | n/a | yes | yes |
| Matches Python `ast` exactly | n/a | n/a | off by 4 imports | yes |
| Single file, no external service required | **needs Neo4j/FalkorDB for a working backend** | yes | yes | yes |

## Reproduce it yourself

### Environment

```bash
uv tool install codegraphcontext     # provides the `cgc` CLI
uv tool install mcp-server-tree-sitter
uv tool install grep-ast
```

### A1. Python `ast` oracle

```bash
python3 -c "
import ast
src = open('tree_sitter_analyzer/health_scorer.py').read()
t = ast.parse(src)
print('classes:',   len([n for n in ast.walk(t) if isinstance(n, ast.ClassDef)]))
print('functions:', len([n for n in ast.walk(t) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]))
print('imports:',   len([n for n in ast.walk(t) if isinstance(n, (ast.Import, ast.ImportFrom))]))"
```

### A2. tree-sitter-analyzer

```bash
uv run python -m tree_sitter_analyzer tree_sitter_analyzer/health_scorer.py \
    --advanced --format json | \
    jq '[.elements[] | .type] | group_by(.) | map({k: .[0], v: length})'
```

### A3. CodeGraphContext (`cgc`) — will report a silent zero

```bash
mkdir /tmp/cgc_compare && \
  cp tree_sitter_analyzer/health_scorer.py /tmp/cgc_compare/ && \
  cgc --db kuzudb --db-path /tmp/cgc_compare/.kuzu index /tmp/cgc_compare && \
  cgc --db kuzudb --db-path /tmp/cgc_compare/.kuzu stats
```

### A4. grep-ast (Aider) — will crash on Python >= 3.14

```bash
grep-ast "HealthScorer" tree_sitter_analyzer/health_scorer.py
```

### A5. wrale/mcp-server-tree-sitter (needs an MCP stdio harness)

```bash
{
  echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"manual","version":"0"}}}'
  echo '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
  echo '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"register_project_tool","arguments":{"path":"'$(pwd)'","name":"tsa"}}}'
  echo '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_symbols","arguments":{"project":"tsa","file_path":"tree_sitter_analyzer/health_scorer.py"}}}'
  sleep 2
} | mcp-server-tree-sitter | jq -r 'select(.id==3) | .result.content[0].text'
```

## Conclusion

| Question | Answer |
|---|---|
| Does the tool actually work? | Yes — it matches Python's own `ast` 100%, the only one of four tools to do so on this file. |
| How does it compare to the competition? | `cgc`'s default KuzuDB backend reports success while indexing 0 files; grep-ast crashes outright on Python 3.14; wrale over-counts imports by 4. We hit zero of these failure modes on the same fixture. |
| Can this be reproduced? | Every command is above; each one runs in seconds. Any deviation from the numbers here is a bug — file it. |

This is a narrow, single-file comparison, not a claim that any of these
projects are broadly worse — it is one fixture, one oracle, one afternoon.
Treat it the same way we ask you to treat every other number in this
repository: run it yourself before you cite it. For the larger, multi-repo
cross-language correctness comparison (a different question — call-graph
mis-wires, not symbol counts), see
[GAUNTLET.md](../../benchmarks/codegraph_compare/GAUNTLET.md) and
[REPORT-v1.21.0.md](../../benchmarks/codegraph_compare/REPORT-v1.21.0.md).

---

*Source: extracted and rewritten from an internal working note
(`docs/internal/COMPETITOR_HEAD_TO_HEAD_2026-05-23.md`, commit `68efef86`),
originally recorded 2026-05-23. `docs/internal/` is a gitignored scratch
directory and is not part of the published documentation set — this article
is the durable, public form of that note.*
