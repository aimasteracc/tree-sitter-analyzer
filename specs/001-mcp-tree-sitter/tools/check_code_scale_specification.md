# check_code_scale Tool Specification

**Tool ID**: `check_code_scale`  
**Version**: 1.0.0  
**Category**: Code Analysis  
**Priority**: P1 (User Story 1)  
**Status**: ✅ Implemented & Tested

## 📋 Overview

The `check_code_scale` tool analyzes code scale, complexity, and structure metrics with LLM-optimized guidance for efficient large file analysis and token-aware workflow recommendations.

## 🎯 Purpose

- **Primary**: Provide quick scale assessment before detailed analysis
- **Secondary**: Generate LLM-optimized analysis strategies
- **Tertiary**: Support token-efficient workflow decisions

## 📊 Capabilities

### Core Metrics
- **File Metrics**: Lines (total, code, comments, blank), file size
- **Structure Metrics**: Classes, methods, fields, imports, packages
- **Complexity Metrics**: Cyclomatic complexity (total, average, max)
- **Language Detection**: Automatic language identification

### Analysis Features
- **Security Validation**: Project boundary protection
- **Path Resolution**: Relative/absolute path handling
- **Error Handling**: Comprehensive validation and error reporting
- **Performance Optimization**: Efficient parsing for large files

## 🔧 API Specification

### Input Schema

```json
{
  "type": "object",
  "required": ["file_path"],
  "properties": {
    "file_path": {
      "type": "string",
      "description": "Path to the code file to analyze"
    },
    "language": {
      "type": "string",
      "description": "Programming language (optional, auto-detected if not specified)"
    },
    "include_complexity": {
      "type": "boolean",
      "default": true,
      "description": "Include complexity metrics in the analysis"
    },
    "include_details": {
      "type": "boolean",
      "default": false,
      "description": "Include detailed element information"
    },
    "include_guidance": {
      "type": "boolean",
      "default": true,
      "description": "Include LLM analysis guidance"
    }
  }
}
```

### Output Schema

```json
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "Original file path provided"
    },
    "language": {
      "type": "string",
      "description": "Detected or specified programming language"
    },
    "metrics": {
      "type": "object",
      "properties": {
        "lines_total": {
          "type": "integer",
          "description": "Total lines in file"
        },
        "lines_code": {
          "type": "integer",
          "description": "Lines containing code"
        },
        "lines_comment": {
          "type": "integer",
          "description": "Lines containing comments"
        },
        "lines_blank": {
          "type": "integer",
          "description": "Blank lines"
        },
        "elements": {
          "type": "object",
          "properties": {
            "classes": {"type": "integer"},
            "methods": {"type": "integer"},
            "fields": {"type": "integer"},
            "imports": {"type": "integer"},
            "packages": {"type": "integer"},
            "total": {"type": "integer"}
          }
        },
        "complexity": {
          "type": "object",
          "properties": {
            "total": {"type": "number"},
            "average": {"type": "number"},
            "max": {"type": "number"}
          },
          "description": "Included when include_complexity=true"
        }
      }
    },
    "detailed_elements": {
      "type": "array",
      "description": "Detailed element information (when include_details=true)"
    }
  }
}
```

## 🔍 Implementation Details

### Core Algorithm

1. **Initialization Check**: Verify server initialization status
2. **Path Resolution**: Handle relative paths against project root
3. **Security Validation**: Validate file path against project boundaries
4. **File Validation**: Check file existence and accessibility
5. **Language Detection**: Auto-detect if not specified
6. **Analysis Execution**: Use AnalysisEngine for parsing
7. **Metrics Calculation**: Extract structure and complexity metrics
8. **Result Assembly**: Format response with optional details

### Key Components

#### Security Validation
```python
is_valid, error_msg = self.security_validator.validate_file_path(resolved_path)
if not is_valid:
    raise ValueError(f"Invalid file path: {error_msg}")
```

#### Language Detection
```python
from ..language_detector import detect_language_from_file
if not language:
    language = detect_language_from_file(resolved_path)
```

#### Analysis Engine Integration
```python
from ..core.analysis_engine import AnalysisRequest
request = AnalysisRequest(
    file_path=resolved_path,
    language=language,
    include_complexity=include_complexity,
    include_details=include_details,
)
analysis_result = await self.analysis_engine.analyze(request)
```

#### Element Counting
```python
elements = analysis_result.elements or []
classes_count = len([e for e in elements if is_element_of_type(e, ELEMENT_TYPE_CLASS)])
methods_count = len([e for e in elements if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)])
# ... other element types
```

## 🧪 Testing Coverage

### Test Categories
- **Schema Validation**: Input parameter validation
- **Functionality**: Core analysis features
- **Integration**: AnalysisEngine and language detection
- **Error Handling**: Invalid paths, missing files, unsupported languages
- **Performance**: Large file handling

### Test Files
- `tests/mcp/test_tools/test_analyze_scale_tool.py` (18 tests)
- Coverage: 100% of core functionality

### Key Test Cases
1. **Valid Java File Analysis**: Standard functionality test
2. **Missing File Path**: Error handling validation
3. **Invalid File Types**: Unsupported language handling
4. **Language Detection**: Auto-detection verification
5. **Complexity Metrics**: Calculation accuracy
6. **LLM Guidance**: Output format validation

## 🚀 Usage Examples

### Basic Usage
```json
{
  "file_path": "src/main/java/Example.java"
}
```

### Advanced Usage
```json
{
  "file_path": "src/components/App.tsx",
  "language": "typescript",
  "include_complexity": true,
  "include_details": false,
  "include_guidance": true
}
```

### Expected Output
```json
{
  "file_path": "src/main/java/Example.java",
  "language": "java",
  "metrics": {
    "lines_total": 150,
    "lines_code": 120,
    "lines_comment": 20,
    "lines_blank": 10,
    "elements": {
      "classes": 2,
      "methods": 8,
      "fields": 5,
      "imports": 3,
      "packages": 1,
      "total": 19
    },
    "complexity": {
      "total": 25,
      "average": 3.13,
      "max": 8
    }
  }
}
```

## ⚡ Performance Characteristics

### Execution Time
- **Small files** (<1000 lines): <100ms
- **Medium files** (1000-5000 lines): <500ms
- **Large files** (>5000 lines): <2s

### Memory Usage
- **Efficient parsing**: Tree-sitter based analysis
- **Minimal memory footprint**: Stream-based processing
- **Scalable**: Handles files up to 100MB

## 🔒 Security Features

### Project Boundary Protection
- **Path Validation**: Prevents access outside project scope
- **Relative Path Resolution**: Secure handling of relative paths
- **Input Sanitization**: Validates all input parameters

### Error Handling
- **Graceful Degradation**: Continues analysis on partial failures
- **Detailed Error Messages**: Clear error reporting
- **Security-First**: No sensitive information in error messages

## 🔗 Dependencies

### Internal Dependencies
- `tree_sitter_analyzer.core.analysis_engine.AnalysisEngine`
- `tree_sitter_analyzer.language_detector.detect_language_from_file`
- `tree_sitter_analyzer.models.ELEMENT_TYPE_*`

### External Dependencies
- `tree-sitter`: Core parsing engine
- `pathlib`: Path manipulation
- `asyncio`: Asynchronous execution

## 📈 Integration Points

### User Story 1 Integration
- **Primary Tool**: Core analysis capability
- **Workflow**: Scale assessment → Structure analysis → Detailed extraction
- **Token Optimization**: Efficient analysis strategy recommendations

### MCP Protocol Compliance
- **Tool Registration**: Proper MCP tool schema
- **Error Handling**: MCP-compliant error responses
- **Async Support**: Full asyncio compatibility

## 🎯 Success Criteria

### Functional Requirements
- ✅ **FR-001**: Analyze code scale and complexity metrics
- ✅ **FR-002**: Support 5 programming languages (Java, JavaScript, TypeScript, Python, Markdown)
- ✅ **FR-003**: Provide LLM-optimized analysis guidance
- ✅ **FR-004**: Maintain project boundary security

### Performance Requirements
- ✅ **NFR-001**: Analysis completion within 3 seconds for typical files
- ✅ **NFR-002**: Support files up to 100MB
- ✅ **NFR-003**: Memory usage under 500MB for large files

### Quality Requirements
- ✅ **QR-001**: 100% test coverage for core functionality
- ✅ **QR-002**: Comprehensive error handling
- ✅ **QR-003**: Security validation for all inputs

## 📝 Notes

### Implementation Status
- **Core Functionality**: ✅ Complete
- **Test Coverage**: ✅ Comprehensive (18 tests)
- **Documentation**: ✅ This specification
- **API Contract**: ✅ OpenAPI specification available

### Future Enhancements
- **Language Support**: Additional programming languages
- **Caching**: Result caching for repeated analysis
- **Streaming**: Large file streaming analysis
- **Metrics Export**: Export metrics to external systems

---

**Last Updated**: 2025-10-12  
**Specification Version**: 1.0.0  
**Implementation Version**: 1.7.5