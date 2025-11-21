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
    
class BehaviorProfile:
    """Complete behavior profile for a platform"""
    platform_key: str
    tree_sitter_sql_version: str
    behaviors: dict[str, ParsingBehavior]
    adaptation_rules: list[AdaptationRule]
    
    @classmethod
    def load(cls, platform_key: str) -> Optional['BehaviorProfile']:
        """Load profile from disk"""
        
    def get_adaptation_rules(self, construct_type: str) -> list[AdaptationRule]:
        """Get adaptation rules for a construct type"""

class AdaptationRule:
    """Rule for adapting platform-specific behavior"""
    rule_id: str
    construct_type: str
    condition: Callable[[Any], bool]
    transformation: Callable[[Any], Any]
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
-