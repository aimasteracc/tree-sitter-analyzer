# Design Pattern Detection

## Goal

Detect design patterns and anti-patterns in source code using AST analysis.

## Inspiration

From CodeFlow: "识别 Singleton / Factory / Observer / React Hooks / 反模式"

## MVP Scope

1. **Creational Patterns**: Singleton, Factory Method, Builder, Prototype
2. **Structural Patterns**: Adapter, Decorator, Proxy, Composite
3. **Behavioral Patterns**: Observer, Strategy, Command, Template Method
4. **Anti-Patterns**: God Class, Long Method, Circular Dependencies
5. **MCP Tool Integration**: Expose as `design_patterns` tool in analysis toolset

## Technical Approach

### Detection Algorithm

```
1. Parse AST for each file
2. Analyze class structure (inheritance, composition)
3. Analyze method signatures and call patterns
4. Match against pattern heuristics:
   - Singleton: private static instance + private constructor + getInstance()
   - Factory: create/instance methods returning interface types
   - Observer: addListener/removeListener/notify methods
   - Strategy: interface + multiple implementations + context class
5. Report patterns with confidence scores
```

### Module Structure

```
tree_sitter_analyzer/analysis/design_patterns.py
- PatternType: enum (SINGLETON, FACTORY, OBSERVER, STRATEGY, etc.)
- PatternMatch: dataclass (pattern_type, name, file, line, confidence, elements)
- detect_patterns(project_root): List[PatternMatch]
- is_singleton(class_node): bool
- is_factory(class_node): bool
- is_observer(class_node): bool
```

### Dependencies

- Existing element extractors: For class/method extraction
- Dependency graph: For analyzing relationships
- AST queries: For pattern matching

## Implementation Plan

### Sprint 1: Core Pattern Detection Engine
- [ ] Create `analysis/design_patterns.py` module
- [ ] Implement `PatternMatch` dataclass with confidence scoring
- [ ] Implement Singleton detection (private constructor + static instance)
- [ ] Implement Factory Method detection (create methods returning interfaces)
- [ ] Implement Observer detection (listener management methods)
- [ ] Write unit tests (15+ tests)

### Sprint 2: Multi-Language Support
- [ ] Python: @property, @classmethod, @staticmethod pattern recognition
- [ ] Java: interface + implementation pattern detection
- [ ] JavaScript/TypeScript: prototype and class patterns
- [ ] Add integration tests (10+ tests)

### Sprint 3: MCP Tool Integration
- [ ] Create `mcp/tools/design_patterns_tool.py`
- [ ] Implement schema (file_pattern, min_confidence, pattern_types)
- [ ] Register to ToolRegistry (analysis toolset)
- [ ] Add TOON format output with pattern hierarchy
- [ ] Write tool tests (10+ tests)

## Success Criteria

- [ ] 35+ tests passing
- [ ] Detects patterns in test projects with <20% false positive rate
- [ ] ruff check passes, mypy --strict passes
- [ ] Integrated into MCP toolset (30 tools total)

## References

- CodeFlow: https://codeflow-five.vercel.app/
- Refactoring Guru: https://refactoring.guru/design-patterns
- Tree-sitter-analyzer existing analysis modules for architecture
