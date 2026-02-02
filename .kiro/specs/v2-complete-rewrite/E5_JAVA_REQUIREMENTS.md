# E5: Java Code Graph Support - Requirements

**Enhancement**: E5 (Java Language Support for Code Graph)
**Date**: 2026-02-02
**Priority**: P1 (High Value)
**Estimated Duration**: 8-12 hours

---

## 现状分析 (Current State Analysis)

### Existing Capabilities

**Python Code Graph (✅ Complete)**:
- Module/Class/Function node extraction
- CONTAINS edges (Module → Class → Function)
- CALLS edges (intra-file and cross-file)
- Import resolution and cross-file call tracking
- Mermaid visualization
- MCP tool integration

**Java Language Support (⚠️ Partial)**:
- ✅ Java parser exists (`java_parser.py`, 816 lines)
- ✅ Extracts: classes, interfaces, methods, imports, package
- ✅ Supports: annotations (Spring/JPA/Lombok), generics, records
- ❌ **No Code Graph integration**
- ❌ **No method call extraction**
- ❌ **No call graph visualization**

### Architecture Analysis

**CodeGraphBuilder** (`graph/builder.py`):
- Currently **Python-only** implementation
- Uses `PythonParser` for parsing
- Extracts Python `call` nodes for method invocations
- Works with Python import syntax (`import`, `from...import`)

**Key Insight**: Need **language-specific** method call extraction because:
- Python uses `call` AST node type
- Java uses `method_invocation` AST node type
- Different import systems (Python vs Java package/import)

---

## 问题识别 (Problem Identification)

### P1: No Java Code Graph Support

**Problem**: Java developers cannot use Code Graph features for their projects.

**Impact**:
- Cannot trace Java method calls
- Cannot visualize Java class hierarchies
- Cannot perform impact analysis on Java code
- Limits tool's applicability to Python-only projects

**User Story**:
> As a Java developer, I want to analyze my Spring Boot application's method call graph to understand which services call which repositories, so I can refactor safely.

### P2: Language-Specific Method Call Extraction

**Problem**: Method invocation syntax varies by language.

**Details**:
- **Python**: `func()`, `obj.method()`, tree-sitter node type: `call`
- **Java**: `method()`, `obj.method()`, `Class.staticMethod()`, tree-sitter node type: `method_invocation`
- **Java-specific**: Constructor calls (`new ClassName()`), super/this calls

**Impact**: Cannot reuse Python call extraction logic directly.

### P3: Java Import Resolution Complexity

**Problem**: Java imports differ from Python imports.

**Differences**:

| Aspect | Python | Java |
|--------|--------|------|
| Syntax | `import pkg.module` | `import pkg.ClassName;` |
| Wildcards | Not common | `import pkg.*;` |
| Static imports | N/A | `import static pkg.Class.method;` |
| Package structure | File-based | Directory = package |

**Impact**: Need Java-specific import resolver.

### P4: Java Class Hierarchy

**Problem**: Java has inheritance and interface implementation.

**Features to support**:
- `extends ParentClass` (inheritance)
- `implements Interface1, Interface2` (interface implementation)
- Abstract methods
- Method overriding

**Impact**: Code Graph should track inheritance relationships.

---

## 目标定义 (Goals & Objectives)

### Primary Goals

#### G1: Java Code Graph Construction ✅
**Goal**: Build NetworkX graphs from Java source files with same quality as Python.

**Success Criteria**:
- Extract Module, Class, Interface, Method nodes
- Build CONTAINS edges (Module → Class → Method)
- Build CALLS edges (Method → Method)
- Support intra-file method calls
- 80%+ test coverage

#### G2: Java Method Call Tracking ✅
**Goal**: Accurately track Java method invocations.

**Success Criteria**:
- Detect `method()` calls
- Detect `obj.method()` calls
- Detect `Class.staticMethod()` calls
- Detect constructor calls (`new ClassName()`)
- Ignore standard library calls (java.*, javax.*)

#### G3: Java Cross-File Call Resolution ✅
**Goal**: Resolve method calls across Java files using import analysis.

**Success Criteria**:
- Parse Java imports (`import pkg.ClassName;`)
- Resolve method calls to definitions in imported classes
- Handle wildcard imports (`import pkg.*;`)
- Conservative strategy (skip ambiguous cases)

#### G4: Java Inheritance Tracking (Optional)
**Goal**: Track inheritance and interface relationships.

**Success Criteria**:
- EXTENDS edges (Class → ParentClass)
- IMPLEMENTS edges (Class → Interface)
- OVERRIDES edges (Method → ParentMethod)

**Note**: This is a stretch goal - start with basic call tracking first.

### Non-Functional Requirements

#### NFR1: Performance
- Build graph for 100 Java files in <30 seconds
- No memory issues with large codebases (1000+ files)
- Parallel processing support (same as Python)

#### NFR2: Compatibility
- Work with Java 8+ syntax (lambdas, streams, method references)
- Support Java 14+ features (records, switch expressions)
- Handle Spring framework annotations

#### NFR3: Backward Compatibility
- No breaking changes to Python Code Graph
- Reuse existing infrastructure (ImportResolver pattern, SymbolTable, CrossFileCallResolver pattern)
- Same MCP tool interface

#### NFR4: Code Quality
- 80%+ test coverage for new code
- TDD approach (tests first)
- Type hints for all public APIs
- Docstrings with examples

---

## 用例场景 (Use Cases)

### UC1: Analyze Spring Boot Application

**Actor**: Backend Java Developer

**Goal**: Understand service layer dependencies

**Scenario**:
```java
// UserService.java
@Service
public class UserService {
    @Autowired
    private UserRepository userRepo;

    public User findUser(Long id) {
        return userRepo.findById(id);  // Call to repository
    }
}

// UserRepository.java
@Repository
public interface UserRepository extends JpaRepository<User, Long> {
    User findById(Long id);
}
```

**Expected Result**:
- Code Graph shows: `UserService.findUser` → CALLS → `UserRepository.findById`
- Visualization shows service → repository dependency
- MCP tool can answer: "Which services call UserRepository?"

### UC2: Refactoring Impact Analysis

**Actor**: Java Developer

**Goal**: Understand impact of changing a method signature

**Scenario**:
```java
// Before refactoring validateUser() in AuthHelper
// Want to know: which methods call validateUser()?
```

**Expected Result**:
- `find_function_callers` MCP tool returns all callers
- Code Graph shows call chain from controllers → services → helpers
- Developer can assess refactoring risk

### UC3: Microservice Boundary Analysis

**Actor**: Architect

**Goal**: Identify tightly coupled classes for service decomposition

**Scenario**:
- Large monolithic Spring Boot application
- Want to split into microservices
- Need to identify class clusters with high internal coupling

**Expected Result**:
- Code Graph shows method call density between packages
- Visualization reveals natural boundaries
- Can export graph for further analysis

### UC4: Cross-File Call Discovery

**Actor**: New team member

**Goal**: Understand how a REST endpoint is implemented

**Scenario**:
```java
// UserController.java
@RestController
public class UserController {
    @GetMapping("/users/{id}")
    public User getUser(@PathVariable Long id) {
        return userService.findUser(id);  // Where is this defined?
    }
}
```

**Expected Result**:
- Code Graph resolves `userService.findUser` to `UserService.java`
- Can trace full call chain: Controller → Service → Repository → Database
- Cross-file CALLS edges marked with `cross_file=True`

---

## 术语表 (Glossary)

| Term | Definition |
|------|------------|
| **Method Invocation** | Java AST node type for method calls (`methodName()`) |
| **Qualified Name** | Full class name including package (e.g., `com.example.User`) |
| **Static Import** | Import specific static methods: `import static Math.max;` |
| **Wildcard Import** | Import all classes in package: `import java.util.*;` |
| **Constructor Call** | Object instantiation: `new ClassName()` |
| **Super Call** | Parent class method call: `super.method()` |
| **This Call** | Same class method call: `this.method()` |
| **FQN** | Fully Qualified Name (package + class name) |

---

## 验收标准 (Acceptance Criteria)

### Functional Acceptance

- [ ] Can build Code Graph from single Java file
- [ ] Can build Code Graph from Java directory (multi-file)
- [ ] Extracts Module, Class, Interface, Method nodes
- [ ] Creates CONTAINS edges (Module → Class → Method)
- [ ] Creates CALLS edges (Method → Method) for intra-file calls
- [ ] Creates cross-file CALLS edges with import resolution
- [ ] Handles Java inheritance (extends, implements) - Optional
- [ ] Exports to TOON format
- [ ] Exports to Mermaid diagrams
- [ ] Integrates with MCP tools

### Non-Functional Acceptance

- [ ] 80%+ test coverage on new Java code
- [ ] Performance: <30s for 100 Java files
- [ ] No regressions in Python Code Graph tests
- [ ] All public APIs have type hints and docstrings
- [ ] Examples in documentation

---

## 技术约束 (Technical Constraints)

### TC1: Reuse Existing Architecture
- Must follow same pattern as Python Code Graph
- Use NetworkX for graph storage
- Use tree-sitter for parsing

### TC2: No Breaking Changes
- Python Code Graph must continue working
- Existing MCP tools must remain compatible
- Same graph structure (nodes, edges, attributes)

### TC3: Java-Specific Challenges
- Handle Java package system (not file-based like Python)
- Support static imports and wildcard imports
- Deal with method overloading (same name, different parameters)

---

## 优先级排序 (Prioritization)

| Priority | Feature | Justification |
|----------|---------|---------------|
| **P0 (Must Have)** | Basic Java Code Graph (Module, Class, Method nodes) | Core functionality |
| **P0 (Must Have)** | Intra-file method call tracking | Essential for basic use cases |
| **P1 (High)** | Cross-file call resolution with imports | High value, enables full project analysis |
| **P1 (High)** | MCP tool integration | Makes it usable by Claude |
| **P2 (Medium)** | Inheritance tracking (extends, implements) | Nice to have, can add later |
| **P3 (Low)** | Method overriding detection | Complex, low immediate value |

---

## 下一步 (Next Steps)

1. ✅ Create `E5_JAVA_DESIGN.md` - Technical design
2. ✅ Create `E5_JAVA_TASKS.md` - Task breakdown
3. ✅ Start implementation with TDD approach

---

**Status**: ✅ Requirements Complete
**Ready for**: Design Phase
