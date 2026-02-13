# Spec: trace_symbol MCP Tool

**Change ID**: `add-code-intelligence-graph`
**Spec ID**: `trace-symbol`
**Status**: Draft

---

## Overview

MCP tool that traces a symbol (function/class/variable) across a project, returning its definition, usages, call chains, and inheritance hierarchy.

---

## ADDED Requirements

### Requirement 1: Symbol Definition Lookup
**ID**: TS-001
**Priority**: High

#### Scenario: Trace a function definition
**Given** a Python file `auth.py` containing `def login(user, password):`
**When** trace_symbol is called with `{"symbol": "login", "file_path": "auth.py", "trace_type": "definition"}`
**Then** the result contains definition with file_path, line, type="function", parameters=["user", "password"]

#### Scenario: Trace with disambiguation
**Given** two files both containing a function named `validate`
**When** trace_symbol is called with `{"symbol": "validate"}` (no file_path)
**Then** the result lists all matching definitions

### Requirement 2: Symbol Usage Tracking
**ID**: TS-002
**Priority**: High

#### Scenario: Find all usages of a function
**Given** a project where `login()` is called from 3 different files
**When** trace_symbol is called with `{"symbol": "login", "trace_type": "usages"}`
**Then** the result lists all 3 call sites with file, line, and context

### Requirement 3: Call Chain Tracing
**ID**: TS-003
**Priority**: High

#### Scenario: Trace call chain with depth
**Given** a call chain: endpoint() -> service.login() -> repo.find_user()
**When** trace_symbol is called with `{"symbol": "login", "trace_type": "call_chain", "depth": 2}`
**Then** the result shows callers=[endpoint] and callees=[find_user]

### Requirement 4: Inheritance Tracing
**ID**: TS-004
**Priority**: Medium

#### Scenario: Trace class inheritance
**Given** classes: BaseService -> AuthService -> MockAuthService
**When** trace_symbol is called with `{"symbol": "AuthService", "trace_type": "inheritance"}`
**Then** the result shows parent=BaseService and children=[MockAuthService]

### Requirement 5: Full Trace
**ID**: TS-005
**Priority**: High

#### Scenario: Full symbol trace
**When** trace_symbol is called with `{"symbol": "AuthService", "trace_type": "full"}`
**Then** the result contains definition, usages, call chains, and inheritance

### Requirement 6: Output Formats
**ID**: TS-006
**Priority**: Medium

#### Scenario: Summary format
**When** output_format="summary"
**Then** human-readable text output with section headers

#### Scenario: JSON format
**When** output_format="json"
**Then** structured JSON with all data

#### Scenario: Tree format
**When** output_format="tree"
**Then** compact TOON-style token-optimized output

---

## Acceptance Criteria

- [x] trace_symbol correctly finds definitions across project
- [x] All 5 trace_type modes work correctly
- [x] Output formats produce valid, parseable content
- [x] Depth limiting works for call chains
- [x] Multiple definitions handled when no file_path given
