# Function Parameter Coupling Analyzer

## Goal

Detect functions with too many parameters (>5), complex parameter types, and Data Clumps (multiple functions sharing the same parameter groups). Help developers identify coupling hotspots and refactor opportunities.

## MVP Scope

- Parameter count analysis (flag functions with >5 params, configurable threshold)
- Parameter type complexity detection (nested generics, complex type annotations)
- Data Clump detection (Jaccard similarity for shared parameter groups across functions)
- Multi-language support: Python, JS/TS, Java, Go
- MCP tool registration (analysis toolset)

## Technical Approach

- Independent analysis module: `analysis/parameter_coupling.py` (~500-700 lines)
- MCP tool: `mcp/tools/parameter_coupling_tool.py` (~220 lines)
- Follows env_tracker/import_sanitizer/doc_coverage pattern
- Tree-sitter queries for parameter extraction per language
- Jaccard similarity for Data Clump grouping

### Sprint 1: Core Detection Engine (Python) — ~500 lines
- ParameterInfo dataclass (name, type_annotation, default_value, position)
- FunctionSignature dataclass (name, file, parameters, start_line)
- ParameterCouplingAnalyzer class with analyze() method
- Data Clump detection via Jaccard similarity
- Configurable thresholds (max_params, min_clump_size)
- Tests: ~30 unit tests

### Sprint 2: Multi-Language Support (JS/TS, Java, Go) — ~300 lines
- Language-specific parameter extraction via tree-sitter queries
- TypeScript: type annotations, optional params, rest params
- Java: typed parameters, generics, varargs
- Go: typed parameters, variadic params, multiple return values
- Tests: ~20 multilang tests

### Sprint 3: MCP Tool Integration — ~220 lines
- MCP tool with TOON + JSON output formats
- Filter by element type, min parameter count, clump detection
- Register to analysis toolset
- Tests: ~10 MCP tool tests
