# Requirements - Plugin Contract Alignment

## Current State Analysis
The system supports 17+ languages via a plugin architecture. Each plugin must implement the `LanguagePlugin` protocol defined in `tree_sitter_analyzer/plugins/base.py`.

## Problem Identification
- As the project evolves, the base `LanguagePlugin` interface might have changed.
- Older plugins might not implement newer methods (e.g., `cleanup`, `get_language_name` vs `get_name`).
- Inconsistent method signatures across plugins make the unified engine logic more complex (requiring `hasattr` checks).

## Goals & Objectives
- Define the "Gold Standard" contract based on the current `LanguagePlugin` class.
- Audit all 17 language plugins to find deviations from this contract.
- Automatically fix missing methods or align method names to ensure 100% compliance.
- Eliminate "defensive programming" in the core engine by guaranteeing plugin structure.

## Non-functional Requirements
- **Strict Typing**: Ensure all implemented methods follow the type hints of the base class.
- **Verification**: Use `tree-sitter-analyzer` (TOON output) to verify the fix.
