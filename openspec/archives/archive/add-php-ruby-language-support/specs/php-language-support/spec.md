# Specification: PHP Language Support

**Capability:** php-language-support  
**Status:** Draft  
**Related Change:** add-php-ruby-language-support

---

## Overview

This specification defines the requirements for comprehensive PHP language support in tree-sitter-analyzer, enabling analysis of PHP source files through the existing plugin architecture.

---

## ADDED Requirements

### Requirement: PHP Plugin Implementation

**ID:** PHP-001  
**Priority:** Critical  
**Type:** Functional

The system SHALL provide a PHP language plugin that implements the `LanguagePlugin` interface and supports analysis of PHP source files.

#### Scenario: PHP Plugin Loads Successfully

**Given** the tree-sitter-analyzer system is initialized  
**When** the PluginManager discovers plugins  
**Then** the PHP plugin SHALL be loaded successfully  
**And** the plugin SHALL be registered for `.php` file extensions  
**And** the plugin SHALL return "php" as the language name

**Acceptance Criteria:**
- PHP plugin class instantiates without errors
- Plugin is discoverable via entry points
- Plugin responds to `.php` file extension
- No impact on other language plugins

---

### Requirement: PHP Element Extraction

**ID:** PHP-002  
**Priority:** Critical  
**Type:** Functional

The system SHALL extract PHP code elements including classes, interfaces, traits, methods, functions, properties, and use statements.

#### Scenario: Extract PHP Classes

**Given** a PHP file containing class declarations  
**When** the analyzer processes the file  
**Then** all classes SHALL be extracted as `Class` elements  
**And** each class SHALL include name, namespace, modifiers, visibility  
**And** each class SHALL include extends and implements clauses  
**And** each class SHALL include attributes (PHP 8+)

**Acceptance Criteria:**
- Classes extracted with correct names
- Namespaces resolved correctly
- Modifiers (public, private, protected, static, final, abstract) extracted
- Base classes and interfaces identified
- Attributes associated with classes

#### Scenario: Extract PHP Interfaces

**Given** a PHP file containing interface declarations  
**When** the analyzer processes the file  
**Then** all interfaces SHALL be extracted as `Class` elements with `is_interface=True`  
**And** each interface SHALL include name and namespace  
**And** each interface SHALL include extended interfaces

**Acceptance Criteria:**
- Interfaces extracted correctly
- Interface inheritance detected
- Marked as interface type

#### Scenario: Extract PHP Traits

**Given** a PHP file containing trait declarations  
**When** the analyzer processes the file  
**Then** all traits SHALL be extracted as `Class` elements with `is_trait=True`  
**And** each trait SHALL include name and namespace  
**And** trait usage in classes SHALL be tracked

**Acceptance Criteria:**
- Traits extracted correctly
- Trait usage detected
- Marked as trait type

#### Scenario: Extract PHP Enums (PHP 8.1+)

**Given** a PHP file containing enum declarations  
**When** the analyzer processes the file  
**Then** all enums SHALL be extracted as `Class` elements with `is_enum=True`  
**And** each enum SHALL include name and namespace  
**And** enum cases SHALL be extracted

**Acceptance Criteria:**
- Enums extracted correctly
- Enum cases detected
- Marked as enum type

#### Scenario: Extract PHP Methods

**Given** a PHP file containing method declarations  
**When** the analyzer processes the file  
**Then** all methods SHALL be extracted as `Function` elements  
**And** each method SHALL include name, parameters, return type  
**And** each method SHALL include modifiers and visibility  
**And** each method SHALL include attributes (PHP 8+)  
**And** magic methods SHALL be detected

**Acceptance Criteria:**
- Methods extracted with correct signatures
- Parameters extracted with types
- Return types extracted correctly
- Magic methods (__construct, __get, etc.) detected
- Attributes associated with methods

#### Scenario: Extract PHP Functions

**Given** a PHP file containing function declarations  
**When** the analyzer processes the file  
**Then** all functions SHALL be extracted as `Function` elements  
**And** each function SHALL include name, parameters, return type  
**And** namespaced functions SHALL include namespace

**Acceptance Criteria:**
- Functions extracted correctly
- Global and namespaced functions supported
- Function signatures complete

#### Scenario: Extract PHP Properties

**Given** a PHP file containing property declarations  
**When** the analyzer processes the file  
**Then** all properties SHALL be extracted as `Variable` elements  
**And** typed properties (PHP 7.4+) SHALL include type information  
**And** property modifiers SHALL be extracted  
**And** readonly properties SHALL be detected

**Acceptance Criteria:**
- Properties extracted correctly
- Typed properties detected
- Modifiers extracted
- Readonly properties marked

#### Scenario: Extract PHP Constants

**Given** a PHP file containing constant declarations  
**When** the analyzer processes the file  
**Then** all constants SHALL be extracted as `Variable` elements with `is_constant=True`  
**And** class constants SHALL be associated with their class  
**And** global constants SHALL be extracted

**Acceptance Criteria:**
- Constants extracted correctly
- Class constants associated
- Global constants detected

#### Scenario: Extract PHP Use Statements

**Given** a PHP file containing use statements  
**When** the analyzer processes the file  
**Then** all use statements SHALL be extracted as `Import` elements  
**And** namespace imports SHALL be extracted  
**And** function imports (`use function`) SHALL be extracted  
**And** constant imports (`use const`) SHALL be extracted  
**And** aliases SHALL be recorded

**Acceptance Criteria:**
- Use statements extracted correctly
- Function and constant imports detected
- Aliases preserved

---

### Requirement: PHP Modern Features Support

**ID:** PHP-003  
**Priority:** High  
**Type:** Functional

The system SHALL support modern PHP features including PHP 8+ attributes, typed properties, enums, and union types.

#### Scenario: Extract PHP 8+ Attributes

**Given** a PHP file containing attribute declarations  
**When** the analyzer processes the file  
**Then** all attributes SHALL be extracted and associated with their target elements  
**And** attribute arguments SHALL be preserved

**Acceptance Criteria:**
- Attributes extracted correctly
- Associated with correct elements
- Arguments preserved

#### Scenario: Handle Union Types

**Given** a PHP file containing union type declarations  
**When** the analyzer processes the file  
**Then** union types SHALL be extracted correctly  
**And** all type components SHALL be preserved

**Acceptance Criteria:**
- Union types extracted
- Type components correct

---

### Requirement: PHP Formatter Support

**ID:** PHP-004  
**Priority:** High  
**Type:** Functional

The system SHALL provide dedicated formatters for PHP code output in Full, Compact, and CSV formats.

#### Scenario: Format PHP Code in Full Format

**Given** PHP elements have been extracted  
**When** the Full formatter is applied  
**Then** the output SHALL include all PHP-specific information  
**And** traits SHALL be clearly marked  
**And** attributes SHALL be displayed  
**And** magic methods SHALL be indicated

**Acceptance Criteria:**
- Full format output correct
- PHP-specific features displayed
- Readable and complete

#### Scenario: Format PHP Code in Compact Format

**Given** PHP elements have been extracted  
**When** the Compact formatter is applied  
**Then** the output SHALL provide a concise summary  
**And** key PHP features SHALL be visible

**Acceptance Criteria:**
- Compact format output correct
- Essential information preserved
- Concise presentation

#### Scenario: Format PHP Code in CSV Format

**Given** PHP elements have been extracted  
**When** the CSV formatter is applied  
**Then** the output SHALL be valid CSV  
**And** all PHP elements SHALL be represented

**Acceptance Criteria:**
- Valid CSV output
- All elements included
- Parseable format

---

### Requirement: PHP Query Support

**ID:** PHP-005  
**Priority:** High  
**Type:** Functional

The system SHALL provide tree-sitter queries for efficient PHP element extraction.

#### Scenario: Query PHP Elements

**Given** a PHP AST is available  
**When** tree-sitter queries are executed  
**Then** all PHP constructs SHALL be queryable  
**And** queries SHALL be efficient

**Acceptance Criteria:**
- Queries work correctly
- All constructs covered
- Performance acceptable

---

### Requirement: PHP Golden Master Testing

**ID:** PHP-006  
**Priority:** Medium  
**Type:** Quality

The system SHALL include golden master tests for PHP code to ensure output consistency.

#### Scenario: Generate PHP Golden Masters

**Given** sample PHP files exist  
**When** golden masters are generated  
**Then** output SHALL be consistent across runs  
**And** all formats SHALL have golden masters

**Acceptance Criteria:**
- Golden masters generated
- Consistency verified
- All formats covered

---

## MODIFIED Requirements

None.

---

## REMOVED Requirements

None.

