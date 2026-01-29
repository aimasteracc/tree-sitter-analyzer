# Requirements: Code Quality Analysis & Refactoring

## 现状分析 (Current State Analysis)

### Project Overview
- **Project**: tree-sitter-analyzer
- **Language**: Python 3.10+
- **Total Modules**: 100+ Python files
- **Core Packages**: 10 major packages (core, plugins, languages, formatters, mcp, cli, etc.)

### Current Code Quality Issues

#### Critical Problems Identified
1. **Monster Method**: [`SearchContentTool.execute()`](tree_sitter_analyzer/mcp/tools/search_content_tool.py:337-947)
   - 610 lines in single method
   - Complexity: 176
   - Unmaintainable, untestable, undebuggable

2. **God Module**: [`fd_rg_utils.py`](tree_sitter_analyzer/mcp/tools/fd_rg_utils.py)
   - 825 lines
   - 25 functions with mixed responsibilities
   - 16-18 parameters per function
   - Global mutable state

3. **God Class**: [`UnifiedAnalysisEngine`](tree_sitter_analyzer/core/analysis_engine.py:29-514)
   - 485 lines
   - 32 methods
   - 10+ responsibilities
   - Singleton pattern abuse

4. **Tool Bug**: `check_code_scale` reports incorrect metrics
   - Reports "classes: 0, methods: 0" for files with classes
   - Makes automated analysis unreliable

5. **Test Code in Production**: `MockLanguagePlugin` in production file

## 问题识别 (Problem Identification)

### Impact on Development
- **Maintainability**: 🔴 Critical - Cannot maintain 610-line methods
- **Testability**: 🔴 Critical - Cannot write unit tests for God classes
- **Debuggability**: 🔴 Critical - Bug location unclear in massive methods
- **Code Review**: 🔴 Critical - Reviewers cannot understand entire flow
- **Onboarding**: 🔴 Critical - New developers will be lost
- **Performance**: 🟡 Moderate - Some optimization opportunities

### Root Causes
1. **No Separation of Concerns**: All logic in single methods/classes
2. **No Design Patterns**: Missing Strategy, Builder, Command patterns
3. **Parameter Explosion**: Functions with too many parameters
4. **Global State**: Module-level mutable dictionaries
5. **Mixed Responsibilities**: Single modules doing multiple things

## 目标定义 (Goals & Objectives)

### Primary Goals
1. **Refactor Monster Method** (SearchContentTool.execute)
   - Break into 10-15 smaller methods
   - Apply Strategy pattern for search modes
   - Apply Command pattern for execution flow
   - Target: <50 lines per method, complexity <15

2. **Split God Module** (fd_rg_utils.py)
   - Create 5 separate modules
   - Apply Builder pattern for command construction
   - Remove global mutable state
   - Target: <300 lines per module

3. **Refactor God Class** (UnifiedAnalysisEngine)
   - Extract singleton logic to factory
   - Split into 5 focused classes
   - Move test code to tests/
   - Target: <200 lines per class

4. **Fix Tool Bug** (check_code_scale)
   - Debug tree-sitter parsing
   - Add regression tests
   - Ensure reliable metrics

5. **Implement TDD**
   - Write tests before refactoring
   - Maintain >80% coverage
   - All tests passing

### Success Metrics
**Before**:
- Largest method: 610 lines
- Largest module: 947 lines
- Average complexity: 30-176
- Test coverage: Unknown

**Target After**:
- Max method size: 50 lines
- Max module size: 300 lines
- Max complexity: 15
- Test coverage: >80%
- All tests passing

## 非功能性要求 (Non-functional Requirements)

### Performance
- No regression on existing benchmarks
- Cache performance maintained
- Startup time not increased

### Compatibility
- Backward compatible API
- No breaking changes for users
- MCP tools continue working

### Quality
- 100% mypy compliance
- All ruff checks passing
- Comprehensive docstrings

### Testing
- Unit tests for all new methods
- Integration tests maintained
- Regression tests passing

## 用例场景 (Use Cases)

### UC1: Developer Fixes Bug in SearchContentTool
**Before**: Must read 610 lines to understand flow  
**After**: Read specific 30-line method for bug location

### UC2: Developer Adds New Search Mode
**Before**: Modify 610-line execute() method, risk breaking everything  
**After**: Add new Strategy class, no risk to existing modes

### UC3: Code Reviewer Reviews PR
**Before**: Cannot review 600-line method effectively  
**After**: Review focused 30-50 line methods with clear purpose

### UC4: New Developer Onboards
**Before**: Overwhelmed by God classes and monster methods  
**After**: Understand focused classes with single responsibility

## 术语表 (Glossary)

- **God Class**: Class with too many responsibilities (>10)
- **Monster Method**: Method with >100 lines or complexity >20
- **God Module**: Module with >500 lines and mixed responsibilities
- **Parameter Explosion**: Function with >10 parameters
- **Global Mutable State**: Module-level mutable variables
- **Strategy Pattern**: Design pattern for interchangeable algorithms
- **Builder Pattern**: Design pattern for complex object construction
- **Command Pattern**: Design pattern for encapsulating requests
- **TDD**: Test-Driven Development
- **SOLID**: Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion

## 验收标准 (Acceptance Criteria)

### Phase 1: Analysis Complete ✓
- [x] Module inventory created
- [x] Critical issues identified
- [x] Comprehensive report generated
- [x] Priority order established

### Phase 2: Code Skeptic Analysis Complete ✓
- [x] 4 core modules analyzed
- [x] 13 issues documented
- [x] Evidence collected
- [x] Recommendations provided

### Phase 3: Code Simplifier Fixes (READY)
**Status**: Characterization tests ready, refactoring can begin
**Awaiting**: User approval to start

- [ ] SearchContentTool.execute() refactored
- [ ] fd_rg_utils.py split into modules
- [ ] UnifiedAnalysisEngine refactored
- [ ] check_code_scale bug fixed
- [ ] Test code moved to tests/

### Phase 4: TDD Implementation (Pending)
- [ ] Characterization tests written
- [ ] Unit tests for all new methods
- [ ] Integration tests updated
- [ ] All tests passing
- [ ] Coverage >80%
