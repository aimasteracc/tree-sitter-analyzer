# API Documentation

## Core Analysis Engine

### AnalysisEngine

The main analysis engine for processing code files.

```python
from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine, AnalysisRequest

# Get engine instance
engine = get_analysis_engine()

# Create analysis request
request = AnalysisRequest(
    file_path="example.java",
    language="java",
    include_complexity=True,
    include_details=True
)

# Perform analysis
result = engine.analyze(request)
```

### AnalysisRequest

Configuration for analysis operations.

**Parameters:**
- `file_path` (str): Path to the code file
- `language` (str, optional): Programming language (auto-detected if not specified)
- `include_complexity` (bool): Include complexity metrics
- `include_details` (bool): Include detailed element information
- `format_type` (str): Output format type

### AnalysisResult

Contains the results of code analysis.

**Properties:**
- `elements`: List of code elements (classes, functions, variables)
- `package`: Package information
- `imports`: Import statements
- `metrics`: Code metrics and complexity data

## MCP Tools

### check_code_scale

Get code metrics and complexity information.

```python
{
  "tool": "check_code_scale",
  "arguments": {
    "file_path": "path/to/file.java",
    "include_complexity": true,
    "include_details": false
  }
}
```

### analyze_code_structure

Generate detailed structure tables for large files.

```python
{
  "tool": "analyze_code_structure", 
  "arguments": {
    "file_path": "path/to/file.java",
    "format_type": "full"
  }
}
```

### read_code_partial

Extract specific line ranges from files.

```python
{
  "tool": "read_code_partial",
  "arguments": {
    "file_path": "path/to/file.java",
    "start_line": 84,
    "end_line": 86
  }
}
```

### analyze_code_universal

Universal analysis with automatic language detection.

```python
{
  "tool": "analyze_code_universal",
  "arguments": {
    "file_path": "path/to/file.py",
    "analysis_type": "comprehensive"
  }
}
```

## Language Support

### Supported Languages

- **Java**: Full support with advanced analysis
- **Python**: Complete support
- **JavaScript/TypeScript**: Full support  
- **C/C++**: Basic support
- **Rust**: Basic support
- **Go**: Basic support

### Language Detection

```python
from tree_sitter_analyzer.language_detector import detect_language_from_file

language = detect_language_from_file("example.java")
print(language)  # Output: "java"
```

## CLI Interface

### Basic Usage

```bash
# Analyze file
uv run python -m tree_sitter_analyzer file.java --advanced

# Generate structure table
uv run python -m tree_sitter_analyzer file.java --table=full

# Partial read
uv run python -m tree_sitter_analyzer file.java --partial-read --start-line 10 --end-line 20
```

### Command Options

- `--advanced`: Include complexity metrics
- `--table=TYPE`: Generate structure table (basic/full)
- `--partial-read`: Enable partial file reading
- `--start-line N`: Start line for partial reading
- `--end-line N`: End line for partial reading
- `--language LANG`: Specify programming language

## Error Handling

All API functions include comprehensive error handling:

```python
try:
    result = engine.analyze(request)
except FileNotFoundError:
    print("File not found")
except UnsupportedLanguageError:
    print("Language not supported")
except AnalysisError as e:
    print(f"Analysis failed: {e}")
```

## Performance Considerations

- Use `include_details=False` for faster analysis
- Enable caching for repeated analysis
- Use partial reading for large files
- Consider language-specific optimizations

For more examples, see the `examples/` directory in the repository.
