# Implementation Plan

This implementation plan breaks down the SQL cross-platform compatibility feature into discrete, manageable tasks. Each task builds incrementally on previous work, with checkpoints to ensure quality.

## Phase 1: Core Infrastructure

- [x] 1. Set up platform compatibility module structure
  - Create `tree_sitter_analyzer/platform_compat/` directory
  - Create `__init__.py` with module exports
  - Create `tests/platform_compat/` directory for tests
  - _Requirements: Foundation for all compatibility components_

- [x] 1.1 Implement platform detection module
  - Create `tree_sitter_analyzer/platform_compat/detector.py`
  - Implement `PlatformInfo` dataclass with os_name, os_version, python_version, platform_key
  - Implement `PlatformDetector.detect()` to identify current platform
  - Implement `PlatformDetector.get_profile_path()` for profile file resolution
  - _Requirements: 1.4, 4.1_

- [x] 1.2 Write property test for platform detection
  - **Property 2: Platform detection accuracy**
  - **Validates: Requirements 4.1**
  - Test that detector correctly identifies OS and Python version across mocked environments
  - Use Hypothesis to generate various platform configurations
  - _Requirements: 4.1_

- [x] 1.3 Implement behavior profile data model
  - Create `tree_sitter_analyzer/platform_compat/profiles.py`
  - Implement `ParsingBehavior` dataclass for construct-specific behavior
  - Implement `BehaviorProfile` dataclass with schema_version, platform_key, behaviors, adaptation_rules
  - Implement `PROFILE_SCHEMA_VERSION` constant
  - Add JSON schema validation using jsonschema library
  - _Requirements: 2.2, 2.3_

- [x] 1.4 Implement profile loading and validation
  - Implement `BehaviorProfile.load()` with schema migration support
  - Implement `validate_profile()` function with JSON schema validation
  - Implement `migrate_profile_schema()` for version migration
  - Implement `migrate_to_1_0_0()` for initial migration
  - Handle profile not found gracefully (return None, log warning)
  - _Requirements: 1.4, 4.2_

- [x] 1.5 Write property test for profile loading
  - **Property 3: Profile loading correctness**
  - **Validates: Requirements 1.4, 4.2**
  - Test that correct profile is loaded for each platform
  - Test schema validation catches invalid profiles
  - Test migration from old schema versions
  - _Requirements: 1.4, 4.2_

- [x] 1.6 Implement profile caching system
  - Create `ProfileCache` class with thread-safe operations
  - Implement TTL-based cache expiration
  - Implement LRU eviction when cache is full
  - Add cache statistics logging
  - _Requirements: Performance optimization_

- [x] 1.7 Write unit tests for profile caching
  - Test cache hit/miss behavior
  - Test TTL expiration
  - Test LRU eviction
  - Test thread safety with concurrent access
  - _Requirements: Performance optimization_

## Phase 2: Behavior Recording System

- [x] 2. Create comprehensive test fixture library
  - Create `tests/platform_compat/fixtures.py`
  - Implement `SQLTestFixture` dataclass
  - Create fixtures for all major SQL constructs (tables, views, functions, procedures, triggers, indexes)
  - Create edge case fixtures for known platform issues
  - Document each fixture's purpose and expected behavior
  - _Requirements: 6.1, 6.2, 6.3_

- [x] 2.1 Implement standard SQL construct fixtures
  - `FIXTURE_SIMPLE_TABLE`: Basic table with columns
  - `FIXTURE_COMPLEX_TABLE`: Table with constraints, foreign keys
  - `FIXTURE_VIEW_WITH_JOIN`: View with JOIN operations
  - `FIXTURE_STORED_PROCEDURE`: Procedure with parameters
  - `FIXTURE_FUNCTION_WITH_PARAMS`: Function with parameters and return type
  - `FIXTURE_TRIGGER_BEFORE_INSERT`: Trigger with timing and event
  - `FIXTURE_INDEX_UNIQUE`: Unique index on table
  - _Requirements: 6.1_

- [x] 2.2 Implement edge case fixtures for platform issues
  - `FIXTURE_FUNCTION_WITH_SELECT`: Function with SELECT in body (Ubuntu 3.12 issue)
  - `FIXTURE_TRIGGER_WITH_DESCRIPTION`: Trigger name extraction (macOS issue)
  - `FIXTURE_FUNCTION_WITH_AUTO_INCREMENT`: Function near AUTO_INCREMENT (Windows issue)
  - `FIXTURE_VIEW_IN_ERROR_NODE`: View that appears in ERROR nodes
  - `FIXTURE_PHANTOM_TRIGGER`: Trigger that creates phantom elements
  - _Requirements: 6.2_

- [x] 2.3 Write property test for fixture coverage
  - **Property 12: Fixture library coverage**
  - **Validates: Requirements 6.1, 6.2, 6.3**
  - Test that fixture library contains at least one standard and one edge case for each SQL construct type
  - _Requirements: 6.1, 6.2, 6.3_

- [x] 2.4 Implement behavior recorder
  - Create `tests/platform_compat/recorder.py`
  - Implement `BehaviorRecorder` class
  - Implement `record_all()` to process all fixtures
  - Implement `record_fixture()` to process single fixture
  - Implement `analyze_ast()` to extract AST characteristics
  - Capture node types, attributes, element counts, error conditions
  - _Requirements: 2.1, 2.2_

- [x] 2.5 Write property test for recording completeness
  - **Property 6: Behavior recording completeness**
  - **Validates: Requirements 2.1**
  - Test that recorder executes every fixture in the set
  - Test that no fixtures are skipped
  - _Requirements: 2.1_

- [x] 2.6 Write property test for profile content
  - **Property 7: Profile content completeness**
  - **Validates: Requirements 2.2**
  - Test that recorded profiles contain AST structure, element types, attributes, and errors
  - _Requirements: 2.2_

- [x] 2.7 Implement profile persistence
  - Implement `BehaviorRecorder.save_profile()` to write profile to disk
  - Create directory structure: `tests/platform_profiles/{os_name}/{python_version}/`
  - Generate profile filename: `profile.json`
  - Include schema_version in saved profiles
  - _Requirements: 2.3, 2.5_

- [x] 2.8 Write property test for profile persistence
  - **Property 8: Profile persistence correctness**
  - **Validates: Requirements 2.3, 2.5**
  - Test that profiles are saved in correct directory structure
  - Test that saved profiles can be loaded without data loss
  - _Requirements: 2.3, 2.5_

- [x] 2.9 Implement profile comparison tool
  - Create `tree_sitter_analyzer/platform_compat/compare.py`
  - Implement `compare_profiles()` to identify differences
  - Implement `generate_diff_report()` for human-readable output
  - Detect differences in element counts, node types, attributes
  - _Requirements: 2.4_

- [x] 2.10 Write property test for profile comparison
  - **Property 9: Profile comparison accuracy**
  - **Validates: Requirements 2.4**
  - Test that comparison identifies all significant differences
  - Test that identical profiles show no differences
  - _Requirements: 2.4_

- [x] 2.11 Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Phase 3: Adaptation Rules Implementation

- [x] 3. Implement compatibility adapter structure
  - Create `tree_sitter_analyzer/platform_compat/adapter.py`
  - Implement `AdaptationRule` Protocol with proper type hints
  - Implement `CompatibilityAdapter` class
  - Implement `adapt_elements()` main entry point
  - Implement `_apply_rule()` for single rule application
  - _Requirements: 1.2, 4.3_

- [x] 3.1 Implement function name keyword filtering rule
  - Create adaptation rule `fix_function_name_keywords`
  - Detect when function name is a SQL keyword
  - Recover correct name from raw_text using regex
  - Apply to platforms: windows-3.12, ubuntu-3.12
  - _Requirements: 1.2, 4.3_

- [x] 3.2 Write property test for function name normalization
  - **Property 4: Transformation normalization (function names)**
  - **Validates: Requirements 1.2, 4.3**
  - Test that SQL keywords are not extracted as function names
  - Test that correct names are recovered from raw_text
  - _Requirements: 1.2, 4.3_

- [x] 3.3 Implement trigger name correction rule
  - Create adaptation rule `fix_trigger_name_description`
  - Detect when trigger name is incorrectly set to "description"
  - Recover correct name from raw_text using regex
  - Apply to platforms: darwin-3.12, darwin-3.13
  - _Requirements: 1.2, 4.3_

- [x] 3.4 Write property test for trigger name normalization
  - **Property 4: Transformation normalization (trigger names)**
  - **Validates: Requirements 1.2, 4.3**
  - Test that incorrect trigger names are corrected
  - Test that correct names are preserved
  - _Requirements: 1.2, 4.3_

- [x] 3.5 Implement phantom element removal rule
  - Create adaptation rule `remove_phantom_triggers`
  - Detect elements where type doesn't match content
  - Check for "CREATE TRIGGER" in raw_text for trigger elements
  - Return None to remove phantom elements
  - Apply to platforms: ubuntu-3.12
  - _Requirements: 1.2, 4.3_

- [x] 3.6 Write property test for phantom element removal
  - **Property 4: Transformation normalization (phantom removal)**
  - **Validates: Requirements 1.2, 4.3**
  - Test that phantom elements are removed
  - Test that valid elements are preserved
  - _Requirements: 1.2, 4.3_

- [x] 3.7 Implement view recovery from ERROR nodes
  - Create adaptation rule `recover_views_from_errors`
  - Scan source code for CREATE VIEW statements using regex
  - Create SQLView elements for missing views
  - Extract source tables from view definition
  - Apply to all platforms
  - _Requirements: 1.2, 4.3_

- [x] 3.8 Write property test for view recovery
  - **Property 4: Transformation normalization (view recovery)**
  - **Validates: Requirements 1.2, 4.3**
  - Test that views in ERROR nodes are recovered
  - Test that recovered views have correct attributes
  - _Requirements: 1.2, 4.3_

- [x] 3.9 Implement adaptation rule registry
  - Create registry mapping platform_key to list of rules
  - Load rules from behavior profile
  - Support wildcard rules (apply to all platforms)
  - Implement rule priority/ordering
  - _Requirements: 4.2, 4.3_

- [x] 3.10 Write property test for adaptation idempotence
  - **Property 15: Adaptation rule idempotence**
  - **Validates: Requirements 4.3**
  - Test that applying adaptations twice produces same result as once
  - Test for all adaptation rules
  - _Requirements: 4.3_

- [x] 3.11 Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Phase 4: Integration with SQL Plugin

- [x] 4. Integrate platform detection into SQL plugin
  - Modify `tree_sitter_analyzer/languages/sql_plugin.py`
  - Add platform detection in `SQLPlugin.__init__()`
  - Load behavior profile for current platform
  - Initialize CompatibilityAdapter with loaded profile
  - Handle missing profile gracefully (use defaults, log warning)
  - _Requirements: 1.4, 4.1, 4.2_

- [x] 4.1 Integrate adapter into element extraction pipeline
  - Modify `SQLElementExtractor.extract_sql_elements()`
  - Apply adapter after initial extraction
  - Apply adapter before existing `_validate_and_fix_elements()`
  - Preserve existing validation logic
  - _Requirements: 1.2, 4.3_

- [x] 4.2 Write property test for output schema consistency
  - **Property 5: Output schema consistency**
  - **Validates: Requirements 4.5**
  - Test that adapted output has same schema across platforms
  - Test that all required attributes are present
  - _Requirements: 4.5_

- [x] 4.3 Implement diagnostic logging
  - Add diagnostic mode flag to SQLPlugin
  - Log loaded profile information
  - Log applied adaptation rules
  - Log original and normalized results
  - Include platform info, parser version, profile version
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 4.4 Write property test for diagnostic logging
  - **Property 11: Comprehensive diagnostic logging**
  - **Validates: Requirements 5.2, 5.3, 5.4**
  - Test that diagnostics contain all required information
  - Test that transformations are logged
  - _Requirements: 5.2, 5.3, 5.4_

- [x] 4.5 Implement graceful degradation for SQL failures
  - Wrap SQL parsing in try-except
  - Continue with other languages if SQL fails
  - Log detailed error with platform info
  - Suggest workarounds in error message
  - _Requirements: 7.1, 7.2, 7.3_

- [x] 4.6 Write property test for language isolation
  - **Property 13: Language isolation**
  - **Validates: Requirements 7.1**
  - Test that SQL failure doesn't affect other languages
  - Test that Java, Python, JavaScript still work when SQL fails
  - _Requirements: 7.1_

- [x] 4.7 Implement MCP capability management
  - Modify `tree_sitter_analyzer/mcp/server.py`
  - Check if SQL parsing is available on current platform
  - Remove SQL tools from capabilities if unavailable
  - Add platform info to MCP server metadata
  - _Requirements: 7.5_

- [x] 4.8 Write property test for MCP capability consistency
  - **Property 14: MCP capability consistency**
  - **Validates: Requirements 7.5**
  - Test that SQL tools are removed when SQL is disabled
  - Test that other tools remain available
  - _Requirements: 7.5_

- [x] 4.9 Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Phase 5: CI/CD Integration and Testing

- [x] 5. Create GitHub Actions workflow for platform matrix
  - Create `.github/workflows/sql-platform-compat.yml`
  - Define matrix: 3 OS × 4 Python versions = 12 combinations
  - Set fail-fast: false to test all combinations
  - Install dependencies including tree-sitter-sql
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 5.1 Implement behavior recording step in CI
  - Add step to run `python -m tree_sitter_analyzer.platform_compat.record`
  - Save generated profiles as artifacts
  - Upload artifacts with naming: `profile-{os}-{python-version}`
  - _Requirements: 3.1, 3.2_

- [x] 5.2 Implement profile comparison step in CI
  - Add step to compare generated profiles with baselines
  - Run `python -m tree_sitter_analyzer.platform_compat.compare`
  - Fail build if significant differences detected
  - Generate diff report as artifact
  - _Requirements: 3.2, 3.3_

- [x] 5.3 Implement compatibility matrix report generation
  - Create `tree_sitter_analyzer/platform_compat/report.py`
  - Implement `generate_compatibility_matrix()` function
  - Show support status for each platform-Python combination
  - Include known issues and workarounds
  - Output as Markdown table
  - _Requirements: 3.5_

- [x] 5.4 Write property test for matrix report generation
  - **Property 10: Compatibility matrix generation**
  - **Validates: Requirements 3.5**
  - Test that report includes all tested platforms
  - Test that report shows correct support status
  - _Requirements: 3.5_

- [x] 5.5 Run existing property tests in CI matrix
  - Add step to run `pytest tests/test_sql_function_extraction_properties.py`
  - Run on all platform combinations
  - Collect and report failures by platform
  - _Requirements: 3.1_

- [x] 5.6 Write property test for cross-platform equivalence
  - **Property 1: Cross-platform parsing equivalence**
  - **Validates: Requirements 1.1**
  - Test that same SQL code produces equivalent results on different platforms
  - Use Hypothesis to generate random SQL code
  - Mock different platforms and compare results
  - _Requirements: 1.1_

- [x] 5.7 Create baseline profiles for supported platforms
  - Run recording on all supported platforms
  - Review and validate generated profiles
  - Store in `tests/platform_profiles/baseline/`
  - Commit to version control
  - _Requirements: 2.3, 2.5_

- [x] 5.8 Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Phase 6: Documentation and CLI Tools

- [x] 6. Create user documentation
  - Create `docs/sql-cross-platform-compatibility.md`
  - Document supported platforms and known issues
  - Explain how to record custom profiles
  - Provide troubleshooting guide
  - Include examples of error messages and solutions
  - _Requirements: 1.5, 7.2, 7.4_

- [x] 6.1 Implement CLI command for platform information
  - Add command: `tree-sitter-analyzer --sql-platform-info`
  - Display current platform detection results
  - Show loaded profile information
  - List available adaptation rules
  - Show SQL parsing capabilities
  - _Requirements: 5.5_

- [x] 6.2 Implement CLI command for profile recording
  - Add command: `tree-sitter-analyzer --record-sql-profile`
  - Run behavior recording on current platform
  - Save profile to default or custom location
  - Display recording results
  - _Requirements: 2.1, 2.3_

- [x] 6.3 Implement CLI command for profile comparison
  - Add command: `tree-sitter-analyzer --compare-sql-profiles <profile1> <profile2>`
  - Load and compare two profiles
  - Display differences in human-readable format
  - Suggest adaptation rules for differences
  - _Requirements: 2.4_

- [x] 6.4 Create troubleshooting guide
  - Document common platform-specific issues
  - Provide step-by-step debugging procedures
  - Include diagnostic mode usage examples
  - List workarounds for unsupported platforms
  - _Requirements: 1.3, 7.2, 7.3_

- [x] 6.5 Update main README with platform compatibility info
  - Add section on SQL cross-platform support
  - List supported platforms
  - Link to detailed documentation
  - Include quick start for recording profiles
  - _Requirements: 1.5_

- [x] 6.6 Create migration guide for existing users
  - Explain changes to SQL parsing behavior
  - Document how to enable/disable adaptation layer
  - Provide examples of before/after behavior
  - Explain profile recording process
  - _Requirements: Backward compatibility_

- [x] 6.7 Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - Run full test suite on all platforms
  - Verify documentation accuracy
  - Check that all requirements are met
