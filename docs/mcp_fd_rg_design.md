## MCP Tools: list_files, search_content, find_and_grep

Purpose: Provide a safe, composable file/name search and content search capability via fd and ripgrep, unified behind consistent MCP tool interfaces.

### Principles
- Simple, consistent inputs; machine-readable outputs.
- Security: enforce project-root boundaries, result caps, timeouts, and filesize limits.
- Composability: allow fd-only, rg-only, or fd→rg in one call.

### Common Safety Defaults
- roots must lie within project root; reject paths outside.
- limit caps: list_files.limit default 2000, hard-cap 10000.
- file_limit default 2000, hard-cap 10000.
- rg --max-filesize default 10M; overridable but hard-capped to 200M.
- rg timeout default 4000 ms; hard-capped at 30000 ms.
- Hidden/ignore: by default respect .gitignore; hidden=false; no_ignore=false.

### Tool 1: list_files (fd)
Input schema (subset):
- roots: string[] (required)
- pattern?: string; glob?: boolean=false
- types?: string[] (fd -t f/d/l/x/e)
- extensions?: string[] (fd -e)
- exclude?: string[] (glob -> fd -E)
- depth?: number (fd -d)
- follow_symlinks?: boolean (fd -L)
- hidden?: boolean (fd -H)
- no_ignore?: boolean (fd -I)
- size?: string[] (fd -S, eg +10M)
- changed_within?: string (eg 2d)
- changed_before?: string
- full_path_match?: boolean (-p)
- absolute?: boolean (-a)
- limit?: number

Output:
- JSON array of { path, is_dir, size_bytes?, mtime?, ext? }
- All paths absolute.

Mapping to fd:
- Use fd with --color=never and templated --format to produce machine-readable TSV/JSONL.
- For cross-platform stability, prefer TSV and parse.

### Tool 2: search_content (ripgrep)
Input:
- roots?: string[] or files?: string[] (one required)
- query: string (required)
- regex?: boolean=true; fixed_strings?: boolean; word?: boolean
- case?: "smart"|"insensitive"|"sensitive"
- multiline?: boolean
- include_globs?: string[]; exclude_globs?: string[]
- follow_symlinks?: boolean; hidden?: boolean; no_ignore?: boolean
- max_filesize?: string (default 10M, hard-cap 200M)
- context_before?: number; context_after?: number
- encoding?: string; max_count?: number; timeout_ms?: number (default 4000)

#### Encoding Parameter Support
The `encoding` parameter enables searching files with various character encodings:

**Supported Encodings:**
- UTF-8, UTF-16, UTF-32 (with BOM detection)
- Shift_JIS, CP932 (Japanese)
- GBK, GB2312 (Chinese)
- Latin-1, ISO-8859-1 (European)
- ASCII

**Automatic Normalization:**
The system automatically normalizes encoding names to ripgrep-compatible format:
- "Shift_JIS" → "shift-jis"
- "UTF-8" → "utf-8"
- "CP932" → "shift-jis" (CP932 is treated as Shift_JIS variant)
- "latin1" → "latin1"
- "GBK" → "gbk"

**Usage Examples:**
```json
// Japanese files with Shift_JIS encoding
{
  "tool": "search_content",
  "arguments": {
    "query": "クラス",
    "roots": ["src/"],
    "encoding": "Shift_JIS"
  }
}

// European files with Latin-1 encoding
{
  "tool": "search_content",
  "arguments": {
    "query": "café",
    "roots": ["src/"],
    "encoding": "latin-1"
  }
}

// Chinese files with GBK encoding
{
  "tool": "search_content",
  "arguments": {
    "query": "函数",
    "roots": ["src/"],
    "encoding": "GBK"
  }
}
```

**Encoding Detection Fallback:**
If no encoding is specified, the system uses automatic detection:
1. BOM detection for UTF-8/16/32
2. Statistical analysis via chardet library
3. Confidence threshold (>70%) for non-UTF-8 encodings
4. Fallback chain: UTF-8 → Latin-1 → ASCII

Output:
- Array of matches: { file, abs_path, line_number, line, submatches:[{start,end,match}] }
- Only emit match events from rg --json.

Mapping to ripgrep:
- Always pass --json --no-heading --color=never.
- case -> -S/-i/-s; fixed -> -F; word -> -w; multiline -> -U.
- include_globs/exclude_globs -> repeated -g patterns; exclusions prefixed with '!'.
- Respect hidden/no_ignore/follow_symlinks.
- encoding -> -E with normalized encoding name (e.g., "Shift_JIS" becomes "shift-jis").

**Encoding Normalization Process:**
```python
def normalize_encoding_name(encoding: str) -> str:
    """Normalize encoding names for ripgrep compatibility."""
    if not encoding:
        return encoding
    
    # Convert to lowercase for consistent processing
    normalized = encoding.lower().replace('_', '-')
    
    # Handle specific mappings
    encoding_map = {
        'shift-jis': 'shift-jis',
        'sjis': 'shift-jis',
        'cp932': 'shift-jis',  # CP932 is Shift_JIS variant
        'utf-8': 'utf-8',
        'utf8': 'utf-8',
        'latin-1': 'latin1',
        'iso-8859-1': 'latin1',
        'gbk': 'gbk',
        'gb2312': 'gbk',
        'ascii': 'ascii'
    }
    
    return encoding_map.get(normalized, encoding)
```

### Tool 3: find_and_grep (fd→rg)
Input:
- All relevant list_files inputs + search_content core inputs
- file_limit?: number (truncate fd outputs before rg)
- sort?: "path"|"mtime"|"size"
- encoding?: string (inherited from search_content, with same normalization)

Output:
- Same as search_content plus meta: { searched_file_count, truncated, fd_elapsed_ms, rg_elapsed_ms }

**Encoding Support in find_and_grep:**
The combined tool inherits full encoding support from search_content:
- Automatic encoding normalization for ripgrep compatibility
- Support for international file processing
- Consistent encoding parameter handling across the pipeline

Implementation Notes
- SecurityValidator: validate roots under project boundary; reject absolute roots outside.
- Use PathResolver to normalize/absolutize. De-duplicate files.
- For large sets, write file list to a temporary file; pass via rg --files-from.
- Enforce caps and timeouts at both subprocess level (rg --timeout) and asyncio wait_for.
- Windows/macOS/Linux compatible; ensure UTF-8 I/O; no color codes.
- Encoding normalization applied before ripgrep command construction.

Testing Strategy
- Unit tests: argument validation, boundary checks, flag mapping, JSON parsing.
- Mocked subprocess for fd/rg happy-path and error-path.
- Integration smoke test gated by environment (skipped on CI if binaries missing).
- Encoding normalization tests: verify correct mapping of encoding names.
- International file tests: validate Shift_JIS, Latin-1, GBK file processing.

Version Bounds
- fd ≥ 10.x; ripgrep ≥ 13.x. Tools degrade gracefully with clear error messages if missing.

## LLM Guidance Design

### Token Efficiency Architecture

The search_content tool is designed with a **progressive disclosure** architecture to minimize token consumption for LLM interactions:

#### Output Format Hierarchy (Token Efficiency Order)
1. **total_only** (~10 tokens) - Single integer count
2. **count_only_matches** (~50-200 tokens) - File-level counts object
3. **summary_only** (~500-2000 tokens) - Condensed overview with samples
4. **group_by_file** (~2000-10000 tokens) - Results organized by file
5. **optimize_paths** (10-30% reduction) - Path compression enhancement
6. **Full results** (~2000-50000+ tokens) - Complete match details

#### Smart Format Selection Logic
```python
def determine_optimal_format(query_scope, user_intent):
    if user_intent == "count_validation":
        return "total_only"  # Minimal tokens
    elif user_intent == "file_distribution":
        return "count_only_matches"  # File-level overview
    elif user_intent == "initial_investigation":
        return "summary_only"  # Sample-based exploration
    elif user_intent == "detailed_analysis":
        return "group_by_file"  # Context-aware review
    else:
        return "full_results"  # Complete information
```

### LLM Integration Features

#### 1. Enhanced Tool Descriptions
- **Visual Markers**: Use emoji (⚠️🎯💡) for visual hierarchy
- **Token Estimates**: Explicit token cost information in descriptions
- **Usage Recommendations**: Scenario-specific guidance
- **Mutual Exclusion Warnings**: Clear parameter conflict prevention

#### 2. Progressive Workflow Guidance
Embedded in tool description to guide LLM decision-making:

```
🎯 RECOMMENDED WORKFLOW (Most Efficient Approach):
1. START with total_only=true for initial count validation (~10 tokens)
2. IF more detail needed, use count_only_matches=true for file distribution (~50-200 tokens)
3. IF context needed, use summary_only=true for overview (~500-2000 tokens)
4. ONLY use full results when specific content review is required (~2000-50000+ tokens)
```

#### 3. Error Message Enhancement
- **Multilingual Support**: English/Japanese error messages with locale detection
- **Actionable Guidance**: Specific usage examples in error messages
- **Visual Formatting**: Enhanced readability with visual markers
- **Token Efficiency Reminders**: Include efficiency guide in error responses

### Token Efficiency Considerations

#### Design Principles
1. **Efficiency-First**: Default to most efficient format unless explicitly requested
2. **Progressive Disclosure**: Enable step-by-step information gathering
3. **Context Awareness**: Provide enough context for informed next steps
4. **Format Isolation**: Prevent accidental token waste through parameter conflicts

#### Implementation Strategies

##### 1. Smart Caching with Cross-Format Optimization
```python
# total_only result can serve future count_only_matches queries
if cache_hit_for_total_only:
    derive_count_only_matches_from_cache(total_only_result)
```

##### 2. Path Optimization for Deep Structures
```python
# Remove common prefixes to reduce token overhead
optimized_paths = remove_common_prefix(file_paths)
shortened_paths = apply_smart_truncation(optimized_paths)
```

##### 3. Result Size Monitoring
```python
# Monitor and warn about large results
estimated_tokens = calculate_token_estimate(result)
if estimated_tokens > TOKEN_WARNING_THRESHOLD:
    suggest_more_efficient_format()
```

#### Token Consumption Patterns

| Search Scope | total_only | count_only | summary_only | group_by_file | full_results |
|--------------|------------|------------|--------------|---------------|--------------|
| Single file  | 10 tokens  | 20-50      | 200-500      | 500-2000      | 1000-10000   |
| Small project| 10 tokens  | 50-100     | 500-1000     | 2000-5000     | 5000-25000   |
| Large project| 10 tokens  | 100-200    | 1000-2000    | 5000-10000    | 10000-50000+ |

### LLM Behavioral Optimization

#### 1. Natural Language Processing
- **Intent Recognition**: Tool descriptions help LLMs understand when to use each format
- **Context Preservation**: Summary formats maintain enough context for follow-up queries
- **Decision Support**: Clear efficiency guidance enables informed format selection

#### 2. Conversation Flow Optimization
```
User: "How many TODO comments are in the project?"
LLM: [Chooses total_only] → "47 TODO comments found"

User: "Which files have the most?"
LLM: [Chooses count_only_matches] → Shows file distribution

User: "Show me some examples from the top files"
LLM: [Chooses summary_only] → Shows sample TODOs with context
```

#### 3. Error Prevention
- **Parameter Validation**: Prevent incompatible format combinations
- **Usage Examples**: Show correct usage patterns in error messages
- **Guided Recovery**: Suggest alternative approaches when errors occur

### Performance Monitoring

#### Token Efficiency Metrics
- **Format Usage Distribution**: Track which formats are used most
- **Token Consumption Trends**: Monitor average tokens per query type
- **Efficiency Improvement**: Measure token savings from progressive disclosure

#### Quality Assurance
- **LLM Behavior Testing**: Verify LLMs follow efficiency guidelines
- **Format Selection Accuracy**: Test that appropriate formats are chosen
- **Error Message Effectiveness**: Validate error guidance leads to correct usage

This architecture ensures that tree-sitter-analyzer's search capabilities are optimally integrated with LLM workflows, minimizing token consumption while maximizing analytical capability.

