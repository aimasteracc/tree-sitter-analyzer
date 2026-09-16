---
name: tsa-find
version: 3.0.0
description: |
  Locate code with TSA symbol, graph, AST and optional semantic indexes, then verify bounded live source. Works with OpenCode and other MCP hosts without requiring ripgrep or fd.
allowed-tools:
  - mcp__tree-sitter-analyzer__search
  - mcp__tree-sitter-analyzer__nav
  - mcp__tree-sitter-analyzer__project
  - mcp__tree-sitter-analyzer__structure
  - mcp__tree-sitter-analyzer__health
  - Bash
  - Read
---

# tsa-find — locate, rank, verify

Use indexed retrieval to narrow the candidate set before reading or scanning files.
TSA does not require external ripgrep or fd executables. A host's optional text-search
feature is separate from TSA and may have its own implementation requirements.

| Need | TSA action |
|---|---|
| Known identifier | `search action=symbol query="Name"` |
| Unknown entry point / concept | `nav action=context task="Describe the task"` |
| Meaning-based retrieval, when embeddings are ready | `search action=semantic query="Describe behavior"` |
| AST pattern in a file | `search action=query file_path="..." query_key="functions"` |
| Callers / downstream impact | `nav action=callers` / `nav action=impact` |
| File structure from the index | `structure action=sitemap` |
| Live symbol mentions | `nav action=trace symbol="Name"` |
| Exact source evidence | `structure action=read file_path="..." start_line=10 end_line=30` |

1. Start with the known identifier or a concise task description. Keep the result limit small.
2. Follow returned source paths and line ranges. Semantic similarity is candidate discovery,
   not proof of a call relationship; use graph navigation and live source to confirm it.
3. Check index status and freshness. Refresh when needed; do not treat a missing/stale index
   as proof that a symbol or file does not exist. Missing embeddings are not a lexical miss.
4. Use live symbol verification only after narrowing the scope when possible. Its Python
   scanner preserves complete counts before display truncation and reports budget failures;
   it does not promise ripgrep's whole-repository scan speed.
5. For arbitrary prose or regular expressions, use the host's text-search tool if available,
   or a bounded Python standard-library search over the already selected files.

CLI examples:

```bash
uv run tree-sitter-analyzer --symbol-search Name
uv run tree-sitter-analyzer --codegraph-context "Describe the task"
uv run tree-sitter-analyzer --trace-impact --trace-impact-symbol Name
uv run tree-sitter-analyzer path/to/file.py --partial-read --start-line 10 --end-line 30
```

Do not call retired `search.content`, `search.grep`, `search.batch`, `project.files`,
`project.tools`, `list-files`, `search-content`, or `find-and-grep`.
Do not replace exact source evidence with an embedding score or a stale index result.
