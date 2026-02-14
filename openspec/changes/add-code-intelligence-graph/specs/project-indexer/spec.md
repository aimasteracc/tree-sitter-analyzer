# Spec: Project Indexer

**Change ID**: `add-code-intelligence-graph`
**Spec ID**: `project-indexer`
**Status**: Draft (v3 — 2026-02-14)

---

## Overview

The ProjectIndexer scans a project directory and populates intelligence data structures (SymbolIndex, CallGraphBuilder, DependencyGraphBuilder). This spec defines requirements for file discovery prioritization and test file classification.

---

## Requirements

### Requirement 1: Prioritized File Discovery
**ID**: PI-001
**Priority**: P0 Critical

The indexer must use a two-phase file discovery strategy that prioritizes source code files over test files, ensuring core source directories are always indexed even when a file limit is applied.

#### Scenario: Source files indexed before test files
**Given** a project with 200 source files and 400 test files
**When** `_discover_python_files` is called with a limit of 500
**Then** all 200 source files are discovered first, followed by up to 300 test files

#### Scenario: All project source directories are included
**Given** a project with `tree_sitter_analyzer/mcp/` directory at position 512 in default walk order
**When** `_discover_python_files` is called with the new limit of 2000
**Then** `tree_sitter_analyzer/mcp/` files are included in the result

#### Scenario: Configurable file limit
**Given** `_MAX_FILES` default is 2000
**When** the indexer discovers files
**Then** up to 2000 files are returned, with source files prioritized

### Requirement 2: Test File Classification
**ID**: PI-002
**Priority**: P1 High

The indexer must be able to classify files as test files vs source files.

#### Scenario: Test file by name prefix
**Given** a file named `test_foo.py`
**When** `is_test_file` is called
**Then** returns True

#### Scenario: Test file by name suffix
**Given** a file named `foo_test.py`
**When** `is_test_file` is called
**Then** returns True

#### Scenario: Test file by directory
**Given** a file at `tests/unit/test_bar.py`
**When** `is_test_file` is called
**Then** returns True

#### Scenario: conftest is a test file
**Given** a file named `conftest.py`
**When** `is_test_file` is called
**Then** returns True

#### Scenario: Source file
**Given** a file named `analysis_engine.py` in `tree_sitter_analyzer/core/`
**When** `is_test_file` is called
**Then** returns False

---

## Acceptance Criteria

- [ ] `_MAX_FILES` increased to 2000
- [ ] Two-phase discovery: source files collected before test files
- [ ] `is_test_file(file_path)` static method available on ProjectIndexer
- [ ] `get_test_files()` and `get_source_files()` methods available
- [ ] All files under `tree_sitter_analyzer/mcp/` are indexed for projects within the limit
