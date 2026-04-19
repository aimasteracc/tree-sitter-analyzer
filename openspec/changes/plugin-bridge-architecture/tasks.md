# Plugin Bridge Architecture

## Problem

Two parallel systems exist with zero integration:

| System | Role | Files | Lines |
|--------|------|-------|-------|
| `plugins/` + `languages/` | Language-aware element extraction | 29 | 27,517 |
| `analysis/` | Code quality checks | 85 | 40,328 |

- **0** analyzers import from plugins
- **52** analyzers contain per-language AST node type definitions (duplicated)
- **202** language-dispatch points (`if extension ==`) across 31 analyzers
- **542** individual frozenset/dict definitions for node types that should come from language plugins
- Adding a new language requires editing 31+ analyzer files instead of 1 plugin file

## Root Cause

`LanguagePlugin` + `ElementExtractor` only know how to extract code elements (functions, classes, imports).
There is no interface for analyzers to query per-language knowledge:
- "What are the function node types?"
- "What are the scope boundary nodes?"
- "What are the naming conventions?"
- "How do I detect empty blocks?"

Each analyzer hardcodes this knowledge independently.

## Solution: LanguageKnowledge interface

Add a structured knowledge interface to language plugins so analyzers can query per-language AST knowledge instead of hardcoding it.

### Phase 1: Define LanguageKnowledge protocol

Create `plugins/knowledge.py`:

```python
class LanguageKnowledge(Protocol):
    """Per-language AST knowledge that analyzers can query."""

    # Node type catalogs (used by 50+ analyzers)
    @property
    def function_nodes(self) -> frozenset[str]: ...
    @property
    def class_nodes(self) -> frozenset[str]: ...
    @property
    def scope_boundary_nodes(self) -> frozenset[str]: ...
    @property
    def import_nodes(self) -> frozenset[str]: ...
    @property
    def loop_nodes(self) -> frozenset[str]: ...
    @property
    def exception_handler_nodes(self) -> frozenset[str]: ...
    @property
    def assignment_nodes(self) -> frozenset[str]: ...

    # Naming conventions
    @property
    def naming_conventions(self) -> dict[str, str]: ...

    # Scope analysis
    def is_module_level(self, node: Node, source: bytes) -> bool: ...
    def is_global_statement(self, node: Node) -> bool: ...
```

### Phase 2: Implement in 24 language plugins

Each `languages/*_plugin.py` implements `LanguageKnowledge`:
- Python plugin provides Python AST node types
- Java plugin provides Java AST node types
- etc.

This is mostly moving existing constants from analyzers into plugins.

### Phase 3: Bridge BaseAnalyzer to PluginManager

Modify `analysis/base.py`:

```python
class BaseAnalyzer:
    def _get_knowledge(self, extension: str) -> LanguageKnowledge:
        """Query language plugin for AST knowledge."""
        language = self._EXTENSION_TO_LANGUAGE.get(extension)
        return self._plugin_manager.get_plugin(language).knowledge()
```

### Phase 4: Migrate analyzers (batch)

Replace hardcoded node type dicts with `_get_knowledge()` calls:

Before (52 analyzers, each with):
```python
_FUNCTION_TYPES = {
    ".py": frozenset({"function_definition"}),
    ".js": frozenset({"function_declaration", "method_definition", "arrow_function"}),
    ...
}
```

After:
```python
knowledge = self._get_knowledge(extension)
func_nodes = knowledge.function_nodes
```

### Metrics

- Before: 542 node type definitions spread across 52 files
- After: 24 definitions, one per language plugin
- Before: Adding language X = edit 31+ files
- After: Adding language X = create 1 plugin file

## MVP Scope

- Phase 1 + Phase 2 (4 languages: Python, JS/TS, Java, Go)
- Phase 3 (BaseAnalyzer bridge)
- Phase 4 (migrate 5 most representative analyzers as proof):
  - `empty_block` (simple node-type-only)
  - `naming_convention` (conventions + node types)
  - `global_state` (scope analysis)
  - `boolean_complexity` (expression node types)
  - `nesting_depth` (scope boundary nodes)
- All existing tests must pass unchanged
