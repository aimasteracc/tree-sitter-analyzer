# analyze_code_structure Tool Specification

**Tool ID**: `analyze_code_structure`  
**Version**: 1.0.0  
**Category**: Code Analysis  
**Priority**: P1 (User Story 1)  
**Status**: ✅ Implemented & Tested

## 📋 Overview

The `analyze_code_structure` tool analyzes code structure and generates detailed overview tables (classes, methods, fields) with line positions for large files, optionally saving to file with token optimization features.

## 🎯 Purpose

- **Primary**: Generate comprehensive structure documentation tables
- **Secondary**: Support large file analysis with token optimization
- **Tertiary**: Provide multiple output formats for different use cases

## 📊 Capabilities

### Core Features
- **Structure Analysis**: Classes, methods, fields with line positions
- **Multiple Formats**: Full, compact, CSV, JSON output formats
- **Token Optimization**: suppress_output feature for large files
- **File Output**: Save results to external files
- **Language Support**: 5 programming languages (Java, JavaScript, TypeScript, Python, Markdown)

### Advanced Features
- **Security Validation**: Project boundary protection
- **Performance Monitoring**: Built-in execution time tracking
- **Error Handling**: Comprehensive validation and error reporting
- **Path Resolution**: Relative/absolute path handling

## 🔧 API Specification

### Input Schema

```json
{
  "type": "object",
  "required": ["file_path"],
  "properties": {
    "file_path": {
      "type": "string",
      "description": "Path to the code file to analyze and format"
    },
    "format_type": {
      "type": "string",
      "enum": ["full", "compact", "csv", "json"],
      "default": "full",
      "description": "Table format type"
    },
    "language": {
      "type": "string",
      "description": "Programming language (optional, auto-detected if not specified)"
    },
    "output_file": {
      "type": "string",
      "description": "Optional filename to save output to file (extension auto-detected based on content)"
    },
    "suppress_output": {
      "type": "boolean",
      "default": false,
      "description": "When true and output_file is specified, suppress table_output in response to save tokens"
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
    "format_type": {
      "type": "string",
      "description": "Format type used for output"
    },
    "metadata": {
      "type": "object",
      "properties": {
        "classes_count": {
          "type": "integer",
          "description": "Number of classes found"
        },
        "methods_count": {
          "type": "integer",
          "description": "Number of methods found"
        },
        "fields_count": {
          "type": "integer",
          "description": "Number of fields found"
        },
        "total_lines": {
          "type": "integer",
          "description": "Total lines in file"
        }
      }
    },
    "table_output": {
      "type": "string",
      "description": "Formatted structure table (may be suppressed when suppress_output=true)"
    },
    "output_file": {
      "type": "string",
      "description": "Path to saved output file if requested"
    }
  }
}
```

## 🔍 Implementation Details

### Core Algorithm

1. **Argument Validation**: Validate required file_path and optional parameters
2. **Path Resolution**: Handle relative paths against project root
3. **Security Validation**: Validate file path against project boundaries
4. **Input Sanitization**: Sanitize all input parameters for security
5. **File Validation**: Check file existence and accessibility
6. **Language Detection**: Auto-detect if not specified
7. **Structure Analysis**: Use AnalysisEngine for comprehensive parsing
8. **Table Formatting**: Apply selected format type
9. **File Output**: Save to external file if requested
10. **Response Assembly**: Format response with optional output suppression

### Key Components

#### Security Validation & Sanitization
```python
# Path validation
is_valid, error_msg = self.security_validator.validate_file_path(resolved_path)
if not is_valid:
    raise ValueError(f"Invalid file path: {error_msg}")

# Input sanitization
format_type = self.security_validator.sanitize_input(format_type, max_length=50)
language = self.security_validator.sanitize_input(language, max_length=50)
output_file = self.security_validator.sanitize_input(output_file, max_length=255)
```

#### Analysis Engine Integration
```python
from ..core.analysis_engine import AnalysisRequest
request = AnalysisRequest(
    file_path=resolved_path,
    language=language,
    include_complexity=True,
    include_details=True,
)
structure_result = await self.analysis_engine.analyze(request)
```

#### Table Formatting
```python
from ..table_formatter import TableFormatter
formatter = TableFormatter(format_type)
structure_dict = self._convert_analysis_result_to_dict(structure_result)
table_output = formatter.format_structure(structure_dict)
```

#### Performance Monitoring
```python
from ..utils.performance_monitor import get_performance_monitor
monitor = get_performance_monitor()
with monitor.measure_operation("code_structure_analysis"):
    # Analysis operations
```

## 📊 Output Formats

### Full Format
```markdown
# package.ClassName

## Info
| Property | Value |
|----------|-------|
| Package | com.example |
| Methods | 8 |
| Fields | 3 |

## Methods
| Method | Sig | V | L | Cx | Doc |
|--------|-----|---|---|----|-----|
| getName | ():String | + | 45-47 | 2 | - |
| setName | (name:String):void | + | 49-52 | 3 | + |

## Fields
| Field | Type | V | L | Doc |
|-------|------|---|---|-----|
| name | String | - | 15 | + |
| id | int | - | 16 | - |
```

### Compact Format
```markdown
# ClassName (8 methods, 3 fields)
- getName():String [45-47]
- setName(name:String):void [49-52]
- name:String [15]
- id:int [16]
```

### CSV Format
```csv
Type,Name,Signature,Visibility,Lines,Complexity,Documentation
Method,getName,():String,public,45-47,2,false
Method,setName,(name:String):void,public,49-52,3,true
Field,name,String,private,15,,true
Field,id,int,private,16,,false
```

### JSON Format
```json
{
  "classes": [
    {
      "name": "ClassName",
      "package": "com.example",
      "methods": [
        {
          "name": "getName",
          "signature": "():String",
          "visibility": "public",
          "lines": "45-47",
          "complexity": 2,
          "documentation": false
        }
      ],
      "fields": [
        {
          "name": "name",
          "type": "String",
          "visibility": "private",
          "line": 15,
          "documentation": true
        }
      ]
    }
  ]
}
```

## 🧪 Testing Coverage

### Test Categories
- **Schema Validation**: Input parameter validation
- **Functionality**: Core structure analysis features
- **Format Types**: All 4 output formats (full, compact, csv, json)
- **File Output**: External file saving functionality
- **Integration**: AnalysisEngine and TableFormatter integration
- **Error Handling**: Invalid paths, missing files, format errors
- **Performance**: Large file handling

### Test Files
- `tests/mcp/test_tools/test_table_format_tool.py` (24 tests)
- Coverage: 100% of core functionality

### Key Test Cases
1. **Tool Schema Structure**: Schema validation
2. **Tool Definition**: MCP tool definition compliance
3. **Execution Success**: Standard functionality test
4. **Different Formats**: All format types validation
5. **File Output**: External file saving
6. **Missing File Path**: Error handling validation
7. **File Not Found**: FileNotFoundError handling
8. **Invalid Arguments**: Comprehensive input validation

## 🚀 Usage Examples

### Basic Usage
```json
{
  "file_path": "src/main/java/Example.java"
}
```

### Advanced Usage with File Output
```json
{
  "file_path": "src/components/App.tsx",
  "format_type": "json",
  "language": "typescript",
  "output_file": "app_structure.json",
  "suppress_output": true
}
```

### Token Optimization for Large Files
```json
{
  "file_path": "large_file.py",
  "format_type": "compact",
  "output_file": "structure_summary.md",
  "suppress_output": true
}
```

### Expected Output
```json
{
  "file_path": "src/main/java/Example.java",
  "language": "java",
  "format_type": "full",
  "metadata": {
    "classes_count": 2,
    "methods_count": 8,
    "fields_count": 5,
    "total_lines": 150
  },
  "table_output": "# com.example.Example\n\n## Info\n| Property | Value |\n...",
  "output_file": null
}
```

## ⚡ Performance Characteristics

### Execution Time
- **Small files** (<1000 lines): <200ms
- **Medium files** (1000-5000 lines): <1s
- **Large files** (>5000 lines): <3s

### Memory Usage
- **Efficient parsing**: Tree-sitter based analysis
- **Table formatting**: Optimized string operations
- **File output**: Stream-based writing for large outputs

### Token Optimization
- **suppress_output**: Reduces response size by 80-95% for large files
- **File output**: Enables analysis of files too large for token limits
- **Format selection**: Compact format reduces output by 60-70%

## 🔒 Security Features

### Project Boundary Protection
- **Path Validation**: Prevents access outside project scope
- **Input Sanitization**: All inputs sanitized with length limits
- **Relative Path Resolution**: Secure handling of relative paths

### Input Validation
- **Type Checking**: Strict type validation for all parameters
- **Length Limits**: Maximum lengths enforced for string inputs
- **Enum Validation**: Format types restricted to allowed values

### Error Handling
- **Graceful Degradation**: Continues analysis on partial failures
- **Detailed Error Messages**: Clear error reporting
- **Security-First**: No sensitive information in error messages

## 🔗 Dependencies

### Internal Dependencies
- `tree_sitter_analyzer.core.analysis_engine.AnalysisEngine`
- `tree_sitter_analyzer.table_formatter.TableFormatter`
- `tree_sitter_analyzer.language_detector.detect_language_from_file`
- `tree_sitter_analyzer.utils.performance_monitor`

### External Dependencies
- `tree-sitter`: Core parsing engine
- `pathlib`: Path manipulation
- `asyncio`: Asynchronous execution

## 📈 Integration Points

### User Story 1 Integration
- **Secondary Tool**: Detailed structure analysis after scale assessment
- **Workflow**: Scale assessment → Structure analysis → Detailed extraction
- **Token Optimization**: suppress_output for large file handling

### MCP Protocol Compliance
- **Tool Registration**: Proper MCP tool schema
- **Error Handling**: MCP-compliant error responses
- **Async Support**: Full asyncio compatibility

### File Output Integration
- **Auto-detection**: File extension based on format type
- **Directory Creation**: Automatic directory creation
- **Path Validation**: Security validation for output paths

## 🎯 Success Criteria

### Functional Requirements
- ✅ **FR-005**: Generate detailed structure documentation tables
- ✅ **FR-006**: Support multiple output formats (full, compact, csv, json)
- ✅ **FR-007**: Provide file output capability for large files
- ✅ **FR-008**: Token optimization through suppress_output feature

### Performance Requirements
- ✅ **NFR-004**: Structure analysis completion within 3 seconds for typical files
- ✅ **NFR-005**: Support files up to 100MB with file output
- ✅ **NFR-006**: Token optimization reduces response size by 80%+

### Quality Requirements
- ✅ **QR-004**: 100% test coverage for core functionality
- ✅ **QR-005**: Comprehensive input validation and sanitization
- ✅ **QR-006**: Security validation for all file operations

## 📝 Notes

### Implementation Status
- **Core Functionality**: ✅ Complete
- **Test Coverage**: ✅ Comprehensive (24 tests)
- **Documentation**: ✅ This specification
- **API Contract**: ✅ OpenAPI specification available

### Token Optimization Features
- **suppress_output**: Critical for large file analysis
- **File output**: Enables analysis beyond token limits
- **Format selection**: Compact format for quick overviews

### Future Enhancements
- **Streaming Output**: Real-time structure analysis for very large files
- **Incremental Analysis**: Update structure tables for file changes
- **Custom Templates**: User-defined output formats
- **Diff Analysis**: Compare structure changes between versions

---

**Last Updated**: 2025-10-12  
**Specification Version**: 1.0.0  
**Implementation Version**: 1.7.5