# Golden Master Format Restoration - Requirements

## 1. Background

During the formatter architecture unification work, the golden master files were regenerated
with a new format that differs significantly from the original format. This is a regression
that needs to be fixed.

## 2. Problem Analysis

### 2.1 Observed Issues in Java Full Format

| Issue | Original (Correct) | Current (Incorrect) |
|-------|-------------------|---------------------|
| Header | `# com.example.Sample` | `# com.example.Sample.java` (adds .java extension) |
| Classes section | `## Classes Overview` | `## Classes` (missing "Overview") |
| Per-class sections | Each class has its own `## ClassName (lines)` section | All methods/fields merged into one section |
| Method grouping | Grouped by visibility (Public/Protected/Package/Private) | Only Public and Private, missing Protected/Package |
| Constructors | Separate `### Constructors` section per class | All constructors merged together |
| Inner classes | Each inner class has its own section | Inner class methods mixed with outer class |
| Enum handling | Enum has its own `## EnumName (lines)` section | Enum section uses different format |
| Column info | No `Cols` column in method tables | Added unnecessary `Cols` column |

### 2.2 Impact Assessment

The changes affect:
- **47 golden master files** across all formats (full, compact, csv, toon)
- **7 languages** with significant changes: Java, C#, JavaScript, PHP, Python, Ruby, TypeScript
- **Token efficiency**: New format may use more tokens due to added columns and changed structure

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1 | Restore original header format without file extension | High |
| FR-2 | Restore `## Classes Overview` section header | High |
| FR-3 | Restore per-class method/field organization | High |
| FR-4 | Restore all visibility groupings (Public/Protected/Package/Private) | High |
| FR-5 | Restore separate constructor sections per class | High |
| FR-6 | Restore inner/nested class sections | High |
| FR-7 | Remove unnecessary `Cols` column from method tables | Medium |
| FR-8 | Ensure enum sections use correct format | Medium |

### 3.2 Non-Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-1 | Output should be token-efficient (minimize output size) | High |
| NFR-2 | Output should be accurate to source code structure | High |
| NFR-3 | All existing tests must pass | High |
| NFR-4 | No breaking changes to public API | High |

## 4. Affected Files

### 4.1 Source Files to Modify

1. `tree_sitter_analyzer/formatters/java_formatter.py` - Primary focus
2. `tree_sitter_analyzer/formatters/csharp_formatter.py`
3. `tree_sitter_analyzer/formatters/javascript_formatter.py`
4. `tree_sitter_analyzer/formatters/typescript_formatter.py`
5. `tree_sitter_analyzer/formatters/php_formatter.py`
6. `tree_sitter_analyzer/formatters/python_formatter.py`
7. `tree_sitter_analyzer/formatters/ruby_formatter.py`

### 4.2 Golden Master Files to Restore

- 7 compact format files
- 15 csv format files
- 7 full format files
- 18 toon format files

## 5. Success Criteria

1. All golden master files match their original format (before this PR)
2. All tests pass
3. Output is more token-efficient than current format
4. Source code structure is accurately represented

## 6. Approach

1. Revert golden master files to original state using `git checkout HEAD~`
2. Update formatters to produce output matching original golden masters
3. Run tests to verify compatibility
4. Document any intentional format improvements

