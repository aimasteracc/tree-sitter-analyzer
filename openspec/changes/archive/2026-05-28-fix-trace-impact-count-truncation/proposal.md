# Fix trace_impact: call_count truncated by max_results

## Overview

`trace_impact` returns `call_count` equal to `max_results` instead of the true
total match count when results are truncated. This causes `impact_level` to be
misclassified (e.g., HIGH becomes LOW), breaking `modification_guard` safety verdicts.

## Validation Evidence

Discovered via spring-framework validation:

```python
# @Component appears 695 times in spring-framework
trace_impact("Component", max_results=5)
→ call_count: 5, impact_level: "low"   # WRONG — should be 695, "high"

trace_impact("Component")  # no limit
→ call_count: 695, impact_level: "high"  # CORRECT
```

## Root Cause

In `trace_impact_tool.py`, `total_count` is computed from `len(usages)` AFTER
the results list has been truncated to `max_results`:

```python
# Line 377-378: truncate matches
if len(matches) > max_results:
    matches = matches[:max_results]  # truncate

# Line 394: WRONG — counts truncated list
total_count = len(usages)   # → max_results, not true total
```

## Impact

- `modification_guard` uses `call_count` to compute `safety_verdict`
- With max_results=5 (common default), any symbol with >5 callers shows "LOW IMPACT"
- Claude gets "SAFE" verdict for symbols that are actually "UNSAFE"
- Critical: `@Transactional`, `ApplicationContext` would appear safe to modify

## Fix

Capture true match count before truncation:
```python
true_total = len(matches)
if true_total > max_results:
    matches = matches[:max_results]
    truncated = True
...
total_count = true_total  # pre-truncation count
```

## Success Criteria

1. `trace_impact("Component", max_results=5)` → `call_count=695` (true total)
2. `impact_level` reflects true count, not display count
3. `truncated=True` indicates results were capped
4. `usages` still contains only `max_results` items (display limit preserved)
