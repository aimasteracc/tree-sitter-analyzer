# CLI Reference

Complete command-line interface reference for Tree-sitter Analyzer.

## Table of Contents

- [Basic Usage](#basic-usage)
- [Code Structure Analysis](#code-structure-analysis)
- [Query and Filter Commands](#query-and-filter-commands)
- [File System Operations](#file-system-operations)
- [Information Commands](#information-commands)
- [SQL Cross-Platform Commands](#sql-cross-platform-commands)
- [Output Formats](#output-formats)
- [Filter Syntax](#filter-syntax)

## Basic Usage

```bash
uv run tree-sitter-analyzer <file_path> [options]
```

### Global Options

| Option | Description |
|--------|-------------|
| `--help` | Show help message |
| `--show-supported-languages` | Show supported languages |
| `--language <lang>` | Specify programming language (auto-detected by default) |
| `--output-format <format>` | Output format: `json`, `text` |

## Code Structure Analysis

### Summary Analysis

```bash
# Quick summary (file scale and overview)
uv run tree-sitter-analyzer examples/BigService.java --summary
```

### Structure Analysis

```bash
# Detailed structure (all elements)
uv run tree-sitter-analyzer examples/BigService.java --structure
```

### Advanced Analysis

```bash
# Advanced analysis with complexity metrics
uv run tree-sitter-analyzer examples/BigService.java --advanced

# With JSON output
uv run tree-sitter-analyzer examples/BigService.java --advanced --output-format json

# With text output
uv run tree-sitter-analyzer examples/BigService.java --advanced --output-format text
```

### Table Output

```bash
# Full table (comprehensive)
uv run tree-sitter-analyzer examples/BigService.java --table full

# Compact table (abbreviated)
uv run tree-sitter-analyzer examples/BigService.java --table compact

# CSV format (machine-readable)
uv run tree-sitter-analyzer examples/BigService.java --table csv
```

### Partial Code Extraction

```bash
# Extract specific line range
uv run tree-sitter-analyzer examples/BigService.java --partial-read --start-line 93 --end-line 106

# Extract from start line to end of file
uv run tree-sitter-analyzer examples/BigService.java --partial-read --start-line 100
```

### Language-Specific Examples

#### HTML/CSS Analysis

```bash
# HTML analysis
uv run tree-sitter-analyzer examples/comprehensive_sample.html --table full
uv run tree-sitter-analyzer examples/comprehensive_sample.html --structure

# CSS analysis
uv run tree-sitter-analyzer examples/comprehensive_sample.css --table full
uv run tree-sitter-analyzer examples/comprehensive_sample.css --advanced --output-format text
```

#### SQL Database Analysis

```bash
# Full table output
uv run tree-sitter-analyzer examples/sample_database.sql --table full

# Compact summary
uv run tree-sitter-analyzer examples/sample_database.sql --table compact

# CSV for export
uv run tree-sitter-analyzer examples/sample_database.sql --table csv

# Advanced text analysis
uv run tree-sitter-analyzer examples/sample_database.sql --advanced --output-format text
```

#### Markdown Analysis

```bash
# Analyze markdown structure
uv run tree-sitter-analyzer docs/README.md --table full

# View document structure
uv run tree-sitter-analyzer docs/README.md --structure
```

## Query and Filter Commands

### Query Specific Elements

```bash
# Query methods
uv run tree-sitter-analyzer examples/BigService.java --query-key methods

# Query classes
uv run tree-sitter-analyzer examples/BigService.java --query-key classes

# Query functions (for Python, JavaScript)
uv run tree-sitter-analyzer examples/sample.py --query-key functions

# Query imports
uv run tree-sitter-analyzer examples/BigService.java --query-key imports
```

### Filter Query Results

```bash
# Find specific method by name
uv run tree-sitter-analyzer examples/BigService.java --query-key methods --filter "name=main"

# Pattern matching (wildcard)
uv run tree-sitter-analyzer examples/BigService.java --query-key methods --filter "name=~auth*"

# Find public methods with no parameters
uv run tree-sitter-analyzer examples/BigService.java --query-key methods --filter "params=0,public=true"

# Find static methods
uv run tree-sitter-analyzer examples/BigService.java --query-key methods --filter "static=true"
```

### View Filter Help

```bash
uv run tree-sitter-analyzer --filter-help
```

> **⚠️ Note:** `--table` and `--query-key` are mutually exclusive. Use `--query-key` with `--filter` for filtering.

## File System Operations

### List Files (fd-based)

```bash
# List all files in current directory
uv run list-files .

# Filter by extension
uv run list-files . --extensions java

# Filter by pattern and type
uv run list-files . --pattern "test_*" --extensions py --types f

# Filter by size and modification time
uv run list-files . --types f --size "+1k" --changed-within "1week"

# Exclude directories
uv run list-files . --exclude "node_modules" --exclude "__pycache__"
```

### Search Content (ripgrep-based)

```bash
# Basic content search
uv run search-content --roots . --query "class.*extends" --include-globs "*.java"

# Search with context
uv run search-content --roots tests --query "TODO|FIXME" --context-before 2 --context-after 2

# Case-insensitive search
uv run search-content --files examples/BigService.java --query "public.*method" --case insensitive

# Search multiple directories
uv run search-content --roots src tests --query "import" --include-globs "*.py"
```

### Two-Stage Search (fd + ripgrep)

```bash
# Find files then search content
uv run find-and-grep --roots . --query "@SpringBootApplication" --extensions java

# With file and content limits
uv run find-and-grep --roots examples --query "import.*SQLException" --extensions java --file-limit 10 --max-count 5

# With JSON output
uv run find-and-grep --roots . --query "public.*static.*void" --extensions java --types f --size "+1k" --output-format json
```

## Information Commands

### Help and Version

```bash
# Show help
uv run tree-sitter-analyzer --help

# Show supported languages
uv run tree-sitter-analyzer --show-supported-languages
```

### Language Support Information

```bash
# List supported query keys
uv run tree-sitter-analyzer --list-queries

# Show supported languages
uv run tree-sitter-analyzer --show-supported-languages

# Show supported file extensions
uv run tree-sitter-analyzer --show-supported-extensions

# Show common queries for each language
uv run tree-sitter-analyzer --show-common-queries

# Show query language support matrix
uv run tree-sitter-analyzer --show-query-languages
```

## SQL Cross-Platform Commands

```bash
# Show current platform SQL parsing capabilities
uv run tree-sitter-analyzer --sql-platform-info

# Record a custom SQL parsing profile
uv run tree-sitter-analyzer --record-sql-profile

# Compare two SQL profiles
uv run tree-sitter-analyzer --compare-sql-profiles windows-3.13 linux-3.10
```

## Output Formats

### JSON Output

```bash
# Code analysis to JSON
uv run tree-sitter-analyzer examples/sample.py --advanced --output-format json

# Search results to JSON
uv run find-and-grep --roots . --query "def " --extensions py --output-format json
```

### Text Output

```bash
# Human-readable text output
uv run tree-sitter-analyzer examples/sample.py --advanced --output-format text
```

### Table Formats

| Format | Description | Use Case |
|--------|-------------|----------|
| `full` | Comprehensive table with all details | Detailed analysis |
| `compact` | Abbreviated summary | Quick overview |
| `csv` | Comma-separated values | Export to spreadsheet |

## Filter Syntax

### Exact Match

```bash
--filter "name=main"          # Method named exactly "main"
--filter "visibility=public"  # Public visibility
--filter "params=2"           # Methods with 2 parameters
```

### Pattern Match (Wildcard)

```bash
--filter "name=~get*"         # Names starting with "get"
--filter "name=~*Service"     # Names ending with "Service"
--filter "name=~*auth*"       # Names containing "auth"
```

### Boolean Filters

```bash
--filter "public=true"        # Public methods
--filter "static=true"        # Static methods
--filter "async=true"         # Async methods
```

### Compound Filters

```bash
# Multiple conditions (AND)
--filter "public=true,static=true"

# Combine with pattern
--filter "name=~get*,public=true"

# Multiple conditions
--filter "params=0,public=true,static=false"
```

### Available Filter Fields

| Field | Description | Example |
|-------|-------------|---------|
| `name` | Element name | `name=main`, `name=~get*` |
| `visibility` | Visibility modifier | `visibility=public` |
| `public` | Is public | `public=true` |
| `private` | Is private | `private=true` |
| `protected` | Is protected | `protected=true` |
| `static` | Is static | `static=true` |
| `async` | Is async | `async=true` |
| `params` | Parameter count | `params=2`, `params=0` |

## Security Notes

Tree-sitter Analyzer enforces security boundaries:

- Files outside the project directory are inaccessible
- Path traversal attacks are automatically prevented
- Invalid parameter combinations are rejected with clear error messages

```bash
# ✅ Allowed: File within project
uv run tree-sitter-analyzer examples/BigService.java --advanced

# ❌ Denied: File outside project boundary
# uv run tree-sitter-analyzer /etc/passwd --advanced
# Error: Access denied - file outside project boundary
```

## Examples

### Complete Workflow Example

```bash
# 1. Check what files exist
uv run list-files . --extensions java --types f

# 2. Search for specific content
uv run search-content --roots . --query "class.*Service" --include-globs "*.java"

# 3. Analyze found file
uv run tree-sitter-analyzer src/UserService.java --summary

# 4. Get detailed structure
uv run tree-sitter-analyzer src/UserService.java --table full

# 5. Extract specific method
uv run tree-sitter-analyzer src/UserService.java --query-key methods --filter "name=authenticate"
```

### Token-Optimized Analysis (for large files)

```bash
# 1. Check file scale first
uv run tree-sitter-analyzer large_file.java --summary

# 2. If large, use compact format
uv run tree-sitter-analyzer large_file.java --table compact

# 3. Query specific elements instead of full analysis
uv run tree-sitter-analyzer large_file.java --query-key methods --filter "public=true"

# 4. Extract only the lines you need
uv run tree-sitter-analyzer large_file.java --partial-read --start-line 100 --end-line 150
```

