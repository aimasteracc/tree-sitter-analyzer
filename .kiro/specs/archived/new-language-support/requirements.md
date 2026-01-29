# Requirements Document

## Introduction

本功能旨在为 Tree-sitter Analyzer 添加 Go、Rust 和 Kotlin 三种热门编程语言的完整支持。这些语言在现代软件开发中广泛使用：Go 用于云原生和微服务开发，Rust 用于系统编程和高性能应用，Kotlin 用于 Android 开发和后端服务。添加这些语言支持将显著扩大项目的用户群体，提升项目的吸引力。

### Language Priority and Rationale

| 语言 | 优先级 | 理由 |
|------|--------|------|
| **Go** | 高 | 云原生生态系统核心语言，Kubernetes、Docker 等项目使用 |
| **Rust** | 高 | 系统编程新星，安全性和性能优势，社区活跃 |
| **Kotlin** | 中 | Android 官方推荐语言，JVM 生态系统重要成员 |

### Existing Plugin Architecture Reference

项目已有成熟的语言插件架构（参考 `docs/new-language-support-checklist.md`），新语言支持应遵循现有模式：

| 组件 | 文件路径 | 必需方法 |
|------|---------|---------|
| 语言插件 | `tree_sitter_analyzer/languages/{language}_plugin.py` | `get_language_name()`, `get_file_extensions()`, `create_extractor()`, `get_supported_element_types()`, `get_queries()`, `analyze_file()` |
| 元素提取器 | 同上（内部类） | 继承 `ElementExtractor` |
| 查询定义 | `tree_sitter_analyzer/queries/{language}.py` | Tree-sitter 查询字符串 |
| 格式化器 | `tree_sitter_analyzer/formatters/{language}_formatter.py` | `format_summary()`, `format_structure()`, `format_advanced()`, `format_table()` |
| 格式化器注册 | `tree_sitter_analyzer/formatters/formatter_registry.py` | 注册新格式化器 |
| 示例文件 | `examples/sample.{ext}` | 覆盖语言主要特性 |
| 单元测试 | `tests/test_{language}/test_{language}_plugin.py` | 插件基本功能测试 |
| Golden Master | `tests/golden_masters/{format}/{language}_sample_full.md` | 输出验证 |
| 属性测试 | `tests/test_{language}/test_{language}_properties.py` | 属性基测试 |

### Reference Implementations

- **Java**: `java_plugin.py` - 最完整的实现
- **Python**: `python_plugin.py` - 简单实现
- **SQL**: `sql_plugin.py` - 专用格式化器
- **YAML**: `yaml_plugin.py` - 异步解析示例

## Glossary

- **Language Plugin**: 实现特定语言解析和元素提取的模块
- **Formatter**: 将解析结果格式化为可读输出的组件
- **Tree-sitter Query**: 用于从 AST 中提取特定模式的查询语言
- **Element Extractor**: 从源代码中提取结构化元素（类、函数、变量等）的组件
- **Golden Master Test**: 使用预期输出文件验证实际输出的测试方法

## Requirements

### Requirement 1: Go Language Support

**User Story:** As a Go developer, I want to analyze Go source code, so that I can understand code structure and navigate large Go projects with AI assistance.

#### Acceptance Criteria

1. WHEN a user analyzes a Go file THEN the system SHALL extract all package declarations with name and line number
2. WHEN a user analyzes a Go file THEN the system SHALL extract all function declarations including name, parameters, return types, and receiver type for methods
3. WHEN a user analyzes a Go file THEN the system SHALL extract all struct definitions with field names and types
4. WHEN a user analyzes a Go file THEN the system SHALL extract all interface definitions with method signatures
5. WHEN a user analyzes a Go file THEN the system SHALL extract all type aliases and type definitions
6. WHEN a user analyzes a Go file THEN the system SHALL extract all const and var declarations
7. WHEN a user analyzes a Go file THEN the system SHALL detect goroutine and channel usage patterns
8. WHEN a user requests table output THEN the system SHALL format Go elements using Go-specific terminology (package, func, struct, interface)

### Requirement 2: Rust Language Support

**User Story:** As a Rust developer, I want to analyze Rust source code, so that I can understand ownership patterns, trait implementations, and module structure.

#### Acceptance Criteria

1. WHEN a user analyzes a Rust file THEN the system SHALL extract all module declarations (mod) with visibility
2. WHEN a user analyzes a Rust file THEN the system SHALL extract all function declarations (fn) including name, parameters, return type, and visibility
3. WHEN a user analyzes a Rust file THEN the system SHALL extract all struct definitions with fields, visibility, and derive macros
4. WHEN a user analyzes a Rust file THEN the system SHALL extract all enum definitions with variants
5. WHEN a user analyzes a Rust file THEN the system SHALL extract all trait definitions with method signatures
6. WHEN a user analyzes a Rust file THEN the system SHALL extract all impl blocks including trait implementations
7. WHEN a user analyzes a Rust file THEN the system SHALL extract all macro definitions (macro_rules!)
8. WHEN a user analyzes a Rust file THEN the system SHALL detect async functions and lifetime annotations
9. WHEN a user requests table output THEN the system SHALL format Rust elements using Rust-specific terminology (mod, fn, struct, enum, trait, impl)

### Requirement 3: Kotlin Language Support

**User Story:** As a Kotlin developer, I want to analyze Kotlin source code, so that I can understand class hierarchies, extension functions, and coroutine usage.

#### Acceptance Criteria

1. WHEN a user analyzes a Kotlin file THEN the system SHALL extract all package declarations
2. WHEN a user analyzes a Kotlin file THEN the system SHALL extract all class declarations including data classes, sealed classes, and object declarations
3. WHEN a user analyzes a Kotlin file THEN the system SHALL extract all function declarations including extension functions with receiver type
4. WHEN a user analyzes a Kotlin file THEN the system SHALL extract all property declarations with val/var distinction
5. WHEN a user analyzes a Kotlin file THEN the system SHALL extract all interface definitions
6. WHEN a user analyzes a Kotlin file THEN the system SHALL detect suspend functions and coroutine patterns
7. WHEN a user analyzes a Kotlin file THEN the system SHALL extract annotations and their parameters
8. WHEN a user requests table output THEN the system SHALL format Kotlin elements using Kotlin-specific terminology (class, data class, object, fun, val, var)

### Requirement 4: Plugin Integration

**User Story:** As a system integrator, I want the new language plugins to integrate seamlessly with existing infrastructure, so that all existing features work with new languages.

#### Acceptance Criteria

1. WHEN a new language plugin is added THEN the system SHALL register it via entry points in pyproject.toml `[project.entry-points."tree_sitter_analyzer.plugins"]`
2. WHEN a new language plugin is added THEN the system SHALL add tree-sitter dependency to pyproject.toml `[project.optional-dependencies]`
3. WHEN a new language plugin is added THEN the system SHALL create query definitions in `tree_sitter_analyzer/queries/{language}.py`
4. WHEN a new language plugin is added THEN the system SHALL register formatter in `formatter_registry.py`
5. WHEN a new language plugin is added THEN the system SHALL add language to `LANGUAGE_FORMATTER_CONFIG` in `table_command.py`
6. WHEN a user uses CLI with new language files THEN the system SHALL auto-detect the language from file extension
7. WHEN a user uses MCP tools with new language files THEN the system SHALL provide the same analysis capabilities as existing languages
8. WHEN a user requests any output format (full, compact, csv) THEN the system SHALL support all formats for new languages

### Requirement 5: Testing and Quality

**User Story:** As a project maintainer, I want comprehensive tests for new language support, so that I can ensure reliability and prevent regressions.

#### Acceptance Criteria

1. WHEN a new language plugin is implemented THEN the system SHALL include unit tests in `tests/test_{language}/test_{language}_plugin.py` covering plugin basic functions, element extraction, and edge cases
2. WHEN a new language plugin is implemented THEN the system SHALL include golden master tests in `tests/golden_masters/full/{language}_sample_full.md`
3. WHEN a new language plugin is implemented THEN the system SHALL register golden master test cases in `tests/test_golden_master_regression.py`
4. WHEN a new language plugin is implemented THEN the system SHALL include property-based tests in `tests/test_{language}/test_{language}_properties.py`
5. WHEN a new language plugin is implemented THEN the system SHALL include example files in `examples/` demonstrating all supported features
6. WHEN tests are run THEN the system SHALL achieve at least 80% code coverage for new language modules
7. WHEN golden master tests are created THEN the system SHALL use `normalize_output()` function to handle environment-dependent differences

### Requirement 6: Documentation

**User Story:** As a user, I want documentation for new language support, so that I can understand available features and usage.

#### Acceptance Criteria

1. WHEN new language support is added THEN the system SHALL update README.md language support table
2. WHEN new language support is added THEN the system SHALL update README_ja.md language support table
3. WHEN new language support is added THEN the system SHALL update README_zh.md language support table
4. WHEN new language support is added THEN the system SHALL update CHANGELOG.md with new feature entry
5. WHEN new language support is added THEN the system SHALL update docs/features.md with language-specific details
6. WHEN new language support is added THEN the system SHALL provide example files in examples/ directory
