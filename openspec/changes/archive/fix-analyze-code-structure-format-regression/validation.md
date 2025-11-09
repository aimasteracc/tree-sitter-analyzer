# Validation Plan: Fix analyze_code_structure Format Regression

## Overview

This document defines the comprehensive validation strategy to ensure the format restoration correctly addresses all identified issues and maintains backward compatibility with v1.6.1.4.

## Validation Phases

### Phase 1: Reference Output Generation

#### V1.1: Create v1.6.1.4 Reference Outputs
**Objective**: Establish ground truth for format validation

**Steps**:
1. Set up v1.6.1.4 environment in isolated container
2. Execute `analyze_code_structure` with test files for each format:
   - `examples/Sample.java` with `format_type="full"`
   - `examples/MultiClass.java` with `format_type="full"`
   - `examples/Sample.java` with `format_type="compact"`
   - `examples/Sample.java` with `format_type="csv"`
3. Capture exact outputs as reference files
4. Document any platform-specific differences (line endings, etc.)

**Success Criteria**:
- Reference outputs captured for all supported formats
- Reference files stored in `tests/reference_outputs/v1.6.1.4/`
- Documentation of expected format specifications

### Phase 2: Format Compliance Testing

#### V2.1: Full Format Validation
**Objective**: Ensure full format produces correct Markdown tables

**Test Cases**:
```python
def test_full_format_single_class():
    """Test full format with single class matches v1.6.1.4"""
    result = analyze_code_structure("examples/Sample.java", format_type="full")
    reference = load_reference("Sample.java.full.md")
    assert_format_match(result, reference)

def test_full_format_multi_class():
    """Test full format with multiple classes"""
    result = analyze_code_structure("examples/MultiClass.java", format_type="full")
    reference = load_reference("MultiClass.java.full.md")
    assert_format_match(result, reference)

def test_full_format_markdown_structure():
    """Validate Markdown table structure"""
    result = analyze_code_structure("examples/Sample.java", format_type="full")
    assert_contains_markdown_headers(result)
    assert_contains_markdown_tables(result)
    assert_proper_table_formatting(result)
```

#### V2.2: Compact Format Validation
**Objective**: Ensure compact format includes complexity information

**Test Cases**:
```python
def test_compact_format_complexity():
    """Test compact format includes complexity scores"""
    result = analyze_code_structure("examples/Sample.java", format_type="compact")
    assert_contains_complexity_column(result)
    assert_markdown_table_format(result)

def test_compact_format_structure():
    """Validate compact format table structure"""
    result = analyze_code_structure("examples/Sample.java", format_type="compact")
    assert_contains_methods_table(result)
    assert_contains_fields_table(result)
    assert_proper_column_headers(result)
```

#### V2.3: CSV Format Validation
**Objective**: Ensure CSV format maintains simple structure

**Test Cases**:
```python
def test_csv_format_structure():
    """Test CSV format produces valid CSV"""
    result = analyze_code_structure("examples/Sample.java", format_type="csv")
    assert_valid_csv_format(result)
    assert_simple_parameter_format(result)

def test_csv_format_headers():
    """Validate CSV headers match specification"""
    result = analyze_code_structure("examples/Sample.java", format_type="csv")
    headers = result.split('\n')[0].split(',')
    expected = ["Type", "Name", "Visibility", "Lines", "Complexity", "Parameters"]
    assert headers == expected
```

### Phase 3: Schema and API Validation

#### V3.1: Tool Schema Validation
**Objective**: Ensure tool schema reflects correct supported formats

**Test Cases**:
```python
def test_tool_schema_formats():
    """Test tool schema only includes supported formats"""
    schema = table_format_tool.get_tool_schema()
    format_enum = schema["properties"]["format_type"]["enum"]
    expected_formats = ["full", "compact", "csv"]
    assert set(format_enum) == set(expected_formats)

def test_html_formats_removed():
    """Ensure HTML formats are not supported"""
    html_formats = ["html", "html_compact", "html_json"]
    for html_format in html_formats:
        with pytest.raises(ValueError):
            analyze_code_structure("examples/Sample.java", format_type=html_format)
```

#### V3.2: Error Handling Validation
**Objective**: Ensure error handling matches v1.6.1.4 behavior

**Test Cases**:
```python
def test_file_not_found_error():
    """Test FileNotFoundError for non-existent files"""
    with pytest.raises(FileNotFoundError):
        analyze_code_structure("nonexistent.java", format_type="full")

def test_invalid_format_error():
    """Test ValueError for unsupported formats"""
    with pytest.raises(ValueError, match="Unsupported format"):
        analyze_code_structure("examples/Sample.java", format_type="invalid")
```

### Phase 4: Integration Testing

#### V4.1: MCP Server Integration
**Objective**: Ensure MCP server correctly handles restored formats

**Test Cases**:
```python
async def test_mcp_server_format_restoration():
    """Test MCP server with restored formats"""
    server = MCPServer()
    
    # Test each format through MCP protocol
    for format_type in ["full", "compact", "csv"]:
        request = {
            "name": "analyze_code_structure",
            "arguments": {
                "file_path": "examples/Sample.java",
                "format_type": format_type
            }
        }
        response = await server.call_tool(request)
        assert response["success"] is True
        validate_format_output(response["table_output"], format_type)
```

#### V4.2: CLI Compatibility
**Objective**: Ensure CLI produces identical outputs

**Test Cases**:
```bash
# Test CLI format outputs match MCP outputs
python -m tree_sitter_analyzer examples/Sample.java --format full > cli_full.txt
python -m tree_sitter_analyzer examples/Sample.java --format compact > cli_compact.txt
python -m tree_sitter_analyzer examples/Sample.java --format csv > cli_csv.txt

# Compare with MCP outputs
diff cli_full.txt mcp_full.txt
diff cli_compact.txt mcp_compact.txt
diff cli_csv.txt mcp_csv.txt
```

### Phase 5: Performance and Regression Testing

#### V5.1: Performance Impact Assessment
**Objective**: Ensure hybrid formatter architecture has minimal performance impact

**Test Cases**:
```python
def test_format_performance():
    """Measure performance impact of format decision logic"""
    import time
    
    # Baseline: direct formatter call
    start = time.time()
    for _ in range(100):
        legacy_formatter = LegacyTableFormatter("full")
        legacy_formatter.format_structure(test_data)
    baseline_time = time.time() - start
    
    # With decision logic
    start = time.time()
    for _ in range(100):
        analyze_code_structure("examples/Sample.java", format_type="full")
    actual_time = time.time() - start
    
    # Performance impact should be < 5%
    assert actual_time < baseline_time * 1.05
```

#### V5.2: Regression Testing
**Objective**: Ensure no existing functionality is broken

**Test Cases**:
- Run complete existing test suite
- Verify all language plugins work correctly
- Test file output functionality
- Test security validation
- Test path resolution

### Phase 6: Documentation Validation

#### V6.1: Tool Documentation Accuracy
**Objective**: Ensure documentation reflects actual behavior

**Validation Steps**:
1. Review tool description in MCP server
2. Verify format examples in documentation
3. Check CHANGELOG entries for accuracy
4. Validate migration guide completeness

#### V6.2: API Documentation Consistency
**Objective**: Ensure API documentation matches implementation

**Validation Steps**:
1. Verify tool schema documentation
2. Check format specification examples
3. Validate error message documentation
4. Review integration examples

## Automated Validation Pipeline

### Continuous Integration Checks
```yaml
validation_pipeline:
  - name: "Format Compliance"
    tests: ["test_full_format_*", "test_compact_format_*", "test_csv_format_*"]
  
  - name: "Schema Validation"
    tests: ["test_tool_schema_*", "test_html_formats_removed"]
  
  - name: "Integration Testing"
    tests: ["test_mcp_server_*", "test_cli_compatibility"]
  
  - name: "Performance Testing"
    tests: ["test_format_performance"]
  
  - name: "Regression Testing"
    tests: ["existing_test_suite"]
```

### Quality Gates
1. **Format Compliance**: 100% of format tests must pass
2. **Schema Validation**: Tool schema must exactly match specification
3. **Integration Testing**: All integration tests must pass
4. **Performance**: No more than 5% performance degradation
5. **Regression**: All existing tests must continue to pass

## Success Criteria

### Primary Success Criteria
- [ ] All format outputs match v1.6.1.4 reference samples exactly
- [ ] Tool schema reflects only supported formats: `["full", "compact", "csv"]`
- [ ] HTML formats are completely inaccessible
- [ ] All integration tests pass
- [ ] Performance impact is negligible (< 5%)

### Secondary Success Criteria
- [ ] Documentation accurately reflects restored behavior
- [ ] Migration guide helps v1.9.4 users transition
- [ ] Error messages are clear and helpful
- [ ] Code maintainability is preserved or improved

## Risk Mitigation

### High-Risk Areas
1. **Format Compatibility**: Use reference output comparison
2. **Integration Breakage**: Comprehensive integration testing
3. **Performance Regression**: Automated performance monitoring
4. **Documentation Drift**: Automated documentation validation

### Rollback Plan
If validation fails:
1. Identify specific failure points
2. Implement targeted fixes
3. Re-run validation pipeline
4. If critical issues persist, rollback to v1.9.4 with issue documentation
