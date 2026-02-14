# Spec: check_architecture_health MCP Tool

**Change ID**: `add-code-intelligence-graph`
**Spec ID**: `architecture-health`
**Status**: Implemented (v2 — 2026-02-14)

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
