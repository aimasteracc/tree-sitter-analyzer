# Memory Limits and Monitoring

## System Limits

**Total RAM**: 18 GB (Apple M5)
**Safe headroom**: 4 GB (22%)
**Maximum for QMD**: 1 GB per process

## Tool Memory Budgets

| Tool | Max Memory | Notes |
|------|-----------|-------|
| qmd (BM25) | 50 MB | No LLM, fastest |
| qmd (Vector) | 400 MB | 300M embedding only |
| qmd (Hybrid) | 2000 MB | 1.7B + 0.6B models - avoid |
| tree-sitter | 100 MB | Per language parser |
| Python runtime | 150 MB | Base + dependencies |
| Claude Code | 500 MB | Agent runtime |

## Monitoring Commands

```bash
# Real-time memory monitoring
watch -n 5 'ps aux | grep -E "qmd|python" | awk "{print \$11, \$6/1024 \"MB\"}"'

# Check swap pressure (critical if > 1GB compressed)
vm_stat | grep "Pages compressed" | awk '{print $3 * 16384 / 1024 / 1024 "MB compressed"}'

# Find memory hogs (>1GB)
ps aux | awk '$6 > 1048576 {print $2, $11, $6/1024 "MB"}'

# QMD specific
ps aux | grep qmd | grep -v grep | awk '{sum+=$6; count++} END {print count " processes, " sum/1024 "MB total"}'
```

## Automated Kill Switch

```bash
# Kill processes exceeding memory limit
kill_memory_hogs() {
    local limit_mb=${1:-1024}
    ps aux | awk -v limit="$limit_mb" '$6 > limit*1024 {print $2}' | xargs -r kill -9
}

# Usage
kill_memory_hogs 1024  # Kill processes >1GB
```

## Pre-flight Checks

Add to autonomous loop:

```bash
# Check available memory before heavy operations
check_memory() {
    local free_pages=$(vm_stat | grep "Pages free" | awk '{print $3}')
    local free_mb=$((free_pages * 16384 / 1024 / 1024))

    if [ "$free_mb" -lt 2048 ]; then
        echo "ERROR: Low memory ($free_mb MB free), aborting"
        return 1
    fi
}

check_memory && ./scripts/qmd-safe-search.sh "$@"
```

## Alert Thresholds

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Free RAM | < 2 GB | < 1 GB | Kill non-essential |
| Compressed | > 1 GB | > 5 GB | Kill qmd processes |
| QMD total | > 500 MB | > 1 GB | Kill excess qmd |
| Swap used | > 1 GB | > 3 GB | Restart session |
