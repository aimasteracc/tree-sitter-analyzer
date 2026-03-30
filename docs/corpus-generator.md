# Golden Corpus Generator

## Overview

The Golden Corpus Generator is part of the Grammar Coverage MECE Framework (Phase 2). It automatically generates minimal, valid code examples for different node types in tree-sitter grammars. These code examples serve as the "golden corpus" for validating that language plugins correctly extract all grammar elements.

## Purpose

**Problem**: How do we verify that a language plugin covers all possible node types defined in the tree-sitter grammar?

**Solution**: Generate minimal code examples for each node type, then:
1. Parse these examples with tree-sitter to identify all node types present
2. Run the language plugin to see which node types it extracts
3. Calculate coverage: extracted types / total types

## Architecture

### Core Functions

#### 1. `generate_minimal_code_for_node_type(language: str, node_type: str) -> str`

Generates minimal valid code for a specific node type.

**Examples:**
```python
from tree_sitter_analyzer.grammar_coverage import generate_minimal_code_for_node_type

# Python function
code = generate_minimal_code_for_node_type("python", "function_definition")
# Returns: "def foo():\n    pass\n"

# JavaScript arrow function
code = generate_minimal_code_for_node_type("javascript", "arrow_function")
# Returns: "const f = () => {};\n"

# Java class
code = generate_minimal_code_for_node_type("java", "class_declaration")
# Returns: "class Foo {}\n"
```

#### 2. `generate_corpus_by_category(language: str) -> dict[str, str]`

Generates a complete corpus organized by category (functions, classes, statements, etc.).

**Returns:** Dictionary mapping relative paths to code content.

**Examples:**
```python
from tree_sitter_analyzer.grammar_coverage import generate_corpus_by_category

corpus = generate_corpus_by_category("python")
# Returns:
# {
#     "functions/basic_functions.py": "# Node type: function_definition\ndef foo():\n    pass\n\n...",
#     "classes/basic_classes.py": "# Node type: class_definition\nclass Foo:\n    pass\n\n...",
#     "statements/basic_statements.py": "...",
#     ...
# }
```

#### 3. `validate_generated_code(language: str, code: str) -> bool`

Validates that generated code can be parsed by tree-sitter without syntax errors.

**Examples:**
```python
from tree_sitter_analyzer.grammar_coverage import validate_generated_code

# Valid code
is_valid = validate_generated_code("python", "def foo():\n    pass\n")
# Returns: True

# Invalid code
is_valid = validate_generated_code("python", "def foo(\n")
# Returns: False
```

#### 4. `save_corpus_files(language: str, corpus: dict[str, str], base_dir: str) -> list[Path]`

Saves corpus files to disk with proper directory structure.

**Examples:**
```python
from tree_sitter_analyzer.grammar_coverage import generate_corpus_by_category, save_corpus_files

corpus = generate_corpus_by_category("python")
paths = save_corpus_files("python", corpus, "corpus/")
# Saves files to:
# corpus/python/functions/basic_functions.py
# corpus/python/classes/basic_classes.py
# corpus/python/statements/basic_statements.py
# ...
```

#### 5. `generate_and_save_corpus(language: str, base_dir: str, validate: bool) -> tuple[list[Path], int, int]`

Convenience function that generates, validates, and saves corpus in one call.

**Returns:** Tuple of (saved_paths, validation_success_count, validation_failed_count)

**Examples:**
```python
from tree_sitter_analyzer.grammar_coverage import generate_and_save_corpus

paths, success, failed = generate_and_save_corpus(
    language="python",
    base_dir="corpus/",
    validate=True
)
print(f"Saved {len(paths)} files")
print(f"Validation: {success} passed, {failed} failed")
```

## Directory Structure

The corpus generator organizes files by category:

```
corpus/
  python/
    functions/
      basic_functions.py          # function_definition, async_function, lambda, etc.
    classes/
      basic_classes.py            # class_definition
    statements/
      basic_statements.py         # if_statement, for_statement, while_statement, etc.
    imports/
      basic_imports.py            # import_statement, import_from_statement
    expressions/
      basic_expressions.py        # expression_statement, assignment, comprehensions
  javascript/
    functions/
      basic_functions.js          # function_declaration, arrow_function, method_definition
    classes/
      basic_classes.js            # class_declaration
    statements/
      basic_statements.js         # if_statement, for_statement, while_statement, etc.
    imports/
      basic_imports.js            # import_statement, export_statement
    declarations/
      basic_declarations.js       # variable_declaration, lexical_declaration
  java/
    methods/
      basic_methods.java          # method_declaration, constructor_declaration
    classes/
      basic_classes.java          # class_declaration, interface_declaration, enum_declaration
    statements/
      basic_statements.java       # if_statement, for_statement, while_statement, etc.
    declarations/
      basic_declarations.java     # field_declaration, local_variable_declaration, etc.
```

## Supported Languages (Phase 2 - Proof of Concept)

Currently supports the following languages with complete templates:

1. **Python** (25 node types)
   - Functions: function_definition, async_function, lambda, decorated_definition
   - Classes: class_definition
   - Statements: if, for, while, try, with, return, raise, assert, pass, break, continue, delete, global, nonlocal
   - Imports: import_statement, import_from_statement
   - Expressions: assignment, list_comprehension, dictionary_comprehension

2. **JavaScript** (20 node types)
   - Functions: function_declaration, arrow_function, method_definition
   - Classes: class_declaration
   - Statements: if, for, while, do, switch, try, return, throw, break, continue, debugger, labeled
   - Imports: import_statement, export_statement
   - Declarations: variable_declaration, lexical_declaration

3. **Java** (20 node types)
   - Methods: method_declaration, constructor_declaration
   - Classes: class_declaration, interface_declaration, enum_declaration, annotation_type_declaration
   - Statements: if, for, while, do, switch, try, return, throw, break, continue, synchronized
   - Declarations: field_declaration, local_variable_declaration, import_declaration, package_declaration

## Design Principles

### 1. Template-Based Generation

We use predefined code templates rather than generating code dynamically. This ensures:
- **Correctness**: All templates are manually verified and tested
- **Simplicity**: Easy to understand and maintain
- **Reliability**: No risk of generating invalid code

### 2. Multiple Small Files

We organize corpus by category with multiple small files instead of one large file per language:
- **Better organization**: Related node types grouped together
- **Easier debugging**: Can test specific categories independently
- **Scalability**: Easy to add new categories without bloating existing files

### 3. Language-Aware Comments

Each code snippet includes a comment indicating the node type it targets:
```python
# Node type: function_definition
def foo():
    pass
```

Comment syntax is language-specific:
- Python, Ruby, Bash, YAML: `#`
- JavaScript, Java, C, C++, Go, Rust, etc.: `//`

### 4. Validation-First

All generated code is validated using tree-sitter before being saved:
- Parse with tree-sitter
- Check for ERROR nodes
- Ensure code is syntactically correct

## Usage Examples

### Example 1: Generate Single Code Snippet

```python
from tree_sitter_analyzer.grammar_coverage import generate_minimal_code_for_node_type

# Generate Python function
code = generate_minimal_code_for_node_type("python", "function_definition")
print(code)
# Output:
# def foo():
#     pass
```

### Example 2: Generate Complete Corpus

```python
from tree_sitter_analyzer.grammar_coverage import generate_corpus_by_category

# Generate Python corpus
corpus = generate_corpus_by_category("python")

print(f"Generated {len(corpus)} files:")
for path in sorted(corpus.keys()):
    print(f"  - {path}")

# Output:
# Generated 5 files:
#   - classes/basic_classes.py
#   - expressions/basic_expressions.py
#   - functions/basic_functions.py
#   - imports/basic_imports.py
#   - statements/basic_statements.py
```

### Example 3: Generate and Save for All Languages

```python
from tree_sitter_analyzer.grammar_coverage import generate_and_save_corpus
from pathlib import Path

languages = ["python", "javascript", "java"]
output_dir = Path("corpus_output")

for language in languages:
    paths, success, failed = generate_and_save_corpus(
        language=language,
        base_dir=str(output_dir),
        validate=True,
    )

    print(f"{language}: {len(paths)} files, {success} valid, {failed} invalid")
```

### Example 4: Run the Demo Script

```bash
cd tree_sitter_analyzer/grammar_coverage
python corpus_example.py
```

## Testing

The corpus generator has comprehensive unit tests covering:

1. **Code Generation** (9 tests)
   - Valid code generation for all supported languages
   - Unsupported language handling
   - Unsupported node type handling

2. **Code Validation** (6 tests)
   - Valid code passes validation
   - Invalid code fails validation
   - Language-specific validation

3. **Corpus Generation** (8 tests)
   - Corpus structure and organization
   - File extension correctness
   - Comment syntax

4. **File Saving** (4 tests)
   - Single file saving
   - Multiple file saving
   - Nested directory creation
   - UTF-8 encoding support

5. **End-to-End** (5 tests)
   - Complete workflow for each language
   - Validation integration
   - Error handling

6. **Template Validation** (3 tests)
   - All Python templates are valid
   - All JavaScript templates are valid
   - All Java templates are valid

Run tests with:
```bash
uv run pytest tests/unit/grammar_coverage/test_corpus_generator.py -v
```

## Next Steps (Phase 3)

Once the corpus is generated, it will be used for coverage validation:

1. **Parse corpus files** with tree-sitter to extract all node types present
2. **Run language plugin** on the same files to see which types are extracted
3. **Calculate coverage**: extracted_types / all_types * 100%
4. **Generate reports** showing:
   - Coverage percentage per language
   - Missing node types (uncovered)
   - Correctly extracted node types (covered)

This enables us to:
- Identify gaps in language plugin extraction logic
- Prioritize improvements for low-coverage areas
- Verify MECE (Mutually Exclusive, Collectively Exhaustive) coverage
- Track coverage improvements over time

## Technical Details

### Node Type Categories

Node types are organized into semantic categories:

- **functions**: Function definitions, methods, lambdas
- **classes**: Class declarations, interfaces, enums
- **statements**: Control flow (if/for/while), returns, throws
- **imports**: Import/export statements
- **declarations**: Variable declarations, field declarations
- **expressions**: Assignments, comprehensions

### Comment Prefix Detection

The `_get_comment_prefix()` function determines the correct comment syntax:

```python
def _get_comment_prefix(language: str) -> str:
    if language in ["python", "ruby", "bash", "yaml"]:
        return "#"
    elif language in ["javascript", "java", "c", "cpp", "go", "rust", ...]:
        return "//"
    else:
        return "#"  # Default
```

### Tree-Sitter Language Loading

The corpus generator uses the same language loading logic as the introspector:

1. Import the tree-sitter language module dynamically
2. Try multiple function name patterns: `language_{lang}()`, `language()`, `language_{lang}_only()`
3. Create a `tree_sitter.Language` object
4. Parse code with `parser.parse(bytes(code, "utf-8"))`

### Error Detection

Validation checks for tree-sitter ERROR nodes recursively:

```python
def has_error_node(node: tree_sitter.Node) -> bool:
    if node.type == "ERROR" or node.is_missing:
        return True
    return any(has_error_node(child) for child in node.children)
```

## Code Quality

All code follows project standards:

- ✅ **Ruff**: All checks pass
- ✅ **MyPy**: Strict mode, all type annotations correct
- ✅ **Tests**: 35 tests, 100% pass rate
- ✅ **Documentation**: Comprehensive docstrings with examples
- ✅ **Immutability**: All functions are pure (no mutations)
- ✅ **Error Handling**: Proper logging and error messages

## Future Enhancements

Potential improvements for future phases:

1. **More Languages**: Add templates for remaining 14 languages (Go, Rust, C, C++, etc.)
2. **More Node Types**: Expand templates to cover additional node types
3. **Dynamic Generation**: Use tree-sitter queries to generate code for node types without templates
4. **LLM-Assisted Generation**: Use LLMs to generate code for rare/complex node types
5. **Corpus Optimization**: Minimize file count by combining compatible node types
6. **Version Tracking**: Track which grammar version the corpus was generated for
7. **Incremental Updates**: Only regenerate changed templates
8. **Performance**: Parallel generation for multiple languages

## References

- [Grammar Coverage Phase 1: Introspection](../tree_sitter_analyzer/grammar_coverage/introspector.py)
- [Grammar Coverage Validator](../tree_sitter_analyzer/grammar_coverage/validator.py)
- [Test Governance Framework](./test-governance-framework.md)
- [Tree-sitter Documentation](https://tree-sitter.github.io/tree-sitter/)
