<!-- Created: 2026-05-22 r37fE -->
# Agent Task Benchmarks

> **Why**: CodeGraph's competitive moat is published `6-repo × 92%-tool-call-reduction × 71%-faster` benchmarks. We have none. **Without numbers we don't exist in agent-harness default lists.**

## 6 reference repos (clone via wiki submodules or fresh)

| Repo | Lang | Size | Why |
|---|---|---|---|
| VS Code | TS | ~25k files | CodeGraph's headline benchmark |
| Claude Code reverse-eng | Python+Rust | ~2k files | self-recursive credibility |
| Excalidraw | TS | ~600 files | mid-size SPA |
| Alamofire | Swift | ~300 files | iOS canonical |
| **tree-sitter-analyzer** (self) | Python | ~1.4k files | dogfood demonstration |
| Aider | Python | ~200 files | direct competitor self-analysis |

## 4 task scenarios (per repo)

1. **cold-start**: "What is this project? What's the entry point? What was changed recently?"
   - Target: 1 tool call / ≤2k tokens
2. **find-callers**: "Who calls `X`?"
   - Target: 1 call / ≤500 tokens
3. **change-impact**: "I changed `Y.method`. What tests must re-run?"
   - Target: 1 call with `verification_command` field
4. **refactor-suggest**: "Find code smells in this file and tell me how to fix them"
   - Target: 1 call with priority-ordered suggestions

## Metrics per (repo, task)

```jsonc
{
  "repo": "vscode",
  "task": "cold-start",
  "tool": "tree-sitter-analyzer",
  "tool_calls": 1,
  "tokens_in": 850,
  "tokens_out": 1100,
  "wall_clock_s": 0.42,
  "verdict": "INFO",
  "agent_decidable": true
}
```

## Comparison harness

For each `(repo, task)`:
1. **Baseline (no tool)**: Claude Code Read+Grep+Bash only, count calls + tokens
2. **Us**: 1 MCP tool call, count + verify agent_decidable
3. **CodeGraph** (if installable): same task, same metric

Output: `benchmarks/agent-tasks/results-YYYY-MM-DD.json` + README table.

## Status

- [x] Implement harness `bench_runner.py` (r37fE, 2026-05-22)
- [x] Wire up baseline tracker (r37fE)
- [x] Self-bench landed: `results-2026-05-22.json` (1 repo × 4 scenarios × 2 tools)
- [ ] Run 6×4 matrix (24 cases — needs `git clone` of vscode/excalidraw/alamofire/aider/claude-code-reverse)
- [ ] Publish in main README

## CodeGraph parity table (2026-05-22 self-bench)

Self-bench against ``tree-sitter-analyzer`` itself (~1.4k Python files,
24k indexed functions, 330k call edges). CodeGraph's public numbers come
from their VS Code benchmark in the [Voideditor CodeGraph
README](https://github.com/voideditor/codegraph) — direct apples-to-apples
on tool-call count; tokens/time are estimated from their published
"6 tools × 92% reduction" claim and 71% wall-clock saving.

| Repo | Task | CodeGraph (calls / time) | **Us (TSA)** (calls / time / tokens-out) | Baseline (calls / time / tokens-out) |
|---|---|---|---|---|
| tree-sitter-analyzer | cold-start | 1 / ~0.4 s | **1 / 0.31 s / 1542** | 4 / 0.042 s / 1032 |
| tree-sitter-analyzer | find-callers (`compute_graph_fingerprint`, 8 callers) | 1 / ~0.3 s | **1 / 2.22 s / 457** | 4 / 0.025 s / 1029 |
| tree-sitter-analyzer | change-impact (git diff) | 1 / ~0.5 s | **1 / 3.35 s / 1205** | 3 / 0.050 s / 118 |
| tree-sitter-analyzer | refactor-suggest (`get_project_summary_tool.py`) | n/a | **1 / 0.16 s / 2137** | 3 / 0.051 s / 1060 |

**Decidable column (the one CodeGraph doesn't break out):**

| Task | TSA decidable | Baseline decidable | Why baseline loses |
|---|---|---|---|
| cold-start | yes | yes | tie (both surface README + structure) |
| find-callers | yes | yes | tie on signal, **TSA wins on tokens (457 vs 1029, -56%)** |
| change-impact | yes | **no** | baseline has no `verification_command` — agent has to guess tests |
| refactor-suggest | yes | **no** | baseline has no priority-ordered extraction plan |

**Honest caveats** (vs CodeGraph's marketing numbers):

- TSA call-graph build is **cold** on first call (~2 s for find-callers, ~3 s
  for change-impact dependency graph). CodeGraph claims sub-second; their
  published numbers don't disclose whether they include build time.
  Subsequent calls in the same session hit warm cache (<50 ms).
- TSA tokens-out is sometimes *higher* than baseline (cold-start 1542 vs
  1032) because the structured envelope carries `agent_summary`,
  `verdict`, `summary_line`, `verification_command`. The trade is: more
  tokens **once** instead of more agent loops, more retries, more
  human-readable output to re-parse. For a 50-step agent task this nets
  out lower.
- Symbol choice for find-callers matters a lot: TSA on `execute` (1427
  callers) emits ~63 k tokens. Production agents should pass a more
  scoped symbol or use ``codegraph_call_graph mode=summary`` first.

## Reproducing

```bash
# Self-bench (this repo only):
uv run python benchmarks/agent-tasks/bench_runner.py \
  --out benchmarks/agent-tasks/results-2026-05-22.jsonl \
  --aggregate benchmarks/agent-tasks/results-2026-05-22.json \
  --symbol compute_graph_fingerprint

# Specific scenario, baseline only:
uv run python benchmarks/agent-tasks/bench_runner.py \
  --scenario change-impact --tool baseline

# Multi-repo: pass --repo for each (clone the 6 reference repos first):
uv run python benchmarks/agent-tasks/bench_runner.py \
  --repo /path/to/vscode \
  --repo /path/to/excalidraw \
  --repo .
```
