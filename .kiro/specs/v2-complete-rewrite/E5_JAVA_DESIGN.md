# E5: Java Code Graph Support - Technical Design

**Date**: 2026-02-02
**Status**: Design Complete
**Estimated Effort**: 8-12 hours

---

## Executive Summary

Design for adding Java Code Graph support by creating a **language-agnostic graph builder** that delegates language-specific operations to parser-specific extractors. This approach allows reusing the core graph construction logic while handling Java's unique syntax (method invocations, imports, package system).

**Key Decision**: Create `LanguageSpecificExtractor` protocol and implement `JavaCallExtractor`, rather than duplicating entire `CodeGraphBuilder` for Java.

---

## Architecture Design

### Current Architecture (Python-Only)

```
┌─────────────────────┐
│ CodeGraphBuilder    │
│ (graph/builder.py)  │
│                     │
│ - PythonParser      │  ← Hardcoded to Python
│ - _extract_call_name│  ← Python 'call' nodes
│ - _build_calls_edges│  ← Python-specific
└─────────────────────┘
```

**Problem**: Tightly coupled to Python syntax.

---

### Proposed Architecture (Multi-Language)

```
┌──────────────────────────────────────────────┐
│         CodeGraphBuilder                     │
│         (graph/builder.py)                   │
│                                              │
│  - parser: Union[PythonParser, JavaParser]   │
│  - extractor: CallExtractor protocol         │
│  - build_from_file()                         │
│  - build_from_directory()                    │
│  - _build_calls_edges() ← Delegates to       │
│                           extractor          │
└──────────────────────────────────────────────┘
             │
             ├──────────────────────────┬─────────────────────────
             ▼                          ▼
    ┌─────────────────┐      ┌──────────────────┐
    │ PythonCallEx-   │      │ JavaCallEx-      │
    │ tractor         │      │ tractor          │
    │                 │      │                  │
    │ - extract_calls │      │ - extract_calls  │
    │   (looks for    │      │   (looks for     │
    │    'call' nodes)│      │    'method_invo  │
    │                 │      │     cation')     │
    └─────────────────┘      └──────────────────┘
```

**Benefits**:
- ✅ Single CodeGraphBuilder for all languages
- ✅ Language-specific logic isolated in extractors
- ✅ Easy to add TypeScript/JavaScript later
- ✅ No duplication of core graph logic

---

## Component Design

### 1. CallExtractor Protocol

**File**: `tree_sitter_analyzer_v2/graph/extractors.py` (NEW)

```python
from typing import Protocol, Any, List, Dict
from tree_sitter_analyzer_v2.core.types import ASTNode

class CallExtractor(Protocol):
    """Protocol for language-specific method/function call extraction."""

    def extract_calls(self, ast_node: ASTNode) -> List[Dict[str, Any]]:
        """
        Extract all function/method calls from AST.

        Args:
            ast_node: Root AST node

        Returns:
            List of dicts with keys:
            - name: str (function/method name)
            - line: int (line number)
            - type: str ('simple'|'method'|'static'|'constructor')
            - qualifier: Optional[str] (class/object name for method calls)
        """
        ...

    def get_call_node_types(self) -> List[str]:
        """Return AST node types that represent calls in this language."""
        ...
```

---

### 2. PythonCallExtractor

**File**: `tree_sitter_analyzer_v2/graph/extractors.py`

```python
class PythonCallExtractor:
    """Extract Python function calls from AST."""

    def get_call_node_types(self) -> List[str]:
        """Python uses 'call' node type."""
        return ['call']

    def extract_calls(self, ast_node: ASTNode) -> List[Dict[str, Any]]:
        """
        Extract Python function/method calls.

        Handles:
        - Simple calls: func()
        - Method calls: obj.method()
        - Module calls: Module.function()
        """
        calls = []

        def traverse(node: ASTNode) -> None:
            if node.type == 'call':
                call_info = self._parse_call_node(node)
                if call_info:
                    calls.append(call_info)

            for child in node.children:
                traverse(child)

        traverse(ast_node)
        return calls

    def _parse_call_node(self, node: ASTNode) -> Optional[Dict[str, Any]]:
        """Parse Python call node."""
        # Extract function/method name
        func_expr = node.children[0] if node.children else None
        if not func_expr:
            return None

        if func_expr.type == 'identifier':
            # Simple call: func()
            return {
                'name': func_expr.text,
                'line': node.start_point[0] + 1,
                'type': 'simple',
                'qualifier': None
            }
        elif func_expr.type == 'attribute':
            # Method call: obj.method()
            # Extract method name (last identifier in attribute chain)
            for child in reversed(func_expr.children):
                if child.type == 'identifier':
                    return {
                        'name': child.text,
                        'line': node.start_point[0] + 1,
                        'type': 'method',
                        'qualifier': func_expr.children[0].text if func_expr.children else None
                    }

        return None
```

---

### 3. JavaCallExtractor (NEW)

**File**: `tree_sitter_analyzer_v2/graph/extractors.py`

```python
class JavaCallExtractor:
    """Extract Java method calls from AST."""

    def get_call_node_types(self) -> List[str]:
        """Java uses 'method_invocation' and 'object_creation_expression'."""
        return ['method_invocation', 'object_creation_expression']

    def extract_calls(self, ast_node: ASTNode) -> List[Dict[str, Any]]:
        """
        Extract Java method invocations and constructor calls.

        Handles:
        - Simple calls: method()
        - Method calls: obj.method()
        - Static calls: ClassName.staticMethod()
        - Constructor calls: new ClassName()
        - Super calls: super.method()
        - This calls: this.method()
        """
        calls = []

        def traverse(node: ASTNode) -> None:
            if node.type == 'method_invocation':
                call_info = self._parse_method_invocation(node)
                if call_info:
                    calls.append(call_info)
            elif node.type == 'object_creation_expression':
                call_info = self._parse_constructor_call(node)
                if call_info:
                    calls.append(call_info)

            for child in node.children:
                traverse(child)

        traverse(ast_node)
        return calls

    def _parse_method_invocation(self, node: ASTNode) -> Optional[Dict[str, Any]]:
        """
        Parse Java method_invocation node.

        Examples:
        - method()           → {name: 'method', type: 'simple'}
        - obj.method()       → {name: 'method', type: 'method', qualifier: 'obj'}
        - Class.method()     → {name: 'method', type: 'static', qualifier: 'Class'}
        - super.method()     → {name: 'method', type: 'super'}
        - this.method()      → {name: 'method', type: 'this'}
        """
        method_name = None
        qualifier = None
        call_type = 'simple'

        for child in node.children:
            if child.type == 'identifier':
                # This is the method name (last identifier wins)
                method_name = child.text
            elif child.type == 'field_access':
                # obj.method() or Class.method()
                qualifier, method_name = self._parse_field_access(child)
                call_type = 'method'  # Could be instance or static, hard to tell without type info
            elif child.type == 'super':
                call_type = 'super'
            elif child.type == 'this':
                call_type = 'this'

        if not method_name:
            return None

        return {
            'name': method_name,
            'line': node.start_point[0] + 1,
            'type': call_type,
            'qualifier': qualifier
        }

    def _parse_field_access(self, node: ASTNode) -> tuple[Optional[str], Optional[str]]:
        """
        Parse field_access node to extract object/class and method name.

        Examples:
        - obj.method     → ('obj', 'method')
        - Class.method   → ('Class', 'method')
        """
        object_name = None
        field_name = None

        for child in node.children:
            if child.type == 'identifier':
                if object_name is None:
                    object_name = child.text
                else:
                    field_name = child.text

        return (object_name, field_name)

    def _parse_constructor_call(self, node: ASTNode) -> Optional[Dict[str, Any]]:
        """
        Parse constructor call: new ClassName()

        Returns call info with type='constructor'
        """
        class_name = None

        for child in node.children:
            if child.type == 'type_identifier':
                class_name = child.text
                break
            elif child.type == 'generic_type':
                # new List<String>()
                for grandchild in child.children:
                    if grandchild.type == 'type_identifier':
                        class_name = grandchild.text
                        break

        if not class_name:
            return None

        return {
            'name': class_name,  # Constructor name is class name
            'line': node.start_point[0] + 1,
            'type': 'constructor',
            'qualifier': None
        }
```

---

### 4. Modified CodeGraphBuilder

**File**: `tree_sitter_analyzer_v2/graph/builder.py` (MODIFIED)

**Changes**:

```python
class CodeGraphBuilder:
    """Builds code graphs from source files (multi-language support)."""

    def __init__(self, language: str = "python") -> None:
        """
        Initialize code graph builder for specified language.

        Args:
            language: Programming language ('python' or 'java')
        """
        self.language = language.lower()

        # Initialize language-specific parser
        if self.language == "python":
            from tree_sitter_analyzer_v2.languages.python_parser import PythonParser
            from tree_sitter_analyzer_v2.graph.extractors import PythonCallExtractor
            self.parser = PythonParser()
            self.call_extractor = PythonCallExtractor()
        elif self.language == "java":
            from tree_sitter_analyzer_v2.languages.java_parser import JavaParser
            from tree_sitter_analyzer_v2.graph.extractors import JavaCallExtractor
            self.parser = JavaParser()
            self.call_extractor = JavaCallExtractor()
        else:
            raise ValueError(f"Unsupported language: {language}")

    def _build_calls_edges(self, graph: nx.DiGraph, result: Dict[str, Any]) -> None:
        """
        Build CALLS edges using language-specific call extractor.

        Args:
            graph: NetworkX graph to add edges to
            result: Parser result with AST
        """
        if 'ast' not in result or not result['ast']:
            return

        # Use language-specific extractor
        function_calls = self.call_extractor.extract_calls(result['ast'])

        # Build mapping of function/method names to node IDs
        func_name_to_id: Dict[str, List[str]] = {}
        for node_id, node_data in graph.nodes(data=True):
            if node_data['type'] == 'FUNCTION':
                name = node_data.get('name', '')
                if name not in func_name_to_id:
                    func_name_to_id[name] = []
                func_name_to_id[name].append(node_id)

        # Resolve calls to definitions
        for call in function_calls:
            self._resolve_and_add_call_edge(graph, call, func_name_to_id)

    def _resolve_and_add_call_edge(
        self,
        graph: nx.DiGraph,
        call: Dict[str, Any],
        func_name_to_id: Dict[str, List[str]]
    ) -> None:
        """Resolve a call to its definition and add CALLS edge."""
        call_name = call.get('name', '')
        call_line = call.get('line', 0)

        # Find caller function (which function contains this call)
        caller_nodes = [
            node_id
            for node_id, data in graph.nodes(data=True)
            if data['type'] == 'FUNCTION'
            and data.get('start_line', 0) <= call_line <= data.get('end_line', 0)
        ]

        if not caller_nodes:
            return

        caller_id = caller_nodes[0]

        # Resolve callee (simple name matching for now)
        if call_name in func_name_to_id:
            for target_id in func_name_to_id[call_name]:
                if target_id != caller_id:
                    if not graph.has_edge(caller_id, target_id):
                        graph.add_edge(caller_id, target_id, type='CALLS')
```

---

## Java-Specific Import Resolution

### Java Import Types

```java
// 1. Single class import
import com.example.User;

// 2. Wildcard import (all classes in package)
import com.example.*;

// 3. Static import (specific static method/field)
import static java.lang.Math.max;

// 4. Static wildcard import
import static com.example.Constants.*;
```

### JavaImportResolver Design

**File**: `tree_sitter_analyzer_v2/graph/java_imports.py` (NEW)

```python
from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path

@dataclass
class JavaImport:
    """Represents a Java import statement."""
    package: str  # e.g., "com.example"
    class_name: Optional[str]  # e.g., "User" or None for wildcard
    is_static: bool = False
    is_wildcard: bool = False

class JavaImportResolver:
    """Resolves Java imports to file paths."""

    def __init__(self, project_root: Path):
        """
        Initialize resolver.

        Args:
            project_root: Root directory of Java project
        """
        self.project_root = project_root
        self._package_to_files: Dict[str, List[Path]] = {}
        self._build_package_index()

    def _build_package_index(self) -> None:
        """
        Build index of package → file mappings.

        Java package structure:
        - com.example.User → src/main/java/com/example/User.java
        - Package = directory structure
        """
        # Find all .java files
        for java_file in self.project_root.rglob("*.java"):
            # Parse package declaration from file
            package = self._extract_package_from_file(java_file)
            if package:
                if package not in self._package_to_files:
                    self._package_to_files[package] = []
                self._package_to_files[package].append(java_file)

    def _extract_package_from_file(self, file_path: Path) -> Optional[str]:
        """
        Extract package declaration from Java file.

        Example: "package com.example;" → "com.example"
        """
        try:
            content = file_path.read_text(encoding='utf-8')
            # Simple regex to find package declaration
            import re
            match = re.search(r'package\s+([\w.]+)\s*;', content)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    def parse_imports(self, java_file: Path) -> List[JavaImport]:
        """
        Parse all import statements from a Java file.

        Args:
            java_file: Path to Java file

        Returns:
            List of JavaImport objects
        """
        imports = []

        try:
            content = java_file.read_text(encoding='utf-8')
            import re

            # Match: import [static] package.Class[.*];
            import_pattern = r'import\s+(static\s+)?([\w.]+)(\.\*)?;'
            for match in re.finditer(import_pattern, content):
                is_static = match.group(1) is not None
                full_path = match.group(2)
                is_wildcard = match.group(3) is not None

                if is_wildcard:
                    # import com.example.*;
                    imports.append(JavaImport(
                        package=full_path,
                        class_name=None,
                        is_static=is_static,
                        is_wildcard=True
                    ))
                else:
                    # import com.example.User;
                    parts = full_path.rsplit('.', 1)
                    if len(parts) == 2:
                        package, class_name = parts
                        imports.append(JavaImport(
                            package=package,
                            class_name=class_name,
                            is_static=is_static,
                            is_wildcard=False
                        ))

        except Exception:
            pass

        return imports

    def resolve_import(self, java_import: JavaImport) -> List[Path]:
        """
        Resolve import to file path(s).

        Args:
            java_import: Import to resolve

        Returns:
            List of matching file paths (multiple for wildcard imports)
        """
        package = java_import.package

        if java_import.is_wildcard:
            # Return all files in package
            return self._package_to_files.get(package, [])
        else:
            # Find specific class
            class_name = java_import.class_name
            matching_files = []

            for file_path in self._package_to_files.get(package, []):
                if file_path.stem == class_name:
                    matching_files.append(file_path)

            return matching_files
```

---

## Data Flow

### Building Java Code Graph

```
1. User calls builder.build_from_file("App.java")
           ↓
2. CodeGraphBuilder.__init__(language="java")
   - Creates JavaParser
   - Creates JavaCallExtractor
           ↓
3. Parse Java file
   - JavaParser extracts classes, methods, imports
   - Returns structured result dict
           ↓
4. Build graph nodes
   - MODULE node (file)
   - CLASS nodes
   - FUNCTION nodes (methods)
   - CONTAINS edges
           ↓
5. Extract method calls
   - JavaCallExtractor.extract_calls(ast)
   - Finds 'method_invocation' nodes
   - Returns list of calls with names and lines
           ↓
6. Build CALLS edges
   - Resolve call names to method definitions
   - Add edges: caller → callee
           ↓
7. Return NetworkX graph
```

### Cross-File Resolution (Java)

```
1. User calls builder.build_from_directory("src", cross_file=True, language="java")
           ↓
2. Build per-file graphs (parallel)
           ↓
3. JavaImportResolver.build_package_index()
   - Scan all .java files
   - Build package → files mapping
           ↓
4. For each file:
   - Parse imports with JavaImportResolver
   - Resolve imports to file paths
           ↓
5. Build symbol table
   - All methods from all files
   - Indexed by (class_name, method_name)
           ↓
6. Resolve cross-file calls
   - For each unresolved call:
     - Check if class is imported
     - Look up method in that class
     - Add CALLS edge with cross_file=True
           ↓
7. Return unified graph
```

---

## Node and Edge Schemas

### Java Module Node

```python
{
    'type': 'MODULE',
    'name': 'com.example.App',  # Fully qualified
    'file_path': '/path/to/src/main/java/com/example/App.java',
    'package': 'com.example',
    'imports': ['java.util.List', 'com.example.User'],
}
```

### Java Class Node

```python
{
    'type': 'CLASS',
    'name': 'UserService',
    'module_id': 'com.example.UserService',
    'start_line': 10,
    'end_line': 50,
    'modifiers': ['public'],
    'annotations': ['@Service'],
    'extends': 'BaseService',  # Optional
    'implements': ['UserInterface'],  # Optional
}
```

### Java Method Node

```python
{
    'type': 'FUNCTION',
    'name': 'findUser',
    'class_id': 'com.example.UserService:class:UserService',
    'module_id': 'com.example.UserService',
    'start_line': 20,
    'end_line': 25,
    'modifiers': ['public'],
    'params': ['Long id'],
    'return_type': 'User',
    'annotations': ['@Transactional'],
}
```

---

## Testing Strategy

### Unit Tests

**File**: `tests/unit/test_java_call_extractor.py`
- Test `JavaCallExtractor.extract_calls()`
- Test simple calls, method calls, static calls, constructor calls
- 20+ test cases

**File**: `tests/unit/test_java_import_resolver.py`
- Test Java import parsing
- Test package index building
- Test import resolution
- 15+ test cases

### Integration Tests

**File**: `tests/integration/test_java_code_graph.py`
- Test building graph from single Java file
- Test building graph from Java project
- Test cross-file call resolution
- 10+ test cases

### Test Fixtures

**Directory**: `tests/fixtures/java_project/`
```
java_project/
├── src/main/java/com/example/
│   ├── App.java (main class, calls UserService)
│   ├── service/
│   │   └── UserService.java (calls UserRepository)
│   └── repository/
│       └── UserRepository.java (interface)
└── README.md (documents expected graph structure)
```

---

## Performance Considerations

### Java-Specific Optimizations

1. **Package Index Caching**: Build once per project
2. **Import Resolution Cache**: Cache resolved imports
3. **Parallel File Processing**: Same as Python (ThreadPoolExecutor)

### Expected Performance

| Operation | Files | Expected Time |
|-----------|-------|---------------|
| Single file | 1 | <100ms |
| Small project | 10-50 | <2s |
| Medium project | 100-500 | <30s |
| Large project | 1000+ | <3min |

---

## Risks and Mitigation

### R1: Method Overloading Ambiguity

**Risk**: Java allows multiple methods with same name but different parameters.

**Example**:
```java
void process(String s) { }
void process(int n) { }
```

**Mitigation**:
- Phase 1: Ignore parameters, create edges to all matching names
- Phase 2 (future): Parse call arguments and match signatures

### R2: Wildcard Import Ambiguity

**Risk**: `import com.example.*;` could match multiple classes.

**Mitigation**: Conservative strategy - skip if ambiguous, log warning.

### R3: Standard Library False Positives

**Risk**: Tracking calls to `java.util.List.add()` is noise.

**Mitigation**: Filter out calls to packages starting with `java.*` or `javax.*`.

---

## Migration Path

### Phase 1: Basic Java Support (This PR)
- JavaCallExtractor
- JavaImportResolver
- CodeGraphBuilder with language parameter
- Intra-file and cross-file calls

### Phase 2: Inheritance Support (Future)
- EXTENDS edges
- IMPLEMENTS edges
- OVERRIDES edges

### Phase 3: Multi-Language Unification (Future)
- TypeScript support
- JavaScript support
- Unified multi-language graphs

---

## API Examples

### Usage Example 1: Build Java Graph

```python
from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder

# Create builder for Java
builder = CodeGraphBuilder(language="java")

# Analyze single file
graph = builder.build_from_file("src/main/java/com/example/App.java")

# Query the graph
print(f"Nodes: {graph.number_of_nodes()}")
print(f"Edges: {graph.number_of_edges()}")

# Find all classes
classes = [n for n, d in graph.nodes(data=True) if d['type'] == 'CLASS']
```

### Usage Example 2: Cross-File Analysis

```python
builder = CodeGraphBuilder(language="java")

# Analyze entire project with cross-file resolution
graph = builder.build_from_directory(
    "src/main/java",
    pattern="**/*.java",
    exclude_patterns=["**/test/**"],
    cross_file=True
)

# Find cross-file calls
cross_file_calls = [
    (u, v) for u, v, d in graph.edges(data=True)
    if d.get('type') == 'CALLS' and d.get('cross_file') is True
]

print(f"Cross-file calls: {len(cross_file_calls)}")
```

### Usage Example 3: MCP Tool Integration

```python
# MCP tools automatically detect language from file extension
result = analyze_code_graph_tool.execute({
    "file_path": "src/main/java/App.java"  # .java → use JavaParser
})

# Or explicit language specification
result = analyze_code_graph_tool.execute({
    "directory": "src/main/java",
    "language": "java",
    "cross_file": True
})
```

---

## Acceptance Criteria

- [ ] `JavaCallExtractor` implements `CallExtractor` protocol
- [ ] `JavaImportResolver` resolves Java imports
- [ ] `CodeGraphBuilder(language="java")` works
- [ ] Can build graph from single Java file
- [ ] Can build graph from Java directory
- [ ] Cross-file call resolution works
- [ ] 80%+ test coverage for new code
- [ ] No regressions in Python Code Graph
- [ ] MCP tools support Java files

---

**Status**: ✅ Design Complete
**Next**: Create E5_JAVA_TASKS.md for implementation breakdown
