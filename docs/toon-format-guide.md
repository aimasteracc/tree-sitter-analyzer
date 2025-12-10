# TOON Format Guide

TOON (Token-Oriented Object Notation) is a data format optimized for LLM consumption, providing 50-70% token reduction compared to JSON while maintaining human readability.

## Overview

### What is TOON?

TOON is a YAML-like data format designed specifically to reduce token consumption when communicating with Large Language Models (LLMs) like GPT-4 and Claude. It achieves this by:

- Eliminating redundant syntax (quotes, brackets, commas)
- Using compact array table format for homogeneous data
- Maintaining human readability

### Token Reduction Results

| Data Type | Reduction |
|-----------|-----------|
| Simple Dictionary | ~41% |
| Code Analysis Result | ~52% |
| MCP Tool Response | ~59% |
| **Average** | **~51%** |

## Format Specification

### Primitive Values

```
# Null
null

# Boolean
true
false

# Numbers
42
3.14
-100

# Strings (unquoted when safe)
hello
simple_string
```

### Strings with Special Characters

Strings containing special characters are quoted and escaped:

```
# String with newline
"line1\nline2"

# String with tab
"col1\tcol2"

# String with colon
"key:value"

# String with quotes
"said \"hello\""
```

### Dictionaries

TOON uses YAML-like key-value syntax:

```
name: example
count: 42
active: true
```

Nested dictionaries use indentation:

```
file: sample.py
metadata:
  language: python
  version: 3.11
statistics:
  lines: 100
  methods: 5
```

### Simple Arrays

Simple arrays use bracket notation:

```
items: [1,2,3,4,5]
tags: [python,typescript,rust]
```

### Array Tables (Compact Format)

Homogeneous arrays of objects use a compact table format:

```
[count]{field1,field2,field3}:
  value1,value2,value3
  value4,value5,value6
```

Example:

```
methods:
  [4]{name,visibility,lines}:
    init,public,1-10
    process,public,12-45
    validate,private,47-60
    cleanup,public,62-70
```

This is equivalent to the JSON:

```json
{
  "methods": [
    {"name": "init", "visibility": "public", "lines": "1-10"},
    {"name": "process", "visibility": "public", "lines": "12-45"},
    {"name": "validate", "visibility": "private", "lines": "47-60"},
    {"name": "cleanup", "visibility": "public", "lines": "62-70"}
  ]
}
```

**Token savings: ~53%** for this example.

## CLI Usage

### Basic Commands

```bash
# Structure analysis with TOON output
uv run python -m tree_sitter_analyzer.cli file.py --structure --format toon

# Or use --output-format
uv run python -m tree_sitter_analyzer.cli file.py --structure --output-format toon

# Summary with TOON
uv run python -m tree_sitter_analyzer.cli file.py --summary --format toon

# Advanced analysis
uv run python -m tree_sitter_analyzer.cli file.py --advanced --format toon

# Partial read
uv run python -m tree_sitter_analyzer.cli file.py --partial-read --start-line 1 --end-line 50 --format toon
```

### Tab Delimiter Mode

For additional compression, use tab delimiters:

```bash
uv run python -m tree_sitter_analyzer.cli file.py --structure --format toon --toon-use-tabs
```

### Example Output

```bash
$ uv run python -m tree_sitter_analyzer.cli examples/sample.py --structure --format toon

--- Structure Analysis Results ---
file_path: examples/sample.py
language: python
package: null
classes:
  [3]{name}:
    Animal
    Dog
    Cat
methods:
  [18]{name}:
    __init__
    describe
    ...
fields: []
imports: []
statistics:
  class_count: 3
  method_count: 18
  field_count: 1
  import_count: 4
  total_lines: 256
```

## MCP Tool Usage

All MCP tools support the `output_format` parameter:

### analyze_code_structure

```json
{
  "file_path": "sample.py",
  "output_format": "toon"
}
```

### list_files

```json
{
  "directory": "src",
  "output_format": "toon"
}
```

### search_content

```json
{
  "pattern": "def.*test",
  "output_format": "toon"
}
```

### query_code

```json
{
  "file_path": "sample.py",
  "query_key": "function",
  "output_format": "toon"
}
```

### read_partial

```json
{
  "file_path": "sample.py",
  "start_line": 1,
  "end_line": 50,
  "output_format": "toon"
}
```

### table_format

```json
{
  "file_path": "sample.py",
  "output_format": "toon"
}
```

## Python API

### Using ToonEncoder (Low-Level)

```python
from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

encoder = ToonEncoder()

# Encode simple data
data = {"name": "test", "count": 42}
print(encoder.encode(data))
# Output:
# name: test
# count: 42

# Encode array table
methods = [
    {"name": "init", "line": 10},
    {"name": "process", "line": 20},
]
print(encoder.encode_array_table(methods))
# Output:
# [2]{name,line}:
#   init,10
#   process,20
```

### Using ToonFormatter (High-Level)

```python
from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter

formatter = ToonFormatter()

# Format any data
data = {
    "success": True,
    "results": [
        {"file": "a.py", "lines": 100},
        {"file": "b.py", "lines": 200},
    ]
}
print(formatter.format(data))
```

### Using OutputManager

```python
from tree_sitter_analyzer.output_manager import OutputManager

manager = OutputManager(output_format="toon")
manager.data({"key": "value"})
```

### Tab Delimiter Mode

```python
encoder = ToonEncoder(use_tabs=True)
formatter = ToonFormatter(use_tabs=True)
```

## Error Handling

### Circular Reference Detection

TOON encoder automatically detects and handles circular references:

```python
from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder, ToonEncodeError

encoder = ToonEncoder(fallback_to_json=False)

# This will raise ToonEncodeError
circular = {"key": "value"}
circular["self"] = circular

try:
    encoder.encode(circular)
except ToonEncodeError as e:
    print(f"Error: {e.message}")
```

### JSON Fallback

By default, encoding errors fall back to JSON:

```python
encoder = ToonEncoder(fallback_to_json=True)  # Default

# On error, returns JSON instead of raising
result = encoder.encode(problematic_data)
```

### Safe Encoding

Use `encode_safe()` for guaranteed string output:

```python
encoder = ToonEncoder()

# Never raises, always returns a string
result = encoder.encode_safe(any_data)
```

### Maximum Depth Limit

Prevent stack overflow with depth limits:

```python
encoder = ToonEncoder(max_depth=50)  # Default: 100
```

## Best Practices

### When to Use TOON

✅ **Use TOON for:**
- LLM API calls (reduce token costs)
- Code analysis results
- MCP tool responses
- Structured data with arrays of similar objects

❌ **Avoid TOON for:**
- Data interchange with external systems
- APIs requiring JSON
- Cases where JSON schema validation is needed

### Maximizing Token Savings

1. **Use array tables** for homogeneous data:
   ```
   # Good: Array table format
   [100]{name,line}:
     func1,10
     func2,20
     ...
   
   # Avoid: Individual objects
   - name: func1
     line: 10
   - name: func2
     line: 20
   ```

2. **Keep keys short but descriptive**:
   ```
   # Good
   ln: 100
   
   # Okay
   line_count: 100
   
   # Avoid
   total_number_of_lines_in_file: 100
   ```

3. **Use tab delimiter for maximum compression**:
   ```bash
   --format toon --toon-use-tabs
   ```

## Comparison with Other Formats

| Feature | JSON | YAML | TOON |
|---------|------|------|------|
| Token Efficiency | Low | Medium | High |
| Human Readable | Medium | High | High |
| LLM Optimized | No | No | **Yes** |
| Array Tables | No | No | **Yes** |
| Schema Support | Yes | Yes | Partial |
| Standard | RFC 8259 | YAML 1.2 | Custom |

## Running Benchmarks

```bash
# Run token reduction benchmark
uv run python examples/toon_token_benchmark.py

# Run demo
uv run python examples/toon_demo.py
```

## Troubleshooting

### "Circular reference detected"

Your data contains a circular reference. Either:
1. Remove the circular reference
2. Use `fallback_to_json=True` (default)
3. Use `encode_safe()` method

### "Maximum nesting depth exceeded"

Your data is too deeply nested. Either:
1. Flatten the data structure
2. Increase `max_depth` parameter

### Output looks like JSON

TOON fell back to JSON due to an encoding error. Check logs for details:

```python
import logging
logging.basicConfig(level=logging.WARNING)
```

## Version History

- **v1.6.2**: Initial TOON support
  - ToonEncoder and ToonFormatter
  - CLI `--format toon` option
  - MCP tool `output_format` parameter
  - Error handling with JSON fallback
  - Iterative implementation (no recursion)

## See Also

- [CLI Reference](cli-reference.md)
- [API Documentation](api/)
- [Examples](../examples/)

