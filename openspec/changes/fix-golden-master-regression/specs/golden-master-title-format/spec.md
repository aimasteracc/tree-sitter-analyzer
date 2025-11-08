# Spec: Golden Master Title Format Correction

## Capability
**golden-master-title-format**

## Overview
Ensure all golden master test files use correct title formats based on language-specific conventions and actual code structure.

---

## MODIFIED Requirements

### Requirement: Title Generation for Java Files
**Priority**: HIGH  
**Status**: MODIFIED

Golden master outputs for Java files must use the correct title format based on file structure.

#### Scenario: Single Java class with package
**Given** a Java file with one class and package information  
**When** generating markdown output  
**Then** title must be `package.ClassName` format  
**Example**: `# com.example.service.BigService`

#### Scenario: Single Java class without package
**Given** a Java file with one class but no package  
**When** generating markdown output  
**Then** title must be just the class name  
**Example**: `# UserService`

#### Scenario: Multiple Java classes in one file
**Given** a Java file with multiple classes  
**When** generating markdown output  
**Then** title must be the filename (without .java extension)  
**Example**: `# Sample`

---

### Requirement: Title Generation for JavaScript/TypeScript Files
**Priority**: HIGH  
**Status**: MODIFIED

Golden master outputs for JavaScript/TypeScript files must not use package prefixes.

#### Scenario: JavaScript file with class
**Given** a JavaScript file with a class definition  
**When** generating markdown output  
**Then** title must be just the class name (no package prefix)  
**And** must not include "unknown" prefix  
**Example**: `# Animal` (NOT `# unknown.Animal`)

#### Scenario: TypeScript file with enum
**Given** a TypeScript file with an enum  
**When** generating markdown output  
**Then** title must be just the enum name  
**And** must not include "unknown" prefix  
**Example**: `# Color` (NOT `# unknown.Color`)

---

### Requirement: Title Generation for Python Files
**Priority**: HIGH  
**Status**: MODIFIED

Golden master outputs for Python files must use module format.

#### Scenario: Python module with classes
**Given** a Python file (module) with class definitions  
**When** generating markdown output  
**Then** title must use "Module: filename" format  
**Example**: `# Module: sample`

#### Scenario: Python module with functions only
**Given** a Python file with only function definitions  
**When** generating markdown output  
**Then** title must still use "Module: filename" format  
**Example**: `# Module: utilities`

---

## MODIFIED Requirements

### Requirement: Full Format Structure Preservation
**Priority**: HIGH  
**Status**: MODIFIED

Full format golden master files must maintain their original section structure and organization.

#### Scenario: Java BigService full format
**Given** the `java_bigservice_full.md` golden master  
**When** regenerating output  
**Then** must maintain all original sections (Package, Imports, Class Info, Fields, Constructor, Public Methods, Private Methods)  
**And** section headers must match original format  
**And** table structures must be identical  

#### Scenario: Python sample full format
**Given** the `python_sample_full.md` golden master  
**When** regenerating output  
**Then** must maintain module-level organization  
**And** must include Classes Overview, per-class sections, and Module Functions  

---

## ADDED Requirements

### Requirement: No "unknown" Package Prefix
**Priority**: HIGH  
**Status**: ADDED

Output formatters must never use "unknown" as a package prefix for languages that don't have packages.

#### Scenario: Missing package for Java
**Given** a Java file without package declaration  
**When** generating title  
**Then** use just the class name without prefix  
**And** do not add "unknown" prefix

#### Scenario: JavaScript without package concept
**Given** any JavaScript file  
**When** generating title  
**Then** use class name or filename  
**And** never add any package prefix including "unknown"

---

### Requirement: Language-Specific Title Logic
**Priority**: MEDIUM  
**Status**: ADDED

Title generation must be handled with language-specific logic.

#### Scenario: Title generation dispatch by language
**Given** analysis data for any supported language  
**When** `_generate_title()` is called  
**Then** must dispatch to language-specific helper method  
**And** each language must have documented title rules  
**And** fallback logic must handle unknown languages gracefully

---

### Requirement: Title Format Regression Testing
**Priority**: MEDIUM  
**Status**: ADDED

Automated tests must prevent title format regressions.

#### Scenario: Unit tests for title generation
**Given** `TableFormatter` class  
**When** running unit tests  
**Then** must have dedicated tests for `_generate_title()` method  
**And** must cover all supported languages  
**And** must test edge cases (no package, no classes, multiple classes)

#### Scenario: Golden master validation
**Given** any golden master file  
**When** running golden master tests  
**Then** title format must match language-specific rules  
**And** test failure must clearly indicate title mismatch  

---

## Validation Criteria

### Correctness
- [ ] All golden master files have titles matching their actual content
- [ ] No "unknown" prefixes in JavaScript/TypeScript files
- [ ] Java files use package.ClassName format when appropriate
- [ ] Python files use Module: name format

### Completeness
- [ ] All languages have documented title generation rules
- [ ] All edge cases are handled (no package, no classes, etc.)
- [ ] Golden masters cover all title format variations

### Testing
- [ ] Unit tests for `_generate_title()` pass
- [ ] All golden master tests pass
- [ ] Format validation tests pass
- [ ] No regressions in CSV/JSON formats

---

## Dependencies

- Depends on: `table_formatter.py` implementation
- Related to: `fix-analyze-code-structure-format-regression` change
- Tested by: Golden master test framework

---

## References

- Implementation: `tree_sitter_analyzer/table_formatter.py`
- Tests: `tests/golden_masters/`
- Documentation: `docs/format_specifications.md`

