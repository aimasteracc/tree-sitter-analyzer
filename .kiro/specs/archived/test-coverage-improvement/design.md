# Design Document: Test Coverage Improvement to 100%

## Overview

本设计文档描述了将 Tree-sitter Analyzer 项目测试覆盖率从 79.06% 提升到 100% 的技术方案。通过系统性地分析覆盖率缺口，设计针对性的测试策略，使用单元测试和属性测试相结合的方法，确保所有代码路径都被验证。

### 目标
- 将测试覆盖率从 79.06% 提升到 100%
- 覆盖所有 3,393 行未测试代码
- 确保所有 88 个需要改进的文件达到 100% 覆盖率
- 使用属性测试验证关键功能的正确性

## Architecture

### 测试架构分层

```
┌─────────────────────────────────────────────────────────────┐
│                    Property-Based Tests                      │
│  (Hypothesis - 验证跨输入范围的通用属性)                      │
├─────────────────────────────────────────────────────────────┤
│                    Integration Tests                         │
│  (组件协作、端到端工作流)                                     │
├─────────────────────────────────────────────────────────────┤
│                      Unit Tests                              │
│  (单个函数、类、模块的测试)                                   │
├─────────────────────────────────────────────────────────────┤
│                    Test Fixtures                             │
│  (测试数据、Mock 对象、辅助函数)                              │
└─────────────────────────────────────────────────────────────┘
```

### 测试文件组织

```
tests/
├── unit/                           # 单元测试
│   ├── test_utils/                 # utils 模块测试
│   │   ├── test_tree_sitter_compat.py
│   │   └── test_utils_init.py
│   ├── test_formatters/            # 格式化器测试
│   │   └── test_java_formatter.py
│   ├── test_mcp/                   # MCP 测试
│   │   ├── test_mcp_server.py
│   │   └── test_universal_analyze_tool.py
│   ├── test_core/                  # 核心引擎测试
│   │   ├── test_engine.py
│   │   └── test_query.py
│   └── test_exceptions.py          # 异常测试
├── integration/                    # 集成测试
│   ├── test_cli_integration.py
│   ├── test_mcp_integration.py
│   └── test_workflow_integration.py
├── property/                       # 属性测试
│   ├── test_serialization_roundtrip.py
│   ├── test_parser_properties.py
│   ├── test_formatter_properties.py
│   └── test_security_properties.py
└── fixtures/                       # 测试数据
    ├── sample_code/
    └── conftest.py
```

## Components and Interfaces

### 1. 测试工具组件

#### TestCoverageAnalyzer
分析当前覆盖率并识别缺口的工具类。

```python
class TestCoverageAnalyzer:
    def analyze_coverage_gaps(self) -> Dict[str, CoverageGap]:
        """分析覆盖率缺口"""
        pass
    
    def get_uncovered_lines(self, file_path: str) -> List[int]:
        """获取未覆盖的行号"""
        pass
    
    def get_uncovered_branches(self, file_path: str) -> List[Tuple[int, int]]:
        """获取未覆盖的分支"""
        pass
```

#### PropertyTestGenerator
生成属性测试输入的策略类。

```python
class PropertyTestGenerator:
    def generate_valid_code(self, language: str) -> str:
        """生成有效的源代码"""
        pass
    
    def generate_analysis_result(self) -> AnalysisResult:
        """生成分析结果"""
        pass
    
    def generate_file_path(self, valid: bool = True) -> str:
        """生成文件路径"""
        pass
```

### 2. 测试覆盖优先级

| 优先级 | 模块 | 当前覆盖率 | 未覆盖行数 | 测试策略 |
|--------|------|-----------|-----------|----------|
| P0 | utils/__init__.py | 22.2% | 45 | 单元测试 + 边界测试 |
| P0 | utils/tree_sitter_compat.py | 34.0% | 92 | 单元测试 + 版本兼容测试 |
| P0 | formatters/java_formatter.py | 39.9% | 91 | 单元测试 + 属性测试 |
| P0 | interfaces/mcp_server.py | 40.8% | 60 | 集成测试 + Mock 测试 |
| P0 | mcp/tools/universal_analyze_tool.py | 44.9% | 82 | 单元测试 + 集成测试 |
| P1 | exceptions.py | 50.4% | 137 | 单元测试 |
| P1 | core/engine.py | 62.3% | 77 | 单元测试 + 属性测试 |
| P1 | core/query.py | 63.4% | 74 | 单元测试 + 属性测试 |
| P2 | languages/markdown_plugin.py | 68.6% | 303 | 属性测试 |
| P2 | languages/typescript_plugin.py | 71.7% | 221 | 属性测试 |

## Data Models

### CoverageGap
```python
@dataclass
class CoverageGap:
    file_path: str
    current_coverage: float
    target_coverage: float
    uncovered_lines: List[int]
    uncovered_branches: List[Tuple[int, int]]
    priority: str  # P0, P1, P2
    estimated_tests_needed: int
```

### TestCase
```python
@dataclass
class TestCase:
    name: str
    target_file: str
    target_lines: List[int]
    test_type: str  # unit, integration, property
    inputs: Dict[str, Any]
    expected_behavior: str
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

Based on the prework analysis, the following correctness properties have been identified:

### Property 1: Serialization Round-Trip Consistency
*For any* valid analysis result object, serializing to JSON and then deserializing SHALL produce an equivalent object.
**Validates: Requirements 2.4, 6.4, 10.3**

### Property 2: Formatter Output Completeness
*For any* valid analysis result with classes, methods, and fields, the formatted output SHALL contain all element names and types.
**Validates: Requirements 2.1, 2.2, 2.3, 10.2**

### Property 3: MCP Request-Response Consistency
*For any* valid MCP tool request, the response SHALL contain either a successful result or a well-formed error response.
**Validates: Requirements 3.1, 3.2, 3.3**

### Property 4: Security Boundary Enforcement
*For any* file path outside the project boundary, the security validator SHALL reject the path with a security error.
**Validates: Requirements 3.4, 10.5**

### Property 5: Exception Context Preservation
*For any* chained exception, the exception chain SHALL preserve all original cause information.
**Validates: Requirements 4.2, 4.3**

### Property 6: Parser Error Recovery
*For any* source code with syntax errors, the parser SHALL return partial results without crashing.
**Validates: Requirements 5.1**

### Property 7: Query Filter Correctness
*For any* query with filter criteria, all returned results SHALL satisfy all filter conditions.
**Validates: Requirements 5.2, 5.4**

### Property 8: Language Plugin Parsing Completeness
*For any* valid source file in a supported language, the plugin SHALL extract all structural elements (classes, functions, imports).
**Validates: Requirements 6.1, 6.2, 6.3, 10.1**

### Property 9: Edge Case Handling
*For any* edge case input (empty, None, special characters), the system SHALL handle it without raising unexpected exceptions.
**Validates: Requirements 1.2, 7.1**

### Property 10: Encoding Fallback Correctness
*For any* file with non-UTF-8 encoding, the system SHALL either successfully decode with fallback encoding or report a clear encoding error.
**Validates: Requirements 7.2**

### Property 11: Cache Consistency
*For any* identical analysis request, the cached result SHALL be equivalent to a fresh analysis result.
**Validates: Requirements 9.4**

### Property 12: CLI Output Format Consistency
*For any* CLI command with a specified output format, the output SHALL conform to that format's specification.
**Validates: Requirements 9.2**

### Property 13: Concurrent Operation Safety
*For any* set of concurrent analysis operations, each operation SHALL complete independently without data corruption.
**Validates: Requirements 7.4**

### Property 14: Tree-sitter Version Compatibility
*For any* tree-sitter API call through the compatibility wrapper, the result SHALL be consistent regardless of the underlying tree-sitter version.
**Validates: Requirements 1.1, 1.4**

## Error Handling

### 测试错误处理策略

1. **测试失败分类**
   - 断言失败：测试逻辑错误或代码 bug
   - 超时失败：性能问题或死锁
   - 环境失败：依赖缺失或配置错误

2. **错误恢复机制**
   - 使用 pytest fixtures 确保测试隔离
   - 使用 mock 避免外部依赖
   - 使用 timeout 防止测试挂起

3. **错误报告**
   - 详细的失败信息
   - 覆盖率差异报告
   - 回归测试结果

## Testing Strategy

### 双重测试方法

本项目采用单元测试和属性测试相结合的方法：

#### 单元测试
- 验证特定示例和边界情况
- 测试错误条件和异常路径
- 测试组件集成点

#### 属性测试
- 使用 **Hypothesis** 库进行属性测试
- 每个属性测试运行至少 **100 次迭代**
- 测试标注格式：`**Feature: test-coverage-improvement, Property {number}: {property_text}**`

### 测试覆盖率目标

| 指标 | 当前值 | 目标值 |
|------|--------|--------|
| 行覆盖率 | 79.06% | 100% |
| 分支覆盖率 | ~75% | 100% |
| 函数覆盖率 | ~80% | 100% |

### 测试执行命令

```bash
# 运行所有测试并生成覆盖率报告
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html --cov-report=term-missing

# 运行属性测试
uv run pytest tests/property/ -v

# 检查覆盖率是否达标
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-fail-under=100
```

### 测试优先级执行顺序

1. **Phase 1 (P0)**: 覆盖率 < 50% 的文件
   - utils/__init__.py
   - utils/tree_sitter_compat.py
   - formatters/java_formatter.py
   - interfaces/mcp_server.py
   - mcp/tools/universal_analyze_tool.py

2. **Phase 2 (P1)**: 覆盖率 50-70% 的文件
   - exceptions.py
   - core/engine.py
   - core/query.py
   - CLI 命令文件

3. **Phase 3 (P2)**: 覆盖率 70-90% 的文件
   - 语言插件
   - 格式化器
   - 安全模块

4. **Phase 4 (P3)**: 覆盖率 90-99% 的文件
   - 完成剩余分支覆盖
   - 边界情况测试
