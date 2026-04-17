# Incremental Analysis Cache

## Goal

Leverage tree-sitter's parsing efficiency to cache analysis results, providing 10-100x speedup for repeated queries on the same codebase.

## Inspiration

From office-hours design discussion: "The 'whoa' moment is when a 30-second analysis becomes 300ms for the second query."

## MVP Scope

1. **File-Hash Cache** — Cache analysis results by file content hash
2. **Git-Aware Invalidation** — Use git SHA for repo-level invalidation
3. **Concurrent Access** — File locks for safe multi-process access
4. **Bounded Memory** — Size-based eviction (max 1GB)
5. **Integration** — Existing MCP tools automatically benefit

## Technical Approach

### Cache Format

```python
@dataclass
class CacheKey:
    file_path: str
    content_hash: str  # SHA256
    tree_sitter_version: str
    language: str

@dataclass
class CachedAnalysis:
    key: CacheKey
    ast_bytes: bytes  # Pickled tree-sitter Tree
    analysis_result: dict
    timestamp: float
    git_sha: str | None
```

### Sprint Breakdown

**Sprint 1: Core Cache Manager (2 days)** ⏳ IN PROGRESS
- [ ] Create `tree_sitter_analyzer/cache/incremental_cache.py`
- [ ] Implement CacheKey, CachedAnalysis, CacheEntry dataclasses
- [ ] Implement file-hash based caching
- [ ] Add cache invalidation on file change
- [ ] Implement size-based eviction (LRU)
- [ ] Write 15+ tests

**Sprint 2: Git-Aware Invalidation (2 days)** ⏳ PENDING
- [ ] Integrate with git_analyzer.py for SHA tracking
- [ ] Implement repo-level invalidation
- [ ] Handle branch switching
- [ ] Add file locking for concurrent access
- [ ] Write 10+ tests

**Sprint 3: Integration & Optimization (1 day)** ⏳ PENDING
- [ ] Integrate with existing MCP tools
- [ ] Add cache warming for top-20 complex files
- [ ] Benchmark: 10-100x speedup
- [ ] Write 5+ tests

## Success Criteria

- [ ] Second query on unchanged repo is <500ms (vs 30s baseline)
- [ ] Cache invalidation is 100% safe (no stale results)
- [ ] Works without git (falls back to file-hash only)
- [ ] Memory usage bounded (<1GB for 10K file repo)
- [ ] 30+ tests passing (15 + 10 + 5)

## Dependencies

- tree-sitter (existing)
- git_analyzer.py (existing, from add-project-radar)
- query_cache.py (existing, from semantic_code_search)

## References

- Design doc: `~/.gstack/projects/aimasteracc-tree-sitter-analyzer/aisheng.yu-feat_autonomous-dev-design-20260417-213950.md`
- tree-sitter incremental parsing: `/Users/aisheng.yu/wiki/wiki/ai-tech/tree-sitter-performance.md`

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
