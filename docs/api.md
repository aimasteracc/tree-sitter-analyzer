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

Get code metrics and complexity information with automatic encoding detection.

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

**Encoding Support**: Automatically detects and handles Shift_JIS, CP932, Latin-1, and other encodings.

### analyze_code_structure

Generate detailed structure tables for large files with encoding support.

```python
{
  "tool": "analyze_code_structure",
  "arguments": {
    "file_path": "path/to/file.java",
    "format_type": "full"
  }
}
```

**Encoding Support**: Works with international source files including Japanese (Shift_JIS, CP932) and European (Latin-1) encodings.

### read_code_partial

Extract specific line ranges from files with safe encoding detection.

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

**Encoding Support**: Automatically detects file encoding and handles various character sets safely.

### analyze_code_universal

Universal analysis with automatic language and encoding detection.

```python
{
  "tool": "analyze_code_universal",
  "arguments": {
    "file_path": "path/to/file.py",
    "analysis_type": "comprehensive"
  }
}
```

**Encoding Support**: Full international support with automatic encoding detection and normalization.

### search_content

Search text content in files with encoding parameter support.

```python
{
  "tool": "search_content",
  "arguments": {
    "query": "function",
    "roots": ["src/"],
    "encoding": "Shift_JIS"  # Automatically normalized to ripgrep-compatible format
  }
}
```

**Encoding Parameters**:
- `encoding` (str, optional): File encoding for search operations
- Automatic normalization: "Shift_JIS" → "shift-jis", "UTF-8" → "utf-8"
- Supported encodings: UTF-8, Shift_JIS, CP932, Latin-1, GBK, ASCII

**Token-Efficient Search Options**:
- `total_only`: Return only match count (~10 tokens)
- `count_only_matches`: Return file-level counts (~50-200 tokens)
- `summary_only`: Return condensed overview (~500-2000 tokens)
- `group_by_file`: Return organized results (~2000-10000 tokens)

### list_files

List files with advanced filtering and encoding awareness.

```python
{
  "tool": "list_files",
  "arguments": {
    "roots": ["src/"],
    "extensions": ["py", "java", "js"],
    "encoding_filter": "non-utf8"  # Optional: filter by encoding type
  }
}
```

**Encoding Features**:
- Automatic encoding detection for file metadata
- Filter files by encoding type
- Handle international file names correctly

## Encoding Support

### read_file_safe()

Safe file reading with automatic encoding detection.

```python
from tree_sitter_analyzer.encoding_utils import read_file_safe

# Read file with automatic encoding detection
content, detected_encoding = read_file_safe("path/to/file.py")
print(f"Content: {content}")
print(f"Detected encoding: {detected_encoding}")
```

**Parameters:**
- `file_path` (str | Path): Path to the file to read
- `fallback_encoding` (str, optional): Fallback encoding if detection fails (default: 'utf-8')

**Returns:**
- `tuple[str, str]`: Content and detected encoding name

**Supported Encodings:**
- UTF-8, UTF-16, UTF-32 (with BOM detection)
- Shift_JIS, CP932 (Japanese)
- GBK, GB2312 (Chinese)
- Latin-1, ISO-8859-1 (European)
- ASCII

### Encoding Detection Behavior

The system automatically detects file encoding using the following strategy:

1. **BOM Detection**: Checks for UTF-8, UTF-16, UTF-32 byte order marks
2. **Chardet Library**: Uses statistical analysis for encoding detection
3. **Confidence Threshold**: Requires >70% confidence for non-UTF-8 encodings
4. **Fallback Chain**: UTF-8 → Latin-1 → ASCII if detection fails

### Encoding Cache

For performance optimization, encoding detection results are cached:

```python
from tree_sitter_analyzer.encoding_utils import EncodingCache

# Get cache instance
cache = EncodingCache()

# Cache statistics
stats = cache.get_stats()
print(f"Cache hits: {stats['hits']}")
print(f"Cache misses: {stats['misses']}")
print(f"Hit rate: {stats['hit_rate']:.2%}")
```

**Cache Features:**
- Thread-safe operation
- TTL-based expiration (default: 1 hour)
- LRU eviction policy
- Configurable size limits

### Encoding Best Practices

#### For File Processing
```python
# ✅ Recommended: Use read_file_safe()
content, encoding = read_file_safe(file_path)

# ❌ Avoid: Hardcoded UTF-8
with open(file_path, 'r', encoding='utf-8') as f:  # May fail
    content = f.read()
```

#### For Search Operations
```python
# MCP search_content tool automatically normalizes encoding names
{
  "tool": "search_content",
  "arguments": {
    "query": "function",
    "roots": ["src/"],
    "encoding": "Shift_JIS"  # Automatically normalized to "shift-jis"
  }
}
```

#### For Language Plugins
```python
# Language plugins automatically use safe encoding detection
from tree_sitter_analyzer.languages.java_plugin import JavaPlugin

plugin = JavaPlugin()
# Automatically handles Shift_JIS, CP932, Latin-1, etc.
result = await plugin.analyze_file("japanese_file.java", request)
```

### Encoding Error Handling

```python
from tree_sitter_analyzer.encoding_utils import read_file_safe
from tree_sitter_analyzer.exceptions import EncodingError

try:
    content, encoding = read_file_safe(file_path)
    print(f"Successfully read file with {encoding} encoding")
except EncodingError as e:
    print(f"Encoding detection failed: {e}")
except FileNotFoundError:
    print("File not found")
except PermissionError:
    print("Permission denied")
```

### International File Support

The system now supports international source code files:

- **Japanese**: Shift_JIS, CP932 encoded files
- **Chinese**: GBK, GB2312 encoded files
- **European**: Latin-1, ISO-8859-1 encoded files
- **Universal**: UTF-8, UTF-16, UTF-32 with BOM

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

All API functions include comprehensive error handling with encoding support:

```python
from tree_sitter_analyzer.exceptions import EncodingError, UnsupportedLanguageError, AnalysisError

try:
    result = engine.analyze(request)
except FileNotFoundError:
    print("File not found")
except EncodingError as e:
    print(f"Encoding detection failed: {e}")
except UnsupportedLanguageError:
    print("Language not supported")
except AnalysisError as e:
    print(f"Analysis failed: {e}")
```

### Encoding-Specific Error Handling

```python
from tree_sitter_analyzer.encoding_utils import read_file_safe

try:
    content, encoding = read_file_safe(file_path)
    print(f"File read successfully with {encoding} encoding")
except EncodingError as e:
    print(f"Could not detect encoding: {e}")
    # Fallback to manual encoding specification
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
except UnicodeDecodeError as e:
    print(f"Unicode decode error: {e}")
    # Try with different encoding
    with open(file_path, 'r', encoding='latin-1') as f:
        content = f.read()
```

## Performance Considerations

### General Optimizations
- Use `include_details=False` for faster analysis
- Enable caching for repeated analysis
- Use partial reading for large files
- Consider language-specific optimizations

### Encoding Performance
- **Encoding Cache**: Automatic caching reduces detection overhead by 80%+
- **UTF-8 Fast Path**: UTF-8 files have minimal performance impact (<5%)
- **BOM Detection**: Instant detection for files with byte order marks
- **Confidence Threshold**: Optimized detection reduces false positives

### Search Performance with Encoding
```python
# ✅ Efficient: Use token-optimized search formats
{
  "tool": "search_content",
  "arguments": {
    "query": "function",
    "roots": ["src/"],
    "total_only": true  # ~10 tokens vs ~50000+ for full results
  }
}

# ✅ Efficient: Cache-friendly encoding specification
{
  "tool": "search_content",
  "arguments": {
    "query": "class",
    "roots": ["src/"],
    "encoding": "shift-jis"  # Normalized and cached
  }
}
```

### Memory Optimization
- Encoding cache uses TTL-based expiration (1 hour default)
- LRU eviction prevents memory bloat
- Thread-safe operations for concurrent access
- Configurable cache size limits

## Examples and Demos

### Encoding Demo
See `examples/encoding_demo.py` for a comprehensive demonstration of:
- Shift_JIS file processing
- Encoding normalization
- Search functionality with various encodings
- Performance comparison

### International File Support
```python
# Japanese source files
result = analyze_file("日本語ファイル.java")  # Shift_JIS/CP932 support

# Chinese source files
result = analyze_file("中文文件.py")  # GBK/GB2312 support

# European source files
result = analyze_file("français.js")  # Latin-1 support
```

For more examples, see the `examples/` directory in the repository.
