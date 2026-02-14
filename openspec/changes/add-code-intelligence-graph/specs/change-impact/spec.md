# Spec: assess_change_impact MCP Tool

**Change ID**: `add-code-intelligence-graph`
**Spec ID**: `change-impact`
**Status**: Implemented (v2 — 2026-02-14)

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

### Requirement 6: File Path Target Support (v2)
**ID**: CI-006
**Priority**: High

#### Scenario: Assess impact of a file change
**Given** `auth.py` defines `login()` and `AuthService`, and is imported by `api.py` and `cli.py`
**When** assess_change_impact is called with `{"target": "auth.py"}`
**Then** direct_impacts includes `api.py` (importer) and `cli.py` (importer)

#### Scenario: File target includes symbol callers
**Given** `auth.py` defines `login()`, and `handler.py` calls `login()`
**When** assess_change_impact is called with `{"target": "auth.py"}`
**Then** direct_impacts includes `handler.py` as a direct_caller

#### Scenario: File path detection
**Given** target contains `/` or ends with `.py`
**When** `_is_file_path()` is evaluated
**Then** returns `True` and triggers file-level analysis instead of symbol lookup

#### Scenario: Symbol target unchanged
**Given** target is `"AuthService"` (no `/` or `.py`)
**When** assess_change_impact is called
**Then** original symbol-based analysis is used (backward compatible)

---

## Acceptance Criteria

- [x] Direct impacts correctly identified via call graph
- [x] Transitive impacts traced to correct depth
- [x] Test files identified by naming convention and import analysis
- [x] Risk levels calculated based on impact count and depth
- [x] Change type affects severity classification
- [x] (v2) File path targets correctly identify importers and callers of defined symbols
- [x] (v2) Symbol targets remain backward compatible
