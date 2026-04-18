# Tasks: Add PHP and Ruby Language Support

**Change ID:** `add-php-ruby-language-support`  
**Status:** ✅ Completed

---

## Task Breakdown

### Phase 1: Foundation Setup (Day 1)

#### Task 1.1: Verify tree-sitter Packages Availability
**Priority:** Critical  
**Estimated Time:** 1 hour

- [x] Verify `tree-sitter-php` package exists on PyPI
- [x] Verify `tree-sitter-ruby` package exists on PyPI
- [x] Check compatibility with `tree-sitter>=0.25.0`
- [x] Test basic installation: `pip install tree-sitter-php tree-sitter-ruby`
- [x] Verify language loading works with current tree-sitter version
- [x] Document any version constraints

**Validation:**
- Both packages install successfully
- Language objects can be created
- No version conflicts with existing dependencies

**Dependencies:** None

---

#### Task 1.2: Update pyproject.toml
**Priority:** Critical  
**Estimated Time:** 30 minutes

- [x] Add `tree-sitter-php` to optional dependencies
- [x] Add `tree-sitter-ruby` to optional dependencies
- [x] Add PHP and Ruby to language bundles (e.g., `all-languages`, `web`)
- [x] Update project description to mention PHP and Ruby support
- [x] Verify dependency resolution with `uv lock`

**Files to Modify:**
- `pyproject.toml`

**Validation:**
- `uv lock` succeeds
- `uv sync --extra php` installs correctly
- `uv sync --extra ruby` installs correctly
- No dependency conflicts

**Dependencies:** Task 1.1

---

### Phase 2: PHP Plugin Implementation (Day 2-3)

#### Task 2.1: Create PHP Plugin Structure
**Priority:** Critical  
**Estimated Time:** 2 hours

- [x] Create `tree_sitter_analyzer/languages/php_plugin.py`
- [x] Implement `PHPPlugin` class extending `LanguagePlugin`
- [x] Implement `get_language_name()` → "php"
- [x] Implement `get_file_extensions()` → [".php"]
- [x] Implement `get_tree_sitter_language()` with caching
- [x] Implement `create_extractor()` → PHPElementExtractor()
- [x] Add proper type hints for mypy compliance
- [x] Add docstrings for all public methods

**Files to Create:**
- `tree_sitter_analyzer/languages/php_plugin.py`

**Validation:**
- Plugin class instantiates successfully
- All interface methods implemented
- Mypy passes with zero errors
- Ruff passes with zero errors

**Dependencies:** Task 1.2

---

#### Task 2.2: Implement PHP Element Extractor Base
**Priority:** Critical  
**Estimated Time:** 3 hours

- [x] Implement `PHPElementExtractor` class extending `ElementExtractor`
- [x] Initialize caches and state variables
- [x] Implement `_reset_caches()` method
- [x] Implement `_get_node_text_optimized()` method
- [x] Implement `_extract_namespace()` method
- [x] Implement `_extract_modifiers()` method (public, private, protected, static, final, abstract)
- [x] Implement `_determine_visibility()` method
- [x] Add performance optimization caches

**Files to Modify:**
- `tree_sitter_analyzer/languages/php_plugin.py`

**Validation:**
- Extractor instantiates successfully
- Helper methods work correctly
- No memory leaks in caches

**Dependencies:** Task 2.1

---

#### Task 2.3: Implement PHP Class Extraction
**Priority:** Critical  
**Estimated Time:** 4 hours

- [x] Implement `extract_classes()` method
- [x] Implement `_extract_php_classes()` for class declarations
- [x] Implement `_extract_interfaces()` for interface declarations
- [x] Implement `_extract_traits()` for trait declarations
- [x] Implement `_extract_enums()` for enum declarations (PHP 8.1+)
- [x] Extract class name, modifiers, visibility
- [x] Extract extends and implements
- [x] Extract attributes (PHP 8+)
- [x] Generate fully qualified names with namespace

**Files to Modify:**
- `tree_sitter_analyzer/languages/php_plugin.py`

**Validation:**
- Classes extracted correctly
- Interfaces extracted correctly
- Traits extracted correctly
- Enums extracted correctly
- Attributes associated correctly

**Dependencies:** Task 2.2

---

#### Task 2.4: Implement PHP Method/Function Extraction
**Priority:** Critical  
**Estimated Time:** 4 hours

- [x] Implement `extract_functions()` method
- [x] Implement `_extract_methods()` for method declarations
- [x] Implement `_extract_functions()` for function declarations
- [x] Extract method/function name, parameters, return type
- [x] Extract modifiers (public, private, static, final, abstract)
- [x] Extract attributes (PHP 8+)
- [x] Detect magic methods (`__construct`, `__get`, etc.)
- [x] Calculate complexity score
- [x] Extract PHPDoc comments

**Files to Modify:**
- `tree_sitter_analyzer/languages/php_plugin.py`

**Validation:**
- Methods extracted correctly
- Functions extracted correctly
- Magic methods detected
- Attributes associated correctly
- Parameters extracted correctly

**Dependencies:** Task 2.2

---

#### Task 2.5: Implement PHP Property/Constant Extraction
**Priority:** High  
**Estimated Time:** 3 hours

- [x] Implement `extract_variables()` method
- [x] Implement `_extract_properties()` for property declarations
- [x] Implement `_extract_constants()` for constant declarations
- [x] Extract property/constant name, type, modifiers
- [x] Detect typed properties (PHP 7.4+)
- [x] Extract attributes on properties
- [x] Map properties/constants to Variable elements

**Files to Modify:**
- `tree_sitter_analyzer/languages/php_plugin.py`

**Validation:**
- Properties extracted correctly
- Constants extracted correctly
- Typed properties detected correctly
- Attributes associated correctly

**Dependencies:** Task 2.2

---

#### Task 2.6: Implement PHP Import Extraction
**Priority:** High  
**Estimated Time:** 2 hours

- [x] Implement `extract_imports()` method
- [x] Implement `_extract_use_statements()` for use declarations
- [x] Extract namespace imports
- [x] Extract function imports (`use function`)
- [x] Extract constant imports (`use const`)
- [x] Extract aliases
- [x] Map use statements to Import elements

**Files to Modify:**
- `tree_sitter_analyzer/languages/php_plugin.py`

**Validation:**
- Use statements extracted correctly
- Function imports extracted correctly
- Constant imports extracted correctly
- Aliases extracted correctly

**Dependencies:** Task 2.2

---

#### Task 2.7: Implement PHP analyze_file() Method
**Priority:** Critical  
**Estimated Time:** 2 hours

- [x] Implement `analyze_file()` async method
- [x] Load PHP file with safe encoding detection
- [x] Parse file with tree-sitter-php
- [x] Extract all element types
- [x] Combine elements into AnalysisResult
- [x] Handle errors gracefully
- [x] Count AST nodes

**Files to Modify:**
- `tree_sitter_analyzer/languages/php_plugin.py`

**Validation:**
- File analysis works end-to-end
- All element types extracted
- Error handling works
- AnalysisResult structure correct

**Dependencies:** Tasks 2.3, 2.4, 2.5, 2.6

---

#### Task 2.8: Create PHP Tree-sitter Queries
**Priority:** High  
**Estimated Time:** 2 hours

- [x] Create `tree_sitter_analyzer/queries/php.py`
- [x] Define PHP-specific tree-sitter queries
- [x] Query for classes, interfaces, traits, enums
- [x] Query for methods, functions
- [x] Query for properties, constants
- [x] Query for use statements
- [x] Query for attributes (PHP 8+)
- [x] Add docstrings and type hints

**Files to Create:**
- `tree_sitter_analyzer/queries/php.py`

**Validation:**
- Queries work with tree-sitter-php
- All PHP constructs covered
- Queries are efficient

**Dependencies:** Task 2.1

---

#### Task 2.9: Create PHP Formatter
**Priority:** High  
**Estimated Time:** 3 hours

- [x] Create `tree_sitter_analyzer/formatters/php_formatter.py`
- [x] Implement `PHPFullFormatter` for full table format
- [x] Implement `PHPCompactFormatter` for compact format
- [x] Implement `PHPCSVFormatter` for CSV format
- [x] Handle PHP-specific elements (traits, attributes, magic methods)
- [x] Update `formatter_config.py` to register PHP formatters
- [x] Update `language_formatter_factory.py` to include PHP
- [x] Add proper type hints and docstrings

**Files to Create:**
- `tree_sitter_analyzer/formatters/php_formatter.py`

**Files to Modify:**
- `tree_sitter_analyzer/formatters/formatter_config.py`
- `tree_sitter_analyzer/formatters/language_formatter_factory.py`

**Validation:**
- Full format output correct
- Compact format output correct
- CSV format output correct
- PHP-specific features displayed properly

**Dependencies:** Task 2.7

---

### Phase 3: Ruby Plugin Implementation (Day 4-5)

#### Task 3.1: Create Ruby Plugin Structure
**Priority:** Critical  
**Estimated Time:** 2 hours

- [x] Create `tree_sitter_analyzer/languages/ruby_plugin.py`
- [x] Implement `RubyPlugin` class extending `LanguagePlugin`
- [x] Implement `get_language_name()` → "ruby"
- [x] Implement `get_file_extensions()` → [".rb"]
- [x] Implement `get_tree_sitter_language()` with caching
- [x] Implement `create_extractor()` → RubyElementExtractor()
- [x] Add proper type hints for mypy compliance
- [x] Add docstrings for all public methods

**Files to Create:**
- `tree_sitter_analyzer/languages/ruby_plugin.py`

**Validation:**
- Plugin class instantiates successfully
- All interface methods implemented
- Mypy passes with zero errors
- Ruff passes with zero errors

**Dependencies:** Task 1.2

---

#### Task 3.2: Implement Ruby Element Extractor Base
**Priority:** Critical  
**Estimated Time:** 3 hours

- [x] Implement `RubyElementExtractor` class extending `ElementExtractor`
- [x] Initialize caches and state variables
- [x] Implement `_reset_caches()` method
- [x] Implement `_get_node_text_optimized()` method
- [x] Implement `_extract_modifiers()` method
- [x] Implement `_determine_visibility()` method (public, private, protected)
- [x] Add performance optimization caches

**Files to Modify:**
- `tree_sitter_analyzer/languages/ruby_plugin.py`

**Validation:**
- Extractor instantiates successfully
- Helper methods work correctly
- No memory leaks in caches

**Dependencies:** Task 3.1

---

#### Task 3.3: Implement Ruby Class/Module Extraction
**Priority:** Critical  
**Estimated Time:** 4 hours

- [x] Implement `extract_classes()` method
- [x] Implement `_extract_ruby_classes()` for class declarations
- [x] Implement `_extract_modules()` for module declarations
- [x] Extract class/module name
- [x] Extract inheritance (< SuperClass)
- [x] Extract included modules (include, prepend, extend)
- [x] Generate fully qualified names with namespace

**Files to Modify:**
- `tree_sitter_analyzer/languages/ruby_plugin.py`

**Validation:**
- Classes extracted correctly
- Modules extracted correctly
- Inheritance detected correctly
- Included modules detected correctly

**Dependencies:** Task 3.2

---

#### Task 3.4: Implement Ruby Method Extraction
**Priority:** Critical  
**Estimated Time:** 4 hours

- [x] Implement `extract_functions()` method
- [x] Implement `_extract_methods()` for method declarations
- [x] Extract instance methods (`def method_name`)
- [x] Extract class methods (`def self.method_name`)
- [x] Extract method parameters
- [x] Detect blocks, procs, lambdas
- [x] Detect attr_accessor, attr_reader, attr_writer
- [x] Calculate complexity score
- [x] Extract YARD/RDoc comments

**Files to Modify:**
- `tree_sitter_analyzer/languages/ruby_plugin.py`

**Validation:**
- Instance methods extracted correctly
- Class methods extracted correctly
- attr_* shortcuts detected correctly
- Parameters extracted correctly
- Blocks detected correctly

**Dependencies:** Task 3.2

---

#### Task 3.5: Implement Ruby Variable/Constant Extraction
**Priority:** High  
**Estimated Time:** 3 hours

- [x] Implement `extract_variables()` method
- [x] Implement `_extract_constants()` for constant declarations
- [x] Implement `_extract_instance_variables()` for @variables
- [x] Implement `_extract_class_variables()` for @@variables
- [x] Extract global variables ($variables)
- [x] Map variables to Variable elements

**Files to Modify:**
- `tree_sitter_analyzer/languages/ruby_plugin.py`

**Validation:**
- Constants extracted correctly
- Instance variables extracted correctly
- Class variables extracted correctly
- Global variables extracted correctly

**Dependencies:** Task 3.2

---

#### Task 3.6: Implement Ruby Import Extraction
**Priority:** High  
**Estimated Time:** 2 hours

- [x] Implement `extract_imports()` method
- [x] Implement `_extract_requires()` for require statements
- [x] Extract require_relative statements
- [x] Extract load statements
- [x] Map require statements to Import elements

**Files to Modify:**
- `tree_sitter_analyzer/languages/ruby_plugin.py`

**Validation:**
- require statements extracted correctly
- require_relative statements extracted correctly
- load statements extracted correctly

**Dependencies:** Task 3.2

---

#### Task 3.7: Implement Ruby analyze_file() Method
**Priority:** Critical  
**Estimated Time:** 2 hours

- [x] Implement `analyze_file()` async method
- [x] Load Ruby file with safe encoding detection
- [x] Parse file with tree-sitter-ruby
- [x] Extract all element types
- [x] Combine elements into AnalysisResult
- [x] Handle errors gracefully
- [x] Count AST nodes

**Files to Modify:**
- `tree_sitter_analyzer/languages/ruby_plugin.py`

**Validation:**
- File analysis works end-to-end
- All element types extracted
- Error handling works
- AnalysisResult structure correct

**Dependencies:** Tasks 3.3, 3.4, 3.5, 3.6

---

### Phase 4: Testing (Day 6-7)

#### Task 4.1: Create Sample Files
**Priority:** Critical  
**Estimated Time:** 3 hours

**PHP Samples:**
- [x] Create `examples/Sample.php` with basic PHP features
  - Classes, methods, properties, functions
  - Namespaces, use statements
  - Attributes (PHP 8+)
- [x] Create `examples/SampleLaravel.php` with Laravel patterns
  - Controller class
  - Route attributes
  - Dependency injection
- [x] Create `examples/SampleWordPress.php` with WordPress patterns
  - Hooks, filters
  - Custom post types

**Ruby Samples:**
- [x] Create `examples/Sample.rb` with basic Ruby features
  - Classes, modules, methods
  - attr_accessor, attr_reader, attr_writer
  - require statements
- [x] Create `examples/SampleRails.rb` with Rails patterns
  - ActiveRecord model
  - Controller actions
  - Validations
- [x] Create `examples/SampleRSpec.rb` with RSpec patterns
  - describe, context, it blocks
  - let, before, after

**Files to Create:**
- `examples/Sample.php`
- `examples/SampleLaravel.php`
- `examples/SampleWordPress.php`
- `examples/Sample.rb`
- `examples/SampleRails.rb`
- `examples/SampleRSpec.rb`

**Validation:**
- PHP files contain valid PHP syntax
- Ruby files contain valid Ruby syntax
- Files cover common patterns

**Dependencies:** None (can be done in parallel)

---

#### Task 4.2: Create PHP Unit Tests
**Priority:** Critical  
**Estimated Time:** 4 hours

- [x] Create `tests/test_languages/test_php_plugin.py`
- [x] Test plugin instantiation
- [x] Test `get_language_name()`
- [x] Test `get_file_extensions()`
- [x] Test `get_tree_sitter_language()`
- [x] Test class extraction
- [x] Test interface extraction
- [x] Test trait extraction
- [x] Test enum extraction (PHP 8.1+)
- [x] Test method extraction
- [x] Test function extraction
- [x] Test property extraction
- [x] Test constant extraction
- [x] Test use statement extraction
- [x] Test attribute extraction (PHP 8+)
- [x] Test magic method detection
- [x] Test edge cases (empty files, invalid syntax)

**Files to Create:**
- `tests/test_languages/test_php_plugin.py`

**Validation:**
- All tests pass
- Test coverage >80%
- Tests cover all element types
- Tests cover edge cases

**Dependencies:** Task 2.7, Task 4.1

---

#### Task 4.3: Create Ruby Unit Tests
**Priority:** Critical  
**Estimated Time:** 4 hours

- [x] Create `tests/test_languages/test_ruby_plugin.py`
- [x] Test plugin instantiation
- [x] Test `get_language_name()`
- [x] Test `get_file_extensions()`
- [x] Test `get_tree_sitter_language()`
- [x] Test class extraction
- [x] Test module extraction
- [x] Test method extraction (instance and class methods)
- [x] Test attr_accessor/reader/writer detection
- [x] Test constant extraction
- [x] Test instance variable extraction
- [x] Test class variable extraction
- [x] Test require statement extraction
- [x] Test block/proc/lambda detection
- [x] Test edge cases (empty files, invalid syntax)

**Files to Create:**
- `tests/test_languages/test_ruby_plugin.py`

**Validation:**
- All tests pass
- Test coverage >80%
- Tests cover all element types
- Tests cover edge cases

**Dependencies:** Task 3.7, Task 4.1

---

#### Task 4.4: Create Integration Tests
**Priority:** High  
**Estimated Time:** 3 hours

- [x] Test CLI analysis of PHP files
- [x] Test CLI analysis of Ruby files
- [x] Test format output (Full, Compact, CSV) for PHP
- [x] Test format output (Full, Compact, CSV) for Ruby
- [x] Test MCP tools with PHP files
- [x] Test MCP tools with Ruby files
- [x] Test large file performance

**Files to Modify:**
- `tests/test_integration/` (add PHP/Ruby test cases)

**Validation:**
- CLI works with PHP/Ruby files
- Format output correct
- MCP tools work
- Performance acceptable

**Dependencies:** Tasks 4.2, 4.3

---

#### Task 4.5: Create Golden Master Tests
**Priority:** Medium  
**Estimated Time:** 3 hours

**PHP Golden Masters:**
- [x] Run `uv run python scripts/generate_golden_masters.py php examples/Sample.php --name php_sample`
- [x] Verify generated files:
  - `tests/golden_masters/full/php_sample_full.md`
  - `tests/golden_masters/compact/php_sample_compact.md`
  - `tests/golden_masters/csv/php_sample_csv.csv`
- [x] Run consistency check (3 times) to verify stable output
- [x] Fix any inconsistencies in PHP formatter

**Ruby Golden Masters:**
- [x] Run `uv run python scripts/generate_golden_masters.py ruby examples/Sample.rb --name ruby_sample`
- [x] Verify generated files:
  - `tests/golden_masters/full/ruby_sample_full.md`
  - `tests/golden_masters/compact/ruby_sample_compact.md`
  - `tests/golden_masters/csv/ruby_sample_csv.csv`
- [x] Run consistency check (3 times) to verify stable output
- [x] Fix any inconsistencies in Ruby formatter

**Update Test Suite:**
- [x] Add PHP golden master test cases to `tests/test_golden_master_regression.py`
- [x] Add Ruby golden master test cases to `tests/test_golden_master_regression.py`
- [x] Verify all golden master tests pass

**Files to Create:**
- `tests/golden_masters/full/php_sample_full.md`
- `tests/golden_masters/compact/php_sample_compact.md`
- `tests/golden_masters/csv/php_sample_csv.csv`
- `tests/golden_masters/full/ruby_sample_full.md`
- `tests/golden_masters/compact/ruby_sample_compact.md`
- `tests/golden_masters/csv/ruby_sample_csv.csv`

**Files to Modify:**
- `tests/test_golden_master_regression.py`

**Validation:**
- Golden master generation succeeds
- Consistency check passes (no random variations)
- Golden master tests pass
- Output format consistent
- CSV format correct

**Dependencies:** Tasks 2.9 (PHP Formatter), 3.9 (Ruby Formatter), 4.1, 4.2, 4.3

---

### Phase 5: Documentation and Quality (Day 8)

#### Task 5.1: Update Documentation
**Priority:** High  
**Estimated Time:** 3 hours

- [x] Update `README.md` to include PHP and Ruby in supported languages
- [x] Update language support table
- [x] Add PHP example to README
- [x] Add Ruby example to README
- [x] Update `README_ja.md`
- [x] Update `README_zh.md`
- [x] Update `CHANGELOG.md` with PHP and Ruby support
- [x] Update language count (9 → 11 languages)

**Files to Modify:**
- `README.md`
- `README_ja.md`
- `README_zh.md`
- `CHANGELOG.md`

**Validation:**
- Documentation accurate
- Examples work
- Language count correct

**Dependencies:** Tasks 4.2, 4.3

---

#### Task 5.2: Run Quality Checks
**Priority:** Critical  
**Estimated Time:** 1 hour

- [x] Run `mypy` on PHP plugin - must pass with zero errors
- [x] Run `mypy` on Ruby plugin - must pass with zero errors
- [x] Run `ruff` on PHP plugin - must pass with zero errors
- [x] Run `ruff` on Ruby plugin - must pass with zero errors
- [x] Run `black` on both plugins - must pass
- [x] Run `isort` on both plugins - must pass
- [x] Run `pytest` - all tests must pass
- [x] Run `pytest --cov` - coverage must be >80%
- [x] Verify no regression in existing tests

**Validation:**
- All quality checks pass
- No linting errors
- No type errors
- Test coverage adequate
- No regression

**Dependencies:** Tasks 4.2, 4.3

---

#### Task 5.3: Manual Testing
**Priority:** High  
**Estimated Time:** 2 hours

**PHP Testing:**
- [x] Test PHP analysis via CLI
  - `uv run tree-sitter-analyzer examples/Sample.php`
  - `uv run tree-sitter-analyzer examples/Sample.php --format compact`
  - `uv run tree-sitter-analyzer examples/Sample.php --format csv`
- [x] Test PHP analysis via MCP
  - `mcp analyze_code_structure examples/Sample.php`
- [x] Test with real-world PHP projects (WordPress, Laravel)

**Ruby Testing:**
- [x] Test Ruby analysis via CLI
  - `uv run tree-sitter-analyzer examples/Sample.rb`
  - `uv run tree-sitter-analyzer examples/Sample.rb --format compact`
  - `uv run tree-sitter-analyzer examples/Sample.rb --format csv`
- [x] Test Ruby analysis via MCP
  - `mcp analyze_code_structure examples/Sample.rb`
- [x] Test with real-world Ruby projects (Rails, RSpec)

**Validation:**
- CLI works correctly for both languages
- MCP works correctly for both languages
- Output quality good
- Performance acceptable

**Dependencies:** Task 5.2

---

### Phase 6: Validation and Review (Day 8)

#### Task 6.1: Final Review
**Priority:** Critical  
**Estimated Time:** 2 hours

- [x] Review all code changes
- [x] Verify no breaking changes
- [x] Verify isolation (no impact on other languages)
- [x] Check code quality
- [x] Check documentation completeness
- [x] Verify all success criteria met

**Validation:**
- Code review complete
- All success criteria met
- Ready for merge

**Dependencies:** Task 5.3

---

## Task Dependencies Graph

```
1.1 (Verify tree-sitter packages)
  └─> 1.2 (Update pyproject.toml)
        ├─> 2.1 (PHP Plugin Structure)
        │     ├─> 2.8 (PHP Queries)
        │     └─> 2.2 (PHP Extractor Base)
        │           ├─> 2.3 (PHP Class Extraction)
        │           ├─> 2.4 (PHP Method/Function Extraction)
        │           ├─> 2.5 (PHP Property/Constant Extraction)
        │           └─> 2.6 (PHP Import Extraction)
        │                 └─> 2.7 (PHP analyze_file())
        │                       ├─> 2.9 (PHP Formatter)
        │                       └─> 4.2 (PHP Unit Tests)
        │
        └─> 3.1 (Ruby Plugin Structure)
              ├─> 3.8 (Ruby Queries)
              └─> 3.2 (Ruby Extractor Base)
                    ├─> 3.3 (Ruby Class/Module Extraction)
                    ├─> 3.4 (Ruby Method Extraction)
                    ├─> 3.5 (Ruby Variable/Constant Extraction)
                    └─> 3.6 (Ruby Import Extraction)
                          └─> 3.7 (Ruby analyze_file())
                                ├─> 3.9 (Ruby Formatter)
                                └─> 4.3 (Ruby Unit Tests)

4.1 (Sample Files) ──────────────────────────┐
                                              │
2.9 (PHP Formatter) ──┐                      │
3.9 (Ruby Formatter) ─┤                      │
                       │                      │
4.2 (PHP Unit Tests) ──┼──┐                  │
4.3 (Ruby Unit Tests) ─┴──┴─> 4.4 (Integration Tests)
                                └─> 4.5 (Golden Master Tests)
                                      └─> 5.1 (Documentation)
                                            └─> 5.2 (Quality Checks)
                                                  └─> 5.3 (Manual Testing)
                                                        └─> 6.1 (Final Review)

Parallel Tasks:
- PHP plugin (2.1-2.9) and Ruby plugin (3.1-3.9) can be done in parallel
- PHP queries (2.8) and Ruby queries (3.8) can be done early
- Sample files (4.1) can be done anytime
- Formatters (2.9, 3.9) required before golden master tests (4.5)
- Documentation (5.1) can start after unit tests (4.2, 4.3)
```

---

## Time Estimates

| Phase | Estimated Time |
|-------|----------------|
| Phase 1: Foundation Setup | 1.5 hours |
| Phase 2: PHP Plugin Implementation (including Queries & Formatter) | 25 hours |
| Phase 3: Ruby Plugin Implementation (including Queries & Formatter) | 25 hours |
| Phase 4: Testing | 17 hours |
| Phase 5: Documentation and Quality | 6 hours |
| Phase 6: Validation and Review | 2 hours |
| **Total** | **76.5 hours** (~9-10 days with parallel work) |

---

## Success Criteria Checklist

### PHP Support
- [x] PHP plugin loads successfully via PluginManager
- [x] PHP files (`.php`) are recognized and processed
- [x] PHP elements (classes, methods, functions, properties) are extracted correctly
- [x] PHP analysis works through CLI, API, and MCP interfaces
- [x] Format output (Full, Compact, CSV) works for PHP files
- [x] Modern PHP 8+ features are supported (attributes, enums, union types)

### Ruby Support
- [x] Ruby plugin loads successfully via PluginManager
- [x] Ruby files (`.rb`) are recognized and processed
- [x] Ruby elements (classes, modules, methods) are extracted correctly
- [x] Ruby analysis works through CLI, API, and MCP interfaces
- [x] Format output (Full, Compact, CSV) works for Ruby files
- [x] Modern Ruby 3+ features are supported (pattern matching, endless methods)

### Quality
- [x] All tests pass (mypy, ruff, pytest)
- [x] Test coverage ≥80% for both plugins
- [x] No regression in existing language plugins

---

## Risk Mitigation

### Risk: tree-sitter packages not compatible
**Mitigation:** Verify compatibility in Task 1.1 before proceeding

### Risk: Complex PHP/Ruby syntax not parsing correctly
**Mitigation:** Create comprehensive sample files in Task 4.1, test edge cases

### Risk: Performance issues with large files
**Mitigation:** Use iterative traversal, optimize caching, test with large files

### Risk: Breaking existing functionality
**Mitigation:** Run full test suite, verify no regression, ensure isolation

### Risk: PHP/Ruby-specific features not handled correctly
**Mitigation:** Study language specifications, test with real-world projects

---

## Notes

- Follow exact same pattern as C# plugin (most recent addition)
- Refer to Python plugin for dynamic typing patterns
- PHP has unique features (traits, magic methods) requiring special handling
- Ruby has unique features (modules, blocks, symbols) requiring special handling
- Ensure complete isolation from other language plugins
- Maintain backward compatibility
- All code must pass mypy, ruff, and pytest
- PHP and Ruby plugins can be implemented in parallel by different developers

