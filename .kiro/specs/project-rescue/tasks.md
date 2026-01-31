# Project Rescue - Tasks

## Task Breakdown (任务拆解)

---

## Phase 0: Emergency Cleanup (Day 1)

### T0.1: Assess Current File Structure
**Status**: pending
**Objective**: Understand exact state of planning files
**Files**:
- `task_plan.md` (root)
- `progress.md` (root)
- `findings.md` (root)
- `.kiro/specs/codebase-optimization/` (existing spec)

**Acceptance Criteria**:
- [ ] List all planning files in root
- [ ] List all specs in `.kiro/specs/`
- [ ] Identify which files belong to same feature

**Command**:
```bash
ls *.md
ls .kiro/specs/*/
```

---

### T0.2: Migrate Root Planning Files
**Status**: pending
**Objective**: Move scattered files to `.kiro/specs/rescue-cleanup/`
**Dependencies**: T0.1

**Actions**:
1. Create `.kiro/specs/rescue-cleanup/` directory
2. Move `task_plan.md` → `.kiro/specs/rescue-cleanup/original_task_plan.md`
3. Move `progress.md` → `.kiro/specs/rescue-cleanup/original_progress.md`
4. Move `findings.md` → `.kiro/specs/rescue-cleanup/original_findings.md`
5. Git commit with message: "chore: migrate root planning files to .kiro/specs/rescue-cleanup"

**Acceptance Criteria**:
- [ ] No `task_plan.md`, `progress.md`, `findings.md` in root
- [ ] All files preserved in `.kiro/specs/rescue-cleanup/`
- [ ] Git commit clean

**Command**:
```bash
mkdir -p .kiro/specs/rescue-cleanup
mv task_plan.md .kiro/specs/rescue-cleanup/original_task_plan.md
mv progress.md .kiro/specs/rescue-cleanup/original_progress.md
mv findings.md .kiro/specs/rescue-cleanup/original_findings.md
git add .kiro/specs/rescue-cleanup/
git commit -m "chore: migrate root planning files to .kiro/specs/rescue-cleanup"
```

---

### T0.3: Create Planning Structure Checker Script
**Status**: pending
**Objective**: Automate detection of misplaced planning files
**Dependencies**: None

**Files to Create**:
- `scripts/check_planning_structure.py`

**Implementation**: See Design document Section 1

**Acceptance Criteria**:
- [ ] Script detects `task_plan.md`, `progress.md`, `findings.md` in root
- [ ] Returns exit code 1 if violations found
- [ ] Prints helpful error message

**Test**:
```bash
# Create test file
touch task_plan.md
python scripts/check_planning_structure.py
# Should fail with error
rm task_plan.md
python scripts/check_planning_structure.py
# Should pass
```

---

### T0.4: Install Pre-commit Framework
**Status**: pending
**Objective**: Set up pre-commit hook infrastructure
**Dependencies**: None

**Actions**:
```bash
# Install pre-commit (if not already in dev dependencies)
uv add --dev pre-commit

# Install git hook scripts
uv run pre-commit install
```

**Acceptance Criteria**:
- [ ] `.git/hooks/pre-commit` exists
- [ ] Running `git commit` triggers hooks

---

### T0.5: Configure Planning Structure Hook
**Status**: pending
**Objective**: Block commits with misplaced planning files
**Dependencies**: T0.3, T0.4

**Files to Modify**:
- `.pre-commit-config.yaml`

**Configuration**: See Design document Section 1

**Acceptance Criteria**:
- [ ] Hook runs on every commit
- [ ] Test: Create `task_plan.md`, try commit → blocked
- [ ] Test: Remove `task_plan.md`, commit → allowed

**Test**:
```bash
touch task_plan.md
git add task_plan.md
git commit -m "test"  # Should fail
rm task_plan.md
```

---

### T0.6: Document Emergency Cleanup
**Status**: pending
**Objective**: Record what was done and why
**Dependencies**: T0.1, T0.2, T0.3, T0.4, T0.5

**Files to Create**:
- `.kiro/specs/rescue-cleanup/README.md`

**Content**:
- What files were moved
- Why they were moved
- New structure explanation
- How to create proper planning files

**Acceptance Criteria**:
- [ ] README exists
- [ ] Clear instructions for future planning

---

## Phase 1: Python Excellence Foundation (Week 1)

### T1.1: Baseline Python Plugin Quality
**Status**: pending
**Objective**: Measure current state of `python_plugin.py`
**Dependencies**: None

**Command**:
```bash
python scripts/check_code_quality.py tree_sitter_analyzer/languages/python_plugin.py
```

**Acceptance Criteria**:
- [ ] Record current score (expected: 60-80/100)
- [ ] Identify missing components
- [ ] Estimate work required

---

### T1.2: Optimize Python Plugin Module Header
**Status**: pending
**Objective**: Add complete 11-section module header
**Dependencies**: T1.1

**Sections Required**:
1. Brief description
2. Detailed description
3. Features
4. Architecture
5. Usage
6. Performance Characteristics
7. Thread Safety
8. Dependencies
9. Error Handling
10. Note
11. Example

**Acceptance Criteria**:
- [ ] All 11 sections present
- [ ] Quality check shows +10-15 points
- [ ] Docstring follows Google style

**Files Modified**:
- `tree_sitter_analyzer/languages/python_plugin.py`

---

### T1.3: Add Exception Classes to Python Plugin
**Status**: pending
**Objective**: Define 3 custom exception classes
**Dependencies**: T1.2

**Implementation**:
```python
class PythonPluginException(Exception):
    """Base exception for Python plugin operations.
    
    This is the base class for all Python plugin-specific exceptions.
    """
    pass


class PythonParseError(PythonPluginException):
    """Raised when Python source code cannot be parsed.
    
    This error occurs when tree-sitter fails to parse Python syntax,
    typically due to syntax errors or unsupported Python versions.
    """
    pass


class PythonFeatureNotSupported(PythonPluginException):
    """Raised when a Python feature is not yet supported.
    
    This error indicates that the plugin encountered a valid Python
    feature that is not yet implemented in the extraction logic.
    """
    pass
```

**Acceptance Criteria**:
- [ ] 3 exception classes defined
- [ ] Proper inheritance hierarchy
- [ ] Docstrings for each exception
- [ ] Added to `__all__`

---

### T1.4: Document All Public Methods
**Status**: pending
**Objective**: Add Args/Returns/Note to all public methods
**Dependencies**: T1.3

**Target Methods**:
- `analyze_file()`
- `get_language_name()`
- `get_supported_extensions()`
- Any other public methods

**Format**:
```python
def analyze_file(self, file_path: str, request: AnalysisRequest) -> AnalysisResult:
    """Analyze Python source file.
    
    Args:
        file_path: Path to Python source file
        request: Analysis configuration and options
        
    Returns:
        AnalysisResult: Complete analysis including classes, functions, imports
        
    Note:
        This method uses tree-sitter-python for AST parsing. It supports
        Python 3.8+ syntax including type hints and async/await.
    """
```

**Acceptance Criteria**:
- [ ] All public methods documented
- [ ] Args section present (even if "None")
- [ ] Returns section with type and description
- [ ] Note section with important behavior

---

### T1.5: Add Performance Monitoring to Python Plugin
**Status**: pending
**Objective**: Instrument with 5-8 performance tracking points
**Dependencies**: T1.4

**Implementation**:
```python
from time import perf_counter

class PythonPlugin:
    def __init__(self):
        self._stats = {
            'total_analyses': 0,
            'total_parse_time': 0.0,
            'total_extract_time': 0.0,
            'cache_hits': 0,
            'parse_errors': 0
        }
    
    def analyze_file(self, file_path: str, request: AnalysisRequest):
        self._stats['total_analyses'] += 1
        
        parse_start = perf_counter()
        tree = self._parse(file_path)
        self._stats['total_parse_time'] += perf_counter() - parse_start
        
        extract_start = perf_counter()
        result = self._extract_elements(tree, request)
        self._stats['total_extract_time'] += perf_counter() - extract_start
        
        return result
```

**Acceptance Criteria**:
- [ ] 5-8 monitoring points added
- [ ] `_stats` dictionary initialized
- [ ] All critical operations timed

---

### T1.6: Add Statistics Method to Python Plugin
**Status**: pending
**Objective**: Implement `get_statistics()` method
**Dependencies**: T1.5

**Implementation**:
```python
def get_statistics(self) -> dict[str, Any]:
    """Get performance and usage statistics.
    
    Args:
        None (instance method with no parameters)
        
    Returns:
        dict[str, Any]: Statistics including:
            - total_analyses: Number of files analyzed
            - avg_parse_time: Average parsing time in seconds
            - avg_extract_time: Average extraction time in seconds
            - cache_hit_rate: Percentage of cache hits
            - error_rate: Percentage of parse errors
            
    Note:
        Statistics are cumulative since plugin initialization.
        Use for performance monitoring and optimization.
    """
    total = max(1, self._stats['total_analyses'])
    return {
        **self._stats,
        'avg_parse_time': self._stats['total_parse_time'] / total,
        'avg_extract_time': self._stats['total_extract_time'] / total,
        'cache_hit_rate': self._stats['cache_hits'] / total,
        'error_rate': self._stats['parse_errors'] / total
    }
```

**Acceptance Criteria**:
- [ ] Method implemented
- [ ] Returns dict with derived metrics
- [ ] Documented with Args/Returns/Note

---

### T1.7: Update Python Plugin __all__
**Status**: pending
**Objective**: Export public API and exceptions
**Dependencies**: T1.6

**Implementation**:
```python
__all__ = [
    # Main plugin class
    'PythonPlugin',
    # Exceptions
    'PythonPluginException',
    'PythonParseError',
    'PythonFeatureNotSupported'
]
```

**Acceptance Criteria**:
- [ ] `__all__` defined at module level
- [ ] Includes main class
- [ ] Includes all exceptions
- [ ] No internal/private classes exported

---

### T1.8: Validate Python Plugin Quality Score
**Status**: pending
**Objective**: Achieve 97-100/100 score
**Dependencies**: T1.2, T1.3, T1.4, T1.5, T1.6, T1.7

**Command**:
```bash
python scripts/check_code_quality.py tree_sitter_analyzer/languages/python_plugin.py
```

**Acceptance Criteria**:
- [ ] Score >= 97/100
- [ ] All sections present
- [ ] No missing documentation

**If score < 97**:
- Review quality check output
- Fix identified issues
- Re-run check

---

### T1.9: Repeat for Python Formatter
**Status**: pending
**Objective**: Apply same optimization to `python_formatter.py`
**Dependencies**: T1.8 complete

**Subtasks**:
- Baseline quality
- Module header (11 sections)
- 3 exception classes
- Document public methods
- Performance monitoring
- Statistics method
- Update `__all__`
- Validate >= 97/100

**Acceptance Criteria**:
- [ ] `python_formatter.py` scores >= 97/100
- [ ] Same structure as `python_plugin.py`
- [ ] Consistent style

---

### T1.10: Write Python Plugin Tests (TDD)
**Status**: pending
**Objective**: Achieve 80%+ coverage using TDD
**Dependencies**: T1.9

**Approach**:
```bash
# Start TDD workflow
/tdd
```

**Test Categories**:
1. **Unit Tests**:
   - Parse valid Python files
   - Handle syntax errors
   - Extract classes correctly
   - Extract functions with decorators
   - Extract type annotations
   - Handle async/await

2. **Integration Tests**:
   - Full file analysis
   - Multiple classes in one file
   - Complex inheritance hierarchies

3. **Edge Cases**:
   - Empty files
   - Comments only
   - Invalid Python
   - Large files (>1000 lines)

**Acceptance Criteria**:
- [ ] 80%+ line coverage
- [ ] 50+ tests written
- [ ] All tests pass
- [ ] Tests follow pytest conventions

**Files Created**:
- `tests/unit/test_python_plugin.py`
- `tests/integration/test_python_plugin_integration.py`

---

### T1.11: Document Python Optimization Pattern
**Status**: pending
**Objective**: Create reusable template for other languages
**Dependencies**: T1.10

**Files to Create**:
- `.kiro/optimization_work/python_optimization_complete.md`

**Content**:
- Step-by-step process used
- Before/after quality scores
- Common issues encountered
- Solutions applied
- Time invested
- Lessons learned

**Acceptance Criteria**:
- [ ] Document complete
- [ ] Clear enough for others to follow
- [ ] Includes code examples

---

## Phase 2: Test Infrastructure Rebuild (Weeks 2-3)

### T2.1: Analyze Core Modules Needing Tests
**Status**: pending
**Objective**: Prioritize which modules to test first
**Dependencies**: Phase 1 complete

**Target Modules** (priority order):
1. `core/analysis_engine.py` (highest priority)
2. `core/parser.py`
3. `core/query.py`
4. `languages/java_plugin.py`
5. `formatters/java_formatter.py`

**Acceptance Criteria**:
- [ ] List of modules prioritized
- [ ] Current coverage measured
- [ ] Test plan for each module

**Command**:
```bash
uv run pytest --cov=tree_sitter_analyzer.core --cov-report=term-missing
```

---

### T2.2-T2.6: Write Tests for Core Modules
**Status**: pending
**Objective**: Rebuild test suite using TDD
**Dependencies**: T2.1

**For Each Module**:
1. Baseline coverage
2. Use `/tdd` to guide process
3. Write tests until 80%+ coverage
4. Commit tests

**Subtasks**:
- **T2.2**: `analysis_engine.py` tests
- **T2.3**: `parser.py` tests
- **T2.4**: `query.py` tests
- **T2.5**: `java_plugin.py` tests
- **T2.6**: `java_formatter.py` tests

**Acceptance Criteria**:
- [ ] Each module >= 80% coverage
- [ ] All tests pass
- [ ] No skipped tests
- [ ] Tests run in < 2 minutes total

---

### T2.7: Set Up Coverage Reporting
**Status**: pending
**Objective**: Track coverage trends over time
**Dependencies**: T2.2-T2.6

**Implementation**:
```yaml
# .github/workflows/test-coverage.yml
name: Test Coverage
on: [push, pull_request]
jobs:
  coverage:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run tests with coverage
        run: |
          uv sync --extra all
          uv run pytest --cov=tree_sitter_analyzer --cov-report=xml
      - name: Upload to Codecov
        uses: codecov/codecov-action@v2
```

**Acceptance Criteria**:
- [ ] CI runs coverage on every commit
- [ ] Coverage badge in README
- [ ] Trend visible over time

---

## Phase 3: Language Standardization (Week 4)

### T3.1: Create Comment Translation Script
**Status**: pending
**Objective**: Automate detection and translation template generation
**Dependencies**: None

**Files to Create**:
- `scripts/translate_comments.py` (see Design doc)
- `scripts/apply_translations.py` (applies translations)

**Acceptance Criteria**:
- [ ] Script detects non-English comments
- [ ] Generates translation template
- [ ] Template is human-editable

---

### T3.2: Scan All Python Files for Non-English Comments
**Status**: pending
**Objective**: Identify scope of translation work
**Dependencies**: T3.1

**Command**:
```bash
for file in $(find tree_sitter_analyzer -name "*.py"); do
    python scripts/translate_comments.py "$file"
done
```

**Acceptance Criteria**:
- [ ] All files scanned
- [ ] Translation templates generated
- [ ] Total comment count known

---

### T3.3-T3.5: Translate and Apply (Batch Processing)
**Status**: pending
**Objective**: Convert comments to English in batches
**Dependencies**: T3.2

**Batches**:
- **T3.3**: Core modules (`core/`, `plugins/`)
- **T3.4**: Language plugins (`languages/`)
- **T3.5**: Formatters and CLI (`formatters/`, `cli/`)

**Process per Batch**:
1. Review translation templates
2. Manually translate "TRANSLATE_ME" entries
3. Run apply script
4. Verify quality score maintained
5. Commit changes

**Acceptance Criteria**:
- [ ] All comments translated
- [ ] Quality scores maintained
- [ ] Git history clean

---

### T3.6: Add English-Only Pre-commit Hook
**Status**: pending
**Objective**: Prevent future non-English comments
**Dependencies**: T3.3-T3.5 complete

**Files to Create**:
- `scripts/check_comment_language.py` (see Design doc)

**Configuration**: Update `.pre-commit-config.yaml`

**Acceptance Criteria**:
- [ ] Hook detects non-English comments
- [ ] Warns on commit
- [ ] Allows bypass with `--no-verify`

---

## Phase 4: Quality Automation (Week 5)

### T4.1: Create Pre-commit Quality Check Script
**Status**: pending
**Objective**: Integrate quality check into git workflow
**Dependencies**: None

**Files to Create**:
- `scripts/pre_commit_quality_check.py` (see Design doc)

**Acceptance Criteria**:
- [ ] Checks only staged Python files
- [ ] Runs in < 5 seconds per file
- [ ] Clear error messages

---

### T4.2: Configure Quality Check Hook
**Status**: pending
**Objective**: Enforce 90/100 minimum on commits
**Dependencies**: T4.1

**Configuration**: Update `.pre-commit-config.yaml`

**Acceptance Criteria**:
- [ ] Hook blocks commits < 90/100
- [ ] Test: Commit low-quality code → blocked
- [ ] Test: Commit high-quality code → allowed

---

### T4.3: Create Auto-fix Script (Optional)
**Status**: pending
**Objective**: Automatically fix common quality issues
**Dependencies**: T4.2

**Target Fixes**:
- Add missing "Args: None" for no-parameter methods
- Format exception classes (remove inline `pass`)
- Add empty `__all__ = []` if missing

**Acceptance Criteria**:
- [ ] Script runs on single file
- [ ] Fixes common issues
- [ ] Preserves functionality

---

### T4.4: Update Contributing Guidelines
**Status**: pending
**Objective**: Document new workflow for contributors
**Dependencies**: T4.2

**Files to Modify**:
- `docs/CONTRIBUTING.md`

**Content to Add**:
- Pre-commit hook explanation
- How to check quality manually
- How to fix common issues
- How to bypass hooks (when appropriate)

**Acceptance Criteria**:
- [ ] Clear instructions
- [ ] Examples provided
- [ ] FAQ section

---

## Phase 5: Pattern Propagation (Weeks 6-7)

### T5.1: Prioritize Languages for Optimization
**Status**: pending
**Objective**: Decide order of language plugin optimization
**Dependencies**: Phase 4 complete

**Criteria**:
- Usage frequency
- Complexity
- Similarity to Python (reuse patterns)

**Proposed Order**:
1. Java (most similar, high usage)
2. JavaScript (high usage)
3. TypeScript (similar to JavaScript)
4. C# (similar to Java)
5. PHP, Ruby, SQL, HTML, CSS, Markdown, YAML

**Acceptance Criteria**:
- [ ] Priority list created
- [ ] Rationale documented
- [ ] Timeline estimated (1-2 days per language)

---

### T5.2-T5.12: Optimize Each Language Plugin
**Status**: pending
**Objective**: Apply Python optimization pattern to all languages
**Dependencies**: T5.1

**For Each Language**:
1. Baseline quality
2. Module header (11 sections)
3. 3 exception classes
4. Document public methods
5. Performance monitoring
6. Statistics method
7. Update `__all__`
8. Validate >= 90/100 (target 97-100)
9. Write tests (80%+ coverage)

**Subtasks**:
- **T5.2**: Java plugin + formatter
- **T5.3**: JavaScript plugin + formatter
- **T5.4**: TypeScript plugin + formatter
- **T5.5**: C# plugin + formatter
- **T5.6**: PHP plugin + formatter
- **T5.7**: Ruby plugin + formatter
- **T5.8**: SQL plugin + formatter
- **T5.9**: HTML plugin + formatter
- **T5.10**: CSS plugin + formatter
- **T5.11**: Markdown plugin + formatter
- **T5.12**: YAML plugin + formatter

**Acceptance Criteria per Language**:
- [ ] Plugin >= 90/100 (ideally 97-100)
- [ ] Formatter >= 90/100 (ideally 97-100)
- [ ] Tests >= 80% coverage
- [ ] Consistent with Python pattern

---

## Continuous Tasks (Ongoing)

### TC.1: Monitor Quality Metrics
**Frequency**: Weekly
**Objective**: Track progress towards goals

**Metrics to Track**:
- Average quality score across all files
- Test coverage percentage
- Non-English comment count
- Planning file compliance

**Tool**:
```bash
python scripts/quality_dashboard.py
```

---

### TC.2: Update Documentation
**Frequency**: After each phase
**Objective**: Keep docs in sync with code

**Files to Update**:
- `CLAUDE.md`
- `.github/copilot-instructions.md`
- `.kiro/steering/*.md`

---

### TC.3: Refine Optimization Process
**Frequency**: After each language
**Objective**: Improve efficiency

**Actions**:
- Note time taken
- Identify repeated issues
- Update auto-fix script
- Update documentation template

---

## Dependencies Graph

```
Phase 0 (Emergency)
  ├─> T0.1 (Assess) ─> T0.2 (Migrate)
  ├─> T0.3 (Script) ─┬─> T0.5 (Hook)
  └─> T0.4 (Install) ┘
       └─> T0.6 (Document)

Phase 1 (Python Excellence)
  T1.1 ─> T1.2 ─> T1.3 ─> T1.4 ─> T1.5 ─> T1.6 ─> T1.7 ─> T1.8
  T1.8 ─> T1.9 (Formatter)
  T1.9 ─> T1.10 (Tests)
  T1.10 ─> T1.11 (Document)

Phase 2 (Tests)
  T2.1 ─> T2.2, T2.3, T2.4, T2.5, T2.6 (parallel)
  T2.2-T2.6 ─> T2.7 (Coverage)

Phase 3 (Language)
  T3.1 ─> T3.2 ─> T3.3, T3.4, T3.5 (parallel)
  T3.3-T3.5 ─> T3.6 (Hook)

Phase 4 (Automation)
  T4.1 ─> T4.2 ─> T4.3 (optional)
  T4.2 ─> T4.4 (Docs)

Phase 5 (Propagation)
  T5.1 ─> T5.2, T5.3, ..., T5.12 (sequential)
```

---

## Time Estimates (预估时间)

| Phase | Tasks | Estimated Time |
|-------|-------|----------------|
| Phase 0 | T0.1-T0.6 | 1 day |
| Phase 1 | T1.1-T1.11 | 5-7 days |
| Phase 2 | T2.1-T2.7 | 10-14 days |
| Phase 3 | T3.1-T3.6 | 5-7 days |
| Phase 4 | T4.1-T4.4 | 2-3 days |
| Phase 5 | T5.1-T5.12 | 12-14 days |
| **Total** | | **35-45 days** |

**Note**: Assumes full-time focus. Can be accelerated with parallel work or extended if part-time.

---

## Risk Mitigation (风险缓解)

**If Python optimization takes longer than expected**:
- Reduce scope: Focus on plugin only, defer formatter
- Lower target: Accept 90/100 instead of 97-100

**If test writing is too slow**:
- Use property-based testing (Hypothesis) for faster coverage
- Focus on critical paths, accept lower coverage (70%) initially

**If translation is overwhelming**:
- Automate with LLM translation + manual review
- Accept phased migration (core modules first)

**If developer resistance to hooks**:
- Make hooks warning-only initially
- Collect data on issues prevented
- Build consensus before enforcement
