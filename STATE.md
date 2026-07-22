# Loop State — tree-sitter-analyzer

Last run: 2026-07-22 (CI Sweeper + No.1 loop calibration)

## Mission

**Become the most trusted code-intelligence tool for AI coding agents.**

No.1 requires reproducible task, benchmark, reliability and dogfood evidence;
feature inventory alone is not proof of competitive leadership.

Key pillars:
1. **Indexing performance** — fast initial index, low latency incremental
2. **Graph database excellence** — centrality metrics, auto-build, agent-readable
3. **Visualization** — force-directed layout, DOT/GraphML/HTML export (competitor-parity)
4. **Agent neural interface** — 16-language moat, Synapse resolver, MCP tool suite

## High Priority

- `loop-pause-all`: clear
- `weekly_plan_used_pct`: unknown — record from the Codex Max UI before
  speculative L2 work; CI/review closure remains allowed.
- PR #1161: CI green and no Codex review threads at the 2026-07-22 snapshot.
- Next product defect: change-impact took ~96 seconds and recommended
  `tests/unit/hyphae/test_evaluator.py` for `constraints/evaluator.py`.
- Next trust defect: project health reports `no_data` as grade F, creating 776
  critical-looking false signals in the self-repository snapshot.

## Loop Queue

1. Close PR #1161 review/CI lifecycle without auto-merge.
2. Fix change-impact same-basename routing and feedback latency.
3. Separate health `unknown/no_data` from measured F grades.
4. Turn PR #1160 manifests into reproducible competitor evidence.
5. Re-measure installation, first/incremental index and agent task success.

---

## Completed

- [x] **Lua plugin promoted to production** (2026-07-15)
  - `synapse_resolver/languages/lua.py` — moat slot registered (16th resolver)
  - `pyproject.toml` — entry-point + optional dep `tree-sitter-lua>=0.5.0` + all-languages bundle
  - `tests/unit/test_lua_resolver.py` — 13 tests covering moat contract, context gating, registry
  - `lua_plugin/plugin.py` — "Phase 2 extensibility demo" replaced with production docstring
  - `server.json` — "13 languages" updated to "16 languages"

- [x] **RFC-0019: complexity cross-path invariant confirmed GREEN** (2026-07-15)
  - Scalar CC is canonical; `test_complexity_cross_path_invariant.py` passes for Java/JS/TS/Go/Rust
  - Remaining cleanup: `_COMPLEXITY_NODES` table drives `decision_points` breakdown (display-only)

- [x] **Indexing performance uplift** (2026-07-15)
  - `ast_cache.py` `get_conn()`: added PRAGMA cache_size=-65536 (64MB), mmap_size=268435456 (256MB), temp_store=MEMORY
  - `ast_cache.py` `_resolve_worker_count()`: retained the measured 64-file spawn threshold
  - Windows 14-core benchmark (50 files): serial 5.77s vs auto-at-4 9.55s; early spawn was 65% slower and was reverted

- [x] **Degree centrality in KnowledgeGraph** (2026-07-15)
  - `knowledge_graph/builder.py`: `_annotate_centrality()` — degree_in, degree_out, centrality [0,1] per node
  - Every `build()` call annotates nodes; stored in `KnowledgeNode.metadata`
  - Hub nodes are visually larger in the HTML viewer

- [x] **Auto-build KnowledgeGraph after full index** (2026-07-15)
  - `cache/indexer.py` `post_index_backfill()`: keeps SQLite canonical and invalidates stale LadybugDB projections
  - Agents get an up-to-date graph immediately after `tsa index`; no separate `--knowledge-graph-index` step
  - Failure is silently logged (never breaks indexing)

- [x] **Visualization: force-directed HTML viewer** (2026-07-15)
  - `knowledge_graph/html_viewer.py` — full rewrite with spring-electrical force simulation
  - Pre-settles 180 ticks on load; related files cluster together (structural layout)
  - "Physics ON/OFF" toggle; hub nodes glow by centrality; node size = f(kind) + centrality*8
  - Grid-cell approximation for graphs >800 nodes (avoids O(n²) slowdown)

- [x] **Visualization: DOT/Graphviz export** (2026-07-15)
  - `knowledge_graph/exporters.py` `to_dot()` — LOD-aware, focus filter, node colors/shapes by kind
  - MCP `viz` tool: `export_format=dot` → returns DOT string; render with `dot -Tsvg`

- [x] **Visualization: GraphML export** (2026-07-15)
  - `knowledge_graph/exporters.py` `to_graphml()` — Gephi/yEd/Cytoscape compatible XML
  - Nodes carry `degree_in`, `degree_out`, `centrality` attributes
  - MCP `viz` tool: `export_format=graphml` → returns GraphML XML

- [x] **knowledge_graph public API** (2026-07-15)
  - `__init__.py`: `to_dot`, `to_graphml`, `to_graphology`, `to_html_viewer`, `to_mermaid_uml` all exported

---

## Watch List

- [ ] **RFC-0019 decision_points cleanup** (display-only, lower priority)
  - `complexity_heatmap._COMPLEXITY_NODES` drives `decision_points` breakdown (cosmetic only)
  - Next: replace with canonical `decision_node_types(language)` from `languages/shared/`

- [ ] **tsa_explore promotion to production MCP**
  - Prototype in `mcp/tsa_explore.py`, not wired into `server.py`
  - Block: 21-question benchmark not yet run

- [ ] **CSS/HTML/SQL/YAML/JSON full-index gap** — plugins exist, indexer path not exercised

- [ ] **Pre-existing test failures (not caused by our changes)**
  - `test_introspector.py` — C# grammar node count drift (229 != 239)
  - `test_cli_async.py::test_help_command` — `result.stdout is None`

---

## Feature Inventory (not competitive proof)

| Feature | TSA implementation | Outside baseline status |
|---------|--------------------|-------------------------|
| Force-directed layout | implemented | re-measure required |
| DOT/Graphviz export | implemented | re-measure required |
| GraphML export | implemented | re-measure required |
| Degree centrality metadata | implemented | re-measure required |
| Auto-built graph after index | implemented | re-measure required |
| Language support | 16 resolver claim | manifest/invariant required |
| MCP agent interface | implemented | agent-task comparison required |

---
Run log: see `loop-run-log.md`; competitive claims remain unproven until the
benchmark evidence queue is complete.
