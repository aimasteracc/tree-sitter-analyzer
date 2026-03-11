# Proposal: Fix Java Plugin Annotation Extraction

**Change ID**: `fix-java-plugin-annotation-extraction`
**Status**: In Progress
**Date**: 2026-03-11

---

## Problem Statement

Java classes and methods extracted by `JavaPlugin` always have empty `annotations` fields,
even when the source code contains annotations like `@RestController`, `@Override`, or `@GetMapping`.

This is silent data loss: no error is raised, but annotation information is permanently discarded.

## Root Cause

`extract_elements()` in `JavaPlugin` calls extraction methods in this order:

```
extract_functions()   ← internally reads self.annotations (empty at this point)
extract_classes()     ← internally reads self.annotations (empty at this point)
extract_variables()
extract_imports()
extract_packages()
extract_annotations() ← only HERE are annotations collected (too late)
```

Each `extract_*()` call begins by calling `_reset_caches()`, which clears
`self.annotations` as a side effect. Even if `extract_annotations()` were called
first, subsequent `_reset_caches()` calls would destroy the data.

`_reset_caches()` conflates two responsibilities:
1. Clearing performance caches (correct)
2. Resetting business state (`self.annotations`, `self.current_package`) — incorrect

Additionally, `self.extractor` (set in `__init__`) is never updated after analysis,
diverging from the pattern established by `GoPlugin`, which syncs metadata back to
`self.extractor` after each analysis.

## Solution

1. Remove `self.annotations.clear()` and `self.current_package = ""` from `_reset_caches()`
2. In `extract_elements()`, call `extract_annotations()` and `extract_packages()` first
3. Sync analysis state back to `self.extractor` after extraction (align with `GoPlugin`)

## Impact

- Java classes and methods will correctly report their annotations
- `plugin.extractor.annotations` will reflect the last analyzed file (consistent with Go)
- No breaking changes to public API
- Existing tests remain valid; new tests added to cover the fixed behavior
