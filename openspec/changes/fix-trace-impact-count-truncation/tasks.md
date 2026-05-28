# Tasks: Fix trace_impact call_count truncation

## Status: RESOLVED — already fixed

Verified 2026-05-28 by code inspection of `trace_impact_tool.py`:

```python
# Line 806-808 (current code):
source_total = len(source_matches)           # ← FULL count, before truncation
display_matches, truncated = _truncate_for_display(source_matches, max_results)
usages = _matches_to_usages(display_matches) # ← only display list is truncated
```

`source_total` is set from `len(source_matches)` BEFORE `_truncate_for_display()` is called.
The fix described in the proposal is already present in the codebase.
`call_count` in the response uses `source_total`, not `len(usages)`.

## Action Taken

No code changes required. Proposal archived in-place.
