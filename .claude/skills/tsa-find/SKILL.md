---
name: tsa-find
version: 1.0.0
description: |
  Fast file + content search with code-aware sizing. Replaces Read/Grep/find
  for routine "where is this file" / "grep for X" / "show me lines 10-20 of Y"
  questions. Returns file paths + line numbers + a sized chunk, not the whole file.

  Use when:
  - "Find files matching <pattern>" / "show me all *.yml under config/"
  - "Grep for 'TODO' / 'FIXME' / 'TODO\\(perf\\)' / regex anywhere"
  - "How big is <file>" / "is this file too large to read fully"
  - "Show me lines 50-80 of <file>" / "read just the relevant slice"
  - "Find all files matching name + containing string"

  Replaces: native find + grep + cat invocations (~3-10k tokens for big repos)
  with single MCP calls (200-500 tokens).
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

| Question                                  | Tool                    |
|-------------------------------------------|-------------------------|
| Filename pattern only                     | `list_files`            |
| Content pattern only (regex / literal)    | `search_content`        |
| Filename pattern AND content              | `find_and_grep`         |
| Read specific lines of one file           | `extract_code_section`  |
| "Is this file too big to read fully?"     | `check_code_scale`      |

## Procedure

### Single search

```yaml
search_content(pattern: "TODO", path: "tree_sitter_analyzer/", file_pattern: "*.py")
```

Returns: `matches: [{file, line, content}]` with sized previews. Always
includes file:line so the agent can cite without reading the file.

### Sized partial read (the killer feature)

Before reading a large file blind, use:

```yaml
check_code_scale(file_path: "tree_sitter_analyzer/ast_cache.py")
# returns {lines: 2144, size_bytes: 79809, is_large: true, recommendation: "use extract_code_section"}
```

Then extract only what you need:

```yaml
extract_code_section(file_path: "...", start_line: 800, end_line: 870)
```

Avoids reading 80KB when you need 2KB.

### Combined find+grep

```yaml
find_and_grep(file_pattern: "test_*.py", content_pattern: "def test_synapse")
# returns: list of test functions matching both criteria
```

## CLI equivalents

```bash
uv run tree-sitter-analyzer --list-files --extensions py,yml
uv run tree-sitter-analyzer --search-content "TODO" --include "*.py"
uv run tree-sitter-analyzer --find-and-grep "test_*.py" "def test_synapse"
uv run tree-sitter-analyzer <file> --check-scale
uv run tree-sitter-analyzer <file> --partial-read --start-line 800 --end-line 870
```

## Anti-patterns

- DON'T `Read` a large file before checking scale — burns tokens
- DON'T `Bash grep -rn` for things `search_content` handles — slower + noisier
- DON'T re-search the same query twice in one session — cache the result mentally
