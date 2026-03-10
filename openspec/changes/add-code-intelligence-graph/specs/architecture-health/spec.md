# Spec: check_architecture_health MCP Tool

**Change ID**: `add-code-intelligence-graph`
**Spec ID**: `architecture-health`
**Status**: Partially Implemented (v5 — 2026-03-11)

---

## Overview

MCP tool that assesses the architectural health of a project or module, computing coupling metrics, detecting circular dependencies, checking layer violations, and identifying god classes and dead code.

---

## ADDED Requirements

### Requirement 1: Coupling Metrics
**ID**: AH-001
**Priority**: High

#### Scenario: Compute afferent and efferent coupling
**Given** module A imports from B and C; module D imports from A
**When** check_architecture_health is called with checks=["coupling_metrics"]
**Then** module A has Ca=1 (D depends on it), Ce=2 (depends on B, C)

#### Scenario: Compute instability
**Given** module with Ca=1, Ce=2
**When** instability is computed
**Then** I = Ce / (Ca + Ce) = 2/3 = 0.67

### Requirement 2: Circular Dependency Detection
**ID**: AH-002
**Priority**: High

#### Scenario: Detect simple cycle
**Given** file A imports B, file B imports A
**When** check_architecture_health is called with checks=["circular_dependencies"]
**Then** cycles contains [A, B] with length=2

#### Scenario: Detect transitive cycle
**Given** A imports B, B imports C, C imports A
**When** cycles are detected
**Then** cycles contains [A, B, C] with length=3

#### Scenario: No cycles
**Given** a clean dependency graph with no cycles
**When** cycles are detected
**Then** cycles is empty

### Requirement 3: Layer Violation Detection
**ID**: AH-003
**Priority**: Medium

#### Scenario: Detect downward dependency violation
**Given** layer_rules: {"models": {"allowed_deps": ["utils"]}, "services": {"allowed_deps": ["models", "utils"]}}
**And** models/user.py imports services/auth.py
**When** check_architecture_health is called with checks=["layer_violations"]
**Then** violations contains models/user.py -> services/auth.py

### Requirement 4: God Class Detection
**ID**: AH-004
**Priority**: Medium

#### Scenario: Detect class with too many methods
**Given** a class with 30 methods
**When** check_architecture_health is called with checks=["god_classes"]
**Then** god_classes contains the class with method_count=30

### Requirement 5: Dead Code Detection
**ID**: AH-005
**Priority**: Low

#### Scenario: Detect unreferenced symbol
**Given** a function `old_helper()` defined but never imported or called
**When** check_architecture_health is called with checks=["dead_code"]
**Then** dead_symbols contains "old_helper"

### Requirement 6: Architecture Score
**ID**: AH-006
**Priority**: Medium

#### Scenario: Healthy project
**Given** no cycles, no violations, low coupling
**When** architecture score is computed
**Then** score > 80

#### Scenario: Unhealthy project
**Given** 3 cycles, 5 violations, high coupling
**When** architecture score is computed
**Then** score < 50

---

### Requirement 7: Path Scoping (v2)
**ID**: AH-007
**Priority**: High

#### Scenario: Scoped god class detection
**Given** a god class in `src/` and another in `tests/`
**When** check_architecture_health is called with `path="src/"`
**Then** only the god class in `src/` is reported

#### Scenario: Scoped cycle detection
**Given** a cycle in `src/` and another in `tests/`
**When** check_architecture_health is called with `path="src/"`
**Then** only the cycle within `src/` files is reported

#### Scenario: Scoped coupling and dead code
**Given** definitions in `src/` and `lib/`
**When** check_architecture_health is called with `path="src/"`
**Then** coupling metrics and dead code only include `src/` files

### Requirement 8: Abstractness Calculation (v2)
**ID**: AH-008
**Priority**: High

#### Scenario: Module with abstract classes
**Given** a module where 1 out of 2 classes inherits from ABC
**When** coupling metrics are computed
**Then** abstractness = 0.5

#### Scenario: Pure concrete module
**Given** a module with only concrete classes
**When** coupling metrics are computed
**Then** abstractness = 0.0

#### Scenario: Protocol counted as abstract
**Given** a class with `Protocol` in its base classes
**When** abstractness is computed
**Then** the class counts as abstract

### Requirement 9: Score Capping (v2)
**ID**: AH-009
**Priority**: High

#### Scenario: Moderate project does not score 0
**Given** a project with 2 cycles and 30 god classes
**When** architecture score is computed
**Then** score > 0 (not collapsed to 0 due to uncapped deductions)

#### Scenario: Each category has a deduction cap
**Given** 100 god classes
**When** score is computed with only god_classes check
**Then** god class deduction is capped at -20 (score >= 80)

### Requirement 10: TYPE_CHECKING Awareness (v2)
**ID**: AH-010
**Priority**: High

#### Scenario: TYPE_CHECKING cycle excluded
**Given** A imports B (normal), B imports A (inside `if TYPE_CHECKING:`)
**When** cycle detection is run
**Then** no cycle is reported (the type-only edge is excluded)

#### Scenario: Real cycle still detected
**Given** A imports B (normal), B imports A (normal)
**When** cycle detection is run
**Then** the cycle [A, B] is reported

### Requirement 11: Property-Aware Dead Code Detection (v3)
**ID**: AH-011
**Priority**: P1 High

Dead code detection must not report `@property`-decorated methods as dead, since they are accessed via attribute syntax (not function calls) and won't appear as call references.

#### Scenario: Property method not reported as dead
**Given** a class with a `@property` method `instability` that has no call references
**When** dead code detection runs
**Then** `instability` is NOT in the dead_symbols list

#### Scenario: Truly dead method still detected
**Given** a regular method `old_helper` with no references
**When** dead code detection runs
**Then** `old_helper` IS in the dead_symbols list

### Requirement 12: Test Coverage Analysis (v3)
**ID**: AH-012
**Priority**: P1 High

A new `"test_coverage"` check that analyses which source code symbols are tested, untested, or over-tested.

#### Scenario: Detect untested public method
**Given** a public function `process_data()` in source code with zero references from test files
**When** test coverage analysis runs
**Then** `process_data` appears in `untested_symbols`

#### Scenario: Detect over-tested symbol
**Given** a function referenced by more than `overtested_threshold` distinct test functions
**When** test coverage analysis runs
**Then** it appears in `overtested_symbols`

#### Scenario: Detect test-only symbol
**Given** a function with references ONLY from test files (no source code references)
**When** test coverage analysis runs
**Then** it appears in `test_only_symbols`

#### Scenario: Coverage ratio calculated
**Given** 10 public source symbols, 7 have at least one test reference
**When** test coverage analysis runs
**Then** `coverage_ratio` = 0.7

### Requirement 13: Test Coverage Excludes Property and Inner Functions (v4)
**ID**: AH-013
**Priority**: P1 High

The `test_coverage` check must not report `@property`-decorated methods or inner (nested) functions as untested, since these symbols are accessed implicitly (attribute syntax or closure invocation) and won't appear as direct call references in test files.

#### Scenario: Property method not reported as untested
**Given** a class with a `@property` method `instability` that is tested via attribute access
**When** test coverage analysis runs
**Then** `instability` is NOT in the `untested_symbols` list

#### Scenario: Inner function not reported as untested
**Given** a nested function `wrapper` inside a decorator `handle_exceptions`
**When** test coverage analysis runs
**Then** `wrapper` is NOT in the `untested_symbols` list (it inherits coverage from its enclosing function)

#### Scenario: Truly untested regular method still detected
**Given** a public method `old_helper` with no test references and no implicit-access modifiers
**When** test coverage analysis runs
**Then** `old_helper` IS in the `untested_symbols` list

### Requirement 14: Overtested Scoped by Definition File (v4)
**ID**: AH-014
**Priority**: P1 High

The `test_coverage` overtested detection must scope counts by `(file_path, symbol_name)` rather than by `symbol_name` alone. This prevents common method names like `execute` or `format` (implemented by many classes across different files) from being falsely aggregated into a single overtested entry.

#### Scenario: Same-name methods in different files not aggregated
**Given** `ToolA.execute` in `tools/a.py` with 5 test refs and `ToolB.execute` in `tools/b.py` with 5 test refs
**When** test coverage analysis runs with `overtested_threshold=10`
**Then** neither `execute` entry is in `overtested_symbols` (each has only 5 refs, not 10)

#### Scenario: Single file with truly overtested method
**Given** `process` in `src/engine.py` with 15 distinct test function references
**When** test coverage analysis runs with `overtested_threshold=10`
**Then** `process` from `src/engine.py` is in `overtested_symbols` with `test_ref_count=15`

### Requirement 15: Stability Metrics Check (v5)
**ID**: AH-015
**Priority**: High

Report modules that exceed the instability threshold, sorted for prioritized refactoring.

#### Scenario: Report unstable modules
**Given** a module with Ca=1, Ce=5 (instability=0.833)
**When** check_architecture_health is called with checks=["stability_metrics"]
**Then** result.unstable_modules contains the module with instability=0.833

#### Scenario: Stable modules excluded (strict threshold)
**Given** a module with Ca=3, Ce=7 (instability exactly 0.7)
**When** stability_metrics check runs
**Then** the module is NOT in unstable_modules (threshold is strictly > 0.7)

#### Scenario: Works without coupling_metrics in checks
**Given** only checks=["stability_metrics"] specified
**When** the check runs
**Then** coupling is computed internally and unstable_modules is populated

#### Scenario: Sorted by instability descending
**Given** multiple unstable modules with different instability values
**Then** unstable_modules[0].instability >= unstable_modules[1].instability

### Requirement 16: Hotspot Detection (v5)
**ID**: AH-016
**Priority**: High

Identify modules that are both highly unstable AND heavily coupled — the most dangerous refactoring targets.

#### Scenario: High instability + high efferent coupling = hotspot
**Given** a module with instability=0.85 and efferent_coupling=8
**When** check_architecture_health is called with checks=["hotspots"]
**Then** result.hotspot_modules contains the module

#### Scenario: Low coupling excludes from hotspot
**Given** a module with instability=0.9 but efferent_coupling=1 (< 3)
**When** hotspots check runs
**Then** the module is NOT in hotspot_modules

#### Scenario: Sorted by hotspot_score (instability × efferent_coupling) descending
**Given** multiple hotspot modules with different scores
**Then** hotspot_modules are sorted so highest score comes first

---

## Acceptance Criteria

- [x] Coupling metrics (Ca, Ce, I, A) computed correctly
- [x] Tarjan's algorithm detects all cycles
- [x] Layer rules are configurable and violations detected
- [x] God classes identified by method count threshold
- [x] Dead code detected by symbol reference analysis
- [x] Architecture score reflects overall health
- [x] (v2) `path` parameter scopes all metrics to the specified directory
- [x] (v2) Abstractness computed from ABC/Protocol/abstractmethod ratio
- [x] (v2) Score uses per-category caps to prevent collapse to 0
- [x] (v2) TYPE_CHECKING imports excluded from cycle detection
- [x] (v3) `@property` methods excluded from dead code detection
- [x] (v3) `test_coverage` check detects untested/overtested/test-only symbols
- [x] (v4) `test_coverage` excludes `@property` and inner functions from untested list (AH-013)
- [x] (v4) `test_coverage` overtested scoped by `(file, name)` to avoid cross-class aggregation (AH-014)
- [ ] (v5) `stability_metrics` check returns unstable_modules sorted by instability desc (AH-015)
- [ ] (v5) `hotspots` check returns hotspot_modules sorted by instability×Ce desc (AH-016)
