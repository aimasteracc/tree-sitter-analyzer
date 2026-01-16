# Implementation Plan

## 🤝 Parallel Development Assignment (Kiro + Roo)

本任务采用并行开发模式，Kiro 和 Roo 各自负责独立的语言支持，无耦合、无依赖。

| Agent | 负责任务 | 说明 |
|-------|---------|------|
| **Kiro (Claude)** | Phase 1, Phase 2 (Go), Phase 5, Phase 6 (README.md, README_zh.md) | 先完成 Go 作为参考实现 |
| **Roo (Gemini)** | Phase 3 (Rust), Phase 4 (Kotlin), Phase 6 (README_ja.md, CHANGELOG.md) | 参考 Go 实现和 java_plugin.py |

### Roo 任务指令

```
请参考以下文件：
- `.kiro/specs/new-language-support/requirements.md` - 需求文档
- `.kiro/specs/new-language-support/design.md` - 设计文档
- `docs/new-language-support-checklist.md` - 实现检查清单
- `tree_sitter_analyzer/languages/java_plugin.py` - 参考实现

你的任务：实现 Rust (Phase 3) 和 Kotlin (Phase 4) 语言支持。
每种语言需要：plugin.py, queries/{lang}.py, formatter.py, 示例文件, 单元测试, golden master。
```

---

## Phase 1: Configuration and Core Setup

- [x] 1. Update pyproject.toml dependencies
  - [x] 1.1 Add tree-sitter-go dependency
    - Add `tree-sitter-go>=0.20.0,<0.25.0` to optional dependencies
    - Add to `systems` and `all-languages` bundles
    - _Requirements: 4.2_

  - [x] 1.2 Add tree-sitter-rust dependency
    - Add `tree-sitter-rust>=0.20.0,<0.25.0` to optional dependencies
    - Add to `systems` and `all-languages` bundles
    - _Requirements: 4.2_

  - [x] 1.3 Add tree-sitter-kotlin dependency
    - Add `tree-sitter-kotlin>=0.3.0` to optional dependencies
    - Add to `all-languages` bundle
    - _Requirements: 4.2_

  - [x] 1.4 Register entry points for new plugins
    - Add go, rust, kotlin to `[project.entry-points."tree_sitter_analyzer.plugins"]`
    - _Requirements: 4.1_

- [x] 2. Checkpoint - Verify dependencies
  - All dependencies and entry points are registered in pyproject.toml

## Phase 2: Go Language Support

- [x] 3. Implement Go plugin
  - [x] 3.1 Create go_plugin.py with GoPlugin class
    - Implement `get_language_name()`, `get_file_extensions()`
    - Implement `create_extractor()`, `get_supported_element_types()`
    - Implement `get_queries()`, `analyze_file()`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 3.2 Implement GoElementExtractor
    - Extract package declarations
    - Extract function and method declarations
    - Extract struct and interface definitions
    - Extract type aliases, const, var declarations
    - Detect goroutine and channel patterns
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [x] 3.3 Create queries/go.py with Tree-sitter queries
    - Define queries for all Go element types
    - _Requirements: 4.3_

  - [x] 3.4 Create go_formatter.py
    - Implement `format_summary()`, `format_structure()`
    - Implement `format_advanced()`, `format_table()`
    - Use Go-specific terminology
    - _Requirements: 1.8_

  - [x] 3.5 Register Go formatter
    - Add to `language_formatter_factory.py`
    - Add to `formatter_config.py` (LANGUAGE_FORMATTER_CONFIG)
    - _Requirements: 4.4, 4.5_

  - [x] 3.6 Create examples/sample.go
    - Include package, functions, methods, structs, interfaces
    - Include type aliases, const, var, goroutines, channels
    - _Requirements: 5.5_

  - [x] 3.7 Create tests/test_go/test_go_plugin.py
    - Test plugin basic functions
    - Test element extraction
    - Test edge cases
    - _Requirements: 5.1_

  - [x] 3.8 Write property test for Go element extraction
    - **Property 1: Go Element Extraction Completeness**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4**
    - Created `tests/test_go/test_go_properties.py`

  - [x] 3.9 Create golden master tests for Go
    - Create `tests/golden_masters/full/go_sample_full.md`
    - Register in `test_golden_master_regression.py`
    - _Requirements: 5.2, 5.3_

  - [x] 3.10 Write property test for Go terminology
    - **Property 7: Go-Specific Terminology**
    - **Validates: Requirements 1.8**
    - Created in `tests/test_go/test_go_properties.py`

- [x] 4. Checkpoint - Verify Go support
  - Ensure all tests pass, ask the user if questions arise.

## Phase 3: Rust Language Support

- [x] 5. Implement Rust plugin
  - [x] 5.1 Create rust_plugin.py with RustPlugin class
    - Implement all required methods
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

  - [x] 5.2 Implement RustElementExtractor
    - Extract mod, fn, struct, enum, trait, impl
    - Extract macro definitions
    - Detect async functions and lifetime annotations
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

  - [x] 5.3 Create queries/rust.py with Tree-sitter queries
    - Define queries for all Rust element types
    - _Requirements: 4.3_

  - [x] 5.4 Create rust_formatter.py
    - Use Rust-specific terminology
    - _Requirements: 2.9_

  - [x] 5.5 Register Rust formatter
    - Add to `language_formatter_factory.py`
    - Add to `formatter_config.py` (LANGUAGE_FORMATTER_CONFIG)
    - _Requirements: 4.4, 4.5_

  - [x] 5.6 Create examples/sample.rs
    - Include all Rust element types
    - _Requirements: 5.5_

  - [x] 5.7 Create tests/test_rust/test_rust_plugin.py
    - _Requirements: 5.1_

  - [x] 5.8 Write property test for Rust element extraction
    - **Property 2: Rust Element Extraction Completeness**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**
    - Already exists in `tests/test_rust/test_rust_properties.py`

  - [x] 5.9 Register Rust golden master in test_golden_master_regression.py
    - Golden master file exists at `tests/golden_masters/full/rust_sample_full.md`
    - Add test cases for full, compact, csv formats
    - _Requirements: 5.2, 5.3_
    - Already registered with full, compact, csv formats

  - [x] 5.10 Write property test for Rust terminology
    - **Property 8: Rust-Specific Terminology**
    - **Validates: Requirements 2.9**
    - Already exists in `tests/test_rust/test_rust_properties.py`

- [x] 6. Checkpoint - Verify Rust support
  - Ensure all tests pass, ask the user if questions arise.

## Phase 4: Kotlin Language Support

- [x] 7. Implement Kotlin plugin
  - [x] 7.1 Create kotlin_plugin.py with KotlinPlugin class
    - Implement all required methods
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [x] 7.2 Implement KotlinElementExtractor
    - Extract package, class, data class, sealed class, object
    - Extract interface, fun, val/var
    - Detect suspend functions and coroutine patterns
    - Extract annotations
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [x] 7.3 Create queries/kotlin.py with Tree-sitter queries
    - Define queries for all Kotlin element types
    - _Requirements: 4.3_

  - [x] 7.4 Create kotlin_formatter.py
    - Use Kotlin-specific terminology
    - _Requirements: 3.8_

  - [x] 7.5 Register Kotlin formatter
    - Add to `language_formatter_factory.py`
    - Add to `formatter_config.py` (LANGUAGE_FORMATTER_CONFIG)
    - _Requirements: 4.4, 4.5_

  - [x] 7.6 Create examples/Sample.kt
    - Include all Kotlin element types
    - _Requirements: 5.5_

  - [x] 7.7 Create tests/test_kotlin/test_kotlin_plugin.py
    - _Requirements: 5.1_

  - [x] 7.8 Write property test for Kotlin element extraction
    - **Property 3: Kotlin Element Extraction Completeness**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
    - Already exists in `tests/test_kotlin/test_kotlin_properties.py`

  - [x] 7.9 Register Kotlin golden master in test_golden_master_regression.py
    - Golden master file exists at `tests/golden_masters/full/kotlin_sample_full.md`
    - Add test cases for full, compact, csv formats
    - _Requirements: 5.2, 5.3_
    - Already registered with full, compact, csv formats

  - [x] 7.10 Write property test for Kotlin terminology
    - **Property 9: Kotlin-Specific Terminology**
    - **Validates: Requirements 3.8**
    - Already exists in `tests/test_kotlin/test_kotlin_properties.py`

- [x] 8. Checkpoint - Verify Kotlin support
  - Ensure all tests pass, ask the user if questions arise.

## Phase 5: Integration and Cross-Language Tests

- [x] 9. Integration tests
  - [x] 9.1 Test language auto-detection
    - Verify .go, .rs, .kt, .kts files are correctly detected
    - _Requirements: 4.6_

  - [x] 9.2 Write property test for language auto-detection
    - **Property 4: Language Auto-Detection**
    - **Validates: Requirements 4.6**
    - Created `tests/integration/test_language_detection_properties.py`

  - [x] 9.3 Test MCP tools with new languages
    - Verify all MCP tools work with Go, Rust, Kotlin
    - _Requirements: 4.7_
    - Verified through golden master tests (analyze_code_structure)

  - [x] 9.4 Test all output formats
    - Verify full, compact, csv formats work for all languages
    - _Requirements: 4.8_

  - [x] 9.5 Write property test for output format consistency
    - **Property 5: Output Format Consistency**
    - **Validates: Requirements 4.8**
    - Created in `tests/integration/test_language_detection_properties.py`

- [x] 10. Checkpoint - Verify integration
  - Ensure all tests pass, ask the user if questions arise.

## Phase 6: Documentation Updates

- [x] 11. Update documentation
  - [x] 11.1 Update README.md language support table
    - Add Go, Rust, Kotlin with feature descriptions
    - _Requirements: 6.1_

  - [x] 11.2 Update README_ja.md language support table
    - Add Go, Rust, Kotlin in Japanese
    - _Requirements: 6.2_
    - Already updated in `README_ja.md`

  - [x] 11.3 Update README_zh.md language support table
    - Add Go, Rust, Kotlin in Chinese
    - _Requirements: 6.3_

  - [x] 11.4 Update CHANGELOG.md
    - Add new feature entry for Go, Rust, Kotlin support
    - _Requirements: 6.4_
    - Already has entry in [Unreleased] section

  - [x] 11.5 Update docs/features.md
    - Add language-specific feature details
    - _Requirements: 6.5_
    - Created `docs/features.md` with comprehensive language feature documentation

- [x] 12. Final Checkpoint - Verify all tests pass
  - Ensure all tests pass, ask the user if questions arise.
