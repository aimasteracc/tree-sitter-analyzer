# Requirements Document: C/C++ Language Support

## Introduction

Adds C and C++ language plugins to Tree-sitter Analyzer, covering functions, types, variables, and imports as core elements. Integrates into the existing plugin architecture and CLI/MCP workflows. Depends on `tree-sitter-c` and `tree-sitter-cpp`, registered as discoverable plugins via entry points.

## Terminology

- **CPlugin/CppPlugin**: Language plugin classes for C and C++
- **CElementExtractor/CppElementExtractor**: AST traversal classes extracting code elements
- **ElementExtractor**: Base class for element extractors
- **CodeElement**: Unified element data model base class
- **Function/Class/Variable/Import**: Core element models
- **BFS (Breadth-First Search)**: Algorithm used for identifier extraction to ensure correct name resolution
- **Translation Unit**: Top-level AST node representing the entire source file

## Requirements

### Requirement 1: C Language Support

**User Story:** As a developer, I want to analyze C source files, so that I can understand the structure of my C codebase.

#### Acceptance Criteria

1. WHEN a user provides a `.c` or `.h` file THEN the CPlugin SHALL parse the file and extract functions, types, and variables
2. WHEN the C file contains function definitions THEN the CPlugin SHALL extract name, parameters, return type, line range, and raw text
3. WHEN the C file contains `struct`/`union`/`enum` definitions THEN the CPlugin SHALL extract only top-level definitions with bodies (not type references)
4. WHEN the C file contains global variable declarations THEN the CPlugin SHALL extract them (excluding local variables inside function bodies)
5. WHEN the C file contains `#include` directives THEN the CPlugin SHALL extract them as import elements
6. WHEN tree-sitter-c is unavailable THEN the CPlugin SHALL gracefully degrade with a diagnosable error message

### Requirement 2: C++ Language Support

**User Story:** As a developer, I want to analyze C++ source files, so that I can understand the structure of my C++ codebase.

#### Acceptance Criteria

1. WHEN a user provides a `.cpp`/`.cxx`/`.cc`/`.hpp`/`.hxx`/`.hh` file THEN the CppPlugin SHALL parse and extract functions, types, and variables
2. WHEN the C++ file contains function/method definitions THEN the CppPlugin SHALL extract them including constructors, destructors, and operator overloads
3. WHEN the C++ file contains `class`/`struct` definitions THEN the CppPlugin SHALL extract only top-level definitions with bodies
4. WHEN the C++ file contains global/namespace-level variables THEN the CppPlugin SHALL extract them (excluding local variables and class members)
5. WHEN the C++ file contains imports THEN the CppPlugin SHALL extract `#include`, `using` declarations, and `namespace` names
6. WHEN tree-sitter-cpp is unavailable THEN the CppPlugin SHALL gracefully degrade with a diagnosable error message

### Requirement 3: Integration

**User Story:** As a developer, I want the C/C++ plugins to integrate seamlessly with the existing analyzer, so that I can use them alongside other language plugins.

#### Acceptance Criteria

1. WHEN the CPlugin/CppPlugin is loaded THEN the plugin manager SHALL register them automatically via entry points
2. WHEN analyzing a C/C++ file THEN the analyzer SHALL automatically select the appropriate plugin based on file extension
3. WHEN the C/C++ plugin fails to parse a file THEN the analyzer SHALL continue processing other files without crashing
4. WHEN tree-sitter-c/cpp is not installed THEN the respective plugin SHALL gracefully degrade and log a warning
5. WHEN the C/C++ plugins are used THEN other language plugins SHALL remain unaffected
6. WHEN the plugins are registered THEN query modules (`queries/c.py` and `queries/cpp.py`) SHALL be created for tree-sitter queries
7. WHEN formatting output THEN the plugins SHALL use the legacy formatting strategy compatible with existing formats (table/compact/full/csv/json)

### Requirement 4: Output Consistency and Robustness

**User Story:** As a developer, I want consistent and accurate output from C/C++ analysis, so that I can process results reliably.

#### Acceptance Criteria

1. WHEN extracting elements THEN the plugin SHALL provide accurate `start_line`, `end_line`, and `raw_text` for each element
2. WHEN parsing fails THEN the plugin SHALL return `AnalysisResult.success=False` with `error_message`
3. WHEN analyzing multiple files THEN the plugin SHALL support batch analysis with correct node count statistics
4. WHEN extracting function/type names THEN the plugin SHALL use BFS to ensure correct name resolution (not parameter names)

### Requirement 5: Query Support

**User Story:** As a developer, I want to query C/C++ code structures, so that I can find specific code patterns.

#### Acceptance Criteria

1. WHEN executing tree-sitter queries THEN the plugins SHALL support standard query syntax via query modules
2. WHEN querying for functions THEN the plugins SHALL return matching function definitions
3. WHEN querying for types (struct/class/enum) THEN the plugins SHALL return matching type definitions
4. WHEN querying for variables THEN the plugins SHALL return matching variable declarations
5. WHEN querying for imports THEN the plugins SHALL return matching include/using directives
6. WHEN no matches are found THEN the plugins SHALL return an empty result set
7. WHEN queries are accessed THEN common aliases (`functions`, `classes`, `variables`, `imports`) SHALL be available for cross-language compatibility

### Requirement 6: Sample Files

**User Story:** As a developer, I want comprehensive sample files for testing, so that I can verify the plugin handles all major language constructs.

#### Acceptance Criteria

1. WHEN testing C plugin THEN sample files SHALL include: preprocessor directives, enums, structs, unions, typedefs, function pointers, global/static/const variables, function definitions/declarations
2. WHEN testing C++ plugin THEN sample files SHALL include: namespaces, classes, structs, enum classes, templates, inheritance, virtual functions, operator overloading, lambdas, smart pointers

### Requirement 7: Testing

**User Story:** As a developer, I want the C/C++ plugins to be well-tested, so that I can rely on their correctness.

#### Acceptance Criteria

1. WHEN testing the plugins THEN unit tests SHALL verify plugin metadata and element extraction
2. WHEN testing the plugins THEN Golden Master tests SHALL ensure output stability
3. WHEN testing the plugins THEN integration tests SHALL verify analyze_file functionality
4. WHEN testing the plugins THEN tests SHALL pass consistently across multiple runs

