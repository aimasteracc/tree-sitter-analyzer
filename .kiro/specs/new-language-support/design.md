# Design Document: Go, Rust, Kotlin Language Support

## Overview

本设计文档描述了为 Tree-sitter Analyzer 添加 Go、Rust 和 Kotlin 三种编程语言支持的技术方案。设计遵循项目现有的插件架构模式，确保与现有基础设施无缝集成。

## Architecture

### 插件架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    Tree-sitter Analyzer                      │
├─────────────────────────────────────────────────────────────┤
│  CLI Interface          │  MCP Interface                     │
├─────────────────────────────────────────────────────────────┤
│                    Plugin Manager                            │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐           │
│  │   Go    │ │  Rust   │ │ Kotlin  │ │ Existing│           │
│  │ Plugin  │ │ Plugin  │ │ Plugin  │ │ Plugins │           │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘           │
│       │           │           │           │                  │
│  ┌────▼────┐ ┌────▼────┐ ┌────▼────┐ ┌────▼────┐           │
│  │   Go    │ │  Rust   │ │ Kotlin  │ │Existing │           │
│  │Extractor│ │Extractor│ │Extractor│ │Extractors│          │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘           │
├─────────────────────────────────────────────────────────────┤
│                   Formatter Registry                         │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐                        │
│  │   Go    │ │  Rust   │ │ Kotlin  │                        │
│  │Formatter│ │Formatter│ │Formatter│                        │
│  └─────────┘ └─────────┘ └─────────┘                        │
├─────────────────────────────────────────────────────────────┤
│                    Tree-sitter Core                          │
│  tree-sitter-go  │  tree-sitter-rust  │  tree-sitter-kotlin │
└─────────────────────────────────────────────────────────────┘
```

### 文件结构

```
tree_sitter_analyzer/
├── languages/
│   ├── go_plugin.py           # Go 语言插件
│   ├── rust_plugin.py         # Rust 语言插件
│   └── kotlin_plugin.py       # Kotlin 语言插件
├── formatters/
│   ├── go_formatter.py        # Go 格式化器
│   ├── rust_formatter.py      # Rust 格式化器
│   └── kotlin_formatter.py    # Kotlin 格式化器
└── queries/
    ├── go.py                  # Go 查询定义
    ├── rust.py                # Rust 查询定义
    └── kotlin.py              # Kotlin 查询定义

examples/
├── sample.go                  # Go 示例文件
├── sample.rs                  # Rust 示例文件
└── Sample.kt                  # Kotlin 示例文件

tests/
├── test_go/
│   ├── test_go_plugin.py
│   ├── test_go_properties.py
│   └── test_go_golden_master.py
├── test_rust/
│   ├── test_rust_plugin.py
│   ├── test_rust_properties.py
│   └── test_rust_golden_master.py
├── test_kotlin/
│   ├── test_kotlin_plugin.py
│   ├── test_kotlin_properties.py
│   └── test_kotlin_golden_master.py
└── golden_masters/
    └── full/
        ├── go_sample_full.md
        ├── rust_sample_full.md
        └── kotlin_sample_full.md
```

## Components and Interfaces

### 1. Go Plugin Component

```python
class GoPlugin(LanguagePlugin):
    """Go 语言插件实现"""
    
    def get_language_name(self) -> str:
        return "go"
    
    def get_file_extensions(self) -> list[str]:
        return [".go"]
    
    def create_extractor(self) -> GoElementExtractor:
        return GoElementExtractor()
    
    def get_supported_element_types(self) -> list[str]:
        return ["package", "function", "method", "struct", "interface", 
                "type_alias", "const", "var"]
    
    def get_queries(self) -> dict[str, str]:
        return GO_QUERIES
    
    async def analyze_file(self, file_path: str) -> AnalysisResult:
        # 实现文件分析逻辑
        pass
```

### 2. Rust Plugin Component

```python
class RustPlugin(LanguagePlugin):
    """Rust 语言插件实现"""
    
    def get_language_name(self) -> str:
        return "rust"
    
    def get_file_extensions(self) -> list[str]:
        return [".rs"]
    
    def get_supported_element_types(self) -> list[str]:
        return ["mod", "fn", "struct", "enum", "trait", "impl", 
                "macro", "const", "static", "type_alias"]
```

### 3. Kotlin Plugin Component

```python
class KotlinPlugin(LanguagePlugin):
    """Kotlin 语言插件实现"""
    
    def get_language_name(self) -> str:
        return "kotlin"
    
    def get_file_extensions(self) -> list[str]:
        return [".kt", ".kts"]
    
    def get_supported_element_types(self) -> list[str]:
        return ["package", "class", "data_class", "sealed_class", "object",
                "interface", "fun", "val", "var", "annotation"]
```

## Data Models

### Go Element Types

| Element Type | AST Node | Extracted Metadata |
|-------------|----------|-------------------|
| package | package_clause | name, line |
| function | function_declaration | name, params, return_type, line, visibility |
| method | method_declaration | name, receiver, params, return_type, line |
| struct | type_declaration (struct_type) | name, fields, line |
| interface | type_declaration (interface_type) | name, methods, line |
| type_alias | type_declaration | name, underlying_type, line |
| const | const_declaration | name, type, value, line |
| var | var_declaration | name, type, line |

### Rust Element Types

| Element Type | AST Node | Extracted Metadata |
|-------------|----------|-------------------|
| mod | mod_item | name, visibility, line |
| fn | function_item | name, params, return_type, visibility, async, line |
| struct | struct_item | name, fields, visibility, derives, line |
| enum | enum_item | name, variants, visibility, line |
| trait | trait_item | name, methods, visibility, line |
| impl | impl_item | type, trait, methods, line |
| macro | macro_definition | name, line |

### Kotlin Element Types

| Element Type | AST Node | Extracted Metadata |
|-------------|----------|-------------------|
| package | package_header | name, line |
| class | class_declaration | name, modifiers, superclass, interfaces, line |
| data_class | class_declaration (data) | name, properties, line |
| sealed_class | class_declaration (sealed) | name, subclasses, line |
| object | object_declaration | name, line |
| interface | class_declaration (interface) | name, methods, line |
| fun | function_declaration | name, params, return_type, receiver, suspend, line |
| val/var | property_declaration | name, type, mutable, line |

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Go Element Extraction Completeness
*For any* valid Go source file, all declared packages, functions, methods, structs, and interfaces SHALL be extracted with correct names and line numbers.
**Validates: Requirements 1.1, 1.2, 1.3, 1.4**

### Property 2: Rust Element Extraction Completeness
*For any* valid Rust source file, all declared modules, functions, structs, enums, traits, and impl blocks SHALL be extracted with correct metadata.
**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**

### Property 3: Kotlin Element Extraction Completeness
*For any* valid Kotlin source file, all declared packages, classes, functions, and properties SHALL be extracted with correct metadata.
**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

### Property 4: Language Auto-Detection
*For any* file with extension .go, .rs, .kt, or .kts, the system SHALL correctly detect and use the corresponding language plugin.
**Validates: Requirements 4.6**

### Property 5: Output Format Consistency
*For any* supported language and output format (full, compact, csv), the system SHALL produce valid, parseable output.
**Validates: Requirements 4.8**

### Property 6: Golden Master Stability
*For any* example file, the analysis output SHALL match the golden master file after normalization.
**Validates: Requirements 5.2**

### Property 7: Go-Specific Terminology
*For any* Go analysis output in table format, the output SHALL use Go-specific terminology (package, func, struct, interface).
**Validates: Requirements 1.8**

### Property 8: Rust-Specific Terminology
*For any* Rust analysis output in table format, the output SHALL use Rust-specific terminology (mod, fn, struct, enum, trait, impl).
**Validates: Requirements 2.9**

### Property 9: Kotlin-Specific Terminology
*For any* Kotlin analysis output in table format, the output SHALL use Kotlin-specific terminology (class, data class, object, fun, val, var).
**Validates: Requirements 3.8**

## Error Handling

### Parser Not Installed
```python
try:
    import tree_sitter_go
except ImportError:
    raise LanguageNotAvailableError(
        "Go language support requires tree-sitter-go. "
        "Install with: uv add tree-sitter-go"
    )
```

### Invalid Source File
- 返回空元素列表而非抛出异常
- 在结果中包含解析错误信息

### Encoding Issues
- 使用 chardet 检测文件编码
- 支持 UTF-8、UTF-16、Latin-1 等常见编码

## Testing Strategy

### Unit Testing
- 每个插件的基本功能测试
- 元素提取测试（各种语言构造）
- 边缘情况测试（空文件、语法错误等）

### Property-Based Testing
使用 **hypothesis** 库进行属性测试：

1. **Element Extraction Property**: 验证所有声明的元素都被提取
2. **Line Number Accuracy Property**: 验证行号准确性
3. **Output Format Property**: 验证输出格式一致性

### Golden Master Testing
- 使用 `normalize_output()` 处理环境差异
- 每种语言至少一个 golden master 文件
- 覆盖 full、compact、csv 三种格式

### Test File Structure
```
tests/test_{language}/
├── test_{language}_plugin.py           # 单元测试
├── test_{language}_properties.py       # 属性测试
└── test_{language}_golden_master.py    # Golden Master 测试
```

### Property Test Annotation Format
```python
# **Feature: new-language-support, Property 1: Go Element Extraction Completeness**
# **Validates: Requirements 1.1, 1.2, 1.3, 1.4**
@given(go_source_code())
def test_go_element_extraction_completeness(source: str):
    ...
```

## Dependencies

### Tree-sitter Parsers

| Language | Package | Version |
|----------|---------|---------|
| Go | tree-sitter-go | >=0.20.0,<0.25.0 |
| Rust | tree-sitter-rust | >=0.20.0,<0.25.0 |
| Kotlin | tree-sitter-kotlin | >=0.3.0 |

### pyproject.toml Updates

```toml
[project.optional-dependencies]
go = ["tree-sitter-go>=0.20.0,<0.25.0"]
rust = ["tree-sitter-rust>=0.20.0,<0.25.0"]
kotlin = ["tree-sitter-kotlin>=0.3.0"]

[project.entry-points."tree_sitter_analyzer.plugins"]
go = "tree_sitter_analyzer.languages.go_plugin:GoPlugin"
rust = "tree_sitter_analyzer.languages.rust_plugin:RustPlugin"
kotlin = "tree_sitter_analyzer.languages.kotlin_plugin:KotlinPlugin"
```
