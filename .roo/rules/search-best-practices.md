# Tree-Sitter Analyzer: Search Content Best Practices

## Token-Efficient Search Strategies

### 📋 Overview
The `search_content` tool offers multiple output formats optimized for different token usage scenarios. Understanding the efficiency hierarchy is crucial for effective LLM usage.

### 🎯 Recommended Workflow (Most Efficient Approach)

#### Stage 1: Count Validation (~10 tokens)
```json
{
  "query": "function",
  "roots": ["src/"],
  "total_only": true
}
```
**Use when:** You need to quickly check if matches exist or validate query effectiveness.
**Result:** Single integer (e.g., `42`)

#### Stage 2: File Distribution Analysis (~50-200 tokens)
```json
{
  "query": "function", 
  "roots": ["src/"],
  "count_only_matches": true
}
```
**Use when:** You need to understand match distribution across files.
**Result:** Object with file-level counts

#### Stage 3: Initial Investigation (~500-2000 tokens)
```json
{
  "query": "function",
  "roots": ["src/"],
  "summary_only": true
}
```
**Use when:** You need sample matches and overview for pattern validation.
**Result:** Condensed summary with top files and sample matches

#### Stage 4: Context-Aware Review (~2000-10000 tokens)
```json
{
  "query": "function",
  "roots": ["src/"], 
  "group_by_file": true
}
```
**Use when:** You need organized results for detailed analysis.
**Result:** Matches grouped by file, eliminating path duplication

#### Stage 5: Full Detail Analysis (~2000-50000+ tokens)
```json
{
  "query": "function",
  "roots": ["src/"]
}
```
**Use when:** You need complete match details for specific content review.
**Result:** Full match results with all context

### 💡 Token Efficiency Comparison

| Format | Token Range | Best Use Case | Priority |
|--------|------------|---------------|----------|
| `total_only` | ~10 tokens | Count validation, existence checks | 🥇 Highest |
| `count_only_matches` | ~50-200 tokens | File distribution analysis | 🥈 High |
| `summary_only` | ~500-2000 tokens | Initial investigation, scope confirmation | 🥉 Medium |
| `group_by_file` | ~2000-10000 tokens | Context-aware detailed review | 🔸 Low |
| `optimize_paths` | 10-30% reduction | Path compression for deep structures | 🔹 Enhancement |
| Full results | ~2000-50000+ tokens | Complete content analysis | 🔻 Last resort |

### ⚠️ Output Format Selection Guidelines

#### Mutually Exclusive Parameters
Only ONE of these can be `true` at a time:
- `total_only`
- `count_only_matches`
- `summary_only`
- `group_by_file`
- `optimize_paths`

#### Common Combinations That Cause Errors
```json
// ❌ WRONG: Multiple output formats
{
  "query": "test",
  "roots": ["src/"],
  "total_only": true,
  "summary_only": true
}

// ✅ CORRECT: Single output format
{
  "query": "test", 
  "roots": ["src/"],
  "total_only": true
}
```

### 🚨 Common Mistakes and Solutions

#### Mistake 1: Starting with Full Results
**Problem:** Requesting full results without understanding scope
```json
// ❌ Inefficient - could return 50000+ tokens
{
  "query": "function",
  "roots": ["."]
}
```

**Solution:** Start with count validation
```json
// ✅ Efficient - 10 tokens to check scope
{
  "query": "function",
  "roots": ["."],
  "total_only": true
}
```

#### Mistake 2: Combining Incompatible Parameters
**Problem:** Using multiple output format parameters
```json
// ❌ Will cause validation error
{
  "query": "test",
  "roots": ["src/"],
  "count_only_matches": true,
  "group_by_file": true
}
```

**Solution:** Choose the most appropriate single format
```json
// ✅ For file distribution analysis
{
  "query": "test",
  "roots": ["src/"],
  "count_only_matches": true
}

// ✅ For detailed grouped results  
{
  "query": "test",
  "roots": ["src/"],
  "group_by_file": true
}
```

#### Mistake 3: Ignoring Token Limits
**Problem:** Requesting detailed results in large codebases without bounds
**Solution:** Use progressive disclosure:
1. `total_only` to check if results are manageable
2. `summary_only` if count is reasonable (< 1000 matches)
3. `group_by_file` if summary looks useful
4. Full results only for specific, targeted analysis

### 📊 Advanced Optimization Strategies

#### Path Optimization for Deep Directories
```json
{
  "query": "component",
  "roots": ["frontend/src/components/"],
  "optimize_paths": true
}
```
**Use when:** Working with deeply nested directory structures to reduce path token overhead.

#### Context-Aware Searching
```json
{
  "query": "TODO",
  "roots": ["src/"],
  "context_before": 2,
  "context_after": 1,
  "summary_only": true
}
```
**Use when:** You need surrounding context but want to limit token usage.

#### Targeted File Type Searches
```json
{
  "query": "class.*Component",
  "roots": ["src/"],
  "include_globs": ["*.tsx", "*.jsx"],
  "count_only_matches": true
}
```
**Use when:** Searching specific file types to reduce noise and improve efficiency.

### 🔄 Progressive Disclosure Pattern

For unknown codebases or queries, follow this pattern:

1. **Discovery:** `total_only=true` (10 tokens)
2. **Distribution:** `count_only_matches=true` (50-200 tokens)  
3. **Sampling:** `summary_only=true` (500-2000 tokens)
4. **Detailed Review:** `group_by_file=true` (2000-10000 tokens)
5. **Full Analysis:** Default format (2000-50000+ tokens)

This approach ensures you never accidentally consume excessive tokens while still getting the information you need.

### 🎲 Example Scenarios

#### Scenario 1: Bug Investigation
```bash
# Step 1: Check if error pattern exists
total_only=true → 15 matches found

# Step 2: See which files are affected  
count_only_matches=true → errors in 3 files

# Step 3: Get sample of error patterns
summary_only=true → shows typical error patterns

# Step 4: Detailed review of specific files
group_by_file=true → organized view of all errors
```

#### Scenario 2: Code Review
```bash
# Step 1: Count TODO comments
total_only=true → 47 TODOs found

# Step 2: Distribution across files
count_only_matches=true → TODOs spread across 12 files

# Step 3: Sample of TODO types
summary_only=true → shows priority levels and types
```

#### Scenario 3: Refactoring Planning
```bash
# Step 1: Find usage of deprecated function
total_only=true → 156 usages found

# Step 2: Check file distribution
count_only_matches=true → used in 23 files

# Step 3: See usage patterns
summary_only=true → shows common usage patterns

# Step 4: Full analysis for refactoring
group_by_file=true → detailed view for systematic refactoring