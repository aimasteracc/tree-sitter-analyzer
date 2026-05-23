---
name: tsa-structure
version: 1.0.0
description: |
  Structural analysis of one file — classes, methods, exports, common patterns,
  semantic classification of a diff. Returns the file's *shape* without reading
  the file body.

  Use when:
  - "What classes and methods does X file have"
  - "Show me a table / outline of <file>"
  - "Run query: find all decorated functions in file X"
  - "Is this diff a refactor or a behavior change" (semantic classification)
  - "Find patterns like singleton / factory in this code"

  Replaces: reading the whole file (~20k tokens for big files) with structural
  views (200-1000 tokens).
allowed-tools:
  - mcp__tree-sitter-analyzer__analyze_code_structure
  - mcp__tree-sitter-analyzer__query_code
  - mcp__tree-sitter-analyzer__code_patterns
  - mcp__tree-sitter-analyzer__semantic_classify
  - Bash
  - Read
---

# tsa-structure — File shape without the file body

## Tool routing

| Question                                        | Tool                   |
|-------------------------------------------------|------------------------|
| Outline / table of classes + methods            | `analyze_code_structure` |
| Run a tree-sitter query (e.g., all `def` nodes) | `query_code`           |
| Detect design patterns (singleton, factory, …)  | `code_patterns`        |
| Classify a diff (refactor vs feature vs fix)    | `semantic_classify`    |

## Procedure

### File outline (most common)

```yaml
analyze_code_structure(file_path: "tree_sitter_analyzer/health_scorer.py")
# returns: {classes: [...], functions: [...], imports: [...]}
```

For a markdown-formatted table:

```bash
uv run tree-sitter-analyzer <file> --table full
```

### Custom tree-sitter query

When you need something the built-in tools don't surface:

```yaml
query_code(file_path: "...", query_key: "class")
# OR
query_code(file_path: "...", query_string: "(decorated_definition) @decorated")
```

`--list-queries` (CLI) shows all built-in queries available per language.

### Diff classification

```yaml
semantic_classify(file_path: "...", before_hash: "abc", after_hash: "def")
# returns: {classification: "refactor|feature|bugfix|test|docs|chore", confidence: 0.92}
```

Useful for PR descriptions and CHANGELOG categorization.

### Pattern detection

```yaml
code_patterns(file_path: "...", patterns: ["singleton", "factory", "observer"])
```

## CLI equivalents

```bash
uv run tree-sitter-analyzer <file> --table full           # outline
uv run tree-sitter-analyzer <file> --query-key class      # built-in query
uv run tree-sitter-analyzer <file> --query-string "(...)" # custom query
uv run tree-sitter-analyzer <file> --code-patterns
uv run tree-sitter-analyzer --semantic-classify <diff-args>
```

## Anti-patterns

- DON'T read the whole file just to find "what classes are in it" — use the structure tool
- DON'T write a custom tree-sitter query when `analyze_code_structure` covers it
- DON'T use semantic_classify on huge multi-purpose commits — split them first
