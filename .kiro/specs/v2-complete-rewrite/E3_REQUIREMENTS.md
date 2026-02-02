# E3: Cross-File Call Resolution - Requirements

**Enhancement**: E3 (Cross-File Call Resolution)
**Priority**: P1 (High)
**Complexity**: High (6+ hours)
**Date**: 2026-02-01
**Part of**: v2-complete-rewrite Code Graph Enhancements

---

## 现状分析 (Current State Analysis)

### What We Have (After E1, E2, E4)
- ✅ **Within-file call tracking**: `main() -> helper()` in same file
- ✅ **Multi-file analysis**: Can analyze multiple files in parallel
- ✅ **Import recording**: Track import statements (partial support)
- ✅ **Visualization**: Mermaid diagrams for code structure

### What We're Missing
- ❌ **Cross-file call resolution**: Cannot track calls across file boundaries
- ❌ **Import relationship graph**: No import dependency tracking
- ❌ **Global symbol table**: No project-wide function registry
- ❌ **Name aliasing resolution**: Cannot resolve `import numpy as np`

### Current Limitation Example

**file1.py**:
```python
def helper():
    return 42
```

**file2.py**:
```python
from file1 import helper

def main():
    return helper()  # <-- NOT tracked as cross-file call
```

**Current behavior**: `main() -> helper` edge NOT created (different files)
**Desired behavior**: `file2.main() -> file1.helper()` edge created

---

## 问题识别 (Problem Identification)

### Problem 1: Import Resolution Complexity

**Challenge**: Python import system is complex
- Absolute imports: `from package.module import func`
- Relative imports: `from . import sibling`, `from .. import parent`
- Aliasing: `import numpy as np`, `from x import y as z`
- Dynamic imports: `importlib.import_module()` (cannot be statically analyzed)
- Package structure: `__init__.py` re-exports

**Impact**: Cannot reliably map import names to actual file paths

### Problem 2: Name Resolution Ambiguity

**Challenge**: Multiple definitions of same function name
- Different modules can have functions with same name
- Need to determine which function is called based on import context

**Example**:
```python
# utils/string.py
def format():
    pass

# utils/number.py
def format():
    pass

# app.py
from utils.string import format  # Which format()?
format()  # <-- Need to resolve correctly
```

### Problem 3: Performance at Scale

**Challenge**: Large projects have thousands of files
- Building symbol table requires parsing all files
- Cross-file resolution requires graph traversal
- Memory usage for large projects

**Constraint**: Medium-sized project (500 files) should analyze in <30 seconds

### Problem 4: Python Path Resolution

**Challenge**: Python module resolution depends on:
- `sys.path` configuration
- Virtual environment setup
- `PYTHONPATH` environment variable
- Package installation location

**Impact**: Static analysis cannot know actual module locations without runtime context

---

## 目标定义 (Goals & Objectives)

### Primary Goal
**Enable cross-file call tracking for Python projects**

Track function calls across file boundaries to build a complete project-level call graph.

### Specific Objectives

#### O1: Import Relationship Tracking
- Parse import statements from all files
- Build import dependency graph (file → imported files)
- Support absolute and relative imports
- Handle common aliasing patterns

#### O2: Global Symbol Table
- Build project-wide function registry
- Map function names to file locations
- Handle multiple definitions (track all occurrences)
- Support class methods and module-level functions

#### O3: Cross-File Call Resolution
- Resolve function calls to their definitions across files
- Use import context to disambiguate
- Add cross-file CALLS edges to graph
- Mark edges with `cross_file=True` attribute

#### O4: Performance Optimization
- Analyze medium projects (<500 files) in <30 seconds
- Use caching to avoid re-parsing unchanged files
- Parallel processing where possible

---

## 非功能性要求 (Non-functional Requirements)

### NFR1: Accuracy
- **Target**: 90%+ accuracy for common import patterns
- **Acceptable**: False negatives for dynamic imports (skip rather than guess)
- **Not Acceptable**: False positives (incorrect cross-file edges)

### NFR2: Performance
- **Small project** (<50 files): <5 seconds
- **Medium project** (50-500 files): <30 seconds
- **Large project** (500+ files): <2 minutes (best effort)

### NFR3: Robustness
- Handle parse errors gracefully (skip problematic files)
- Continue analysis even if some imports cannot be resolved
- Provide warnings for unresolved imports (debugging)

### NFR4: Maintainability
- Clear separation of concerns (ImportResolver, SymbolTable, CallResolver)
- Well-tested components (80%+ coverage)
- Comprehensive documentation

### NFR5: Backward Compatibility
- Do not break existing E1, E2, E4 functionality
- Cross-file resolution is opt-in (default: within-file only)
- All existing tests must pass

---

## 用例场景 (Use Cases)

### UC1: Impact Analysis
**Actor**: Developer refactoring code
**Goal**: Understand what breaks if I change this function

**Scenario**:
1. Developer wants to refactor `utils/parser.py::parse_data()`
2. Run: `find_function_callers --cross-file utils/parser.py parse_data`
3. See ALL callers across entire project (not just same file)
4. Identify all affected files before refactoring

**Value**: Prevents breaking changes

### UC2: Dependency Understanding
**Actor**: New developer onboarding
**Goal**: Understand how the project is structured

**Scenario**:
1. New developer joins project
2. Run: `visualize_code_graph --directory src --type dependency --cross-file`
3. See module dependency graph showing import relationships
4. Understand architecture without reading all code

**Value**: Faster onboarding

### UC3: Dead Code Detection
**Actor**: Maintainer cleaning up codebase
**Goal**: Find unused functions across project

**Scenario**:
1. Maintainer suspects `old_utils.py::legacy_function()` is unused
2. Run: `find_function_callers --cross-file old_utils.py legacy_function`
3. Result: No callers found (not called anywhere in project)
4. Safe to delete

**Value**: Code cleanup confidence

### UC4: Call Chain Tracing
**Actor**: Developer debugging production issue
**Goal**: Understand execution flow across multiple files

**Scenario**:
1. Bug in production: `api/routes.py::handle_request()` fails
2. Run: `query_call_chain --cross-file --start handle_request --end database_query`
3. See full call chain: `routes.py::handle_request` → `service.py::process` → `db.py::database_query`
4. Identify where error propagates

**Value**: Faster debugging

---

## 术语表 (Glossary)

| Term | Definition |
|------|------------|
| **Cross-file call** | Function call where caller and callee are in different files |
| **Import graph** | Directed graph of file → imported files relationships |
| **Symbol table** | Project-wide registry mapping function names to file locations |
| **Import resolver** | Component that maps import statements to file paths |
| **Call resolver** | Component that resolves function calls to definitions using import context |
| **Absolute import** | Import using full package path: `from package.module import func` |
| **Relative import** | Import relative to current file: `from . import sibling` |
| **Aliasing** | Import with rename: `import numpy as np` or `from x import y as z` |
| **Module path** | Python module identifier (e.g., `package.subpackage.module`) |
| **File path** | Filesystem path to .py file |

---

## 约束与假设 (Constraints & Assumptions)

### Constraints
- **C1**: Python-only (no Java/TypeScript for E3)
- **C2**: Static analysis only (no runtime execution)
- **C3**: Standard Python import system (no custom import hooks)
- **C4**: Project root must be identified (for resolving absolute imports)

### Assumptions
- **A1**: Most projects use standard import patterns (not heavy `importlib` usage)
- **A2**: Project has clear package structure with `__init__.py` files
- **A3**: Code is parseable (valid Python syntax)
- **A4**: Virtual environment is typical Python project structure

### Out of Scope (Explicitly NOT Supported)
- ❌ Dynamic imports via `importlib.import_module()`
- ❌ Conditional imports inside if-statements (complex heuristics)
- ❌ Import hooks or custom import machinery
- ❌ Cross-language calls (Python calling Java, etc.)
- ❌ Monkey-patching or runtime function replacement

---

## 成功标准 (Success Criteria)

### Must Have (P0)
- ✅ Resolve absolute imports (`from package.module import func`)
- ✅ Resolve relative imports (`from . import sibling`)
- ✅ Build global symbol table (all functions mapped to files)
- ✅ Add cross-file CALLS edges to graph
- ✅ 90%+ accuracy on test projects
- ✅ 80%+ test coverage
- ✅ Documentation complete

### Should Have (P1)
- ✅ Handle import aliasing (`import numpy as np`)
- ✅ Support `from x import *` (with warnings)
- ✅ Performance: <30s for 500 files
- ✅ Warnings for unresolved imports

### Nice to Have (P2)
- 🔲 Incremental cross-file resolution (cache import graph)
- 🔲 Visual indicator in Mermaid diagrams (cross-file edges styled differently)
- 🔲 Statistics (% of calls resolved, # unresolved imports)

---

## 风险评估 (Risk Assessment)

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Import resolution too complex** | High | High | Start with simple cases, incremental complexity |
| **Performance degradation** | Medium | High | Parallel processing, caching, profiling |
| **False positives** | Medium | Medium | Conservative resolution (skip when ambiguous) |
| **Breaking existing features** | Low | High | Comprehensive regression testing |
| **Scope creep** | High | Medium | Strict phase-based approach, clear acceptance criteria |

---

## 验收流程 (Acceptance Process)

1. **Requirements Review**: This document reviewed and approved ✅
2. **Design Review**: E3_DESIGN.md created and approved
3. **Implementation**: Follow E3_TASKS.md with TDD approach
4. **Testing**: All tests passing, 80%+ coverage
5. **Documentation**: User-facing docs updated
6. **Performance Validation**: Benchmarks meet targets
7. **Integration Testing**: No regressions in E1, E2, E4

---

**Requirements Status**: ✅ READY FOR DESIGN PHASE

**Next Step**: Create E3_DESIGN.md with technical architecture

**Related Documents**:
- CODE_GRAPH_ENHANCEMENTS.md - Original enhancement specifications
- CODE_GRAPH_PROGRESS.md - Overall progress (E1, E2, E4 complete)
- PRODUCTION_READY.md - Current production status
