# Tree-sitter Analyzer

A multi-language static code analysis tool that uses tree-sitter to parse source files into structured code elements, exposed via CLI and MCP protocol.

## Language

**Analysis Engine**:
The core component that orchestrates parsing and querying of a source file. Accepts a file path and query parameters, returns structured `CodeElement` results.
_Alias (legacy)_: `UniversalCodeAnalyzer`, `UnifiedAnalysisEngine` — always prefer "Analysis Engine".

**Language Plugin**:
A module that provides analysis support for one programming language (e.g. `JavaPlugin`, `PythonPlugin`). Each Language Plugin knows its file extensions, owns one **Element Extractor**, and registers with the **Plugin Manager**.
_Context_: "Add a Plugin" = add support for a new language.

**Element Extractor**:
The AST-walking component inside a **Language Plugin** that traverses the tree-sitter syntax tree and produces **Code Elements** (Function, Class, Variable, Import).
_Relationship_: Each **Language Plugin** has exactly one **Element Extractor**.

**Plugin Manager**:
The central registry that loads, indexes, and dispatches all registered **Language Plugins**. When the **Analysis Engine** receives a file, it asks the Plugin Manager for the matching Language Plugin.

**Tree-sitter Query** (or **TS Query**):
An S-expression pattern (e.g. `(class_declaration) @class`) that instructs tree-sitter how to extract a specific kind of **Code Element** from the AST. Each TS Query has a name (key) like `"functions"` or `"classes"` and is language-specific.
_Avoid_: just "Query" when SQL context is also present — use "TS Query" to disambiguate.

**Code Element**:
The base abstraction for any structured piece of code extracted from a source file. Four canonical subtypes:
- **Function** — a callable unit (includes methods, constructors, lambdas)
- **Class** — a type definition (includes interfaces, enums, structs)
- **Variable** — a named data holder (includes fields, constants, properties)
- **Import** — a module or package reference
_Note_: "Method" = language-idiomatic term for a **Function** inside a **Class**. Both are the same model object.

## Relationships

- An **Analysis Engine** uses the **Plugin Manager** to find the right **Language Plugin** for a file.
- Each **Language Plugin** owns one **Element Extractor**.
- An **Element Extractor** uses **Tree-sitter Queries** to produce **Code Elements** from the AST.
- A **Function** may belong to a **Class**.
- The **Analysis Engine** hands results to the **Output Manager**, which selects a **Formatter** and routes output.

**Formatter**:
A rendering engine that converts **Code Elements** into a specific output format (table, JSON, markdown, etc.). Formatters are format-specific; the **Output Manager** selects which one to use.
_Avoid_: "output format" to mean the component itself — "format" is what's produced, "Formatter" is what produces it.

**Output Manager**:
The component that decides which **Formatter** to use, where to write output, and in what **Output Mode** (quiet, verbose, structured). It receives results from the **Analysis Engine** and routes them.

**SMART Workflow**:
The recommended five-step process for AI-assisted code analysis: **S**et project root → **M**ap target files → **A**nalyze structure → **R**etrieve code sections → **T**race dependencies. Each step maps to specific MCP tools and CLI commands.

## Example dialogue

> **Dev:** "I have a 2000-line Python file. Should I run the **Analysis Engine** directly or go through **SMART**?"
> **Domain expert:** "Start with SMART. **Map** the file first, then **Analyze** its structure. If you only need method signatures, use a **TS Query** for `functions` and a compact **Formatter**. Only grab full **Code Elements** when you actually need the body."
> **Dev:** "If the file has both SQL and Python, which **Language Plugin** handles it?"
> **Domain expert:** "It doesn't — one file, one language. The **Plugin Manager** picks based on extension. For mixed concerns, analyze each file separately and trace dependencies across them."

## Flagged ambiguities

- "Query" was used to mean both **Tree-sitter Query** and SQL query — resolved: always use "TS Query" for tree-sitter patterns.
- "Plugin" was used for **Language Plugin**, **Element Extractor**, and the whole plugin system — resolved: "Language Plugin" = a language module; "Element Extractor" = its AST walker; "Plugin Manager" = the registry.
- "Analyzer" / "Engine" / "Analysis Engine" were synonyms — resolved: canonical term is **Analysis Engine**.
