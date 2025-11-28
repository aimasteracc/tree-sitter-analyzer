# SMART Workflow Guide

The SMART workflow is the recommended process for analyzing code using AI assistants with Tree-sitter Analyzer.

## What is SMART?

**SMART** is an acronym for the five-step AI-assisted code analysis workflow:

- **S** - **Set**: Set the project root directory
- **M** - **Map**: Map and locate target files
- **A** - **Analyze**: Analyze code structure
- **R** - **Retrieve**: Retrieve specific code sections
- **T** - **Trace**: Trace dependencies and relationships

## Why SMART?

Traditional approaches to AI code analysis have limitations:

| Problem | SMART Solution |
|---------|----------------|
| Token limits prevent reading large files | Structured analysis before code extraction |
| AI struggles with unknown codebases | Systematic file discovery and mapping |
| Context gets lost in long conversations | Step-by-step workflow with clear checkpoints |
| Inefficient back-and-forth | Optimized tool usage sequence |

## Step-by-Step Guide

### S - Set Project (First Step)

**Purpose**: Establish the security boundary and project context.

**How to do it**:

Tell your AI assistant:
```
Please set the project root directory to: /path/to/your/project
```

The AI will call the `set_project_path` MCP tool.

**Why it matters**:
- Enables security boundary protection
- All subsequent operations are relative to this path
- Prevents accidental access to files outside the project

> 💡 **Tip**: You can also pre-set the project path via `TREE_SITTER_PROJECT_ROOT` environment variable in your MCP configuration.

### M - Map Target Files

**Purpose**: Locate and identify files to analyze.

**Scenario 1: Unknown file location**

```
Find all Java files containing "BigService" in the project
```

The AI will use `find_and_grep` to locate relevant files.

**Scenario 2: Known file path**

```
I want to analyze the file examples/BigService.java
```

**Scenario 3: Discover project structure**

```
List all Python files in the src directory
```

**Best practices**:
- Start broad, then narrow down
- Use file patterns when you know naming conventions
- Combine file and content search for precision

### A - Analyze Structure

**Purpose**: Understand file scale and organization before diving into code.

**Example request**:
```
Please analyze the structure of examples/BigService.java, I want to know how big this file is and what main components it contains
```

The AI will call `analyze_code_structure` and return:

```json
{
  "file_path": "examples/BigService.java",
  "language": "java",
  "metrics": {
    "lines_total": 1419,
    "lines_code": 906,
    "lines_comment": 246,
    "lines_blank": 267,
    "elements": {
      "classes": 1,
      "methods": 66,
      "fields": 9,
      "imports": 8,
      "packages": 1,
      "total": 85
    },
    "complexity": {
      "total": 348,
      "average": 5.27,
      "max": 15
    }
  }
}
```

**Key insights**:
- Total line count helps estimate analysis scope
- Element counts show code organization
- Complexity metrics identify potentially problematic areas

### R - Retrieve Key Code

**Purpose**: Extract and examine specific code sections.

**Scenario 1: View structure table**

```
Please generate a detailed structure table for examples/BigService.java
```

**Scenario 2: Extract by line range**

```
Please extract lines 93-106 from examples/BigService.java
```

**Scenario 3: Query specific elements**

```
Show me all public methods in examples/BigService.java
```

**Best practices**:
- Start with structure table to identify targets
- Extract small, focused code sections
- Use queries with filters for precision

### T - Trace Dependencies

**Purpose**: Understand relationships and call chains.

**Scenario 1: Find related methods**

```
Find all methods related to authentication in examples/BigService.java
```

**Scenario 2: Locate entry points**

```
Where is the main method in this file? What does it do?
```

**Scenario 3: Track method calls**

```
Which methods call the authenticateUser method?
```

**Best practices**:
- Trace from entry points to understand flow
- Use content search to find callers
- Combine multiple searches for complete picture

## Complete Example Session

Here's a complete SMART workflow session:

### User:
```
I want to understand the large file examples/BigService.java:
1. How big is it? What main features does it contain?
2. How is the authentication feature implemented?
3. What public API methods are available?
```

### AI Response (Following SMART):

**Step 1 (Set)**: *(Assumed already set or will prompt)*

**Step 2 (Map)**: Located file at examples/BigService.java

**Step 3 (Analyze)**:
- File has 1419 lines total
- Contains 1 class with 66 methods and 9 fields
- Average complexity: 5.27

**Step 4 (Retrieve)**:
- Authentication is handled by `authenticateUser` method (lines 141-172)
- Uses session-based authentication with configurable timeouts

**Step 5 (Trace)**:
- Found 19 public methods available as API
- Authentication is called from the `main` method during initialization

## Language-Specific Examples

### Web Development (HTML/CSS)

```
I want to analyze the HTML structure of index.html:
1. What HTML elements are present?
2. What CSS rules are defined?
3. How are elements classified?
```

AI will:
1. Extract HTML elements with tag names and attributes
2. Analyze CSS selectors and properties
3. Generate classification tables (structure, media, form)

### Database Development (SQL)

```
I want to analyze the database schema in sample_database.sql:
1. What tables, views, and stored procedures are defined?
2. What are the relationships between database objects?
3. Show me the database structure in professional format.
```

AI will:
1. Extract all SQL elements (tables, views, procedures, triggers)
2. Display database-specific terminology
3. Generate professional documentation

## Best Practices

### 1. Natural Language First

Describe your needs in plain language:

```
✅ Good: "I want to understand how user authentication works in this project"
❌ Avoid: "Call analyze_code_structure on auth.py with format=full"
```

### 2. Start High, Go Deep

Begin with overview, then drill down:

```
1. "What does this project contain?"
2. "What files handle authentication?"
3. "Show me the login function"
4. "Extract the password validation logic"
```

### 3. Combine Steps When Appropriate

For simple cases, you can combine steps:

```
"Analyze src/auth.py and show me all public methods"
```

### 4. Use Checkpoints

For complex analysis, verify understanding:

```
"Before we continue, let me confirm: this file has 3 main classes - UserService, AuthService, and SessionManager. Is that correct?"
```

### 5. Optimize for Large Files

For files > 500 lines:

```
1. Always analyze structure first
2. Use table compact for overview
3. Extract specific sections, not whole file
4. Query specific elements with filters
```

## Tool Reference

| Workflow Step | Primary MCP Tool | CLI Equivalent |
|---------------|------------------|----------------|
| Set | `set_project_path` | N/A (config) |
| Map | `list_files`, `find_and_grep` | `list-files`, `find-and-grep` |
| Analyze | `analyze_code_structure`, `check_code_scale` | `--table`, `--summary` |
| Retrieve | `extract_code_section`, `query_code` | `--partial-read`, `--query-key` |
| Trace | `search_content`, `find_and_grep` | `search-content` |

## Troubleshooting

### "File too large to analyze"

Use incremental approach:
1. Check scale with `check_code_scale`
2. Use `--table compact` for overview
3. Query specific elements instead of full analysis

### "Can't find the file"

Use discovery tools:
1. `list_files` with broad pattern
2. `find_and_grep` with content search
3. Check file extension and directory

### "Results are too verbose"

Apply optimization:
1. Use `suppress_output` with `output_file`
2. Apply filters to narrow results
3. Use `summary_only` or `total_only` options

## Further Reading

- [CLI Reference](cli-reference.md) - Complete command-line reference
- [MCP Tools Specification](api/mcp_tools_specification.md) - Detailed API documentation
- [Features Overview](features.md) - Language-specific features

