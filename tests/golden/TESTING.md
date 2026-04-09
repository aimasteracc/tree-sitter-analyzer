# Golden Corpus Test Infrastructure

## Overview

The golden corpus test infrastructure validates that tree-sitter language plugins correctly parse and extract elements from comprehensive code samples.

## Test File

`test_golden_corpus.py` contains parameterized tests for all 17 supported languages.

## Usage

### Run all language tests

```bash
uv run pytest tests/golden/test_golden_corpus.py -v
```

### Run specific language test

```bash
uv run pytest tests/golden/test_golden_corpus.py::TestGoldenCorpus::test_golden_corpus[python] -v
uv run pytest tests/golden/test_golden_corpus.py::TestGoldenCorpus::test_golden_corpus[javascript] -v
```

### Run multiple specific languages

```bash
uv run pytest tests/golden/test_golden_corpus.py -k "python or javascript" -v
```

## Test Behavior

### When corpus file exists

1. Loads `corpus_{lang}_expected.json`
2. Parses `corpus_{lang}.{ext}` using tree-sitter
3. Counts all named node types in the AST
4. Verifies all **critical node types** in expected.json match actual counts
5. **Allows additional node types** to exist (expected.json contains only critical types)

### When corpus file missing

Test is **skipped** with a message:

```
SKIPPED: Corpus file not found: corpus_python.py.
Create it to enable python golden corpus testing.
```

### When expected.json missing

Test **fails** with actionable error:

```
FileNotFoundError: Expected file missing: corpus_python_expected.json.
Run `tsa generate-expected corpus_python.*` to create it.
```

### When expected.json is malformed

Test **fails** with syntax error:

```
JSONDecodeError: Malformed expected.json: Invalid control character at.
Fix JSON syntax in corpus_python_expected.json.
```

## Expected JSON Format

```json
{
  "language": "javascript",
  "node_types": {
    "function_declaration": 8,
    "arrow_function": 4,
    "class_declaration": 3,
    "method_definition": 17
  }
}
```

**Note**: Only include **critical node types** that matter for grammar coverage. Additional node types in the actual AST are allowed and expected.

## Test Output

### Success

```
PASSED tests/golden/test_golden_corpus.py::test_golden_corpus[javascript]
```

### Failure - Node count mismatch

```
JAVASCRIPT Critical Node Type Count Mismatch:

Node Type                                  Expected     Actual       Diff
------------------------------------------------------------------------
✓ arrow_function                                  4          4          0
✓ class_declaration                               3          3          0
✗ method_definition                              17         19         +2
✗ lexical_declaration                            27         35         +8
------------------------------------------------------------------------
Mismatches: 2 / 9 critical node types
Total node types in corpus: 58 (49 additional types OK)
Failed critical types: method_definition, lexical_declaration
```

## Fixing Mismatches

When tests fail due to node count mismatches:

1. **Verify the corpus file** - Ensure it contains the expected features
2. **Update expected.json** - If corpus is correct, regenerate expected.json
3. **Fix the corpus** - If expected.json is correct, update corpus to match

### Regenerate expected.json

Use the `validate_corpus.py` script to count actual node types:

```bash
cd tests/golden
uv run python validate_corpus.py
```

Then manually update `corpus_{lang}_expected.json` with the correct counts.

## Adding New Language Tests

1. Create `corpus_{language}.{ext}` with comprehensive code samples
2. Create `corpus_{language}_expected.json` with critical node types
3. Run the test to verify:

```bash
uv run pytest tests/golden/test_golden_corpus.py::TestGoldenCorpus::test_golden_corpus[{language}] -v
```

See [README.md](README.md) for detailed corpus creation guidelines.

## CI Integration

These tests run automatically in CI to ensure:

- All corpus files can be parsed
- Node type counts remain stable
- Grammar coverage is maintained across changes

## Troubleshooting

### Test skipped but corpus exists

Check the file extension matches `LANGUAGE_EXTENSIONS` in `test_golden_corpus.py`.

### Import error for tree-sitter module

Install the language-specific tree-sitter module:

```bash
uv pip install tree-sitter-{language}
```

### Security validator rejects corpus path

The test automatically uses relative paths from the project root to avoid security issues.
If you see path errors, ensure you're running from the project root directory.
