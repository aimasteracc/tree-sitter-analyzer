# SDD: Project Summary PageRank Enhancement

**Status:** Draft  
**Date:** 2026-04-09  
**Scope:** `build_project_index` + `get_project_summary`

---

## 1. Problem

`get_project_summary` currently returns a directory tree with file counts.
Two critical failures:

1. **Silent directory drops** — top-level dirs with no `__init__.py` and no
   name matching `_DIR_CONVENTIONS` are silently skipped.
   `spring-framework` (11,338 files), `netty` (4,053 files), `caffeine` (824 files)
   all disappear from the output.

2. **No semantic signal** — Claude receives "there are directories" but not
   "these are the most important things to know before touching this project."
   Result: Claude explores with 20+ tool calls what a good summary would answer in 1.

---

## 2. Goal

`get_project_summary` output answers three questions Claude has at the start
of every session:

1. **What is this project?** — one sentence
2. **What is the most dangerous thing to touch?** — PageRank top N nodes
3. **Where do I start?** — entry point + module dependency order

Non-goals:
- LLM-based inference (deterministic only)
- Replacing `trace_impact` or `analyze_code_structure`
- Supporting non-code file types (docs, images)

---

## 3. Design

### 3.1 Storage Layout

```
.tree-sitter-cache/
  project-index.json      ← existing, extended with new fields
  summary.toon            ← NEW: pre-rendered TOON, get_project_summary reads this
  critical_nodes.json     ← NEW: PageRank results, consumed by modification_guard
  file_hashes.json        ← NEW: {filepath: [mtime, size]} for incremental updates
```

`get_project_summary` reads `summary.toon` directly — no computation at read time.

### 3.2 `project-index.json` New Fields

```json
{
  "critical_nodes": [
    {
      "name": "BeanFactory",
      "file": "spring-beans/src/main/java/.../BeanFactory.java",
      "module": "spring-beans",
      "pagerank": 0.94,
      "inbound_refs": 847
    }
  ],
  "module_dependency_order": [
    "spring-core",
    "spring-beans",
    "spring-context"
  ],
  "entry_points": [
    "src/cli/index.ts"
  ],
  "index_built_at": 1712345678.0,
  "schema_version": 2
}
```

### 3.3 `summary.toon` Format

```
project:  <name>
what:     <one-sentence from README first paragraph>

critical: (call graph PageRank top 7)
  <ClassName>   <module>   <score>   (<N> refs)
  ...

modules:  <dep_order joined by →>
entry:    <entry_points[0] basename>
scale:    <file_count> files — <top 2 languages by %>
notes:    <custom_notes if any>
```

Rules:
- `critical:` section omitted if PageRank data unavailable
- `modules:` shows max 7 entries, truncated with `...` if more
- `notes:` omitted if empty
- Total output: target < 30 lines

### 3.4 Directory Classification

Replace the current `_DIR_CONVENTIONS` fallback with active classification:

```python
def _classify_dir(path: Path) -> Literal["core", "context", "tooling"]:
    has_readme = (path / "README.md").exists()
    has_build  = any((path / f).exists() for f in [
        "package.json", "pom.xml", "build.gradle",
        "pyproject.toml", "setup.py", "Cargo.toml", "go.mod",
    ])
    if has_readme and has_build:
        return "context"   # independent project checked in as reference
    if any(kw in path.name.lower() for kw in ["tool", "analyzer", "plugin"]):
        return "tooling"
    return "core"
```

`context` dirs appear under a `context:` section in TOON with file count only.
`core` dirs appear under `structure:` with subdirectory descriptions.

### 3.5 `_describe_dir` Enhancement

Current: reads `__init__.py` docstring → `_DIR_CONVENTIONS` lookup.

New (in order):
1. `__init__.py` docstring
2. `README.md` first non-empty line (strip `#`)
3. `_DIR_CONVENTIONS` lookup
4. Empty string (shown as dir name only, not dropped)

### 3.6 PageRank Computation

**Edge extraction** (per `.java`, `.ts`, `.py` file via tree-sitter):

| Language | Relationship | tree-sitter node |
|---|---|---|
| Java | `import X` | `import_declaration` |
| Java | `extends X` | `superclass` |
| Java | `implements X` | `super_interfaces` |
| TypeScript | `import from 'X'` | `import_statement` |
| Python | `import X` / `from X import` | `import_statement` |

Each relationship becomes a directed edge: `file → imported_symbol`.

**Graph + PageRank:**

```python
import networkx as nx

G = nx.DiGraph()
for src, dst in all_edges:
    G.add_edge(src, dst)

scores = nx.pagerank(G, alpha=0.85, max_iter=100)
top_nodes = sorted(scores.items(), key=lambda x: -x[1])[:10]
```

**Node identity:** class name (not full path) — matches how developers refer to them.
Collision resolution: keep the node with highest inbound_refs.

**Performance target:**
- spring-framework (11,338 Java files): < 30 seconds full build
- Incremental (1-5 changed files): < 3 seconds

### 3.7 Incremental Update Strategy

```
build_project_index called
        ↓
Is git repo? (check .git/)
   YES → git diff --name-only HEAD  →  changed_files
   NO  → fd newer than cache mtime  →  changed_files
        ↓
changed_files is empty?
   YES → skip re-parse, skip PageRank, return cached summary
        ↓
Re-parse changed_files only → update edge_cache
        ↓
Rerun full PageRank on updated graph  (~0.1s)
        ↓
Re-render summary.toon + critical_nodes.json
```

`file_hashes.json` stores `{filepath: [mtime, size]}` — no SHA256.
Invalidation: if `stat(file).mtime != cached_mtime OR stat(file).size != cached_size`
→ file changed.

**Full rebuild triggers:**
- `force_refresh=True`
- First run (no cache)
- File count changed by > 50 (directory restructure)
- `schema_version` mismatch

---

## 4. File Changes

| File | Change |
|---|---|
| `mcp/utils/project_index.py` | Add `_classify_dir`, fix `_describe_dir`, add edge extraction, PageRank, incremental logic |
| `mcp/tools/get_project_summary_tool.py` | Rewrite `_format_toon` to read `summary.toon`; remove computation |
| `mcp/tools/build_project_index_tool.py` | Add incremental update flow; write `summary.toon` + `critical_nodes.json` |
| `.tree-sitter-cache/` | New files: `summary.toon`, `critical_nodes.json`, `file_hashes.json` |

Dependencies to add:
- `networkx` — PageRank (pure Python, no native deps)

---

## 5. Risks

| Risk | Mitigation |
|---|---|
| NetworkX not installed | Catch ImportError; skip PageRank, still write summary without `critical:` section |
| tree-sitter parse failure on edge case file | Per-file try/except; skip file, log warning |
| PageRank timeout on very large graph (>100k nodes) | Hard timeout 25s; write partial results |
| git diff unavailable (detached HEAD, shallow clone) | Fallback to mtime comparison |

---

## 6. Success Criteria

1. `get_project_summary` on spring-framework shows all top-level dirs including
   `spring-framework`, `netty`, `caffeine`, `spring-petclinic`
2. `critical:` section lists ≥ 5 nodes with PageRank scores
3. `BeanFactory` or `ApplicationContext` appears in top 3 for spring-framework
4. Incremental rebuild after touching 1 file: < 3 seconds
5. Full rebuild of spring-framework: < 60 seconds
