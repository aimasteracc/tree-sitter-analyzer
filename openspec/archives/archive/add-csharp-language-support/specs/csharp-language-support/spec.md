# Specification: C# Language Support

**Capability:** csharp-language-support  
**Status:** Draft  
**Related Change:** add-csharp-language-support

---

## Overview

This specification defines the requirements for comprehensive C# language support in tree-sitter-analyzer, enabling analysis of C# source files through the existing plugin architecture.

---

## ADDED Requirements

### Requirement: C# Plugin Implementation

**ID:** CSHARP-001  
**Priority:** Critical  
**Type:** Functional

The system SHALL provide a C# language plugin that implements the `LanguagePlugin` interface and supports analysis of C# source files.

#### Scenario: C# Plugin Loads Successfully

**Given** the tree-sitter-analyzer system is initialized  
**When** the PluginManager discovers plugins  
**Then** the C# plugin SHALL be loaded successfully  
**And** the plugin SHALL be registered for `.cs` file extensions  
**And** the plugin SHALL return "csharp" as the language name

**Acceptance Criteria:**
- C# plugin class instantiates without errors
- Plugin is discoverable via entry points
- Plugin responds to `.cs` file extension
- No impact on other language plugins

---

### Requirement: C# Element Extraction

**ID:** CSHARP-002  
**Priority:** Critical  
**Type:** Functional

The system SHALL extract C# code elements including classes, interfaces, methods, properties, fields, and using directives.

#### Scenario: Extract C# Classes

**Given** a C# file containing class declarations  
**When** the analyzer processes the file  
**Then** all classes SHALL be extracted as `Class` elements  
**And** each class SHALL include name, namespace, modifiers, visibility  
**And** each class SHALL include base class and implemented interfaces  
**And** each class SHALL include attributes (C# annotations)

**Acceptance Criteria:**
- Classes extracted with correct names
- Namespaces resolved correctly
- Modifiers (public, private, static, etc.) extracted
- Base classes and interfaces identified
- Attributes associated with classes

#### Scenario: Extract C# Methods

**Given** a C# file containing method declarations  
**When** the analyzer processes the file  
**Then** all methods SHALL be extracted as `Function` elements  
**And** each method SHALL include name, parameters, return type  
**And** each method SHALL include modifiers and visibility  
**And** each method SHALL include attributes  
**And** async methods SHALL be marked as async

**Acceptance Criteria:**
- Methods extracted with correct signatures
- Parameters extracted with types
- Return types extracted correctly
- Async methods detected
- Attributes associated with methods

#### Scenario: Extract C# Properties

**Given** a C# file containing property declarations  
**When** the analyzer processes the file  
**Then** all properties SHALL be extracted as `Function` elements with `is_property=True`  
**And** auto-properties SHALL be detected  
**And** computed properties SHALL be detected  
**And** property types SHALL be extracted  
**And** getter/setter presence SHALL be recorded

**Acceptance Criteria:**
- Properties extracted correctly
- Auto-properties detected
- Computed properties detected
- Property types correct
- Getter/setter information accurate

#### Scenario: Extract C# Fields

**Given** a C# file containing field declarations  
**When** the analyzer processes the file  
**Then** all fields SHALL be extracted as `Variable` elements  
**And** constants SHALL be marked with `is_constant=True`  
**And** readonly fields SHALL be marked appropriately  
**And** field types SHALL be extracted

**Acceptance Criteria:**
- Fields extracted with correct names and types
- Constants detected
- Readonly fields detected
- Visibility correct

#### Scenario: Extract Using Directives

**Given** a C# file containing using directives  
**When** the analyzer processes the file  
**Then** all using directives SHALL be extracted as `Import` elements  
**And** namespace imports SHALL be recorded  
**And** static using directives SHALL be detected

**Acceptance Criteria:**
- Using directives extracted
- Namespace imports correct
- Static using detected

---

### Requirement: C# Modern Features Support

**ID:** CSHARP-003  
**Priority:** High  
**Type:** Functional

The system SHALL support modern C# language features including records, nullable reference types, and pattern matching.

#### Scenario: Extract C# Records

**Given** a C# file containing record declarations (C# 9+)  
**When** the analyzer processes the file  
**Then** all records SHALL be extracted as `Class` elements with `class_type="record"`  
**And** primary constructor parameters SHALL be extracted as properties  
**And** record inheritance SHALL be detected

**Acceptance Criteria:**
- Records extracted correctly
- Record type identified
- Primary constructor parameters extracted
- Inheritance detected

#### Scenario: Handle Nullable Reference Types

**Given** a C# file using nullable reference types (C# 8+)  
**When** the analyzer processes the file  
**Then** nullable types SHALL preserve the `?` annotation  
**And** non-nullable types SHALL be distinguished from nullable types

**Acceptance Criteria:**
- Nullable types preserve `?` in type information
- Type information accurate

---

### Requirement: C# Interface Extraction

**ID:** CSHARP-004  
**Priority:** High  
**Type:** Functional

The system SHALL extract C# interfaces, enums, structs, and delegates.

#### Scenario: Extract C# Interfaces

**Given** a C# file containing interface declarations  
**When** the analyzer processes the file  
**Then** all interfaces SHALL be extracted as `Class` elements with `class_type="interface"`  
**And** interface methods SHALL be extracted  
**And** interface properties SHALL be extracted

**Acceptance Criteria:**
- Interfaces extracted correctly
- Interface type identified
- Interface members extracted

#### Scenario: Extract C# Enums

**Given** a C# file containing enum declarations  
**When** the analyzer processes the file  
**Then** all enums SHALL be extracted as `Class` elements with `class_type="enum"`  
**And** enum values SHALL be extracted

**Acceptance Criteria:**
- Enums extracted correctly
- Enum type identified
- Enum values extracted

#### Scenario: Extract C# Structs

**Given** a C# file containing struct declarations  
**When** the analyzer processes the file  
**Then** all structs SHALL be extracted as `Class` elements with `class_type="struct"`  
**And** struct members SHALL be extracted

**Acceptance Criteria:**
- Structs extracted correctly
- Struct type identified
- Struct members extracted

---

### Requirement: C# Attribute Extraction

**ID:** CSHARP-005  
**Priority:** High  
**Type:** Functional

The system SHALL extract C# attributes (annotations) and associate them with their target elements.

#### Scenario: Extract Method Attributes

**Given** a C# file containing methods with attributes  
**When** the analyzer processes the file  
**Then** all attributes SHALL be extracted  
**And** attributes SHALL be associated with their target methods  
**And** attribute arguments SHALL be preserved

**Acceptance Criteria:**
- Attributes extracted correctly
- Attributes associated with correct elements
- Attribute arguments preserved

---

### Requirement: C# CLI Integration

**ID:** CSHARP-006  
**Priority:** Critical  
**Type:** Functional

The system SHALL support C# file analysis through the command-line interface.

#### Scenario: Analyze C# File via CLI

**Given** a valid C# source file  
**When** the user runs `tree-sitter-analyzer <file>.cs`  
**Then** the file SHALL be analyzed successfully  
**And** the output SHALL include all extracted C# elements  
**And** the output SHALL be formatted correctly

**Acceptance Criteria:**
- CLI accepts `.cs` files
- Analysis completes successfully
- Output includes all element types
- Format options work (full, compact, csv)

---

### Requirement: C# MCP Integration

**ID:** CSHARP-007  
**Priority:** High  
**Type:** Functional

The system SHALL support C# file analysis through MCP tools.

#### Scenario: Analyze C# File via MCP

**Given** a valid C# source file  
**When** the MCP tool `analyze_code_structure` is called with the C# file  
**Then** the file SHALL be analyzed successfully  
**And** the result SHALL include all extracted C# elements  
**And** the result SHALL be formatted as JSON

**Acceptance Criteria:**
- MCP tools accept `.cs` files
- Analysis completes successfully
- JSON output correct
- All element types included

---

### Requirement: C# Error Handling

**ID:** CSHARP-008  
**Priority:** High  
**Type:** Non-Functional

The system SHALL handle C# analysis errors gracefully without affecting other language plugins.

#### Scenario: Handle Missing tree-sitter-c-sharp

**Given** the tree-sitter-c-sharp package is not installed  
**When** the C# plugin attempts to load  
**Then** the plugin SHALL load but return None from `get_tree_sitter_language()`  
**And** C# file analysis SHALL fail with a clear error message  
**And** other language plugins SHALL continue to work normally

**Acceptance Criteria:**
- Plugin loads without crashing
- Clear error message displayed
- Other plugins unaffected

#### Scenario: Handle Invalid C# Syntax

**Given** a C# file with invalid syntax  
**When** the analyzer processes the file  
**Then** the analysis SHALL not crash  
**And** an error message SHALL be returned  
**And** partial results MAY be returned if possible

**Acceptance Criteria:**
- No crashes on invalid syntax
- Error message clear
- Graceful degradation

---

### Requirement: C# Performance

**ID:** CSHARP-009  
**Priority:** Medium  
**Type:** Non-Functional

The system SHALL analyze C# files efficiently without performance degradation.

#### Scenario: Analyze Large C# File

**Given** a C# file with >1000 lines  
**When** the analyzer processes the file  
**Then** the analysis SHALL complete in reasonable time (<5 seconds)  
**And** memory usage SHALL be reasonable (<500MB)

**Acceptance Criteria:**
- Large files analyzed efficiently
- No memory leaks
- Performance comparable to other languages

---

### Requirement: C# Test Coverage

**ID:** CSHARP-010  
**Priority:** Critical  
**Type:** Quality

The C# plugin SHALL have comprehensive test coverage.

#### Scenario: C# Plugin Test Coverage

**Given** the C# plugin implementation  
**When** test coverage is measured  
**Then** the coverage SHALL be ≥80%  
**And** all element extraction methods SHALL be tested  
**And** edge cases SHALL be tested

**Acceptance Criteria:**
- Test coverage ≥80%
- All methods tested
- Edge cases covered
- Integration tests pass

---

### Requirement: C# Isolation

**ID:** CSHARP-011  
**Priority:** Critical  
**Type:** Non-Functional

The C# plugin SHALL be completely isolated from other language plugins.

#### Scenario: C# Plugin Isolation

**Given** the C# plugin is loaded  
**When** the plugin manager loads all plugins  
**Then** the C# plugin SHALL not affect other language plugins  
**And** other language plugins SHALL not affect the C# plugin  
**And** no shared state SHALL exist between plugins

**Acceptance Criteria:**
- No cross-plugin dependencies
- No shared state
- Independent loading
- No regression in other plugins

---

### Requirement: C# Type Safety

**ID:** CSHARP-012  
**Priority:** Critical  
**Type:** Quality

The C# plugin SHALL be fully type-safe with mypy compliance.

#### Scenario: C# Plugin Type Safety

**Given** the C# plugin implementation  
**When** mypy type checking is run  
**Then** there SHALL be zero type errors  
**And** all functions SHALL have type hints  
**And** all return types SHALL be annotated

**Acceptance Criteria:**
- Mypy passes with zero errors
- All functions type-hinted
- Return types annotated
- No `Any` types where avoidable

---

### Requirement: C# Code Quality

**ID:** CSHARP-013  
**Priority:** Critical  
**Type:** Quality

The C# plugin SHALL meet all code quality standards.

#### Scenario: C# Plugin Code Quality

**Given** the C# plugin implementation  
**When** code quality checks are run  
**Then** ruff SHALL pass with zero errors  
**And** black SHALL pass with zero errors  
**And** isort SHALL pass with zero errors

**Acceptance Criteria:**
- Ruff passes
- Black passes
- Isort passes
- No linting errors

---

### Requirement: C# Documentation

**ID:** CSHARP-014  
**Priority:** High  
**Type:** Documentation

The C# plugin SHALL be fully documented.

#### Scenario: C# Plugin Documentation

**Given** the C# plugin implementation  
**When** documentation is reviewed  
**Then** all public methods SHALL have docstrings  
**And** README SHALL mention C# support  
**And** CHANGELOG SHALL document C# addition  
**And** sample C# files SHALL be provided

**Acceptance Criteria:**
- All methods documented
- README updated
- CHANGELOG updated
- Sample files provided

---

## Dependencies

### Internal Dependencies
- Plugin architecture (existing)
- LanguagePlugin interface (existing)
- ElementExtractor interface (existing)
- PluginManager (existing)

### External Dependencies
- tree-sitter-c-sharp (new, optional)
- tree-sitter>=0.25.0 (existing)

---

## Acceptance Criteria Summary

The C# language support SHALL be considered complete when:

1. ✅ All requirements (CSHARP-001 through CSHARP-014) are met
2. ✅ All scenarios pass acceptance criteria
3. ✅ Test coverage ≥80%
4. ✅ Mypy passes with zero errors
5. ✅ Ruff passes with zero errors
6. ✅ All tests pass
7. ✅ No regression in existing functionality
8. ✅ Documentation complete
9. ✅ Sample files provided
10. ✅ OpenSpec validation passes

---

## Related Specifications

- Plugin Architecture: `docs/ja/specifications/06_言語プラグイン仕様.md`
- Element Model: `tree_sitter_analyzer/models.py`
- SQL Language Support: `openspec/changes/archive/add-sql-language-support/specs/`

---

## Notes

- C# is a complex language with many modern features
- Initial implementation focuses on core features
- Future enhancements can add LINQ analysis, DI pattern detection, etc.
- C# attributes are similar to Java annotations
- C# properties are first-class language features (not just getter/setter methods)
- C# has records (C# 9+) which are immutable data classes
- C# has nullable reference types (C# 8+) which should be preserved in type information

