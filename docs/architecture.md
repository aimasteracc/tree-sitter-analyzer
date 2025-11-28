# Architecture Overview

This document describes the architecture of Tree-sitter Analyzer, including its plugin system, MCP integration, and core components.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           User Interfaces                                │
├────────────────────┬────────────────────┬───────────────────────────────┤
│     CLI Interface  │    MCP Server      │     Python API                │
│  (tree-sitter-     │  (AI Assistant     │   (Direct Import)             │
│   analyzer)        │   Integration)     │                               │
└────────┬───────────┴────────┬───────────┴────────────┬──────────────────┘
         │                    │                        │
         ▼                    ▼                        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Core Engine                                      │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │   Analyzer   │  │   Query      │  │  Formatter   │  │   Cache     │  │
│  │   Engine     │  │   Engine     │  │  Registry    │  │   Service   │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘  │
│         │                 │                 │                 │         │
└─────────┼─────────────────┼─────────────────┼─────────────────┼─────────┘
          │                 │                 │                 │
          ▼                 ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       Language Plugins                                   │
├────────┬────────┬────────┬────────┬────────┬────────┬────────┬─────────┤
│  Java  │ Python │   TS   │  SQL   │  HTML  │  CSS   │  Rust  │   ...   │
└────────┴────────┴────────┴────────┴────────┴────────┴────────┴─────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Tree-sitter Parsers                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Analyzer Engine

The analyzer engine is the central component that orchestrates code analysis.

**Location**: `tree_sitter_analyzer/core/analyzer.py`

**Responsibilities**:
- Parse source code using tree-sitter
- Extract code elements (classes, methods, functions, etc.)
- Calculate metrics (lines, complexity, etc.)
- Coordinate with language plugins

**Key Classes**:
- `CodeAnalyzer`: Main analysis orchestrator
- `AnalysisResult`: Container for analysis results
- `ElementExtractor`: Base class for element extraction

### 2. Language Plugins

Each supported language has a dedicated plugin that understands its syntax and semantics.

**Location**: `tree_sitter_analyzer/plugins/`

**Plugin Structure**:
```
plugins/
├── base_plugin.py          # Abstract base class
├── java_plugin.py          # Java language support
├── python_plugin.py        # Python language support
├── typescript_plugin.py    # TypeScript/JavaScript support
├── sql_plugin.py           # SQL support
├── html_plugin.py          # HTML support
├── css_plugin.py           # CSS support
├── rust_plugin.py          # Rust support
├── go_plugin.py            # Go support
├── kotlin_plugin.py        # Kotlin support
└── ...
```

**Plugin Responsibilities**:
- Define language-specific tree-sitter queries
- Map AST nodes to code elements
- Provide language-specific formatting
- Handle language idioms and patterns

### 3. Formatter Registry

The formatter system provides flexible output formatting.

**Location**: `tree_sitter_analyzer/formatters/`

**Components**:
- `FormatterRegistry`: Central registry for formatters
- `BaseFormatter`: Abstract formatter interface
- Language-specific formatters (Java, SQL, HTML, etc.)

**Output Formats**:
| Format | Description |
|--------|-------------|
| `full` | Comprehensive table with all details |
| `compact` | Abbreviated summary |
| `csv` | Machine-readable CSV |
| `json` | Structured JSON |
| `text` | Human-readable text |
| `html` | HTML-specific format |

### 4. Query Engine

The query engine enables targeted code element extraction.

**Location**: `tree_sitter_analyzer/core/query.py`

**Features**:
- Predefined query keys (methods, classes, functions, etc.)
- Custom tree-sitter query support
- Filter expressions for result refinement

### 5. Cache Service

The cache service optimizes repeated operations.

**Location**: `tree_sitter_analyzer/services/cache_service.py`

**Capabilities**:
- Analysis result caching
- File modification detection
- Memory-efficient storage

## MCP Integration

### MCP Server Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      MCP Server                              │
│  (tree_sitter_analyzer/mcp/server.py)                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                   Tool Registry                      │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │  • check_code_scale                                 │    │
│  │  • analyze_code_structure                           │    │
│  │  • extract_code_section                             │    │
│  │  • query_code                                       │    │
│  │  • list_files                                       │    │
│  │  • search_content                                   │    │
│  │  • find_and_grep                                    │    │
│  │  • set_project_path                                 │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                 Resource Registry                    │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │  • code://file/{path}    - File content access      │    │
│  │  • code://stats/{type}   - Project statistics       │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │               Security Layer                         │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │  • Project boundary validation                      │    │
│  │  • Path traversal prevention                        │    │
│  │  • Input sanitization                               │    │
│  │  • Error message filtering                          │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### MCP Tool Classes

**Location**: `tree_sitter_analyzer/mcp/tools/`

| Tool | File | Purpose |
|------|------|---------|
| `check_code_scale` | `scale_tool.py` | File size and complexity assessment |
| `analyze_code_structure` | `table_format_tool.py` | Structured code analysis |
| `extract_code_section` | `partial_tool.py` | Line-range code extraction |
| `query_code` | `query_tool.py` | Element-specific queries |
| `list_files` | `list_files_tool.py` | File discovery (fd) |
| `search_content` | `search_content_tool.py` | Content search (ripgrep) |
| `find_and_grep` | `find_grep_tool.py` | Combined search |
| `set_project_path` | Various | Project boundary setting |

### External Tool Integration

```
┌──────────────────┐     ┌──────────────────┐
│       fd         │     │     ripgrep      │
│  (file search)   │     │ (content search) │
└────────┬─────────┘     └────────┬─────────┘
         │                        │
         ▼                        ▼
┌─────────────────────────────────────────────┐
│           External Tool Wrapper              │
│   (tree_sitter_analyzer/tools/external/)     │
├─────────────────────────────────────────────┤
│  • Process execution                        │
│  • Output parsing                           │
│  • Error handling                           │
│  • Result normalization                     │
└─────────────────────────────────────────────┘
```

## Data Models

### Code Elements

**Location**: `tree_sitter_analyzer/models/`

```python
# Base element types
CodeElement       # Generic code element
ClassElement      # Class/interface/struct
MethodElement     # Method/function
FieldElement      # Field/property/variable
ImportElement     # Import/include statement
PackageElement    # Package/namespace/module

# Specialized elements
MarkupElement     # HTML elements
StyleElement      # CSS rules
SQLElement        # Database objects
```

### Analysis Results

```python
AnalysisResult:
  - file_path: str
  - language: str
  - metrics: FileMetrics
  - elements: List[CodeElement]
  - errors: List[AnalysisError]

FileMetrics:
  - lines_total: int
  - lines_code: int
  - lines_comment: int
  - lines_blank: int
  - complexity: ComplexityMetrics
```

## Security Architecture

### Project Boundary Protection

```
┌─────────────────────────────────────────┐
│           Security Validator            │
├─────────────────────────────────────────┤
│                                         │
│  Request                                │
│    │                                    │
│    ▼                                    │
│  ┌────────────────────────────────┐    │
│  │     Path Normalization         │    │
│  │  (resolve symlinks, canonize)  │    │
│  └──────────────┬─────────────────┘    │
│                 │                       │
│                 ▼                       │
│  ┌────────────────────────────────┐    │
│  │    Boundary Check              │    │
│  │  (is path within project?)     │    │
│  └──────────────┬─────────────────┘    │
│                 │                       │
│            ┌────┴────┐                  │
│            │ Valid?  │                  │
│            └────┬────┘                  │
│          Yes    │    No                 │
│           │     │     │                 │
│           ▼     │     ▼                 │
│     ┌─────────┐ │  ┌─────────┐          │
│     │ Allow   │ │  │ Reject  │          │
│     └─────────┘ │  └─────────┘          │
│                 │                       │
└─────────────────┴───────────────────────┘
```

### Input Validation

- Path traversal prevention (`../` detection)
- Null byte injection detection
- Unicode normalization attack prevention
- Maximum path length enforcement
- File extension validation

### Error Sanitization

Error responses automatically remove:
- Passwords and tokens
- Full file system paths
- Stack traces (in production)
- Internal configuration details

## Performance Optimization

### Caching Strategy

```
┌─────────────────────────────────────────┐
│              Request                     │
│                │                        │
│                ▼                        │
│        ┌───────────────┐                │
│        │ Cache Check   │                │
│        └───────┬───────┘                │
│                │                        │
│       Hit      │      Miss              │
│        │       │        │               │
│        ▼       │        ▼               │
│  ┌──────────┐  │  ┌──────────┐          │
│  │ Return   │  │  │ Analyze  │          │
│  │ Cached   │  │  │ & Cache  │          │
│  └──────────┘  │  └──────────┘          │
│                │                        │
└────────────────┴────────────────────────┘
```

### Token Optimization

Five levels of token optimization:

| Level | Options | Token Reduction |
|-------|---------|-----------------|
| 1 | `count_only=true` | ~70% |
| 2 | `summary_only=true` | ~80% |
| 3 | `suppress_output=true` + `output_file` | ~95% |
| 4 | `group_by_file=true` | ~60% |
| 5 | `total_only=true` | ~90% |

## Extension Points

### Adding a New Language

1. Create plugin file: `plugins/new_language_plugin.py`
2. Implement `BasePlugin` interface
3. Define tree-sitter queries
4. Register with `PluginRegistry`
5. Create formatter if needed
6. Add tests

See [New Language Support Checklist](new-language-support-checklist.md) for detailed guidance.

### Adding a New MCP Tool

1. Create tool class in `mcp/tools/`
2. Implement `BaseTool` interface
3. Define input/output schemas
4. Register with MCP server
5. Add documentation
6. Add tests

### Adding a New Output Format

1. Create formatter in `formatters/`
2. Implement `BaseFormatter` interface
3. Register with `FormatterRegistry`
4. Add CLI option if needed
5. Add tests

## Directory Structure

```
tree_sitter_analyzer/
├── __init__.py
├── __main__.py              # CLI entry point
├── core/
│   ├── analyzer.py          # Main analyzer
│   ├── query.py             # Query engine
│   └── language_detector.py # Language detection
├── models/
│   ├── elements.py          # Code element models
│   ├── results.py           # Analysis result models
│   └── metrics.py           # Metric models
├── plugins/
│   ├── base_plugin.py       # Plugin base class
│   ├── java_plugin.py
│   ├── python_plugin.py
│   └── ...
├── formatters/
│   ├── base_formatter.py    # Formatter base class
│   ├── registry.py          # Formatter registry
│   ├── java_formatter.py
│   └── ...
├── mcp/
│   ├── server.py            # MCP server
│   ├── tools/               # MCP tool implementations
│   └── resources/           # MCP resource handlers
├── services/
│   ├── cache_service.py     # Caching
│   ├── file_service.py      # File operations
│   └── security_service.py  # Security validation
└── tools/
    └── external/            # External tool wrappers
        ├── fd_wrapper.py
        └── ripgrep_wrapper.py
```

## Related Documentation

- [Installation Guide](installation.md) - Setup instructions
- [CLI Reference](cli-reference.md) - Command-line usage
- [MCP Tools Specification](api/mcp_tools_specification.md) - API details
- [Features Overview](features.md) - Language support
- [SMART Workflow](smart-workflow.md) - Usage methodology
- [Contributing Guide](CONTRIBUTING.md) - Development guidelines

