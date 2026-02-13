# Spec: assess_change_impact MCP Tool

**Change ID**: `add-code-intelligence-graph`
**Spec ID**: `change-impact`
**Status**: Draft

---

## Overview

MCP tool that evaluates the blast radius of a code change, identifying directly and transitively affected files, functions, and tests.

---

## ADDED Requirements

### Requirement 1: Direct Impact Detection
**ID**: CI-001
**Priority**: High

#### Scenario: Identify direct callers
**Given** function `create_token()` is called from `login()` and `refresh()`
**When** assess_change_impact is called with `{"target": "create_token"}`
**Then** direct_impacts includes login() and refresh() with file paths and lines

### Requirement 2: Transitive Impact Detection
**ID**: CI-002
**Priority**: High

#### Scenario: Identify transitive impacts
**Given** call chain: `endpoint()` -> `login()` -> `create_token()`
**When** assess_change_impact is called with `{"target": "create_token", "depth": 2}`
**Then** transitive_impacts includes endpoint() at depth=2

### Requirement 3: Test Impact Detection
**ID**: CI-003
**Priority**: High

#### Scenario: Find affected tests
**Given** `test_login.py` imports and calls `login()`
**When** assess_change_impact is called with `{"target": "login", "include_tests": true}`
**Then** affected_tests includes "test_login.py"

### Requirement 4: Risk Assessment
**ID**: CI-004
**Priority**: Medium

#### Scenario: Calculate risk level
**Given** a change that affects 1 file directly
**When** assess_change_impact is called
**Then** risk_level = "low"

#### Scenario: High risk change
**Given** a change that affects >10 files transitively
**When** assess_change_impact is called
**Then** risk_level = "high"

### Requirement 5: Change Type Sensitivity
**ID**: CI-005
**Priority**: Medium

#### Scenario: Signature change
**When** change_type="signature_change"
**Then** all callers are marked as direct impacts (must update call sites)

#### Scenario: Behavior change
**When** change_type="behavior_change"
**Then** callers are marked but with lower severity than signature changes

---

## Acceptance Criteria

- [x] Direct impacts correctly identified via call graph
- [x] Transitive impacts traced to correct depth
- [x] Test files identified by naming convention and import analysis
- [x] Risk levels calculated based on impact count and depth
- [x] Change type affects severity classification
