# Java Test Fixture Project

This is a realistic Java test project used for E2E testing of the Java Code Graph implementation.

## Project Structure

```
java_project/
└── src/main/java/com/example/
    ├── App.java                    # Main entry point
    ├── service/
    │   ├── UserService.java        # Business logic layer
    │   └── EmailService.java       # Email notification service
    └── repository/
        └── UserRepository.java     # Data access layer
```

## Architecture

This project follows a simple 3-tier architecture:

1. **Application Layer** (`App.java`)
   - Entry point with `main()` method
   - Orchestrates services

2. **Service Layer** (`service/`)
   - `UserService.java`: User management business logic
   - `EmailService.java`: Email notification logic

3. **Repository Layer** (`repository/`)
   - `UserRepository.java`: User data access

## Call Graph Structure

### Expected Nodes

**Modules (4)**:
- `App`
- `UserService`
- `EmailService`
- `UserRepository`

**Classes (4)**:
- `com.example.App`
- `com.example.service.UserService`
- `com.example.service.EmailService`
- `com.example.repository.UserRepository`

**Methods (11)**:
- `App.main` (static)
- `App.run`
- `UserService.createUser` (returns User)
- `UserService.deleteUser` (returns boolean)
- `UserService.validateEmail` (private, returns boolean)
- `EmailService.sendWelcomeEmail`
- `EmailService.sendGoodbyeEmail`
- `EmailService.formatMessage` (private)
- `UserRepository.save`
- `UserRepository.delete`
- `UserRepository.findByEmail`

### Expected Edges

**CONTAINS Edges (15)**:
- Module → Class: 4 edges
- Class → Method: 11 edges

**CALLS Edges (9 total, 6 cross-file)**:

**Intra-file calls (3)**:
1. `UserService.createUser` → `UserService.validateEmail` (same file)
2. `UserService.deleteUser` → `UserService.validateEmail` (same file)
3. `EmailService.sendWelcomeEmail` → `EmailService.formatMessage` (same file)

**Cross-file calls (6)**:
1. `App.main` → `App.run` (technically same file, but static → instance)
2. `App.run` → `UserService.createUser` (App → UserService)
3. `UserService.createUser` → `UserRepository.save` (UserService → UserRepository)
4. `UserService.createUser` → `EmailService.sendWelcomeEmail` (UserService → EmailService)
5. `UserService.deleteUser` → `UserRepository.delete` (UserService → UserRepository)
6. `UserService.deleteUser` → `EmailService.sendGoodbyeEmail` (UserService → EmailService)

### Import Structure

**App.java imports**:
- `com.example.service.UserService`

**UserService.java imports**:
- `com.example.repository.UserRepository`
- `com.example.service.EmailService`

**EmailService.java imports**: (none)

**UserRepository.java imports**: (none)

## Performance Expectations

- Graph construction: < 500ms
- Node count: 15 (4 modules + 4 classes + 11 methods)
- Edge count: 24 (15 CONTAINS + 9 CALLS)
- Cross-file edge count: 6

## Test Scenarios

### Scenario 1: Full Project Analysis
```python
builder = CodeGraphBuilder(language="java")
graph = builder.build_from_directory(
    "tests/fixtures/java_project/src/main/java",
    pattern="**/*.java",
    cross_file=True
)

assert graph.number_of_nodes() == 19  # 4 modules + 4 classes + 11 methods
assert graph.number_of_edges() == 24  # 15 CONTAINS + 9 CALLS
```

### Scenario 2: Cross-File Call Detection
```python
cross_file_calls = [
    (u, v) for u, v, d in graph.edges(data=True)
    if d.get('type') == 'CALLS' and d.get('cross_file') is True
]

assert len(cross_file_calls) == 6
```

### Scenario 3: Impact Analysis
```python
# Find all callers of UserRepository.save
callers = [
    source for source, target, data in graph.edges(data=True)
    if data.get('type') == 'CALLS'
    and graph.nodes[target].get('name') == 'save'
]

assert 'createUser' in [graph.nodes[c].get('name') for c in callers]
```

### Scenario 4: Call Chain Tracing
```python
# Trace call chain from main() to UserRepository.save()
import networkx as nx

main_node = next(n for n, d in graph.nodes(data=True) if d.get('name') == 'main')
save_node = next(n for n, d in graph.nodes(data=True) if d.get('name') == 'save')

paths = list(nx.all_simple_paths(graph, main_node, save_node))
assert len(paths) >= 1

# Expected path: main -> run -> createUser -> save
```

## Code Quality

All Java files in this fixture:
- ✅ Follow Java naming conventions
- ✅ Use proper package declarations
- ✅ Include realistic imports
- ✅ Have meaningful method signatures
- ✅ Contain actual method calls (not just stubs)
- ✅ Represent common architectural patterns
