# Tree-sitter Analyzer Features

This document provides a comprehensive overview of the features and language support in Tree-sitter Analyzer.

## Feature Overview

| Feature Category | Key Capabilities | Core Benefits |
|------------------|------------------|---------------|
| **🤖 Deep AI Integration** | MCP Protocol Support, SMART Workflow, Token Limitation Breaking | Native support for Claude Desktop, Cursor, Roo Code |
| **🔍 Powerful Search** | Intelligent File Discovery, Precise Content Search, Two-Stage Search | fd + ripgrep based high-performance search |
| **📊 Intelligent Analysis** | Fast Structure Analysis, Precise Code Extraction, Complexity Analysis | Enterprise-grade parsing without full file reading |

## Enterprise Capabilities

### Token Optimization

For AI assistants with token limits, Tree-sitter Analyzer provides multiple optimization strategies:

| Strategy | Option | Token Reduction |
|----------|--------|-----------------|
| Count Only | `count_only=true` | ~70% |
| Summary Only | `summary_only=true` | ~80% |
| File Output | `suppress_output=true` + `output_file` | ~95% |
| Group by File | `group_by_file=true` | ~60% |
| Total Only | `total_only=true` | ~90% |

### Security Features

- **Project Boundary Protection**: Automatic security boundaries preventing access outside project
- **Path Traversal Prevention**: Blocks `../` and symbolic link attacks
- **Input Validation**: Sanitizes all user inputs
- **Error Sanitization**: Removes sensitive information from error messages

### Cross-Platform Support

| Platform | Status | Notes |
|----------|--------|-------|
| Windows | ✅ Full Support | PowerShell and CMD |
| macOS | ✅ Full Support | Native and Homebrew |
| Linux | ✅ Full Support | All major distributions |

## Supported Languages

### Systems Programming Languages

#### C 🆕

**Full Support** - Complete C language analysis with C-specific features.

| Feature Category | Supported Elements | Notes |
|------------------|-------------------|-------|
| **Functions** | Function definitions | Parameters, return types |
| **Types** | Struct definitions | Field names and types |
| | Union definitions | Field names and types |
| | Enum definitions | Enumerator values |
| | Typedefs | Type aliases |
| **Declarations** | Global variables | Static, const, extern |
| | Function pointers | Complex type support |
| **Preprocessor** | #include directives | Header file tracking |
| | #define macros | Macro detection |
| | Conditional compilation | #ifdef/#ifndef |

**Formatter Terminology:**
- Uses C-specific terms: `function`, `struct`, `union`, `enum`, `typedef`
- Scope: `global`, `static`, `extern`

#### C++ 🆕

**Full Support** - Complete C++ language analysis with C++-specific features.

| Feature Category | Supported Elements | Notes |
|------------------|-------------------|-------|
| **Classes** | Class definitions | Public/private/protected sections |
| **Functions** | Function declarations | Constructors, destructors |
| | Operator overloading | Custom operators |
| | Virtual functions | Inheritance support |
| **Types** | Struct definitions | With member functions |
| | Enum/enum class | C++11 scoped enums |
| **Templates** | Function templates | Type parameters |
| | Class templates | Template classes |
| **Namespaces** | Namespace definitions | Nested namespaces |
| **Declarations** | Using declarations | Type aliases |
| | Using namespace | Namespace imports |
| **Modern C++** | Lambda expressions | Capture clauses |
| | Smart pointers | unique_ptr, shared_ptr |

**Formatter Terminology:**
- Uses C++-specific terms: `class`, `struct`, `namespace`, `template`
- Visibility: `public`, `protected`, `private`

#### Go

**Full Support** - Complete Go language analysis with Go-specific features.

| Feature Category | Supported Elements | Notes |
|------------------|-------------------|-------|
| **Packages** | Package declarations | With name and line number |
| **Functions** | Function declarations | Parameters, return types, visibility |
| **Methods** | Method declarations | Receiver type support |
| **Types** | Struct definitions | Field names and types |
| | Interface definitions | Method signatures |
| | Type aliases | Type definitions |
| **Declarations** | const declarations | Constants with types |
| | var declarations | Variables with types |
| **Concurrency** | Goroutine detection | `go` statement patterns |
| | Channel detection | Channel usage patterns |

**Formatter Terminology:**
- Uses Go-specific terms: `package`, `func`, `struct`, `interface`
- Visibility: `exported` (capitalized) / `unexported` (lowercase)

#### Rust 🆕

**Full Support** - Complete Rust language analysis with Rust-specific features.

| Feature Category | Supported Elements | Notes |
|------------------|-------------------|-------|
| **Modules** | Module declarations (`mod`) | With visibility |
| **Functions** | Function declarations (`fn`) | Parameters, return type, visibility |
| **Types** | Struct definitions | Fields, visibility, derive macros |
| | Enum definitions | Variants |
| | Trait definitions | Method signatures |
| **Implementations** | impl blocks | Trait implementations |
| **Macros** | macro_rules! | Macro definitions |
| **Async** | async functions | Async pattern detection |
| **Lifetimes** | Lifetime annotations | Lifetime detection |

**Formatter Terminology:**
- Uses Rust-specific terms: `mod`, `fn`, `struct`, `enum`, `trait`, `impl`
- Visibility: `pub`, `pub(crate)`, `private`

### JVM Languages

#### Kotlin 🆕

**Full Support** - Complete Kotlin language analysis with Kotlin-specific features.

| Feature Category | Supported Elements | Notes |
|------------------|-------------------|-------|
| **Packages** | Package declarations | |
| **Classes** | class, data class, sealed class | All class types |
| | object declarations | Singleton objects |
| | interface definitions | |
| **Functions** | Function declarations | Extension functions with receiver |
| | suspend functions | Coroutine support |
| **Properties** | val/var declarations | Property distinction |
| **Annotations** | Annotation extraction | With parameters |

**Formatter Terminology:**
- Uses Kotlin-specific terms: `class`, `data class`, `object`, `fun`, `val`, `var`
- Visibility: `public`, `private`, `protected`, `internal`

#### Java

**Full Support** - Enterprise-grade Java analysis.

| Feature Category | Supported Elements | Notes |
|------------------|-------------------|-------|
| **Packages** | Package declarations | |
| **Classes** | Class, interface, enum, annotation | All types |
| **Methods** | Method declarations | Parameters, return types, annotations |
| **Fields** | Field declarations | With types and modifiers |
| **Framework Support** | Spring, JPA | Enterprise patterns |

### Web Languages

#### JavaScript

**Full Support** - Modern JavaScript analysis.

| Feature Category | Supported Elements | Notes |
|------------------|-------------------|-------|
| **Functions** | Function declarations | Arrow functions, async/await |
| **Classes** | ES6 classes | Methods, properties |
| **Modules** | Import/export | ES modules |
| **Frameworks** | React, Vue, Angular | Component detection |

#### TypeScript

**Full Support** - TypeScript with advanced type analysis.

| Feature Category | Supported Elements | Notes |
|------------------|-------------------|-------|
| **Types** | Interfaces, type aliases | |
| **Decorators** | Decorator extraction | |
| **JSX/TSX** | JSX support | React components |
| **Framework Detection** | Automatic detection | |

#### HTML

**Full Support** - DOM structure analysis.

| Feature Category | Supported Elements | Notes |
|------------------|-------------------|-------|
| **Elements** | All HTML elements | Tag names, attributes |
| **Classification** | Element categorization | Structure, media, form, etc. |
| **Hierarchy** | DOM tree structure | Parent-child relationships |

#### CSS

**Full Support** - CSS rule analysis.

| Feature Category | Supported Elements | Notes |
|------------------|-------------------|-------|
| **Selectors** | All selector types | Class, ID, element, etc. |
| **Properties** | Property extraction | With values |
| **Classification** | Property categorization | Layout, typography, etc. |

### Data Languages

#### SQL

**Enhanced Full Support** - Database schema analysis.

| Feature Category | Supported Elements | Notes |
|------------------|-------------------|-------|
| **Tables** | Table definitions | Columns, constraints |
| **Views** | View definitions | |
| **Stored Procedures** | Procedure definitions | Parameters |
| **Functions** | Function definitions | |
| **Triggers** | Trigger definitions | |
| **Indexes** | Index definitions | |

#### YAML

**Full Support** - YAML configuration analysis.

| Feature Category | Supported Elements | Notes |
|------------------|-------------------|-------|
| **Mappings** | Key-value pairs | |
| **Sequences** | Lists | |
| **Scalars** | String, number, boolean, null | Type identification |
| **Anchors/Aliases** | Reference detection | `&anchor` / `*alias` |
| **Multi-document** | `---` separators | |

#### Markdown

**Full Support** - Document structure analysis.

| Feature Category | Supported Elements | Notes |
|------------------|-------------------|-------|
| **Headings** | ATX and Setext | Levels 1-6 |
| **Code blocks** | Fenced and indented | Language detection |
| **Links/Images** | All link types | URLs, titles |
| **Tables** | GFM tables | |
| **Task lists** | Checkbox items | |

### Other Languages

#### Python

**Full Support** - Modern Python analysis.

| Feature Category | Supported Elements | Notes |
|------------------|-------------------|-------|
| **Classes** | Class definitions | Inheritance |
| **Functions** | Function definitions | Type annotations |
| **Decorators** | Decorator extraction | |

#### C#

**Full Support** - Modern C# analysis.

| Feature Category | Supported Elements | Notes |
|------------------|-------------------|-------|
| **Types** | Class, interface, record, struct | |
| **Properties** | Property definitions | Get/set accessors |
| **Async** | async/await patterns | |
| **Attributes** | Attribute extraction | |

#### PHP

**Full Support** - PHP 8+ support.

| Feature Category | Supported Elements | Notes |
|------------------|-------------------|-------|
| **Types** | Class, interface, trait, enum | |
| **Namespaces** | Namespace declarations | |
| **Attributes** | PHP 8 attributes | |

#### Ruby

**Full Support** - Ruby and Rails analysis.

| Feature Category | Supported Elements | Notes |
|------------------|-------------------|-------|
| **Classes/Modules** | Class, module definitions | Mixins |
| **Methods** | Instance, class, singleton | |
| **Blocks** | Block, Proc, Lambda | |

## UML / Mermaid Diagrams

TSA exports Mermaid diagrams from indexed project intelligence via
`viz action=uml` (MCP) or `--uml` (CLI). Six diagram types are shipped.

### Diagram types

| Type | What it renders | Key params |
|---|---|---|
| `class` | Inheritance graph — classes, superclasses, subclasses | `file_path`, `class_name`, `include_tests`, `--uml-no-external-bases` |
| `package` | Module dependency graph grouped by directory depth | `package_depth` (default: 2) |
| `component` | Import-level component dependencies | `max_edges` |
| `sequence` | Call-path trace between two functions | `source`, `target` (both required) |
| `activity` | Per-function control-flow graph (CFG) built from the AST | `function_name` (required), `file_path`, `max_nodes` |
| `state` | FSM approximation from enum definitions and match/switch statements | `file_path`, `max_nodes` |

`activity` and `state` re-parse the source file at query time (disk read +
tree-sitter parse, typically < 50 ms). All other types read from the index.

### Scoping parameters

| Param | Applies to | Effect |
|---|---|---|
| `file_path` / `--uml-file-path` | `class`, `activity`, `state` | Limit to classes or functions in this file |
| `class_name` / `--uml-class-name` | `class` | Show the named class plus its immediate superclasses and subclasses |
| `function_name` / `--uml-function` | `activity` | Required: function to graph (bare name or `module.function`) |
| `include_tests` / `--uml-include-tests` | `class`, `package`, `component` | Include test-corpus classes (default: excluded) |
| `max_nodes` / `--uml-max-nodes` | `activity`, `state` | Cap on CFG/FSM nodes (default: 50); `truncated=true` when exceeded |

### CLI examples

```bash
# Whole-project class diagram
uv run python -m tree_sitter_analyzer --uml class

# Class diagram for one file (excludes external base classes)
uv run python -m tree_sitter_analyzer --uml class \
  --uml-file-path tree_sitter_analyzer/mcp/tools/base_tool.py \
  --uml-no-external-bases

# Neighbourhood subgraph for one class
uv run python -m tree_sitter_analyzer --uml class \
  --uml-class-name BaseMCPTool

# Call-path sequence diagram
uv run python -m tree_sitter_analyzer --uml sequence \
  --uml-source execute --uml-target build_response

# Per-function CFG (activity diagram)
uv run python -m tree_sitter_analyzer --uml activity \
  --uml-function execute \
  --uml-file-path tree_sitter_analyzer/mcp/tools/uml_tool.py

# Enum/match FSM state diagram
uv run python -m tree_sitter_analyzer --uml state \
  --uml-file-path tree_sitter_analyzer/mcp/tools/uml_tool.py

# Package dependency map
uv run python -m tree_sitter_analyzer --uml package --uml-package-depth 2
```

### MCP equivalent

```json
{ "action": "uml", "diagram": "class", "file_path": "src/models.py" }
{ "action": "uml", "diagram": "activity", "function_name": "execute", "file_path": "src/tool.py" }
{ "action": "uml", "diagram": "sequence", "source": "handle_call", "target": "build_response" }
```

All diagrams require the AST index (`index action=status` to check; `index
action=auto mode=warm` to build). `activity` and `state` additionally need
`file_path` to locate the source.

---

## Output Formats

All languages support the following output formats:

- **Full Table** (`--table full`) - Comprehensive structured output
- **Compact Table** (`--table compact`) - Abbreviated summary
- **CSV** (`--table csv`) - Machine-readable format
- **JSON** (`--advanced --output-format json`) - Structured data
- **Text** (`--advanced --output-format text`) - Human-readable

## Testing and Quality

Each language includes:

- **Unit Tests** - Core functionality testing
- **Property-based Tests** - Hypothesis-based invariant testing
- **Golden Master Tests** - Regression testing with expected outputs

## Adding New Languages

See [New Language Support Checklist](new-language-support-checklist.md) for guidance on adding support for additional languages.

