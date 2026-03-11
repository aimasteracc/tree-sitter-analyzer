# Tasks: Fix Java Plugin Annotation Extraction

**Change ID**: `fix-java-plugin-annotation-extraction`

---

## Implementation Tasks

### Phase 1: Tests (RED)

- [ ] Create `tests/integration/languages/test_java_integration.py`
  - [ ] JAA-001: `test_class_annotations_populated`
  - [ ] JAA-002: `test_method_annotations_populated`
  - [ ] JAA-003: `test_spring_annotations_end_to_end`
- [ ] Add to `tests/unit/languages/test_java_plugin.py`
  - [ ] JAA-004: `TestResetCachesPreservesState.test_reset_caches_preserves_annotations`
  - [ ] JAA-004: `TestResetCachesPreservesState.test_reset_caches_preserves_current_package`
  - [ ] JAA-005: `TestExtractElementsSyncsState.test_extractor_annotations_synced`

### Phase 2: Implementation (GREEN)

- [ ] Fix A: `_reset_caches()` — remove `self.annotations.clear()` and `self.current_package = ""`
- [ ] Fix B: `extract_elements()` — reorder: annotations+packages first, sync self.extractor at end

### Phase 3: Verification

- [ ] Run `uv run pytest tests/integration/languages/test_java_integration.py -v` → all GREEN
- [ ] Run `uv run pytest tests/unit/languages/test_java_plugin.py -v` → all GREEN
- [ ] Run `uv run pytest -q` → no regression
- [ ] Run `uv run python check_quality.py` → pass
