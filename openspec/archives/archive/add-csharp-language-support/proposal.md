# Proposal: Add C# Language Support

**Change ID:** `add-csharp-language-support`  
**Type:** Feature Addition  
**Status:** Draft  
**Created:** 2025-11-09  
**Author:** AI Assistant

---

## Problem Statement

Tree-sitter Analyzer currently supports 8 languages (Python, Java, JavaScript, TypeScript, HTML, CSS, Markdown, SQL) but lacks support for C#, a critical language for .NET enterprise applications. C# files are commonly found in enterprise codebases for:

- ASP.NET Core web applications
- .NET microservices and APIs
- Desktop applications (WPF, WinForms)
- Unity game development
- Xamarin mobile applications
- Azure cloud services

The `language_detector.py` already recognizes `.cs` files (mapped to "csharp" with 0.9 confidence) but there is no corresponding plugin implementation to extract C# elements like classes, methods, properties, interfaces, and namespaces.

### Current Behavior

- C# files are detected by extension (`.cs`) and mapped to "csharp"
- No C# plugin exists in `tree_sitter_analyzer/languages/`
- C# files cannot be analyzed through the analyzer API
- MCP tools cannot process C# files
- No C#-specific element extraction (classes, methods, properties, etc.)

### Expected Behavior

After implementation:
- C# files (`.cs`) are fully supported with dedicated plugin
- C# elements are extracted: classes, interfaces, methods, properties, fields, enums, delegates
- C# analysis works through all interfaces: CLI, API, MCP
- C#-specific queries are available (e.g., `find_classes`, `find_methods`)
- Format output (Full, Compact, CSV) works for C# files
- Support for modern C# features (records, pattern matching, nullable reference types)

---

## Root Cause Analysis

### Missing Components

1. **No C# Plugin**: `tree_sitter_analyzer/languages/csharp_plugin.py` does not exist
2. **No C# Extractor**: No `CSharpElementExtractor` class to parse C# AST
3. **No tree-sitter-c-sharp Dependency**: `pyproject.toml` doesn't include `tree-sitter-c-sharp`
4. **No C# Tests**: Test suite has no C#-specific test cases
5. **No C# Sample Files**: No example C# files for testing and validation

### Architecture Alignment

The project uses a plugin-based architecture where:
- Each language has a `*_plugin.py` file in `languages/` directory
- Plugins implement `LanguagePlugin` interface
- Element extractors implement `ElementExtractor` interface
- Plugins are auto-discovered by `PluginManager`
- Tree-sitter languages are loaded via `get_tree_sitter_language()`

C# support requires implementing this same pattern.

---

## Proposed Solution

Implement comprehensive C# language support following the existing plugin architecture pattern, maintaining consistency with other language plugins (especially Java, as C# shares similar OOP concepts).

### Key Components

1. **C# Plugin** (`csharp_plugin.py`)
   - Implements `LanguagePlugin` interface
   - Supports `.cs` file extension
   - Loads `tree-sitter-c-sharp` language
   - Provides C#-specific element extraction

2. **C# Element Extractor** (`CSharpElementExtractor`)
   - Extracts classes (including partial classes)
   - Extracts interfaces
   - Extracts methods (including async methods, extension methods)
   - Extracts properties (auto-properties, computed properties)
   - Extracts fields and constants
   - Extracts enums and delegates
   - Extracts namespaces and using directives
   - Extracts attributes (C# annotations)
   - Extracts records (C# 9+)
   - Maps C# elements to unified element model (Class, Function, Variable, Import)

3. **Dependencies**
   - Add `tree-sitter-c-sharp` to `pyproject.toml`
   - Add C# to optional dependencies group
   - Verify compatibility with tree-sitter >=0.25.0

4. **Tests**
   - Unit tests for C# plugin
   - Integration tests for C# analysis
   - Test C# element extraction
   - Test format output for C#
   - Test modern C# features (records, nullable reference types)

5. **Sample Files**
   - Create example C# files for testing
   - Cover common C# patterns (ASP.NET, LINQ, async/await)
   - Include modern C# syntax

### Design Principles

- **Consistency**: Follow existing plugin patterns (Java, Python, TypeScript)
- **Type Safety**: Full mypy compliance with proper type hints
- **Code Quality**: Ruff compliance, no linting errors
- **Test Coverage**: >80% coverage for C# plugin
- **Backward Compatibility**: No breaking changes to existing APIs
- **Isolation**: C# plugin is completely independent of other language plugins
- **SOLID Principles**: Single Responsibility, Open/Closed, Dependency Inversion

---

## Impact Analysis

### Affected Components

- ✅ `tree_sitter_analyzer/languages/csharp_plugin.py` - New file
- ✅ `pyproject.toml` - Add tree-sitter-c-sharp dependency
- ✅ `tests/test_languages/test_csharp_plugin.py` - New test file
- ✅ `examples/Sample.cs` - New sample file
- ✅ `README.md` - Update supported languages list
- ❌ No breaking changes to existing code
- ❌ No API changes required
- ❌ No changes to other language plugins

### User Impact

- **Positive**: Users can now analyze C# files
- **Positive**: C# elements are extractable through all interfaces
- **Positive**: MCP tools can process C# files
- **Positive**: Full .NET ecosystem support
- **No Breaking Changes**: Existing functionality remains unchanged

### Dependencies

- **External**: `tree-sitter-c-sharp` Python package (must be available on PyPI)
- **Internal**: Existing plugin architecture (no changes needed)

---

## Success Criteria

1. ✅ C# plugin loads successfully via PluginManager
2. ✅ C# files (`.cs`) are recognized and processed
3. ✅ C# elements (classes, methods, properties, fields) are extracted correctly
4. ✅ C# analysis works through CLI, API, and MCP interfaces
5. ✅ Format output (Full, Compact, CSV) works for C# files
6. ✅ All tests pass (mypy, ruff, pytest)
7. ✅ Test coverage ≥80% for C# plugin
8. ✅ No regression in existing language plugins
9. ✅ Modern C# features are supported (records, nullable reference types)
10. ✅ C# attributes are extracted correctly

---

## Related Issues

- Language detection already recognizes `.cs` but lacks plugin
- Similar pattern to existing language plugins (Java, TypeScript)
- Follows established plugin architecture
- C# shares OOP concepts with Java (classes, interfaces, inheritance)

---

## Alternatives Considered

### Alternative 1: Generic .NET Parser
Use a generic .NET parser library (e.g., Roslyn) instead of tree-sitter-c-sharp.

**Rejected**: 
- Inconsistent with project architecture (all languages use tree-sitter)
- Would require different integration approach
- Breaks consistency principle
- Roslyn is heavyweight and C#-specific

### Alternative 2: Minimal C# Support
Only support basic C# statements without full element extraction.

**Rejected**:
- Doesn't meet user needs for comprehensive C# analysis
- Inconsistent with other language plugins' feature completeness
- Would require future expansion anyway

### Alternative 3: External Plugin
Create C# support as external plugin via entry points.

**Rejected**:
- Core language support should be built-in
- Better integration with existing codebase
- Easier maintenance and testing
- C# is a mainstream language deserving first-class support

---

## Dependencies

- **tree-sitter-c-sharp**: Must be available on PyPI and compatible with tree-sitter >=0.25.0
- **Verification**: Need to confirm tree-sitter-c-sharp package availability and version compatibility

---

## Timeline

- **Proposal**: 2025-11-09
- **Design Review**: 1 day
- **Implementation**: 2-3 days
- **Testing**: 1-2 days
- **Review**: 1 day
- **Target Completion**: 2025-11-14

---

## Notes

- C# is a complex language with many modern features (LINQ, async/await, pattern matching)
- tree-sitter-c-sharp should support modern C# syntax (C# 9+)
- Initial implementation focuses on core C# elements
- Future enhancements could add:
  - LINQ query analysis
  - Async/await pattern detection
  - Dependency injection pattern recognition
  - ASP.NET Core-specific features
  - Unity-specific attributes
- C# has attributes (similar to Java annotations) that should be extracted
- C# has properties (different from Java fields) that need special handling
- C# has partial classes that may span multiple files

---

## Risk Assessment

### Low Risk
- ✅ Plugin architecture is well-established
- ✅ Similar patterns exist in Java and TypeScript plugins
- ✅ No changes to existing code
- ✅ Optional dependency (doesn't affect users who don't need C#)

### Mitigation Strategies
- Follow exact same pattern as SQL plugin (most recent addition)
- Comprehensive testing before merge
- Clear documentation for C#-specific features
- Graceful degradation if tree-sitter-c-sharp not installed

---

## References

- SQL Language Support: `openspec/changes/archive/add-sql-language-support/`
- Java Plugin: `tree_sitter_analyzer/languages/java_plugin.py`
- TypeScript Plugin: `tree_sitter_analyzer/languages/typescript_plugin.py`
- Plugin Manager: `tree_sitter_analyzer/plugins/manager.py`
- Language Detector: `tree_sitter_analyzer/language_detector.py`

