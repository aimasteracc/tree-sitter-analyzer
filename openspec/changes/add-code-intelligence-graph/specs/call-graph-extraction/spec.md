# Spec: Call Graph Extraction

**Change ID**: `add-code-intelligence-graph`
**Spec ID**: `call-graph-extraction`
**Status**: Partially Implemented (v3 — 2026-03-11)

---

## Overview

Extract function/method call sites from Python source code using tree-sitter queries and build caller/callee relationship graphs.

---

## ADDED Requirements

### Requirement 1: Simple Function Call Extraction
**ID**: CGE-001
**Priority**: High
**Category**: Core Functionality

#### Scenario: Extract a simple function call
**Given** a Python file containing `print("hello")`
**When** the call_expression query is executed
**Then** a CallSite is returned with:
- callee_name = "print"
- callee_object = None
- line = correct line number

#### Scenario: Extract a function call with arguments
**Given** a Python file containing `calculate_total(items, tax_rate=0.1)`
**When** the call_expression query is executed
**Then** a CallSite is returned with callee_name = "calculate_total"

### Requirement 2: Method Call Extraction
**ID**: CGE-002
**Priority**: High

#### Scenario: Extract a self method call
**Given** a Python file containing `self.validate(data)`
**When** the call_expression query is executed
**Then** a CallSite is returned with:
- callee_name = "validate"
- callee_object = "self"

#### Scenario: Extract an object method call
**Given** a Python file containing `user_service.find_by_id(user_id)`
**When** the call_expression query is executed
**Then** a CallSite is returned with:
- callee_name = "find_by_id"
- callee_object = "user_service"

### Requirement 3: Chained Call Extraction
**ID**: CGE-003
**Priority**: Medium

#### Scenario: Extract chained method calls
**Given** a Python file containing `queryset.filter(active=True).order_by("name")`
**When** the calls query is executed
**Then** two CallSite entries are returned for both call sites

### Requirement 4: Call Graph Construction
**ID**: CGE-004
**Priority**: High

#### Scenario: Build single-file call graph
**Given** a Python file with functions that call each other
**When** CallGraphBuilder.build_for_file() is called
**Then** a FileCallGraph is returned with correct caller-callee edges

#### Scenario: Find callers of a function with depth=1 (direct only)
**Given** a call chain A() → B() → C()
**When** find_callers("C", depth=1) is called
**Then** only B is returned (direct caller), A is excluded (too deep)

#### Scenario: Find callers with depth=2 (transitive)
**Given** a call chain A() → B() → C()
**When** find_callers("C", depth=2) is called
**Then** both B (depth=1) and A (depth=2) are returned

#### Scenario: depth=0 returns empty
**When** find_callers("C", depth=0) is called
**Then** an empty list is returned

#### Scenario: No duplicates in results
**Given** multiple paths to the same caller
**When** find_callers is called
**Then** each CallSite appears exactly once

---

## Acceptance Criteria

- [x] call_expression query captures simple calls, method calls, chained calls
- [x] CallSite model correctly populated from query results
- [x] CallGraphBuilder builds correct edges for single-file scenarios
- [ ] find_callers and find_callees work with depth limiting (BFS, v3)
