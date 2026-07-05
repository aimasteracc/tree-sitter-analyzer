# Knowledge Graph Scale Benchmark

Date: 2026-06-23

This benchmark validates the graph materialization and interactive query layer
with synthetic Java-shaped project graphs. It does not measure tree-sitter Java
parsing throughput; it measures the whole-project knowledge graph sidecar,
LadybugDB mirror, LOD query, search, node detail, and local neighborhood paths.

## Script

Graph-layer stress test:

```bash
uv run python scripts/benchmark_knowledge_graph_scale.py \
  --files 100000 \
  --packages 1000 \
  --methods-per-file 2 \
  --output-dir /tmp/tsa-kg-scale-100k \
  --clean
```

Real Java source end-to-end test:

```bash
uv run python scripts/benchmark_java_corpus_end_to_end.py \
  --files 10000 \
  --packages 500 \
  --methods-per-file 3 \
  --output-dir /tmp/tsa-java-e2e-10k \
  --clean
```

For a LadybugDB-only database stress run:

```bash
uv run python scripts/benchmark_knowledge_graph_scale.py \
  --files 200000 \
  --packages 2000 \
  --methods-per-file 1 \
  --no-json \
  --output-dir /tmp/tsa-kg-scale-200k-ladybug \
  --clean
```

## Results

### Graph-Layer Synthetic Results

| Files | Nodes | Edges | JSON write | Ladybug COPY write | LOD graph query | Neighborhood query |
|---:|---:|---:|---:|---:|---:|---:|
| 50,000 | 200,500 | 350,000 | 1.222s / 142MB | 2.055s | 0.844s | 0.104s |
| 100,000 | 401,000 | 700,000 | 2.610s / 284MB | 3.648s | 0.835s | 0.144s |
| 200,000 | 602,000 | 1,000,000 | skipped | 5.418s | 1.264s | 0.218s |

All runs reported `truncated: false` in the materialized snapshot. The browser
service still caps each response with LOD `max_nodes` / `max_edges`; these caps
limit a view, not the database.

### Real Java Source End-to-End Results

These runs generated real `.java` files and then executed the TSA path:
ASTCache/tree-sitter parse, SQLite indexing, call-edge backfill, knowledge graph
materialization, JSON fallback write, LadybugDB mirror write, and bounded LOD
queries.

| Java files | Nodes | Edges | Index + materialize | Ladybug COPY write | Total script time | LOD graph query | Neighborhood query |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 920 | 1,300 | 0.664s | 0.123s | 0.746s | 0.028s | 0.014s |
| 1,000 | 9,200 | 13,000 | 2.395s | 0.188s | 2.637s | 0.102s | 0.014s |
| 5,000 | 46,000 | 65,000 | 11.180s | 0.946s | 13.136s | 1.515s | 0.058s |
| 10,000 | 92,000 | 130,000 | 41.620s | 1.807s | 48.560s | 5.655s | 0.100s |

All real-Java runs used `--no-docs` and reported `truncated: false`.

## Interpretation

- LadybugDB mirror construction is no longer the bottleneck for large code
  graph visualization. CSV `COPY` writes a 1M-edge graph in seconds.
- JSON fallback remains useful up to at least 100k Java-shaped files, but its
  size grows quickly. For very large repositories, LadybugDB should be treated
  as the primary interactive store and JSON as an optional fallback/export.
- LOD query latency stays interactive for the tested graph sizes because the
  UI asks for bounded subgraphs instead of rendering the full database.
- For real Java source repositories, first-build time is parser/indexer-bound
  first, then graph-materialization-bound. Use
  `benchmark_java_corpus_end_to_end.py` when measuring the full path from
  `.java` files to browser-queryable sidecars.
- Large repositories should treat SQLite AST/cache data and LadybugDB as a
  division of labor, not a replacement: SQLite remains the source index and FTS
  store, while LadybugDB is the embedded traversal/visualization mirror.
- The database can hold the full graph; the browser view is intentionally
  bounded by LOD `max_nodes` and `max_edges` so users can navigate package,
  file, symbol, docs, callers, and callees without drawing every node at once.
