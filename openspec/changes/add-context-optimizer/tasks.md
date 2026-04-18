# Context Optimizer — LLM Context Window Optimization

## Goal

**一句话定义**: 智能代码上下文摘要器 — 让大文件适应 LLM 上下文窗口。

## Problem Statement

tree-sitter-analyzer has 29 MCP tools that output rich code context. But when analyzing large projects, this output consumes 50k+ tokens — often exceeding LLM context windows.

**The gap**: TOON compression removes formatting (69.6% size reduction) but keeps all content. We need intelligent content reduction that preserves what matters for LLM understanding.

## MVP Scope

1. **Importance-based scoring** — Rank code elements by complexity + dependencies
2. **Filtering** — Keep top 50% by importance score
3. **Post-processing** — Works with any MCP tool's TOON output
4. **Validation** — LLM benchmark to verify fidelity

## Technical Approach

### Algorithm

```python
score = complexity_score * 0.4 + dependency_count * 0.3 + call_frequency * 0.3
```

- `complexity_score`: From existing `complexity.py` module
- `dependency_count`: From `dependency_graph.py` edge_weights
- `call_frequency`: Approximated by dependency in-degree (refined in Sprint 3)

### Module Structure

```
tree_sitter_analyzer/analysis/context_optimizer.py
- score_importance(element: CodeElement) -> float
- filter_by_importance(elements: list[CodeElement], threshold: float) -> list[CodeElement]
- optimize_for_llm(toon_output: str) -> str
```

### Sprint Breakdown

**Sprint 1: Core Scoring Algorithm** (2-3 days)
- [ ] Create `analysis/context_optimizer.py`
- [ ] Implement `CodeElement` dataclass (name, type, complexity, dependencies)
- [ ] Implement `score_importance()` using weighted formula
- [ ] Implement `filter_by_importance()` with percentile threshold
- [ ] Write unit tests (20+ tests)

**Sprint 2: MCP Tool Integration** (2-3 days)
- [ ] Add `--optimize-context` flag to `semantic_impact` tool
- [ ] Add `--optimize-context` flag to `dependency_graph` tool
- [ ] Add `--optimize-context` flag to `complexity_heatmap` tool
- [ ] Implement TOON post-processing pipeline
- [ ] Write integration tests (15+ tests)

**Sprint 3: Validation & Benchmark** (2-3 days)
- [ ] Create LLM benchmark (answer questions before/after optimization)
- [ ] Measure compression ratio vs fidelity
- [ ] Iterate scoring algorithm if needed
- [ ] Update documentation (README.md, ARCHITECTURE.md)

## Success Criteria

- [ ] 50-70% token reduction vs full TOON output
- [ ] 90%+ of questions answerable from optimized output
- [ ] Optimization adds <1s to analysis time
- [ ] Works for all 17 supported languages

## Dependencies

**Existing modules to reuse**:
- `tree_sitter_analyzer/analysis/complexity.py` — complexity scores
- `tree_sitter_analyzer/analysis/dependency_graph.py` — dependency counts
- `tree_sitter_analyzer/formatters/toon.py` — TOON format handling

**New modules**:
- `tree_sitter_analyzer/analysis/context_optimizer.py`

## References

- Headroom: https://github.com/chopratejas/headroom
- Manus Context Engineering: wiki/raw/ai-tech/planning-with-files/skills/planning-with-files/reference.md
