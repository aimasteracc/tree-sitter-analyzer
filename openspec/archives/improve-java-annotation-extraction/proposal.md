# Improve Java Annotation Extraction

## Overview

Java annotation extraction in `analyze_code_structure` was silently returning empty `annotations: []` for all methods, classes, and fields. Three independent bugs compounded to produce complete annotation loss. Validated against spring-petclinic (Spring MVC/JPA reference app).

## Problem Statement

### Bug 1: Wrong extraction order in `extract_elements()`

`extract_elements()` called `extract_functions()` and `extract_classes()` **before** `extract_annotations()`. These calls invoke `_reset_caches()`, which cleared `self.annotations`. When `_find_annotations_for_line_cached()` ran, the raw annotation list was empty.

**Root cause**: `self.annotations` was populated too late in the call sequence.

### Bug 2: `_reset_caches()` cleared source data

`_reset_caches()` cleared `self.annotations` (the raw annotation list extracted from the AST). This is source data, not a lookup cache. The line-keyed lookup cache (`self._annotation_cache`) should be cleared on file change; the source list should not.

**Root cause**: Conflation of source data and derived cache in a single reset operation.

### Bug 3: `analyze_code_structure_tool.py` hardcoded `annotations: []`

The MCP tool layer built output dicts with `"annotations": []` hardcoded, never reading `getattr(method/class/field, "annotations", [])` from the model objects.

**Root cause**: Copy-paste from a stub that was never wired up.

### Bug 4: Field annotations not traversed

`field_declaration` was missing from `container_node_types` in `_traverse_and_extract_iterative()`. When the traversal reached `field_declaration`, it skipped the node and never visited its children (`modifiers` → `annotation`). Field-level annotations (`@ManyToMany`, `@JoinTable`, `@Column`, `@Id`) were never extracted.

**Root cause**: Incomplete container node list; `field_declaration` is a structural node that wraps annotatable declarations.

## Validation Evidence

Validated against `spring-petclinic` open source project (Spring MVC + JPA reference application):

**Before fix** (all annotations=[] everywhere):
```
OwnerController class: annotations=[]
findOwner() method: annotations=[]
specialties field: annotations=[]
```

**After fix**:
```
OwnerController class: annotations=[{'name': 'Controller', 'text': '@Controller'}]
findOwner() method: annotations=[{'name': 'ModelAttribute', 'text': '@ModelAttribute("owner")'}]
initCreationForm() method: annotations=[{'name': 'GetMapping', 'text': '@GetMapping("/owners/new")'}]
specialties field: annotations=[
  {'name': 'ManyToMany', 'text': '@ManyToMany(fetch = FetchType.EAGER)'},
  {'name': 'JoinTable', 'text': '@JoinTable(name = "vet_specialties", ...)'}
]
```

## Impact

Annotation extraction is critical for:
- `modification_guard`: detecting high-risk symbols (`@Transactional`, `@EventListener`)
- `trace_impact`: understanding call context
- Code navigation: `@GetMapping`/`@PostMapping` are the routing table for Spring apps
- AI-assisted refactoring: knowing `@Deprecated` or `@Override` status

## Success Criteria

1. All class-level annotations extracted (`@Entity`, `@Controller`, `@Service`, etc.)
2. All method-level annotations extracted (`@GetMapping`, `@Transactional`, etc.)
3. All field-level annotations extracted (`@ManyToMany`, `@Column`, `@Id`, etc.)
4. Annotation text includes parameters (`@Table(name = "vets")`, not just `@Table`)
5. All 610 existing Java tests pass
6. Golden master tests pass unchanged
