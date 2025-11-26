# Design Document

## Overview

This design implements a comprehensive cross-platform compatibility framework for SQL parsing in tree-sitter-analyzer. The system systematically records, analyzes, and adapts to platform-specific differences in tree-sitter-sql behavior across Windows, Linux, macOS, and Python versions 3.10-3.13.

The solution consists of four main components:
1. **Behavior Recording System**: Captures platform-specific parsing characteristics
2. **Compatibility Layer**: Automatically adapts to platform differences
3. **CI/CD Integration**: Continuous testing across all platform matrices
4. **Diagnostic Tools**: Helps developers understand and debug platform-specific issues

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SQL Plugin Layer                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         Platform Detection & Initialization          │   │
│  └──────────────────────────────────────────────────────┘   │
│                           │                                  │
│                           ▼                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │      Behavior Profile Loader                         │   │
│  │  - Detects OS + Python version                       │   │
│  │  - Loads appropriate profile                         │   │
│  └──────────────────────────────────────────────────────┘   │
│                           │                                  │
│                           ▼                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │      Tree-sitter SQL Parser                          │   │
│  │  - Parses SQL code                                   │   │
│  │  - Generates AST                                     │   │
│  └──────────────────────────────────────────────────────┘   │
│                           │                                  │
│                           ▼                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │      Compatibility Adapter                           │   │
│  │  - Applies platform-specific transformations         │   │
│  │  - Normalizes output                                 │   │
│  └──────────────────────────────────────────────────────┘   │
│                           │                                  │
│                           ▼                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │      Validation & Post-processing                    │   │
│  │  - Existing _validate_and_fix_elements()             │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              Behavior Recording System                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │      Test Fixture Library                            │   │
│  │  - Standard SQL samples                              │   │
│  │  - Edge case coverage                                │   │
│  └──────────────────────────────────────────────────────┘   │
│                           │                                  │
│                           ▼                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │      Platform Behavior Recorder                      │   │
│  │  - Executes fixtures on current platform             │   │
│  │  - Captures AST structures                           │   │
│  │  - Records element types & attributes                │   │
│  └──────────────────────────────────────────────────────┘   │
│                           │                                  │
│                           ▼                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │      Behavior Profile Generator                      │   │
│  │  - Generates JSON profiles                           │   │
│  │  - Stores in tests/platform_profiles/                │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                  CI/CD Integration                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │      GitHub Actions Matrix                           │   │
│  │  - Windows (3.10, 3.11, 3.12, 3.13)                  │   │
│  │  - Ubuntu (3.10, 3.11, 3.12, 3.13)                   │   │
│  │  - macOS (3.10, 3.11, 3.12, 3.13)                    │   │
│  └──────────────────────────────────────────────────────┘   │
│                           │                                  │
│                           ▼                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │      Profile Comparison & Validation                 │   │
│  │  - Compare against baseline                          │   │
│  │  - Detect regressions                                │   │
│  │  - Generate compatibility matrix                     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Component Interaction Flow

```
User Request → SQL Plugin → Platform Detection → Load Profile
                                                      │
                                                      ▼
                                              Parse SQL Code
                                                      │
                                                      ▼
                                              Apply Adaptations
                                                      │
                                                      ▼
                                              Validate & Fix
                                                      │
                                                      ▼
                                              Return Normalized Results
```

## Components and Interfaces

### 1. Platform Detection Module

**Location**: `tree_sitter_analyzer/platform_compat/detector.py`

```python
class PlatformInfo:
    """Platform identification information"""
    os_name: str  # "windows", "linux", "darwin"
    os_version: str
    python_version: str  # "3.10", "3.11", "3.12", "3.13"
    platform_key: str  # "windows-3.12", "linux-3.10", etc.

class PlatformDetector:
    """Detects current platform and Python version"""
    
    @staticmethod
    def detect() -> PlatformInfo:
        """Detect current platform information"""
        
    @staticmethod
    def get_profile_path(platform_info: PlatformInfo) -> Path:
        """Get path to behavior profile for platform"""
```

### 2. Behavior Profile System

**Location**: `tree_sitter_analyzer/platform_compat/profiles.py`

```python
class ParsingBehavior:
    """Describes how a specific SQL construct parses on a platform"""
    construct_type: str  # "function", "trigger", "view", etc.
    node_type: str  # AST node type
    attributes: dict[str, Any]  # Node attributes
    known_issues: list[str]  # Known parsing problems
    
PROFILE_SCHEMA_VERSION = "1.0.0"

class BehaviorProfile:
    """Complete behavior profile for a platform"""
    schema_version: str  # Profile schema version for migration support
    platform_key: str
    tree_sitter_sql_version: str
    behaviors: dict[str, ParsingBehavior]
    adaptation_rules: list[AdaptationRule]
    
    @classmethod
    def load(cls, platform_key: str) -> Optional['BehaviorProfile']:
        """Load profile from disk with schema migration support"""
        data = load_json(profile_path)
        
        # Schema migration
        if data.get("schema_version") != PROFILE_SCHEMA_VERSION:
            data = migrate_profile_schema(data)
        
        # Validate against JSON schema
        validate_profile(data)
        
        return cls(**data)
        
    def get_adaptation_rules(self, construct_type: str) -> list[AdaptationRule]:
        """Get adaptation rules for a construct type"""

from typing import Protocol, TypeVar, Optional

T = TypeVar('T', bound='SQLElement')

class AdaptationRule(Protocol):
    """Rule for adapting platform-specific behavior"""
    rule_id: str
    construct_type: str
    condition: Callable[[T], bool]
    transformation: Callable[[T], Optional[T]]  # None = remove element
    description: str
```

### 3. Compatibility Adapter

**Location**: `tree_sitter_analyzer/platform_compat/adapter.py`

```python
class CompatibilityAdapter:
    """Applies platform-specific adaptations to SQL parsing results"""
    
    def __init__(self, profile: BehaviorProfile):
        self.profile = profile
        self.rules = self._load_adaptation_rules()
        
    def adapt_elements(self, elements: list[SQLElement]) -> list[SQLElement]:
        """Apply adaptations to parsed SQL elements"""
        
    def _apply_rule(self, element: SQLElement, rule: AdaptationRule) -> SQLElement:
        """Apply a single adaptation rule"""
        
    def normalize_function_names(self, elements: list[SQLElement]) -> list[SQLElement]:
        """Normalize function name extraction across platforms"""
        
    def fix_phantom_elements(self, elements: list[SQLElement]) -> list[SQLElement]:
        """Remove phantom elements caused by ERROR nodes"""
        
    def recover_missing_elements(self, elements: list[SQLElement], source: str) -> list[SQLElement]:
        """Recover elements missed due to platform-specific parsing issues"""
```

### 4. Behavior Recording System

**Location**: `tests/platform_compat/recorder.py`

```python
class SQLTestFixture:
    """A SQL code sample for testing"""
    name: str
    sql_code: str
    expected_elements: dict[str, int]  # element_type -> count
    description: str
    
class BehaviorRecorder:
    """Records SQL parsing behavior on current platform"""
    
    def __init__(self, fixtures: list[SQLTestFixture]):
        self.fixtures = fixtures
        self.platform_info = PlatformDetector.detect()
        
    def record_all(self) -> BehaviorProfile:
        """Record behavior for all fixtures"""
        
    def record_fixture(self, fixture: SQLTestFixture) -> dict[str, Any]:
        """Record behavior for a single fixture"""
        
    def analyze_ast(self, tree: Tree, source: str) -> dict[str, Any]:
        """Analyze AST structure and extract characteristics"""
        
    def save_profile(self, profile: BehaviorProfile, output_dir: Path):
        """Save behavior profile to disk"""
```

### 5. Test Fixture Library

**Location**: `tests/platform_compat/fixtures.py`

```python
# Standard SQL constructs
FIXTURE_SIMPLE_TABLE = SQLTestFixture(...)
FIXTURE_COMPLEX_TABLE = SQLTestFixture(...)
FIXTURE_VIEW_WITH_JOIN = SQLTestFixture(...)
FIXTURE_STORED_PROCEDURE = SQLTestFixture(...)
FIXTURE_FUNCTION_WITH_PARAMS = SQLTestFixture(...)
FIXTURE_TRIGGER_BEFORE_INSERT = SQLTestFixture(...)
FIXTURE_INDEX_UNIQUE = SQLTestFixture(...)

# Edge cases known to cause platform differences
FIXTURE_FUNCTION_WITH_SELECT = SQLTestFixture(...)  # Ubuntu 3.12 issue
FIXTURE_TRIGGER_WITH_DESCRIPTION = SQLTestFixture(...)  # macOS issue
FIXTURE_FUNCTION_WITH_AUTO_INCREMENT = SQLTestFixture(...)  # Windows issue
FIXTURE_VIEW_IN_ERROR_NODE = SQLTestFixture(...)  # Cross-platform issue

ALL_FIXTURES = [...]
```

### 6. CI/CD Integration

**Location**: `.github/workflows/sql-platform-compat.yml`

```yaml
name: SQL Platform Compatibility

on: [push, pull_request]

jobs:
  record-behavior:
    strategy:
      matrix:
        os: [windows-latest, ubuntu-latest, macos-latest]
        python-version: ['3.10', '3.11', '3.12', '3.13']
    
    steps:
      - name: Record platform behavior
      - name: Upload behavior profile
      - name: Compare with baseline
      - name: Report differences
```

## Data Models

### Behavior Profile JSON Schema

```json
{
  "schema_version": "1.0.0",
  "platform_key": "windows-3.12",
  "os_name": "windows",
  "os_version": "10.0.19045",
  "python_version": "3.12.0",
  "tree_sitter_sql_version": "0.3.11",
  "recorded_at": "2025-11-21T10:30:00Z",
  
  "behaviors": {
    "function": {
      "node_type": "create_function",
      "name_extraction": {
        "method": "ast_traversal",
        "fallback": "regex",
        "known_issues": ["may_extract_keywords_from_body"]
      },
      "boundary_detection": {
        "start_reliable": true,
        "end_reliable": true
      }
    },
    "trigger": {
      "node_type": "create_trigger",
      "name_extraction": {
        "method": "ast_traversal",
        "fallback": "regex",
        "known_issues": ["may_use_wrong_identifier"]
      },
      "phantom_elements": {
        "occurs": false,
        "description": ""
      }
    },
    "view": {
      "node_type": "create_view",
      "name_extraction": {
        "method": "regex_primary",
        "fallback": "ast_traversal",
        "known_issues": ["may_appear_in_error_nodes"]
      },
      "recovery_needed": true
    }
  },
  
  "adaptation_rules": [
    {
      "rule_id": "fix_function_name_keywords",
      "construct_type": "function",
      "description": "Filter out SQL keywords extracted as function names",
      "applies_to": ["windows-3.12", "ubuntu-3.12"]
    },
    {
      "rule_id": "fix_trigger_name_description",
      "construct_type": "trigger",
      "description": "Correct trigger names that default to 'description'",
      "applies_to": ["darwin-3.12", "darwin-3.13"]
    },
    {
      "rule_id": "recover_views_from_errors",
      "construct_type": "view",
      "description": "Recover views that appear in ERROR nodes",
      "applies_to": ["all"]
    }
  ],
  
  "test_results": {
    "fixture_simple_table": {
      "passed": true,
      "elements_found": {"table": 1},
      "issues": []
    },
    "fixture_function_with_select": {
      "passed": false,
      "elements_found": {"function": 2},
      "expected": {"function": 1},
      "issues": ["extracted_select_keyword_as_function"]
    }
  }
}
```

### Adaptation Rule Format

```python
# Example: Fix function names that are SQL keywords
AdaptationRule(
    rule_id="fix_function_name_keywords",
    construct_type="function",
    condition=lambda elem: elem.name.upper() in SQL_KEYWORDS,
    transformation=lambda elem: recover_correct_name_from_raw_text(elem),
    description="Recover correct function name when keyword is extracted"
)

# Example: Remove phantom triggers
AdaptationRule(
    rule_id="remove_phantom_triggers",
    construct_type="trigger",
    condition=lambda elem: not re.search(r"CREATE\s+TRIGGER", elem.raw_text, re.I),
    transformation=lambda elem: None,  # Remove element
    description="Remove phantom triggers with mismatched content"
)
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*


### Property Reflection

After analyzing all acceptance criteria, I've identified the following testable properties and potential redundancies:

**Core Parsing Properties:**
- Property 1.1 (cross-platform equivalence) and Property 4.3 (transformation normalization) are closely related but distinct - 1.1 tests end-to-end equivalence while 4.3 tests the transformation mechanism specifically
- Property 1.2 (normalization application) is subsumed by Property 4.3 (transformation application) - they test the same thing
- **Decision**: Remove Property 1.2 as redundant, keep Property 4.3 as the comprehensive test

**Profile Management Properties:**
- Property 2.3 (profile generation) and Property 2.5 (profile storage) can be combined - both test the profile saving mechanism
- **Decision**: Combine into single property about profile persistence

**Diagnostic Properties:**
- Properties 5.2, 5.3, and 5.4 all test diagnostic logging completeness
- **Decision**: Combine into single comprehensive diagnostic logging property

**Fixture Properties:**
- Properties 6.1, 6.2, and 6.3 all test fixture library completeness from different angles
- **Decision**: Combine into single property about fixture coverage

**Final Property Set**: 15 unique properties after removing redundancies

### Correctness Properties

Property 1: Cross-platform parsing equivalence
*For any* SQL source code and any two supported platforms, when the code is parsed and normalized on both platforms, the resulting element lists should be functionally equivalent (same element types, names, and line numbers).
**Validates: Requirements 1.1**

Property 2: Platform detection accuracy
*For any* execution environment, the platform detector should correctly identify the operating system and Python version.
**Validates: Requirements 4.1**

Property 3: Profile loading correctness
*For any* platform with an existing behavior profile, initializing the SQL plugin should load the correct profile and adaptation rules for that platform.
**Validates: Requirements 1.4, 4.2**

Property 4: Transformation normalization
*For any* SQL code containing platform-specific parsing issues, applying the compatibility adapter should normalize the output to match the expected standard format.
**Validates: Requirements 1.2, 4.3**

Property 5: Output schema consistency
*For any* SQL parsing result after adaptation, the output schema (element structure, attributes, types) should be identical across all platforms.
**Validates: Requirements 4.5**

Property 6: Behavior recording completeness
*For any* set of test fixtures, running the behavior recorder should execute every fixture and capture results for each one.
**Validates: Requirements 2.1**

Property 7: Profile content completeness
*For any* recorded behavior profile, it should contain AST structure information, element types, node attributes, and error conditions for each tested construct.
**Validates: Requirements 2.2**

Property 8: Profile persistence correctness
*For any* behavior profile that is saved, it should be stored in the correct directory path (organized by platform and Python version) and be loadable with all data intact.
**Validates: Requirements 2.3, 2.5**

Property 9: Profile comparison accuracy
*For any* two behavior profiles with differences in parsing results, the comparison function should identify and report all significant differences.
**Validates: Requirements 2.4**

Property 10: Compatibility matrix generation
*For any* completed test suite run across multiple platforms, the system should generate a compatibility matrix report showing support status for each platform-Python combination.
**Validates: Requirements 3.5**

Property 11: Comprehensive diagnostic logging
*For any* SQL parsing operation with diagnostics enabled, the logs should contain the loaded profile, applied adaptation rules, original parse results, and normalized results.
**Validates: Requirements 5.2, 5.3, 5.4**

Property 12: Fixture library coverage
*For any* major SQL construct type (table, view, function, procedure, trigger, index), the fixture library should contain at least one standard test case and one edge case known to cause platform differences.
**Validates: Requirements 6.1, 6.2, 6.3**

Property 13: Language isolation
*For any* failure in SQL parsing on a platform, the system should continue to successfully parse and analyze files in other supported languages (Java, Python, JavaScript, etc.).
**Validates: Requirements 7.1**

Property 14: MCP capability consistency
*For any* MCP server instance where SQL parsing is disabled, the server's advertised capabilities should not include SQL-related tools.
**Validates: Requirements 7.5**

Property 15: Adaptation rule idempotence
*For any* SQL element that has been adapted once, applying the same adaptation rules again should not change the element (adaptations should be idempotent).
**Validates: Requirements 4.3** (implicit requirement for stability)

## Error Handling

### Error Categories

1. **Platform Detection Errors**
   - Unable to determine OS or Python version
   - Unsupported platform combination
   - **Handling**: Log warning, use default profile, continue with best-effort parsing

2. **Profile Loading Errors**
   - Profile file not found
   - Profile file corrupted or invalid JSON
   - Profile schema version mismatch
   - **Handling**: Log warning, fall back to default behavior, continue parsing

3. **Parsing Errors**
   - tree-sitter-sql not available
   - SQL syntax errors in source code
   - Unexpected AST structure
   - **Handling**: Return empty element list, log detailed error, suggest workarounds

4. **Adaptation Errors**
   - Adaptation rule throws exception
   - Transformation produces invalid element
   - **Handling**: Skip problematic rule, log error, continue with other rules

5. **Recording Errors**
   - Fixture execution fails
   - Unable to write profile file
   - Insufficient permissions
   - **Handling**: Log error, continue with other fixtures, report partial results

### Error Recovery Strategies

```python
# Strategy 1: Graceful Degradation
try:
    profile = BehaviorProfile.load(platform_key)
except ProfileLoadError:
    logger.warning(f"Could not load profile for {platform_key}, using defaults")
    profile = BehaviorProfile.default()

# Strategy 2: Partial Success
adapted_elements = []
for element in elements:
    try:
        adapted = adapter.adapt_element(element)
        adapted_elements.append(adapted)
    except AdaptationError as e:
        logger.error(f"Failed to adapt {element.name}: {e}")
        adapted_elements.append(element)  # Use original

# Strategy 3: Fallback Chain
def get_element_name(element, raw_text):
    # Try AST extraction
    name = extract_from_ast(element)
    if name and is_valid_identifier(name):
        return name
    
    # Fallback to regex
    name = extract_from_regex(raw_text)
    if name and is_valid_identifier(name):
        return name
    
    # Last resort: use node type
    return f"unnamed_{element.node_type}"
```

### User-Facing Error Messages

```python
# Unsupported platform
"""
SQL parsing is not fully supported on {platform_key}.

Known issues:
- Function names may be incorrectly extracted
- Some triggers may not be detected

Workarounds:
1. Use the behavior recording tool to generate a profile for your platform
2. Manually verify SQL parsing results
3. Consider using a supported platform for production use

Supported platforms: {list_supported_platforms()}
"""

# Profile not found
"""
No behavior profile found for {platform_key}.

The system will use default parsing behavior, which may produce inconsistent results.

To improve accuracy:
1. Run: python -m tree_sitter_analyzer.platform_compat.record
2. This will generate a profile for your platform
3. Restart the application

For more information: {docs_url}
"""

# Parsing failure
"""
Failed to parse SQL file: {file_path}

Error: {error_message}

Possible causes:
- SQL syntax errors in the source file
- Unsupported SQL dialect
- Platform-specific parsing limitations

Suggestions:
1. Validate SQL syntax using a SQL linter
2. Check if your SQL dialect is supported
3. Enable diagnostic mode: --diagnostic
4. Report issue with platform info: {platform_key}
"""
```

## Testing Strategy

### Unit Testing

**Core Components**:
- `PlatformDetector`: Test detection on mocked environments
- `BehaviorProfile`: Test loading, saving, validation
- `CompatibilityAdapter`: Test each adaptation rule individually
- `BehaviorRecorder`: Test fixture execution and profile generation

**Test Structure**:
```python
# tests/unit/test_platform_detector.py
def test_detect_windows():
    with mock_platform("windows", "3.12"):
        info = PlatformDetector.detect()
        assert info.os_name == "windows"
        assert info.python_version == "3.12"

# tests/unit/test_compatibility_adapter.py
def test_fix_function_name_keywords():
    adapter = CompatibilityAdapter(test_profile)
    element = SQLFunction(name="SELECT", ...)
    fixed = adapter.adapt_element(element)
    assert fixed.name != "SELECT"
    assert is_valid_identifier(fixed.name)
```

### Property-Based Testing

**Framework**: Hypothesis (already used in the project)

**Test Coverage**:
- Generate random SQL code and verify cross-platform equivalence (Property 1)
- Generate random platform configurations and verify detection (Property 2)
- Generate random SQL elements and verify adaptation idempotence (Property 15)
- Generate random fixture sets and verify recording completeness (Property 6)

**Hypothesis Strategies**:
```python
from hypothesis import strategies as st

@st.composite
def sql_element_strategy(draw):
    """Generate random SQL elements for property testing"""
    element_type = draw(st.sampled_from(['function', 'trigger', 'view', 'table', 'procedure', 'index']))
    
    # Generate valid SQL identifier
    name = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll')), 
        min_size=1, 
        max_size=50
    ).filter(lambda x: x and x[0].isalpha()))
    
    start_line = draw(st.integers(min_value=1, max_value=1000))
    end_line = draw(st.integers(min_value=start_line, max_value=start_line + 100))
    
    raw_text = f"CREATE {element_type.upper()} {name} ..."
    
    return SQLElement(
        sql_element_type=SQLElementType(element_type),
        name=name,
        start_line=start_line,
        end_line=end_line,
        raw_text=raw_text,
        language="sql",
        dependencies=[]
    )

@st.composite
def behavior_profile_strategy(draw):
    """Generate random behavior profiles for testing"""
    platform = draw(st.sampled_from(['windows', 'linux', 'darwin']))
    python_version = draw(st.sampled_from(['3.10', '3.11', '3.12', '3.13']))
    
    return BehaviorProfile(
        schema_version="1.0.0",
        platform_key=f"{platform}-{python_version}",
        tree_sitter_sql_version="0.3.11",
        behaviors={},
        adaptation_rules=[]
    )

@st.composite
def sql_code_strategy(draw):
    """Generate random but valid SQL code"""
    construct_type = draw(st.sampled_from(['table', 'view', 'function', 'procedure']))
    name = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll')),
        min_size=1,
        max_size=30
    ).filter(lambda x: x and x[0].isalpha()))
    
    if construct_type == 'table':
        return f"CREATE TABLE {name} (id INT PRIMARY KEY, name VARCHAR(100));"
    elif construct_type == 'view':
        return f"CREATE VIEW {name} AS SELECT * FROM base_table;"
    elif construct_type == 'function':
        return f"CREATE FUNCTION {name}(x INT) RETURNS INT BEGIN RETURN x * 2; END;"
    else:  # procedure
        return f"CREATE PROCEDURE {name}(IN x INT) BEGIN SELECT x; END;"
```

**Example Property Tests**:
```python
from hypothesis import given, settings

@given(
    sql_code=sql_code_strategy(),
    platform1=st.sampled_from(SUPPORTED_PLATFORMS),
    platform2=st.sampled_from(SUPPORTED_PLATFORMS)
)
@settings(max_examples=100)
def test_property_1_cross_platform_equivalence(sql_code, platform1, platform2):
    """
    Feature: sql-cross-platform-compatibility, Property 1
    
    For any SQL source code and any two supported platforms, parsing and 
    normalization should produce functionally equivalent results.
    
    Validates: Requirements 1.1
    """
    # Parse on platform 1
    with mock_platform(platform1):
        elements1 = parse_and_normalize(sql_code)
    
    # Parse on platform 2
    with mock_platform(platform2):
        elements2 = parse_and_normalize(sql_code)
    
    # Verify equivalence
    assert are_functionally_equivalent(elements1, elements2)

@given(
    element=sql_element_strategy(),
    profile=behavior_profile_strategy()
)
@settings(max_examples=100)
def test_property_15_adaptation_idempotence(element, profile):
    """
    Feature: sql-cross-platform-compatibility, Property 15
    
    For any SQL element, applying adaptations twice should produce the 
    same result as applying them once.
    
    Validates: Requirements 4.3
    """
    adapter = CompatibilityAdapter(profile)
    
    adapted_once = adapter.adapt_element(element)
    adapted_twice = adapter.adapt_element(adapted_once)
    
    assert adapted_once == adapted_twice
```

### Integration Testing

**Scenarios**:
1. End-to-end parsing with real SQL files on different platforms
2. Profile recording and loading cycle
3. CI/CD workflow simulation
4. MCP server integration with SQL disabled

**Test Files**:
```python
# tests/integration/test_sql_cross_platform.py
def test_parse_real_sql_file_windows():
    """Test parsing actual SQL file on Windows"""
    
def test_parse_real_sql_file_linux():
    """Test parsing actual SQL file on Linux"""
    
def test_profile_recording_cycle():
    """Test recording, saving, loading, and using a profile"""
    
def test_mcp_server_without_sql():
    """Test MCP server with SQL disabled"""
```

### Platform Matrix Testing (CI/CD)

**GitHub Actions Strategy**:
```yaml
strategy:
  matrix:
    os: [windows-latest, ubuntu-latest, macos-latest]
    python-version: ['3.10', '3.11', '3.12', '3.13']
  fail-fast: false  # Continue testing all combinations even if one fails

steps:
  - name: Run behavior recording
    run: python -m tree_sitter_analyzer.platform_compat.record
  
  - name: Run property tests
    run: pytest tests/test_sql_function_extraction_properties.py -v
  
  - name: Compare with baseline
    run: python -m tree_sitter_analyzer.platform_compat.compare
  
  - name: Upload profile artifact
    uses: actions/upload-artifact@v3
    with:
      name: profile-${{ matrix.os }}-${{ matrix.python-version }}
      path: tests/platform_profiles/
```

### Test Data Management

**Baseline Profiles**:
- Store known-good profiles in `tests/platform_profiles/baseline/`
- Version control these profiles
- Update baselines when intentional changes are made

**Test Fixtures**:
- Store in `tests/platform_compat/fixtures.py`
- Include comments explaining what each fixture tests
- Organize by SQL construct type and known issues

**Regression Tests**:
- When a platform-specific bug is found, add a fixture for it
- Ensure the fixture fails before the fix
- Ensure the fixture passes after the fix
- Keep the fixture to prevent regression

## Implementation Notes

### Phase 1: Core Infrastructure (Week 1)
- Implement `PlatformDetector`
- Implement `BehaviorProfile` data model
- Create basic `CompatibilityAdapter` structure
- Set up directory structure for profiles

### Phase 2: Behavior Recording (Week 2)
- Create comprehensive test fixture library
- Implement `BehaviorRecorder`
- Test recording on local platform
- Document profile JSON schema

### Phase 3: Adaptation Rules (Week 3)
- Implement adaptation rules for known issues:
  - Function name keyword filtering
  - Trigger name correction
  - Phantom element removal
  - View recovery from ERROR nodes
- Test each rule individually
- Integrate with existing `_validate_and_fix_elements()`

### Phase 4: Integration (Week 4)
- Integrate platform detection into `SQLPlugin.__init__()`
- Add profile loading to plugin initialization
- Apply adapter in element extraction pipeline
- Add diagnostic logging

### Phase 5: CI/CD & Testing (Week 5)
- Set up GitHub Actions matrix workflow
- Implement profile comparison tool
- Generate compatibility matrix reports
- Run full platform matrix tests

### Phase 6: Documentation & Polish (Week 6)
- Write user documentation
- Create troubleshooting guide
- Add CLI commands for platform info
- Final testing and bug fixes

### Profile Schema Migration

**Version Strategy**:
- Semantic versioning for profile schema (MAJOR.MINOR.PATCH)
- MAJOR: Breaking changes requiring migration
- MINOR: Backward-compatible additions
- PATCH: Bug fixes, no schema changes

**Migration Implementation**:
```python
def migrate_profile_schema(data: dict) -> dict:
    """Migrate profile from old schema to current schema"""
    old_version = data.get("schema_version", "0.0.0")
    current_version = PROFILE_SCHEMA_VERSION
    
    if old_version == current_version:
        return data
    
    # Migration chain
    if old_version < "1.0.0":
        data = migrate_to_1_0_0(data)
    
    # Future migrations
    # if old_version < "2.0.0":
    #     data = migrate_to_2_0_0(data)
    
    data["schema_version"] = current_version
    return data

def migrate_to_1_0_0(data: dict) -> dict:
    """Migrate from pre-1.0.0 to 1.0.0"""
    # Add schema_version if missing
    if "schema_version" not in data:
        data["schema_version"] = "1.0.0"
    
    # Ensure all required fields exist
    if "adaptation_rules" not in data:
        data["adaptation_rules"] = []
    
    return data
```

**Migration Testing**:
- Test migration from each old version to current
- Verify no data loss during migration
- Ensure migrated profiles pass validation

### Backward Compatibility

**Existing Code**:
- The current `_validate_and_fix_elements()` method will be preserved
- New adaptation layer will wrap existing validation
- No breaking changes to public API

**Migration Path**:
- System works without profiles (uses defaults)
- Profiles are optional enhancements
- Users can gradually adopt by recording profiles
- Old profiles automatically migrated on load

**Configuration**:
```python
# Optional environment variables
TREE_SITTER_SQL_PROFILE_DIR = "/path/to/profiles"  # Custom profile location
TREE_SITTER_SQL_DISABLE_ADAPTATION = "true"  # Disable adaptation layer
TREE_SITTER_SQL_DIAGNOSTIC = "true"  # Enable diagnostic logging
TREE_SITTER_SQL_PROFILE_CACHE_TTL = "3600"  # Cache TTL in seconds
```

### Performance Considerations

**Profile Loading**:
- Load profiles once at plugin initialization
- Cache loaded profiles in memory with TTL
- Profile files are small (~10-50 KB)
- Implement thread-safe caching:

```python
from threading import Lock
import time

class ProfileCache:
    """Thread-safe profile cache with TTL"""
    
    def __init__(self, max_size: int = 10, ttl_seconds: int = 3600):
        self._cache: dict[str, tuple[BehaviorProfile, float]] = {}
        self._lock = Lock()
        self._max_size = max_size
        self._ttl = ttl_seconds
    
    def get(self, platform_key: str) -> Optional[BehaviorProfile]:
        """Get profile from cache with TTL check"""
        with self._lock:
            if platform_key in self._cache:
                profile, timestamp = self._cache[platform_key]
                if time.time() - timestamp < self._ttl:
                    return profile
                else:
                    del self._cache[platform_key]
        return None
    
    def put(self, platform_key: str, profile: BehaviorProfile) -> None:
        """Put profile in cache with LRU eviction"""
        with self._lock:
            if len(self._cache) >= self._max_size:
                # Evict oldest entry
                oldest_key = min(self._cache.items(), key=lambda x: x[1][1])[0]
                del self._cache[oldest_key]
            self._cache[platform_key] = (profile, time.time())
```

**Adaptation Overhead**:
- Adaptation rules are simple transformations
- Most rules are O(1) per element
- Total overhead: < 5% of parsing time
- Benchmark: ~0.1ms per element on average

**Recording Performance**:
- Recording is a one-time operation per platform
- Can be run offline or in CI/CD
- Not part of normal parsing workflow
- Typical recording time: 5-10 seconds for all fixtures

### Security Considerations

**Profile Files**:
- Validate JSON schema before loading using jsonschema library
- Sanitize file paths to prevent directory traversal
- Restrict profile directory permissions (read-only for application)
- Implement profile validation:

```python
from jsonschema import validate, ValidationError

PROFILE_JSON_SCHEMA = {
    "type": "object",
    "required": ["schema_version", "platform_key", "behaviors"],
    "properties": {
        "schema_version": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$"},
        "platform_key": {
            "type": "string", 
            "pattern": "^(windows|linux|darwin)-3\\.(10|11|12|13)$"
        },
        "tree_sitter_sql_version": {"type": "string"},
        "behaviors": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "required": ["node_type", "name_extraction"]
            }
        },
        "adaptation_rules": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["rule_id", "construct_type", "description"]
            }
        }
    }
}

def validate_profile(profile_data: dict) -> None:
    """Validate profile against JSON schema"""
    try:
        validate(instance=profile_data, schema=PROFILE_JSON_SCHEMA)
    except ValidationError as e:
        raise ProfileValidationError(f"Invalid profile: {e.message}")
```

**Adaptation Rules**:
- Rules are code, not data - no eval() or exec()
- Validate rule outputs (must return SQLElement or None)
- Catch and log exceptions in rules
- Implement rule sandboxing to prevent side effects

**CI/CD**:
- Profiles generated in CI are artifacts, not code
- Review profile changes in PRs
- Sign/checksum profiles for integrity
- Store checksums in separate file for verification

## Future Enhancements

1. **Automatic Profile Updates**: Detect tree-sitter-sql version changes and trigger re-recording
2. **Profile Sharing**: Community-contributed profiles for exotic platforms
3. **Machine Learning**: Learn adaptation rules from examples instead of hand-coding
4. **Real-time Monitoring**: Track parsing success rates across platforms in production
5. **SQL Dialect Support**: Extend to handle MySQL, PostgreSQL, SQL Server differences
6. **Performance Profiling**: Detailed metrics on parsing performance per platform
7. **Visual Diff Tool**: GUI for comparing behavior profiles
8. **Automated Regression Detection**: Alert when new platform issues are detected
