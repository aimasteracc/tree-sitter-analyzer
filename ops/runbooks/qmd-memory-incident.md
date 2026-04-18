# QMD Memory Incident - 2026-04-18

## Incident Summary

**Severity**: High (System instability)
**Impact**: 150GB swap usage, system performance degradation
**Root Cause**: QMD hybrid search loading multiple large models

## Timeline

- **10:04** - Autonomous development started
- **10:19** - Multiple qmd processes detected
  - PID 8635: 45.9% CPU, 1.7GB RAM
  - System showing 92GB compressed pages
- **10:20** - Incident identified and mitigated

## Root Cause Analysis

### What Happened

1. Autonomous development loop triggered multiple `qmd query` commands
2. Each query loaded:
   - 1.2GB generation model (qmd-query-expansion-1.7B)
   - 639MB reranker model (qwen3-reranker-0.6B)
   - 328MB embedding model (embeddinggemma-300M)
3. Multiple processes = 2GB+ × N = memory exhaustion
4. System compressed 92GB data to swap (observed via `vm_stat`)

### Why It Happened

- `AUTONOMOUS.md` documentation used `qmd query` in examples
- No memory limits were set
- No safe search wrapper existed
- Autonomous loop didn't account for model memory overhead

## Resolution

### Immediate Actions

1. Killed all qmd processes: `killall -9 node`
2. Created safe search wrapper: `scripts/qmd-safe-search.sh`
3. Updated `AUTONOMOUS.md` with safe search practices
4. Created monitoring documentation

### Long-term Fixes

1. **Safe Search Wrapper** (`scripts/qmd-safe-search.sh`)
   - Auto-selects search mode based on query complexity
   - Warns before loading large models
   - Simple queries → BM25 (50MB)
   - Medium queries → Vector (400MB)
   - Complex queries → Hybrid (2GB, with warning)

2. **Documentation Updates**
   - `AUTONOMOUS.md`: All examples use safe search
   - `qmd-memory-safety.md`: Complete safety guidelines
   - `qmd-troubleshooting.md`: Metal GPU fix documentation

3. **Memory Monitoring**
   ```bash
   # Check qmd memory usage
   ps aux | grep qmd | awk '{print $6/1024 "MB"}'

   # Check system swap pressure
   vm_stat | grep "Pages compressed"
   ```

## Prevention

### For Autonomous Development

1. Always use `./scripts/qmd-safe-search.sh`
2. Never use `qmd query` in automated scripts
3. Prefer `qmd search` or `qmd vsearch` for batch operations

### For Interactive Use

1. Use `qmd search` for simple keyword queries
2. Use `qmd vsearch` for semantic search
3. Reserve `qmd query` for complex, one-off queries

### Monitoring

Add to autonomous loop:
```bash
# Check before qmd operations
if ps aux | grep qmd | awk '$6 > 1048576 {exit 1}'; then
    echo "ERROR: qmd using too much memory, killing..."
    killall -9 node
    sleep 2
fi
```

## Lessons Learned

1. **LLM tools have significant memory overhead** - Must account for model sizes
2. **Batch operations amplify issues** - Single query = 2GB, 10 queries = 20GB
3. **Documentation matters** - Examples in docs set patterns for usage
4. **Safe defaults beat powerful defaults** - BM25 > Hybrid for automation

## Related

- QMD Memory Safety Guide: `/Users/aisheng.yu/wiki/raw/ai-tech/qmd-memory-safety.md`
- QMD Troubleshooting: `/Users/aisheng.yu/wiki/raw/ai-tech/qmd-troubleshooting.md`
- Safe Search Wrapper: `scripts/qmd-safe-search.sh`
