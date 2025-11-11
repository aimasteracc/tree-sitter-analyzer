# Specification: Ruby Language Support

**Capability:** ruby-language-support  
**Status:** Draft  
**Related Change:** add-php-ruby-language-support

---

## Overview

This specification defines the requirements for comprehensive Ruby language support in tree-sitter-analyzer, enabling analysis of Ruby source files through the existing plugin architecture.

---

## ADDED Requirements

### Requirement: Ruby Plugin Implementation

**ID:** RUBY-001  
**Priority:** Critical  
**Type:** Functional

The system SHALL provide a Ruby language plugin that implements the `LanguagePlugin` interface and supports analysis of Ruby source files.

#### Scenario: Ruby Plugin Loads Successfully

**Given** the tree-sitter-analyzer system is initialized  
**When** the PluginManager discovers plugins  
**Then** the Ruby plugin SHALL be loaded successfully  
**And** the plugin SHALL be registered for `.rb` file extensions  
**And** the plugin SHALL return "ruby" as the language name

**Acceptance Criteria:**
- Ruby plugin class instantiates without errors
- Plugin is discoverable via entry points
- Plugin responds to `.rb` file extension
- No impact on other language plugins

---

### Requirement: Ruby Element Extraction

**ID:** RUBY-002  
**Priority:** Critical  
**Type:** Functional

The system SHALL extract Ruby code elements including classes, modules, methods, constants, variables, and require statements.

#### Scenario: Extract Ruby Classes

**Given** a Ruby file containing class declarations  
**When** the analyzer processes the file  
**Then** all classes SHALL be extracted as `Class` elements  
**And** each class SHALL include name and inheritance  
**And** included modules SHALL be tracked

**Acceptance Criteria:**
- Classes extracted with correct names
- Inheritance detected
- Module inclusion tracked

#### Scenario: Extract Ruby Modules

**Given** a Ruby file containing module declarations  
**When** the analyzer processes the file  
**Then** all modules SHALL be extracted as `Class` elements with `is_module=True`  
**And** each module SHALL include name  
**And** module inclusion methods (include, extend, prepend) SHALL be detected

**Acceptance Criteria:**
- Modules extracted correctly
- Marked as module type
- Inclusion methods detected

#### Scenario: Extract Ruby Instance Methods

**Given** a Ruby file containing instance method declarations  
**When** the analyzer processes the file  
**Then** all instance methods SHALL be extracted as `Function` elements  
**And** each method SHALL include name and parameters  
**And** method visibility SHALL be determined

**Acceptance Criteria:**
- Instance methods extracted correctly
- Parameters extracted
- Visibility (public, private, protected) determined

#### Scenario: Extract Ruby Class Methods

**Given** a Ruby file containing class method declarations  
**When** the analyzer processes the file  
**Then** all class methods SHALL be extracted as `Function` elements with `is_class_method=True`  
**And** both `def self.method` and `class << self` styles SHALL be supported

**Acceptance Criteria:**
- Class methods extracted correctly
- Both definition styles supported
- Marked as class methods

#### Scenario: Extract Ruby Attribute Shortcuts

**Given** a Ruby file containing attr_accessor, attr_reader, or attr_writer declarations  
**When** the analyzer processes the file  
**Then** all attribute shortcuts SHALL be extracted as `Function` elements with `is_property=True`  
**And** read/write permissions SHALL be determined

**Acceptance Criteria:**
- Attribute shortcuts extracted
- Permissions determined correctly
- Marked as properties

#### Scenario: Extract Ruby Constants

**Given** a Ruby file containing constant declarations  
**When** the analyzer processes the file  
**Then** all constants SHALL be extracted as `Variable` elements with `is_constant=True`  
**And** constants SHALL be associated with their class/module

**Acceptance Criteria:**
- Constants extracted correctly
- Associated with correct scope
- Marked as constants

#### Scenario: Extract Ruby Instance Variables

**Given** a Ruby file containing instance variable declarations  
**When** the analyzer processes the file  
**Then** all instance variables SHALL be extracted as `Variable` elements with `is_instance_variable=True`  
**And** variables SHALL be associated with their class

**Acceptance Criteria:**
- Instance variables extracted
- Associated with correct class
- Marked as instance variables

#### Scenario: Extract Ruby Class Variables

**Given** a Ruby file containing class variable declarations  
**When** the analyzer processes the file  
**Then** all class variables SHALL be extracted as `Variable` elements with `is_class_variable=True`  
**And** variables SHALL be associated with their class

**Acceptance Criteria:**
- Class variables extracted
- Associated with correct class
- Marked as class variables

#### Scenario: Extract Ruby Require Statements

**Given** a Ruby file containing require or require_relative statements  
**When** the analyzer processes the file  
**Then** all require statements SHALL be extracted as `Import` elements  
**And** load statements SHALL also be extracted

**Acceptance Criteria:**
- Require statements extracted
- require_relative supported
- load statements included

---

### Requirement: Ruby Modern Features Support

**ID:** RUBY-003  
**Priority:** High  
**Type:** Functional

The system SHALL support modern Ruby features including blocks, procs, lambdas, and symbols.

#### Scenario: Detect Ruby Blocks

**Given** a Ruby file containing block declarations  
**When** the analyzer processes the file  
**Then** blocks SHALL be detected  
**And** both `do...end` and `{...}` styles SHALL be supported

**Acceptance Criteria:**
- Blocks detected
- Both styles supported
- Associated with methods

#### Scenario: Detect Ruby Procs and Lambdas

**Given** a Ruby file containing proc or lambda declarations  
**When** the analyzer processes the file  
**Then** procs and lambdas SHALL be detected  
**And** marked appropriately

**Acceptance Criteria:**
- Procs detected
- Lambdas detected
- Marked correctly

#### Scenario: Handle Ruby Symbols

**Given** a Ruby file containing symbol usage  
**When** the analyzer processes the file  
**Then** symbols SHALL be handled correctly in the AST

**Acceptance Criteria:**
- Symbols processed correctly
- No parsing errors

---

### Requirement: Ruby Formatter Support

**ID:** RUBY-004  
**Priority:** High  
**Type:** Functional

The system SHALL provide dedicated formatters for Ruby code output in Full, Compact, and CSV formats.

#### Scenario: Format Ruby Code in Full Format

**Given** Ruby elements have been extracted  
**When** the Full formatter is applied  
**Then** the output SHALL include all Ruby-specific information  
**And** modules SHALL be clearly marked  
**And** attribute shortcuts SHALL be displayed  
**And** class methods SHALL be indicated

**Acceptance Criteria:**
- Full format output correct
- Ruby-specific features displayed
- Readable and complete

#### Scenario: Format Ruby Code in Compact Format

**Given** Ruby elements have been extracted  
**When** the Compact formatter is applied  
**Then** the output SHALL provide a concise summary  
**And** key Ruby features SHALL be visible

**Acceptance Criteria:**
- Compact format output correct
- Essential information preserved
- Concise presentation

#### Scenario: Format Ruby Code in CSV Format

**Given** Ruby elements have been extracted  
**When** the CSV formatter is applied  
**Then** the output SHALL be valid CSV  
**And** all Ruby elements SHALL be represented

**Acceptance Criteria:**
- Valid CSV output
- All elements included
- Parseable format

---

### Requirement: Ruby Query Support

**ID:** RUBY-005  
**Priority:** High  
**Type:** Functional

The system SHALL provide tree-sitter queries for efficient Ruby element extraction.

#### Scenario: Query Ruby Elements

**Given** a Ruby AST is available  
**When** tree-sitter queries are executed  
**Then** all Ruby constructs SHALL be queryable  
**And** queries SHALL be efficient

**Acceptance Criteria:**
- Queries work correctly
- All constructs covered
- Performance acceptable

---

### Requirement: Ruby Golden Master Testing

**ID:** RUBY-006  
**Priority:** Medium  
**Type:** Quality

The system SHALL include golden master tests for Ruby code to ensure output consistency.

#### Scenario: Generate Ruby Golden Masters

**Given** sample Ruby files exist  
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

