# Design: Comprehensive Format Testing Strategy

## Architecture Overview

This design establishes a multi-layered testing architecture that prevents format regressions through comprehensive validation at every level of the system.

## Current Testing Problems

### 1. Mock-Heavy Anti-Pattern
```python
# PROBLEMATIC: Current test pattern
mock_formatter.format_structure.return_value = "# Mock Table Output\n| Column | Value |"
```
**Issues:**
- Bypasses actual format generation logic
- Mock data doesn't reflect real format complexity
- No validation of format specification compliance
- Creates false confidence in test coverage

### 2. Weak Assertion Pattern
```python
# PROBLEMATIC: Current assertion pattern
assert "# com.example.test.TestClass" in result
assert "## Class Info" in result
```
**Issues:**
- String-contains checks don't validate structure
- No verification of table syntax or alignment
- Missing format-specific requirement validation
- Allows malformed output to pass tests

### 3. Component Isolation Problem
```
TableFormatter ←→ (no integration) ←→ TableFormatTool
     ↓                                        ↓
  Unit Tests                            Mock-based Tests
```
**Issues:**
- No end-to-end format validation
- Integration gaps allow regressions
- Format consistency not verified across components

## Proposed Testing Architecture

### Layer 1: Format Contract Testing
```
Golden Master Files ←→ Schema Validators ←→ Format Assertions
        ↓                      ↓                    ↓
   Reference Truth      Structure Rules      Specific Checks
```

#### Golden Master Framework
```python
class GoldenMasterTester:
    def __init__(self, format_type: str):
        self.reference_dir = Path(f"tests/golden_masters/{format_type}")
        
    def assert_matches_golden_master(self, actual_output: str, test_name: str):
        """Compare actual output against golden master reference"""
        golden_file = self.reference_dir / f"{test_name}.{self.format_type}"
        
        if not golden_file.exists():
            # First run - create golden master
            golden_file.write_text(actual_output)
            pytest.skip(f"Created golden master: {golden_file}")
            
        expected = golden_file.read_text()
        if actual_output != expected:
            # Generate diff and fail with detailed comparison
            diff = self._generate_diff(expected, actual_output)
            pytest.fail(f"Output differs from golden master:\n{diff}")
```

#### Format Schema Validation
```python
class MarkdownTableValidator:
    def validate_structure(self, content: str) -> ValidationResult:
        """Validate markdown table structure and syntax"""
        lines = content.split('\n')
        
        # Check table headers
        header_pattern = r'^\|.*\|$'
        separator_pattern = r'^\|[-:]+\|$'
        
        # Validate table syntax
        for i, line in enumerate(lines):
            if self._is_table_line(line):
                if not re.match(header_pattern, line):
                    return ValidationResult.error(f"Invalid table syntax at line {i}")
                    
        # Check column alignment
        if not self._validate_column_alignment(lines):
            return ValidationResult.error("Table columns not properly aligned")
            
        return ValidationResult.success()

class CSVFormatValidator:
    def validate_structure(self, content: str) -> ValidationResult:
        """Validate CSV format compliance"""
        try:
            reader = csv.reader(StringIO(content))
            rows = list(reader)
            
            # Validate header row
            if not rows or not self._is_valid_header(rows[0]):
                return ValidationResult.error("Invalid or missing CSV header")
                
            # Validate data consistency
            header_count = len(rows[0])
            for i, row in enumerate(rows[1:], 1):
                if len(row) != header_count:
                    return ValidationResult.error(f"Row {i} has inconsistent column count")
                    
            return ValidationResult.success()
        except csv.Error as e:
            return ValidationResult.error(f"CSV parsing error: {e}")
```

#### Format-Specific Assertions
```python
class FormatAssertions:
    @staticmethod
    def assert_markdown_table_structure(content: str, expected_sections: List[str]):
        """Assert markdown table has required sections and structure"""
        # Validate section headers
        for section in expected_sections:
            assert f"## {section}" in content, f"Missing section: {section}"
            
        # Validate table structure after each section
        sections = content.split('## ')
        for section in sections[1:]:  # Skip first empty section
            if '|' in section:  # Has table content
                FormatAssertions._validate_table_in_section(section)
    
    @staticmethod
    def assert_compact_format_includes_complexity(content: str):
        """Assert compact format includes complexity scores"""
        # Look for complexity indicators
        complexity_patterns = [
            r'Complexity:\s*\d+',
            r'CC:\s*\d+',
            r'\(\d+\)',  # Complexity in parentheses
        ]
        
        has_complexity = any(
            re.search(pattern, content) for pattern in complexity_patterns
        )
        assert has_complexity, "Compact format missing complexity information"
    
    @staticmethod
    def assert_csv_format_compliance(content: str):
        """Assert CSV format follows specification"""
        lines = content.strip().split('\n')
        assert len(lines) >= 2, "CSV must have header and at least one data row"
        
        # Validate header
        header = lines[0].split(',')
        expected_columns = ['Name', 'Type', 'Visibility', 'Modifiers', 'Line', 'Description']
        for col in expected_columns:
            assert col in header, f"Missing required CSV column: {col}"
```

### Layer 2: Integration Testing Enhancement

#### Real Implementation Testing
```python
class TestTableFormatToolIntegration:
    """Integration tests using real implementations, minimal mocking"""
    
    @pytest.fixture
    def real_tool(self, temp_project_with_java_file):
        """Create TableFormatTool with real dependencies"""
        # Only mock external dependencies (file system already handled by fixture)
        return TableFormatTool(temp_project_with_java_file)
    
    @pytest.mark.asyncio
    async def test_full_format_end_to_end(self, real_tool, golden_master_tester):
        """Test complete flow with real formatting"""
        # Execute with real implementation
        result = await real_tool.execute({
            "file_path": "TestClass.java",
            "format_type": "full"
        })
        
        # Validate against golden master
        golden_master_tester.assert_matches_golden_master(
            result["table_output"], 
            "java_class_full_format"
        )
        
        # Validate format structure
        MarkdownTableValidator().validate_structure(result["table_output"])
        
        # Validate format-specific requirements
        FormatAssertions.assert_markdown_table_structure(
            result["table_output"],
            ["Class Info", "Fields", "Constructor", "Public Methods", "Private Methods"]
        )
```

#### Cross-Component Validation
```python
class TestFormatConsistency:
    """Test format consistency across different code paths"""
    
    def test_formatter_registry_vs_legacy_formatter(self, sample_java_data):
        """Ensure FormatterRegistry and legacy formatters produce identical output"""
        # Test with FormatterRegistry
        registry_formatter = FormatterRegistry.get_formatter("full")
        registry_output = registry_formatter.format(sample_java_data)
        
        # Test with legacy formatter
        legacy_formatter = LegacyTableFormatter("full")
        legacy_output = legacy_formatter.format_structure(sample_java_data)
        
        # Outputs must be identical
        assert registry_output == legacy_output, "Format inconsistency between registry and legacy"
    
    def test_mcp_vs_cli_format_consistency(self, temp_java_file):
        """Ensure MCP and CLI interfaces produce identical format output"""
        # Get output through MCP interface
        mcp_tool = TableFormatTool()
        mcp_result = await mcp_tool.execute({
            "file_path": str(temp_java_file),
            "format_type": "full"
        })
        
        # Get output through CLI interface
        cli_result = subprocess.run([
            "python", "-m", "tree_sitter_analyzer",
            "--file", str(temp_java_file),
            "--table", "full"
        ], capture_output=True, text=True)
        
        # Extract table content from both outputs
        mcp_table = mcp_result["table_output"]
        cli_table = self._extract_table_from_cli_output(cli_result.stdout)
        
        assert mcp_table == cli_table, "Format inconsistency between MCP and CLI"
```

### Layer 3: Specification Enforcement

#### Format Specification Documents
```yaml
# format_specifications/full_format.yaml
format_type: full
description: "Complete markdown table format with all class details"
required_sections:
  - name: "Class Info"
    type: "table"
    required_columns: ["Property", "Value"]
    required_rows: ["Package", "Type", "Visibility", "Lines", "Total Methods", "Total Fields"]
  - name: "Fields"
    type: "table"
    required_columns: ["Name", "Type", "Visibility", "Modifiers", "Line", "Description"]
    conditional: "if fields exist"
  - name: "Constructor"
    type: "table"
    required_columns: ["Name", "Parameters", "Visibility", "Line", "Description"]
    conditional: "if constructors exist"
  - name: "Public Methods"
    type: "table"
    required_columns: ["Name", "Return Type", "Parameters", "Line", "Description"]
    conditional: "if public methods exist"
  - name: "Private Methods"
    type: "table"
    required_columns: ["Name", "Return Type", "Parameters", "Line", "Description"]
    conditional: "if private methods exist"
syntax_rules:
  - "Must start with class name header (# ClassName)"
  - "Each section must have proper markdown table syntax"
  - "Tables must have header separator row (|---|---|)"
  - "All table columns must be properly aligned"
```

#### Specification Compliance Testing
```python
class SpecificationComplianceValidator:
    def __init__(self, spec_file: Path):
        self.spec = yaml.safe_load(spec_file.read_text())
    
    def validate_compliance(self, content: str, data: Dict[str, Any]) -> ValidationResult:
        """Validate content against format specification"""
        results = []
        
        # Check required sections
        for section_spec in self.spec["required_sections"]:
            result = self._validate_section(content, section_spec, data)
            results.append(result)
        
        # Check syntax rules
        for rule in self.spec["syntax_rules"]:
            result = self._validate_syntax_rule(content, rule)
            results.append(result)
        
        # Combine results
        errors = [r for r in results if not r.is_success()]
        if errors:
            return ValidationResult.error(f"Specification violations: {errors}")
        
        return ValidationResult.success()
```

### Layer 4: Continuous Monitoring

#### CI/CD Integration
```yaml
# .github/workflows/format-validation.yml
name: Format Validation
on: [push, pull_request]

jobs:
  format-regression-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          pip install -e .
          pip install pytest
      
      - name: Run format regression tests
        run: |
          pytest tests/format_regression/ -v
          pytest tests/golden_masters/ -v
          pytest tests/specification_compliance/ -v
      
      - name: Validate format specifications
        run: |
          python scripts/validate_format_specs.py
      
      - name: Check for format changes
        run: |
          python scripts/detect_format_changes.py
```

#### Format Change Detection
```python
class FormatChangeDetector:
    def detect_changes(self, before_commit: str, after_commit: str) -> List[FormatChange]:
        """Detect format changes between commits"""
        changes = []
        
        # Run format tests on both commits
        before_outputs = self._run_format_tests(before_commit)
        after_outputs = self._run_format_tests(after_commit)
        
        # Compare outputs
        for test_name in before_outputs:
            if test_name in after_outputs:
                if before_outputs[test_name] != after_outputs[test_name]:
                    change = FormatChange(
                        test_name=test_name,
                        before=before_outputs[test_name],
                        after=after_outputs[test_name],
                        diff=self._generate_diff(before_outputs[test_name], after_outputs[test_name])
                    )
                    changes.append(change)
        
        return changes
```

## Implementation Strategy

### Phase 1: Foundation (Weeks 1-2)
1. Create golden master test framework
2. Implement basic format validators
3. Set up specification documents

### Phase 2: Integration (Weeks 3-4)
1. Replace mock-heavy tests with real implementations
2. Add end-to-end format validation
3. Implement cross-component consistency tests

### Phase 3: Enforcement (Weeks 5-6)
1. Add specification compliance testing
2. Implement format contract validation
3. Create format change detection tools

### Phase 4: Monitoring (Weeks 7-8)
1. Integrate into CI/CD pipeline
2. Add format monitoring tools
3. Establish change management process

## Benefits

1. **Regression Prevention**: Any format change triggers appropriate test failures
2. **Specification Compliance**: Automated validation ensures output matches documentation
3. **Integration Confidence**: End-to-end testing validates complete format pipeline
4. **Change Visibility**: Clear detection and reporting of format modifications
5. **Quality Assurance**: Comprehensive validation at every level of the system

This architecture ensures that format regressions like the v1.6.1.4 → v1.9.4 incident cannot occur undetected in the future.
