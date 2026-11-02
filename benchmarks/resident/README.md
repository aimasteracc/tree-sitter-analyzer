# RFC-0042 resident-substrate harness

Portable versions of the profiling scripts behind
[RFC-0042](../../rfcs/0042-resident-callers-substrate.md) (the originals, with
hard-coded local paths, stay under `rfcs/evidence/0042-profile/`). Every
script imports `tree_sitter_analyzer` from the environment, so set
`PYTHONPATH` to the checkout under test (or run inside a venv that has the
wheel), and index the repo first:

```bash
tree-sitter-analyzer --project-root PATH --full-index
```

| Script | Measures | RFC section |
|---|---|---|
| `prof_callers.py` | In-process stage buckets of `nav callers` (exclusive time per stage), `first` or `warm` | Motivation, buckets table |
| `mcp_latency.py` | Through a real MCP stdio server: `initialize`, the first query after start, warm, after idle; `--inproc` adds the MCP-layer (facade, encode, transport) share, overall and per answer kind (`mcp_layer_by_kind_ms`) | V2 |
| `idle_probe.py` | In-process: warm, then the query after an idle gap past the 35 s snapshot TTL | §4.4 |
| `graph_size.py` | Files, symbols, graph nodes and edges, retained and peak MB of the call-graph state | §8, V3 |
| `statcost.py` | Unit cost of `os.stat` / `realpath` / one walk on this host | §9 |

Targets come from `--sample` (the dogfood `sample.json` format, or a list of
`{qual|class+name, file}` rows) or, without it, are picked deterministically
from the index.

## Reproducing the RFC numbers (`rich`)

```bash
export PYTHONPATH=/path/to/tree-sitter-analyzer
B=benchmarks/resident
python $B/prof_callers.py --repo rich --mode first --sample rich-sample.json --out first.json
python $B/prof_callers.py --repo rich --mode warm  --sample rich-sample.json --targets 40 --out warm.json
python $B/mcp_latency.py  --repo rich --sample rich-sample.json --targets 10 --idle 40 --inproc
python $B/graph_size.py   --repo rich
python $B/statcost.py     --repo rich
```

For an A/B of the RFC-0042 switch, run `mcp_latency.py` in ABBA order with
`--env TSA_RESIDENT=off` (A) and without it (B), one fresh server per slot,
and drop records with `"suspended": true`.

## P0 measurements (2026-11-02, Windows 11, CPython 3.12.9, `develop` `c9277106`)

The host was saturated by an unrelated test run during these measurements
(load 99–100 %, `stat` 164 µs against 83 µs in the RFC), so absolute times are
about 2.4 × the RFC's. The **structure** reproduces exactly: the warm run on
the same 40 targets gives the same 160 answers (20 `complete`, 112
`incomplete`, 28 `unknown`) and the same split (92 edge-only, 68
review-gated), and the bucket ranking is the same (review gates, then
per-request probes, then edge-layer checks; graph read ≈ 1 %).

| Measure (`rich`) | RFC (idle host) | P0 (loaded host) |
|---|---:|---:|
| Warm median / p90, in-process, n = 160 | 46.2 / 108.5 ms | 119.4 / 256.4 ms |
| Warm edge-only / review-gated median | 31.7 / 74.0 ms | 86.6 / 174.2 ms |
| `stat` calls per warm query | 378 | 385 |
| First query, fresh process (3 runs) | 0.79 / 1.02 / 1.10 s | 3.09 / 1.80 / 1.63 s |
| of which `certified_index_read` enter | 551 / 776 / 695 ms | 2307 / 1364 / 1202 ms |
| MCP warm median (10 targets × 2 forms × 2) | — | 102.5 ms |
| same queries in-process | — | 82.7 ms |
| MCP-layer share (facade + encode + stdio) | — | 19.8 ms (19 %) |
| MCP query after 40 s idle / warm again | 334 / 50 ms (in-process) | 817 / 110 ms |

Graph sizes (§8; `graph_size.py`, both runs on the same index: the first
resolves edges, the second replays the persisted resolution of #1675):

| Repo | Files | Symbols | Nodes | Certain edges | Name-only edges | Retained MB | Peak MB |
|---|---:|---:|---:|---:|---:|---:|---:|
| rich | 213 | 3,509 | 1,810 | 2,954 | 3,312 | 6.6 | 17.1 |
| hono | 453 | 4,175 | 1,549 | 9,968 | 40,425 | 11.5–24.7 | 54.7–57.0 |
| zod | 521 | 6,586 | 2,407 | 13,214 | 67,958 | 15.5–35.0 | 79.1–82.0 |
