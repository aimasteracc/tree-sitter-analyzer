# Design: Java Annotation Extraction Pipeline

## Pipeline Overview

```
AST (tree-sitter parse tree)
         │
         ▼
 extract_annotations()          ← Step 1: always run first
   _traverse_and_extract_iterative()
         │  walks every node looking for:
         │    annotation / marker_annotation
         │
         ▼
 self.annotations                ← raw list[dict], persists for session lifetime
   [{name, text, line}, ...]
         │
         ▼
 extract_classes() / extract_functions()
   _find_annotations_for_line_cached(line)
         │  proximity scan: abs(annotation.line - target_line) <= 2
         │
         ▼
 self._annotation_cache         ← derived lookup cache, keyed by line number
   {line: [annotation, ...]}
```

## Data Flow Details

### Step 1 — Raw Extraction

`extract_annotations(tree, source_code)` in `java_plugin.py`:

1. Calls `_reset_caches()` — clears **performance caches** only (node text, element, signature, annotation lookup).  `self.annotations` is NOT cleared here; it is about to be replaced.
2. Runs `_traverse_and_extract_iterative()` targeting `annotation` and `marker_annotation` AST node types.
3. Assigns `self.annotations = annotations` — stores the raw annotation list for later use.

### Step 2 — Proximity Matching

`_find_annotations_for_line_cached(line)` called during `extract_classes()` / `extract_functions()`:

- Checks `self._annotation_cache` first (O(1) hit for repeated calls on the same line).
- On miss: scans `self.annotations` with a ±2 line window. A window of two lines is sufficient for well-formatted Java code where annotations immediately precede the annotated declaration.
- Stores result in `self._annotation_cache` for future calls.

### Step 3 — Tool Layer

`analyze_code_structure_tool.py` reads `getattr(element, "annotations", [])` from model objects. This is the final step where annotations become visible to MCP callers.

## Source Data vs. Cache — The Critical Distinction

| Name | Type | Lives in | Cleared by |
|---|---|---|---|
| `self.annotations` | Source data (extracted from AST) | `java_plugin.py` instance | Only by a new `extract_annotations()` call |
| `self._annotation_cache` | Derived lookup cache | `java_plugin.py` instance | `_reset_caches()` |

`_reset_caches()` clears the **derived** cache (`_annotation_cache`) because it may be stale after a file change. It must NOT clear `self.annotations` — that is the raw source data that downstream methods depend on. Clearing it before `extract_classes()` runs would leave `_find_annotations_for_line_cached()` scanning an empty list.

## Field Annotation Traversal

The traversal in `_traverse_and_extract_iterative()` uses `container_node_types` to decide which node types to recurse into. `field_declaration` must be in this set because field annotations live in:

```
field_declaration
  └─ modifiers
       └─ annotation   ← @ManyToMany, @Column, @Id, etc.
```

Without `field_declaration` in `container_node_types`, the traversal skips the node and never reaches its `annotation` children.

## Call Order Invariant

```python
# CORRECT — annotations populated before classes/functions
annotations = self.extract_annotations(tree, source_code)
classes     = self.extract_classes(tree, source_code)
functions   = self.extract_functions(tree, source_code)
```

```python
# WRONG — annotations arrive too late; _reset_caches() inside
# extract_classes/functions would have cleared self.annotations
classes     = self.extract_classes(tree, source_code)    # _reset_caches clears _annotation_cache
functions   = self.extract_functions(tree, source_code)
annotations = self.extract_annotations(tree, source_code) # too late
```

The correct order is enforced in `extract_elements()` in `java_plugin.py`.
