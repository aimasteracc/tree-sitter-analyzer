---
name: tsa-find
version: 2.0.0
description: |
  Fast file + content search with code-aware sizing. Use CC built-in Grep/Glob
  for routine "grep for X" or "find files matching pattern" questions.
  Use TSA MCP tools for code-intelligence searches (symbol, batch, chain, select).

  Use when:
  - "Find files matching <pattern>" / "show me all *.yml under config/"
    -> CC Glob tool (single pattern) or project action=files
  - "Grep for 'TODO' / 'FIXME' / regex anywhere"
    -> CC Grep tool
  - "Find all files matching name + containing string" (2-step)
    -> CC Glob tool to find files, then CC Grep tool for content
  - "How big is <file>" / "is this file too large to read fully"
    -> health action=scale
  - "Show me lines 50-80 of <file>"
    -> structure action=read
allowed-tools:
  - mcp__tree-sitter-analyzer__search
  - mcp__tree-sitter-analyzer__project
  - mcp__tree-sitter-analyzer__structure
  - mcp__tree-sitter-analyzer__health
  - Bash
  - Read
---

# tsa-find — File / text search, sized for agents

> The "I just want to find X" skill. Wraps `fd` + `rg` + sized partial reads
> with consistent output formatting.

## Tool routing

| Question                                  | Tool                        |
|-------------------------------------------|-----------------------------|
| Filename pattern only                     | `project action=files`      |
| Content pattern only (regex / literal)    | **Grep tool** (CC built-in) |
| Filename pattern AND content              | **Glob tool** + **Grep tool** (2-step) |
| Several patterns in one call (≥2)        | `search action=batch`       |
| Read specific lines of one file           | `structure action=read`     |
| "Is this file too big to read fully?"     | `health action=scale`       |

## Procedure

### Single search

Use the CC built-in **Grep tool** for single content-pattern searches:

  pattern: "TODO"
  path: tree_sitter_analyzer/
  glob: "*.py"

Returns: file paths + line numbers. No MCP call needed.

### Sized partial read (the killer feature)

Before reading a large file blind, use:

```yaml
health action=scale file_path="tree_sitter_analyzer/ast_cache.py"
# returns {line_count: 938, file_metrics: {file_size_bytes: 38918, total_lines: 938, code_lines: 661, ...},
#          llm_guidance: {analysis_strategy: "This is a large file...", recommended_tools: ["structure action=read", ...]}}
# (there is no top-level is_large / recommendation — judge size from line_count / file_metrics.file_size_bytes,
#  and read llm_guidance.recommended_tools for the next-step suggestion)
```

Then extract only what you need:

```yaml
structure action=read file_path="..." start_line=800 end_line=870
```

Avoids reading 80KB when you need 2KB.

### Combined find+grep

Use CC built-in **Glob tool** + **Grep tool** in two steps:

  Step 1 -- Glob tool:  pattern="test_*.py"  (find candidate files)
  Step 2 -- Grep tool:  pattern="def test_synapse"  path=<result of step 1>

Returns file paths + matching lines. More composable than a single MCP call.

## CLI equivalents

```bash
uv run tree-sitter-analyzer --project-root . --outline   # list project files
uv run tree-sitter-analyzer --check-tools                # verify fd/rg available
uv run tree-sitter-analyzer <file> --partial-read        # sized read with --start-line / --end-line
```

## Anti-patterns

- DON'T `Read` a large file before checking scale — burns tokens
- DON'T `Bash grep -rn` — use the CC built-in **Grep tool** instead (structured output, no shell escaping)
- DON'T call `search action=batch` with a single query — it enforces a ≥2-query minimum (raises "must be at least 2 queries"); use the **CC Grep tool** for a single pattern
- DON'T re-search the same query twice in one session — cache the result mentally
