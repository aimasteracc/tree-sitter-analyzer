# Design: Java Annotation Extraction Pipeline

## Architecture

The Java annotation extraction pipeline consists of four layers:

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 4: MCP Tool Layer                                    │
│  analyze_code_structure_tool.py                             │
│  - Builds output dicts from model objects                   │
│  - Must read annotations via getattr(obj, "annotations", [])│
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: Model Objects                                     │
│  Class, Function, Variable from models.py                   │
│  - Carry .annotations attribute (list of dicts)             │
│  - Populated by extractor during AST traversal              │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: Extraction Engine                                 │
│  JavaElementExtractor (java_plugin.py)                      │
│  - extract_annotations(): populates self.annotations         │
│  - extract_classes/functions/variables(): use self.annotations│
│  - _extract_class_optimized(): calls _extract_annotations_from_modifiers│
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: AST Traversal                                     │
│  tree-sitter-java grammar                                   │
│  - annotation, marker_annotation nodes                      │
│  - modifiers child of class_declaration, method_declaration, field_declaration│
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Initial Extraction (extract_annotations)
```python
def extract_annotations(tree, source_code) -> list[dict]:
    # Traverses all annotation nodes in the AST
    # Populates self.annotations (source data)
    # Returns list of all annotations in the file
```

**Key principle**: `self.annotations` is **source data**, not a cache. It must persist across all extraction calls.

### 2. Class/Method/Field Extraction
```python
def extract_classes(tree, source_code) -> list[Class]:
    # For each class_declaration node:
    #   1. Call _extract_annotations_from_modifiers(node)
    #   2. This reads ONLY annotations directly attached to THIS class
    #   3. No line-proximity heuristics needed
```

### 3. Direct AST Extraction (Bug 2 Fix)
```python
def _extract_annotations_from_modifiers(node) -> list[dict]:
    # Reads from AST node's modifiers child directly
    # Prevents @Override from preceding method from bleeding into next class
    for child in node.children:
        if child.type == "modifiers":
            for mod in child.children:
                if mod.type in ("annotation", "marker_annotation"):
                    annotations.append(_extract_annotation_optimized(mod))
```

### 4. MCP Tool Output (Bug 3 Fix)
```python
# In analyze_code_structure_tool.py:
"annotations": getattr(cls, "annotations", [])  # WAS: hardcoded []
```

## Container Node Types

The `_traverse_and_extract_iterative()` function uses `container_node_types` to determine which nodes can contain children with annotations:

```python
container_node_types = {
    "class_declaration",      # Contains modifiers → annotations
    "interface_declaration",
    "enum_declaration",
    "annotation_type_declaration",
    "record_declaration",
    "method_declaration",     # Contains modifiers → annotations
    "constructor_declaration",
    "field_declaration",      # Bug 4 fix: Contains modifiers → annotations
    "compact_constructor_declaration",
    # ... other structural nodes
}
```

**Key insight**: `field_declaration` is a structural container, not a leaf. Its `modifiers` child contains annotations.

## Cache Management

### What to Clear (and When)
- `self._annotation_cache`: Line-keyed lookup cache. Clear on file change.
- `self._element_cache`: Position-keyed element cache. Clear on file change.
- `self._processed_nodes`: Set of visited node IDs. Clear on file change.

### What NOT to Clear
- `self.annotations`: Raw annotation list from AST. This is **source data**.

### _reset_caches() Behavior (Bug 2 Fix)
```python
def _reset_caches(self):
    self._annotation_cache.clear()
    self._element_cache.clear()
    self._processed_nodes.clear()
    # NOTE: self.annotations is NOT cleared — it's source data
```

## Validation Strategy

### Unit Tests
- Test `extract_annotations()` returns non-empty list
- Test `_extract_annotations_from_modifiers()` extracts only direct annotations
- Test container node types include `field_declaration`

### Integration Tests
- Use spring-petclinic as validation project (real-world Spring MVC/JPA app)
- Verify class annotations: `@Controller`, `@Entity`, `@Table`
- Verify method annotations: `@GetMapping`, `@PostMapping`, `@Transactional`
- Verify field annotations: `@ManyToMany`, `@JoinTable`, `@Column`, `@Id`

### Regression Tests
- All 610 existing Java tests must pass
- Golden master tests (if any) must pass unchanged

## Future Enhancements (Out of Scope)

1. **Annotation parameter decomposition**: Parse `@JoinColumn(name = "user_id")` into structured fields
2. **Qualified name resolution**: Resolve `@org.junit.Test` to simple name `Test`
3. **Annotation inheritance**: Track `@Inherited` meta-annotations
4. **Repeatable annotations**: Handle `@Repeatable` containers (Java 8+)
