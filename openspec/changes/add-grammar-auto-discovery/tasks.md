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
- [ ] Create `grammar_discovery/introspector.py` module
- [ ] Implement `GrammarIntrospector` class
  - enumerate_node_types()
  - enumerate_fields()
  - heuristic_wrapper_detection()
- [ ] Write unit tests (15+ tests)

### Sprint 2: Structural Analysis
- [ ] Create `grammar_discovery/structural_analyzer.py`
- [ ] Implement multi-feature scoring for wrappers
- [ ] Validate on Python golden corpus
- [ ] Write integration tests (10+ tests)

### Sprint 3: Path Enumeration
- [ ] Create `grammar_discovery/path_enumerator.py`
- [ ] Parse code samples and extract paths
- [ ] Record (node_type, parent_path) tuples
- [ ] Write tests (10+ tests)

### Sprint 4: MCP Tool Integration
- [ ] Create `mcp/tools/grammar_discovery_tool.py`
- [ ] Implement schema (language, output_format)
- [ ] Register to ToolRegistry (analysis toolset)
- [ ] Add TOON format output
- [ ] Write tool tests (10+ tests)

## Success Criteria

- [ ] 45+ tests passing (15 + 10 + 10 + 10)
- [ ] Auto-discovery success rate >90% (17 languages)
- [ ] Wrapper identification accuracy >85%
- [ ] ruff check passes, mypy --strict passes
- [ ] Integrated into MCP toolset

## References

- phase3-feasibility-report.md — Full feasibility analysis
- phase3-quick-reference.md — TL;DR summary
- scripts/grammar_introspection_prototype.py — Existing prototype
- scripts/grammar_structural_analysis.py — Structural analysis prototype

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
