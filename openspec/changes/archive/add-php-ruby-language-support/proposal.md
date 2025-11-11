# Proposal: Add PHP and Ruby Language Support

**Change ID:** `add-php-ruby-language-support`  
**Type:** Feature Addition  
**Status:** Draft  
**Created:** 2025-11-10  
**Author:** AI Assistant

---

## Problem Statement

Tree-sitter Analyzer currently supports 9 languages (Python, Java, JavaScript, TypeScript, HTML, CSS, Markdown, SQL, C#) but lacks support for PHP and Ruby, two critical languages for web development and scripting. These languages are commonly found in:

### PHP Use Cases
- WordPress sites and plugins (40% of the web)
- Laravel web applications
- Symfony enterprise applications
- Legacy LAMP stack applications
- E-commerce platforms (Magento, WooCommerce)
- Content Management Systems

### Ruby Use Cases
- Ruby on Rails web applications
- DevOps automation scripts
- API services
- Background job processing (Sidekiq)
- Testing frameworks (RSpec, Minitest)
- Jekyll static site generation

The `language_detector.py` already recognizes `.php` and `.rb` files (mapped to "php" and "ruby" with 0.9 confidence) but there are no corresponding plugin implementations to extract elements like classes, methods, functions, and modules.

### Current Behavior

- PHP files (`.php`) are detected but cannot be analyzed
- Ruby files (`.rb`) are detected but cannot be analyzed
- No PHP plugin exists in `tree_sitter_analyzer/languages/`
- No Ruby plugin exists in `tree_sitter_analyzer/languages/`
- PHP/Ruby files cannot be analyzed through the analyzer API
- MCP tools cannot process PHP/Ruby files

### Expected Behavior

After implementation:
- PHP files (`.php`) are fully supported with dedicated plugin
- Ruby files (`.rb`) are fully supported with dedicated plugin
- PHP/Ruby elements are extracted: classes, modules, methods, functions
- PHP/Ruby analysis works through all interfaces: CLI, API, MCP
- Format output (Full, Compact, CSV) works for PHP/Ruby files
- Support for modern PHP 8+ and Ruby 3+ features

---

## Root Cause Analysis

### Missing Components

#### For PHP:
1. **No PHP Plugin**: `tree_sitter_analyzer/languages/php_plugin.py` does not exist
2. **No PHP Extractor**: No `PHPElementExtractor` class to parse PHP AST
3. **No tree-sitter-php Dependency**: `pyproject.toml` doesn't include `tree-sitter-php`
4. **No PHP Tests**: Test suite has no PHP-specific test cases
5. **No PHP Sample Files**: No example PHP files for testing and validation

#### For Ruby:
1. **No Ruby Plugin**: `tree_sitter_analyzer/languages/ruby_plugin.py` does not exist
2. **No Ruby Extractor**: No `RubyElementExtractor` class to parse Ruby AST
3. **No tree-sitter-ruby Dependency**: `pyproject.toml` doesn't include `tree-sitter-ruby`
4. **No Ruby Tests**: Test suite has no Ruby-specific test cases
5. **No Ruby Sample Files**: No example Ruby files for testing and validation

### Architecture Alignment

The project uses a plugin-based architecture where each language follows the same pattern. PHP and Ruby support requires implementing this pattern for both languages simultaneously.

---

## Proposed Solution

Implement comprehensive PHP and Ruby language support following the existing plugin architecture pattern, maintaining consistency with other language plugins (especially Python and JavaScript, as they share dynamic typing characteristics).

### Key Components

#### 1. PHP Plugin (`php_plugin.py`)
- Implements `LanguagePlugin` interface
- Supports `.php` file extension
- Loads `tree-sitter-php` language
- Provides PHP-specific element extraction
- Extracts classes, interfaces, traits
- Extracts methods, functions
- Extracts properties, constants
- Extracts namespaces and use statements
- Extracts attributes (PHP 8+)
- Handles PHP-specific syntax (heredoc, nowdoc, etc.)

#### 2. Ruby Plugin (`ruby_plugin.py`)
- Implements `LanguagePlugin` interface
- Supports `.rb` file extension
- Loads `tree-sitter-ruby` language
- Provides Ruby-specific element extraction
- Extracts classes, modules
- Extracts methods (instance and class methods)
- Extracts constants, instance variables, class variables
- Extracts require/require_relative statements
- Extracts blocks and lambdas
- Handles Ruby-specific syntax (symbols, string interpolation, etc.)

#### 3. PHP Element Extractor (`PHPElementExtractor`)
- Extracts classes, interfaces, traits, enums (PHP 8.1+)
- Extracts methods (including magic methods)
- Extracts properties (typed properties PHP 7.4+)
- Extracts functions (global and namespaced)
- Extracts constants (class and global)
- Extracts namespaces and use statements
- Extracts attributes (PHP 8+)
- Maps PHP elements to unified element model

#### 4. Ruby Element Extractor (`RubyElementExtractor`)
- Extracts classes and modules
- Extracts methods (def, instance methods, class methods)
- Extracts attr_accessor, attr_reader, attr_writer
- Extracts constants, @instance_variables, @@class_variables
- Extracts require/require_relative statements
- Extracts blocks, procs, lambdas
- Maps Ruby elements to unified element model

#### 5. Dependencies
- Add `tree-sitter-php` to `pyproject.toml`
- Add `tree-sitter-ruby` to `pyproject.toml`
- Add PHP and Ruby to optional dependencies groups
- Verify compatibility with tree-sitter >=0.25.0

#### 6. Tests
- Unit tests for PHP plugin
- Unit tests for Ruby plugin
- Integration tests for PHP/Ruby analysis
- Test element extraction for both languages
- Test format output for PHP/Ruby
- Test modern features (PHP 8+, Ruby 3+)

#### 7. Sample Files
- Create example PHP files (Laravel, WordPress patterns)
- Create example Ruby files (Rails, RSpec patterns)
- Cover common patterns in both languages

### Design Principles

- **Consistency**: Follow existing plugin patterns (C#, Java, Python)
- **Type Safety**: Full mypy compliance with proper type hints
- **Code Quality**: Ruff compliance, no linting errors
- **Test Coverage**: >80% coverage for both plugins
- **Backward Compatibility**: No breaking changes to existing APIs
- **Isolation**: PHP and Ruby plugins are completely independent
- **SOLID Principles**: Single Responsibility, Open/Closed, Dependency Inversion

---

## Impact Analysis

### Affected Components

- ✅ `tree_sitter_analyzer/languages/php_plugin.py` - New file
- ✅ `tree_sitter_analyzer/languages/ruby_plugin.py` - New file
- ✅ `tree_sitter_analyzer/queries/php.py` - New file (tree-sitter queries)
- ✅ `tree_sitter_analyzer/queries/ruby.py` - New file (tree-sitter queries)
- ✅ `tree_sitter_analyzer/formatters/php_formatter.py` - New file (dedicated formatter)
- ✅ `tree_sitter_analyzer/formatters/ruby_formatter.py` - New file (dedicated formatter)
- ✅ `tree_sitter_analyzer/formatters/formatter_config.py` - Register PHP/Ruby formatters
- ✅ `tree_sitter_analyzer/formatters/language_formatter_factory.py` - Add PHP/Ruby
- ✅ `pyproject.toml` - Add tree-sitter-php and tree-sitter-ruby dependencies
- ✅ `tests/test_languages/test_php_plugin.py` - New test file
- ✅ `tests/test_languages/test_ruby_plugin.py` - New test file
- ✅ `tests/golden_masters/` - PHP and Ruby golden master files
- ✅ `tests/test_golden_master_regression.py` - Add PHP/Ruby test cases
- ✅ `examples/Sample.php` - New sample file
- ✅ `examples/Sample.rb` - New sample file
- ✅ `README.md` - Update supported languages list (9 → 11 languages)
- ❌ No breaking changes to existing code
- ❌ No API changes required
- ❌ No changes to other language plugins

### User Impact

- **Positive**: Users can now analyze PHP files (WordPress, Laravel, etc.)
- **Positive**: Users can now analyze Ruby files (Rails, RSpec, etc.)
- **Positive**: PHP/Ruby elements are extractable through all interfaces
- **Positive**: MCP tools can process PHP/Ruby files
- **Positive**: Full web development ecosystem support
- **No Breaking Changes**: Existing functionality remains unchanged

### Dependencies

- **External**: `tree-sitter-php` and `tree-sitter-ruby` Python packages (must be available on PyPI)
- **Internal**: Existing plugin architecture (no changes needed)

---

## Success Criteria

### PHP Support
1. ✅ PHP plugin loads successfully via PluginManager
2. ✅ PHP files (`.php`) are recognized and processed
3. ✅ PHP elements (classes, methods, functions, properties) are extracted correctly
4. ✅ PHP analysis works through CLI, API, and MCP interfaces
5. ✅ Format output (Full, Compact, CSV) works for PHP files
6. ✅ Modern PHP 8+ features are supported (attributes, enums, union types)

### Ruby Support
7. ✅ Ruby plugin loads successfully via PluginManager
8. ✅ Ruby files (`.rb`) are recognized and processed
9. ✅ Ruby elements (classes, modules, methods) are extracted correctly
10. ✅ Ruby analysis works through CLI, API, and MCP interfaces
11. ✅ Format output (Full, Compact, CSV) works for Ruby files
12. ✅ Modern Ruby 3+ features are supported (pattern matching, endless methods)

### Quality
13. ✅ All tests pass (mypy, ruff, pytest)
14. ✅ Test coverage ≥80% for both plugins
15. ✅ No regression in existing language plugins

---

## Related Issues

- Language detection already recognizes `.php` and `.rb` but lacks plugins
- Similar pattern to existing language plugins (C#, Python, JavaScript)
- Follows established plugin architecture
- PHP shares some characteristics with JavaScript (web focus)
- Ruby shares some characteristics with Python (dynamic typing, readability)

---

## Alternatives Considered

### Alternative 1: Add Only PHP or Only Ruby
Implement support for one language at a time.

**Rejected**: 
- Both languages are commonly requested
- Implementation effort is similar for both
- Better to deliver both together
- Shared testing and documentation effort

### Alternative 2: Use External Parsers
Use language-specific parsers (e.g., nikic/PHP-Parser for PHP, parser gem for Ruby).

**Rejected**:
- Inconsistent with project architecture (all languages use tree-sitter)
- Would require different integration approach
- Breaks consistency principle
- More complex dependency management

### Alternative 3: Minimal Support
Only support basic statements without full element extraction.

**Rejected**:
- Doesn't meet user needs for comprehensive analysis
- Inconsistent with other language plugins' feature completeness
- Would require future expansion anyway

---

## Dependencies

- **tree-sitter-php**: Must be available on PyPI and compatible with tree-sitter >=0.25.0
- **tree-sitter-ruby**: Must be available on PyPI and compatible with tree-sitter >=0.25.0
- **Verification**: Need to confirm both packages' availability and version compatibility

---

## Timeline

- **Proposal**: 2025-11-10
- **Design Review**: 1 day
- **Implementation**: 5-6 days (both languages in parallel)
- **Testing**: 2-3 days
- **Review**: 1 day
- **Target Completion**: 2025-11-20

---

## Notes

### PHP-Specific Considerations
- PHP has mixed HTML/PHP syntax (need to handle `<?php ?>` tags)
- PHP has magic methods (`__construct`, `__get`, etc.)
- PHP has traits (similar to mixins)
- PHP 8+ has attributes (similar to C# attributes)
- PHP has namespaces with backslash separator

### Ruby-Specific Considerations
- Ruby has modules (different from classes)
- Ruby has blocks, procs, and lambdas
- Ruby has symbols (`:symbol`)
- Ruby has attr_accessor/reader/writer (property shortcuts)
- Ruby has class methods (def self.method_name)
- Ruby has significant indentation and end keywords

### Future Enhancements
- PHP: Laravel-specific pattern recognition
- PHP: WordPress hook/filter detection
- Ruby: Rails-specific pattern recognition
- Ruby: RSpec test pattern detection
- Both: Framework-specific analysis

---

## Risk Assessment

### Low Risk
- ✅ Plugin architecture is well-established
- ✅ Similar patterns exist in C#, Python, JavaScript plugins
- ✅ No changes to existing code
- ✅ Optional dependencies (doesn't affect users who don't need PHP/Ruby)

### Mitigation Strategies
- Follow exact same pattern as C# plugin (most recent addition)
- Comprehensive testing before merge
- Clear documentation for language-specific features
- Graceful degradation if tree-sitter packages not installed
- Parallel implementation allows learning from first language

---

## References

- C# Language Support: `openspec/changes/add-csharp-language-support/`
- Python Plugin: `tree_sitter_analyzer/languages/python_plugin.py`
- JavaScript Plugin: `tree_sitter_analyzer/languages/javascript_plugin.py`
- Plugin Manager: `tree_sitter_analyzer/plugins/manager.py`
- Language Detector: `tree_sitter_analyzer/language_detector.py`

