# Loop State — tree-sitter-analyzer

Last run: 2026-08-08 (trusted Agent change intelligence No.1 program)

## Mission

**Become the most trusted local code-change intelligence layer for AI coding agents.**

North star: **Verified Change Success Rate (VCSR)**. Feature, language, tool,
test, edge, download, and star counts are supporting signals, not the objective.
Public leadership claims remain bounded by the RFC-0021 evidence ladder. E0–E3
emit no public claim, and an operational E0 canary cannot be promoted to E1.

Key pillars:
1. **Trust evidence** — conservative resolution, provenance, freshness, reproducible Agent-change outcomes
2. **Task UX** — understand → plan_change → assess_change over the existing primitives
3. **Runtime reliability** — low-friction install, fast index/query/refresh, multi-agent safety
4. **Independent adoption** — E2/E3/E4 evidence, integrations, external maintainers, real cases

Active roadmap: [`rfcs/ROADMAP-no1-agent-trust.md`](rfcs/ROADMAP-no1-agent-trust.md).

## Active No.1 Sprint

- **NO1-003A (integration condition):** roadmap, team topology, evidence policy, and 90-day ledger are implemented in PR #1238; completion is established only when that PR merges to `develop`
- [x] **NO1-003B:** production-canary operator runbook and offline rehearsal (E0; real canary remains NO-GO)
- [ ] **NO1-003D:** implement and independently qualify the production dispatcher/admission boundary without a model call
- [ ] **NO1-003C:** execute one real bounded E0 Gin production canary only after NO1-003D, model-free NO1-008A setup, signed attestation, human budget, and judge gates pass; it cannot unlock E1/E2 or public wording
- [ ] **NO1-006A:** exact-wheel native macOS/Linux/Windows package-to-MCP qualification and trusted attestation passed on `refs/heads/develop` run `31272226364`, attempt `1`, with durable byte-bound evidence under `rfcs/evidence/no1-006a/`; native outdated-uv detection/remediation qualification remains pending
- [ ] **NO1-008A:** after a separate reproducible RFC-0021 E1 qualification, complete the seven-repository model-free setup; any failure blocks NO1-003C and every model-backed phase
- [x] **NO1-004A:** claim registry is the fail-closed control plane; arbitrary wording is schema-invalid, E0–E3 emit nothing, and E4 requires a context-bound benchmark plus independent reproduction whose exact digest is admitted by the code-owned trust root (empty by default) before fixed public wording can be emitted
- [x] **NO1-004B:** the English README has a deterministic claim marker and conservative whole-document policy gate; unsupported quantitative marketing was removed from all three public READMEs, and the blocked E0 seed honestly generates no claim
- [x] **NO1-005A:** generated 10-dimension language pipeline inventory; cross-file E2E remains `verified=0`, with 13 `unknown`
- [x] **NO1-007A:** draft RFC for understand / plan_change / assess_change completed; Phase A internal implementation is gated by read-only snapshot Phase 0, while only public ninth-facade registration is gated by the menu experiment
- [x] **NO1-007B:** RFC-0023 edge evidence/confidence/freshness draft with strict schema, closed golden fixtures, and an E0 denial corpus for a future semantic validator
- [ ] **NO1-009A:** qualify a second indexed competitor at install/conformance only after NO1-003A; keep an unavailable arm `NOT_EVALUATED`, and require a separately frozen RFC-0021 v2 experiment before comparative inclusion

Execution policy: at most two L2 agents concurrently; implementation agents use
isolated GitFlow worktrees; model spend and independent-judge gates remain human-controlled.

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

## Historical Comparison Quarantine

The former competitive feature table is removed from active state. Its tool versions,
repository set, date, model/backend, and RFC-0021 evidence level were not recorded, so
its `yes`/`no`/`partial`, language-count, and leadership implications are not admitted
evidence and must not support public wording. Any replacement must be generated from
an artifact admitted by the claim registry under the active roadmap policy.

---
Run log: 2026-07-15 codegraph mission — indexing perf + centrality + auto-KG + force-viz + DOT + GraphML
