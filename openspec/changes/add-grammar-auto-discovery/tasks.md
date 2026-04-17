# Grammar Auto-Discovery - Phase 3.1 Implementation

## Goal

Automatically discover all grammar elements (node types, fields, wrappers) without manually maintaining configuration files. Use tree-sitter's Language API + structural analysis.

## Inspiration

From phase3-feasibility-report.md: "Can we auto-discover all grammar elements without manually maintaining wrapper lists? Answer: YES - Using tree-sitter's Language API + structural analysis"

## MVP Scope

1. **Runtime Introspection** - Enumerate node types and fields via Language API
2. **Wrapper Detection** - Multi-feature scoring to identify wrapper nodes
3. **Path Enumeration** - Discover syntactic paths from code samples
4. **MCP Tool Integration** - Expose as `grammar_discovery` tool

## Technical Approach

### Core Algorithm

```
1. Runtime Introspection (Language API)
   - lang.node_kind_count        # Total node types
   - lang.node_kind_for_id(i)    # Type name
   - lang.field_count            # Total fields
   - lang.field_name_for_id(i)   # Field name

2. Structural Analysis (Code samples)
   - Parse golden corpus files
   - Analyze AST structure
   - Score wrapper candidates:
     score = 30*has_definition_field
           + 30*has_decorator_field
           + 20*len(child_types) >= 2
           + 10*avg_children >= 2
           + 10*matches_name_pattern

3. Validation
   - Verify against expected.json
   - Compare with existing plugins
```

### Module Structure

```
tree_sitter_analyzer/grammar_discovery/
- introspector.py: Language API wrapper
- structural_analyzer.py: Wrapper detection
- path_enumerator.py: Syntactic path discovery
- validator.py: Golden corpus validation

tree_sitter_analyzer/mcp/tools/grammar_discovery_tool.py
- grammar_discovery MCP tool
- schema: language, include_wrappers, include_paths
- TOON and JSON output
```

### Dependencies

- tree_sitter.Language API
- Golden corpus (tests/integration/golden_corpus/)
- Existing grammar_coverage/ module for validation

## Implementation Plan

### Sprint 1: Core Introspection Engine
- [x] Create `grammar_discovery/introspector.py` module
- [x] Implement `GrammarIntrospector` class
  - enumerate_node_types()
  - enumerate_fields()
  - heuristic_wrapper_detection()
- [x] Write unit tests (16 tests passing)

### Sprint 2: Structural Analysis
- [x] Create `grammar_discovery/structural_analyzer.py`
- [x] Implement multi-feature scoring for wrappers
- [x] Validate on Python golden corpus
- [x] Write integration tests (21 tests passing)

### Sprint 3: Path Enumeration
- [x] Create `grammar_discovery/path_enumerator.py`
- [x] Parse code samples and extract paths
- [x] Record (node_type, parent_path) tuples
- [x] Write tests (20 tests passing)

### Sprint 4: MCP Tool Integration
- [x] Create `mcp/tools/grammar_discovery_tool.py`
- [x] Implement schema (language, output_format)
- [x] Register to ToolRegistry (analysis toolset)
- [x] Add TOON format output
- [x] Write tool tests (18 tests passing)

## Success Criteria

- [x] 75+ tests passing (16 + 21 + 20 + 18)
- [x] Auto-discovery success rate >90% (17 languages)
- [x] Wrapper identification accuracy >85%
- [x] ruff check passes, mypy --strict passes
- [x] Integrated into MCP toolset

## References

- phase3-feasibility-report.md — Full feasibility analysis
- phase3-quick-reference.md — TL;DR summary
- scripts/grammar_introspection_prototype.py — Existing prototype
- scripts/grammar_structural_analysis.py — Structural analysis prototype

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
