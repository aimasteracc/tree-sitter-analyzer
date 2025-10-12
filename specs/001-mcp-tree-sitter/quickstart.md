# Tree-sitter Analyzer MCP Server - Quick Start Guide

## Overview

This guide provides step-by-step instructions for setting up and testing the Tree-sitter Analyzer MCP Server functionality. The MCP server provides AI assistants with powerful code analysis capabilities through 8 specialized tools and 2 resource types.

## Prerequisites

- Python 3.8+
- Tree-sitter Analyzer package installed with MCP support
- Basic understanding of Model Context Protocol (MCP)

## Installation

### Option 1: Install from PyPI (Recommended)
```bash
pip install tree-sitter-analyzer[mcp]
```

### Option 2: Install from Source
```bash
git clone https://github.com/aisheng-yu/tree-sitter-analyzer.git
cd tree-sitter-analyzer
pip install -e .[mcp]
```

## Starting the MCP Server

### Method 1: Using UV (Recommended)
```bash
uv run --with tree-sitter-analyzer[mcp] python -m tree_sitter_analyzer.mcp.server
```

### Method 2: Direct Python
```bash
python -m tree_sitter_analyzer.mcp.server
```

### Method 3: Using Startup Script
```bash
python start_mcp_server.py
```

## Basic Usage Examples

### 1. Code Scale Analysis

Check if a file is suitable for direct analysis or requires staged approach:

```python
# MCP Tool: check_code_scale
{
  "file_path": "src/large_module.py",
  "include_complexity": true,
  "include_guidance": true
}
```

Expected response includes:
- File size and line count
- Complexity metrics
- LLM-optimized analysis recommendations
- Token usage estimates

### 2. Code Structure Analysis

Generate detailed overview tables for large files:

```python
# MCP Tool: analyze_code_structure
{
  "file_path": "src/main.py",
  "format_type": "full",
  "output_file": "analysis_output.md",
  "suppress_output": true
}
```

This creates a comprehensive table showing:
- Classes with line positions
- Methods with parameters and return types
- Fields and their types
- Inheritance relationships

### 3. Targeted Code Extraction

Extract specific code sections by line range:

```python
# MCP Tool: extract_code_section
{
  "file_path": "src/utils.py",
  "start_line": 45,
  "end_line": 80,
  "format": "json"
}
```

### 4. Smart File Search

Find files with advanced filtering:

```python
# MCP Tool: list_files
{
  "roots": ["."],
  "extensions": ["py", "js", "ts"],
  "size": ["+10K"],
  "changed_within": "7d",
  "limit": 100
}
```

### 5. Content Search with Context

Search for code patterns across files:

```python
# MCP Tool: search_content
{
  "roots": ["src/"],
  "query": "class.*Exception",
  "include_globs": ["*.py"],
  "context_before": 2,
  "context_after": 2,
  "summary_only": true
}
```

### 6. Combined File and Content Search

Two-stage search for precise results:

```python
# MCP Tool: find_and_grep
{
  "roots": ["src/"],
  "extensions": ["py"],
  "query": "async def",
  "context_before": 1,
  "context_after": 3,
  "group_by_file": true
}
```

### 7. Tree-sitter Query Execution

Execute custom tree-sitter queries:

```python
# MCP Tool: query_code
{
  "file_path": "src/api.py",
  "query_key": "methods",
  "filter": "public=true",
  "output_format": "json"
}
```

### 8. Project Path Management

Set security boundaries for file access:

```python
# MCP Tool: set_project_path
{
  "project_path": "/absolute/path/to/project"
}
```

## Resource Access Examples

### 1. Code File Resource

Access file content through URI:

```
URI: code://file/src/main.py
```

Returns:
- File content as text
- Metadata (size, language, encoding)
- MIME type information

### 2. Project Statistics Resource

Access various project metrics:

```
URI: code://stats/overview
URI: code://stats/languages
URI: code://stats/file_sizes
URI: code://stats/complexity
URI: code://stats/structure
```

## Testing Scenarios

### Scenario 1: Large File Analysis Workflow

1. **Check Scale**: Use `check_code_scale` to assess file complexity
2. **Get Guidance**: Follow LLM recommendations for analysis strategy
3. **Structure Analysis**: Use `analyze_code_structure` with `suppress_output=true`
4. **Targeted Extraction**: Use `extract_code_section` for specific areas of interest

### Scenario 2: Project Discovery Workflow

1. **File Discovery**: Use `list_files` to understand project structure
2. **Language Analysis**: Access `code://stats/languages` resource
3. **Content Search**: Use `search_content` to find specific patterns
4. **Detailed Analysis**: Use `query_code` for structured code elements

### Scenario 3: Security-Conscious Analysis

1. **Set Boundaries**: Use `set_project_path` to establish security perimeter
2. **Verify Access**: Attempt to access files outside boundary (should fail)
3. **Safe Analysis**: Perform analysis within established boundaries

## Performance Optimization

### Token Management

For large-scale analysis, use these optimization strategies:

1. **Suppress Output**: Use `suppress_output=true` with `output_file`
2. **Summary Mode**: Use `summary_only=true` for search operations
3. **Group Results**: Use `group_by_file=true` to reduce duplication
4. **Total Counts**: Use `total_only=true` for quick statistics

### Staged Analysis Strategy

Follow the recommended workflow:

1. **Scale Check**: Always start with `check_code_scale`
2. **Follow Guidance**: Implement recommended analysis approach
3. **Progressive Detail**: Start with summaries, drill down as needed
4. **File Output**: Save detailed results to files for large datasets

## Error Handling

### Common Error Scenarios

1. **File Not Found**: Verify file paths are correct and within project boundaries
2. **Access Denied**: Check project path settings and security constraints
3. **Invalid Parameters**: Validate input parameters against tool schemas
4. **Resource Limits**: Monitor memory usage for large file operations

### Debugging Tips

1. **Enable Logging**: Set appropriate log levels for debugging
2. **Check Boundaries**: Verify project path configuration
3. **Validate Input**: Use schema validation for tool parameters
4. **Monitor Performance**: Track token usage and response times

## Integration Examples

### With Claude/GPT

```python
# Example MCP client integration
async def analyze_codebase():
    # Check file scale first
    scale_result = await mcp_client.call_tool(
        "check_code_scale",
        {"file_path": "src/large_file.py"}
    )
    
    # Follow guidance
    if scale_result["guidance"]["recommended_approach"] == "staged":
        # Use structure analysis with file output
        await mcp_client.call_tool(
            "analyze_code_structure",
            {
                "file_path": "src/large_file.py",
                "output_file": "analysis.md",
                "suppress_output": True
            }
        )
    else:
        # Direct analysis is safe
        content = await mcp_client.access_resource(
            "code://file/src/large_file.py"
        )
```

### With Custom AI Agents

```python
# Example custom agent integration
class CodeAnalysisAgent:
    def __init__(self, mcp_client):
        self.mcp = mcp_client
    
    async def smart_search(self, pattern, file_types):
        # First, get total count
        total = await self.mcp.call_tool(
            "search_content",
            {
                "roots": ["."],
                "query": pattern,
                "include_globs": [f"*.{ext}" for ext in file_types],
                "total_only": True
            }
        )
        
        # Adjust strategy based on result count
        if total > 100:
            # Use summary mode
            return await self.mcp.call_tool(
                "search_content",
                {
                    "roots": ["."],
                    "query": pattern,
                    "include_globs": [f"*.{ext}" for ext in file_types],
                    "summary_only": True
                }
            )
        else:
            # Full results are manageable
            return await self.mcp.call_tool(
                "search_content",
                {
                    "roots": ["."],
                    "query": pattern,
                    "include_globs": [f"*.{ext}" for ext in file_types],
                    "group_by_file": True
                }
            )
```

## Best Practices

### 1. Security
- Always set project boundaries with `set_project_path`
- Validate file paths before analysis
- Use relative paths when possible

### 2. Performance
- Start with scale checks for unknown files
- Use file output for large results
- Implement progressive disclosure patterns

### 3. Token Efficiency
- Use summary modes for exploration
- Group results to reduce duplication
- Suppress output when saving to files

### 4. Error Resilience
- Implement proper error handling
- Validate inputs before tool calls
- Monitor resource usage

## Troubleshooting

### Server Won't Start
- Check Python version (3.8+ required)
- Verify MCP dependencies are installed
- Check for port conflicts

### Tool Calls Fail
- Validate JSON schema compliance
- Check file path accessibility
- Verify project boundary settings

### Performance Issues
- Monitor memory usage for large files
- Use staged analysis for complex codebases
- Implement result caching where appropriate

### Resource Access Denied
- Check project path configuration
- Verify file permissions
- Ensure paths are within security boundaries

## Next Steps

After completing this quick start:

1. **Explore Advanced Features**: Try custom tree-sitter queries
2. **Integrate with Your Workflow**: Adapt examples to your use case
3. **Optimize Performance**: Implement token-efficient patterns
4. **Contribute**: Report issues and suggest improvements

For more detailed information, refer to the full specification and API documentation.