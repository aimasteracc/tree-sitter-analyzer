# Tree-sitter Analyzer Features

This document provides a comprehensive overview of the language-specific features supported by Tree-sitter Analyzer.

## Supported Languages

### Systems Programming Languages

#### Go 🆕

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

