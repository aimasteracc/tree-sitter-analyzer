# Spec: check_architecture_health MCP Tool

**Change ID**: `add-code-intelligence-graph`
**Spec ID**: `architecture-health`
**Status**: Draft

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

## Acceptance Criteria

- [x] Coupling metrics (Ca, Ce, I, A) computed correctly
- [x] Tarjan's algorithm detects all cycles
- [x] Layer rules are configurable and violations detected
- [x] God classes identified by method count threshold
- [x] Dead code detected by symbol reference analysis
- [x] Architecture score reflects overall health
