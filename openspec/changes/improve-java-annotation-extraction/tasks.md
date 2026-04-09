# Tasks: Improve Java Annotation Extraction

## Overview

Fix four independent bugs causing complete annotation loss in `analyze_code_structure`. Validated via spring-petclinic (Spring MVC/JPA). Drive via TDD: write failing tests first, then fix.

## Validation Project

**spring-petclinic** (local: `/workspaces/claude-source-run-version/spring-petclinic`)
- Standard Spring MVC + JPA application
- Representative annotation patterns: `@Controller`, `@GetMapping`, `@Entity`, `@ManyToMany`
- Medium scale: 47 Java files

## Task List

### Phase 1: TDD — Write Failing Tests (Before any fix)

- [x] **T1.1**: Write test for Bug 1+2 (annotation extraction order + reset)
  - Test: `extract_elements()` on a class with annotations → methods/classes/fields have non-empty annotations
  - Test: call `extract_annotations()` then `extract_functions()` → annotations preserved
  - Verify: test FAILS before fix

- [x] **T1.2**: Write test for Bug 3 (tool layer hardcodes annotations=[])
  - Test: `analyze_code_structure` MCP tool on spring-petclinic OwnerController.java
  - Assert: `elements.classes[0].annotations` contains `@Controller`
  - Assert: `elements.methods` with `@GetMapping` have annotation extracted
  - Verify: test FAILS before fix

- [x] **T1.3**: Write test for Bug 4 (field_declaration not in container_node_types)
  - Test: `analyze_code_structure` on Vet.java
  - Assert: `specialties` field has `@ManyToMany` and `@JoinTable` annotations
  - Verify: test FAILS before fix

### Phase 2: Fix Implementation

- [x] **T2.1**: Fix extraction order in `extract_elements()` (`java_plugin.py`)
  - Move `extract_annotations()` call to FIRST position
  - Save result in local var; reuse in returned dict (avoid double call)

- [x] **T2.2**: Remove `self.annotations.clear()` from `_reset_caches()` (`java_plugin.py`)
  - Add explanatory comment: source data vs lookup cache distinction
  - Ensure `extract_annotations()` itself still clears via `_reset_caches()` → `self.annotations = annotations`

- [x] **T2.3**: Fix `analyze_code_structure_tool.py` to read annotations from model objects
  - Replace `"annotations": []` with `"annotations": getattr(obj, "annotations", [])`
  - Apply to classes, methods, and fields

- [x] **T2.4**: Add `"field_declaration"` to `container_node_types` (`java_plugin.py`)
  - Add with explanatory comment: field annotations live in field_declaration > modifiers

### Phase 3: Validation

- [x] **T3.1**: Run all Java tests (`uv run pytest tests/ -k "java"`)
  - Target: 610 passed, 0 failed

- [x] **T3.2**: Verify against spring-petclinic
  - OwnerController: `@Controller` on class, `@GetMapping`/`@PostMapping` on methods
  - Vet: `@ManyToMany`, `@JoinTable` on specialties field
  - Owner: `@Entity`, `@Table` on class

- [x] **T3.3**: Update `test_reset_caches` to match correct behavior
  - Document why `self.annotations` is NOT cleared: it's source data, not cache

### Phase 4: SDD Documentation

- [x] **T4.1**: Write `proposal.md` (this change's problem statement + root causes)
- [x] **T4.2**: Write `tasks.md` (this file)
- [ ] **T4.3**: Write `design.md` (architecture of annotation extraction pipeline)
- [ ] **T4.4**: Update CHANGELOG.md

## Next Java Quality Issues (Backlog)

From spring-petclinic scan — additional items to address in future specs:

1. **Annotation parameters nested annotations** — `@JoinColumn` inside `@JoinTable` detected but parsed as part of parent text (not decomposed). Low priority.
2. **`implements=[]` for classes with implicit serialization** — Not a bug (Serializable is via superclass). No action needed.
3. **Class visibility hardcoded to `"public"`** — `analyze_code_structure_tool.py` line 282 forces `"visibility": "public"` for all classes. Package-private classes not distinguished.

## Dependencies

- T1.* (write tests) must complete before T2.* (fixes)
- T2.1, T2.2, T2.3, T2.4 are independent — can implement in any order
- T3.1 validates T2.* changes
- T3.2 validates T3.1

## Completed Status

All T1, T2, T3 tasks: COMPLETE (2026-04-09)
T4.1, T4.2: COMPLETE
T4.3, T4.4: PENDING
