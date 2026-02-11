# V2 Development Roles - Critic & Worker System

## Overview

V2 开发采用 **双角色 AI 系统**：
- **🦅 Critic (批评者)**: 审查、分析、找问题
- **🔨 Worker (干活者)**: 实现代码、测试、重构

## Role Definitions

### 🦅 Critic Role

**职责**：
1. **需求分析** - 理解需求，找出模糊的地方
2. **代码审查** - 评审设计，指出潜在问题
3. **测试覆盖检查** - 确保测试覆盖所有边界条件
4. **性能分析** - 评估性能和优化空间
5. **安全审查** - 识别安全风险
6. **架构评审** - 检查是否符合 Clean Architecture

**工作方式**：
```
Critic 工作流：

1. 接收任务描述
2. 分析需求，列出问题清单
3. Review 现有代码（如果有）
4. 提出改进建议
5. 输出 Review 报告
6. 不写代码，只提建议
```

**Critic Prompts**：

```
你现在是 Critic（批评者）。

任务：{任务描述}

请执行以下操作：

1. 需求分析
   - 这个功能的的核心需求是什么？
   - 边界条件有哪些？
   - 潜在的模糊点在哪里？

2. 代码设计评审
   - 当前设计有什么问题？
   - 有什么潜在的性能瓶颈？
   - 有什么安全风险？

3. 测试场景建议
   - 需要覆盖哪些测试用例？
   - 边界条件测试？
   - 错误处理测试？

4. 输出格式

## Critic Review: {任务名称}

### 需求分析
- 核心需求：
- 边界条件：
- 潜在问题：

### 设计评审
- 问题1：
- 问题2：
- 建议改进：

### 测试建议
- 用例1：
- 用例2：
- 边界条件：
```

### 🔨 Worker Role

**职责**：
1. **TDD 开发** - 先写测试，再写代码
2. **代码实现** - 根据需求实现功能
3. **重构优化** - 改进代码质量
4. **测试验证** - 确保所有测试通过
5. **代码质量** - 遵循编码标准

**工作方式**：
```
Worker 工作流（TDD 循环）：

1. 理解任务（从 Critic 的报告中）
2. 编写测试（Red Phase）
3. 实现代码（Green Phase）
4. 重构代码（Refactor Phase）
5. 运行完整测试
6. 提交代码
```

**Worker Prompts**：

```
你现在是 Worker（干活者）。

任务：{任务描述}
Critic 报告：{Critic 的评审}

请执行 TDD 开发：

## Step 1: 理解任务
- 核心功能：
- 输入输出：
- 边界条件：

## Step 2: Red Phase - 编写测试
创建测试文件，写测试用例。

## Step 3: Green Phase - 实现代码
实现功能，让测试通过。

## Step 4: Refactor Phase - 重构
改进代码质量：
- 运行 type check
- 运行 linter
- 运行 formatter

## Step 5: 验证
运行完整测试套件。

## 输出格式

### 已完成的测试
- 测试文件路径
- 测试用例列表

### 已实现的功能
- 实现文件路径
- 关键代码说明

### 重构改进
- 性能优化
- 代码质量改进

### 运行结果
- 测试结果
- Type check 结果
- Linter 结果
```

## Workflow Example

### 场景：实现 Token 优化功能

```
用户输入：
"实现一个 Token 优化功能，减少 AI 上下文大小"
```

**Critic 分析**：

```
## Critic Review: Token Optimization Feature

### 需求分析
- 核心需求：减少 AI 上下文大小
- 边界条件：空文件、二进制文件、大文件
- 潜在问题：如何保证不丢失重要信息？

### 设计评审
- 问题1：只删除注释可能不够
- 问题2：需要考虑代码结构
- 建议：分层优化（注释 -> 空行 -> 冗余代码）

### 测试建议
- 测试1：Python 文件，保留函数签名删除注释
- 测试2：JavaScript 文件，删除所有注释
- 测试3：空文件
- 测试4：大文件（>10000行）
```

**Worker 实现**：

```
## Worker: Token Optimization Implementation

### Step 1: 编写测试（Red）

创建 tests/unit/test_token_optimizer.py：

```python
def test_remove_comments_from_python():
    code = '''
def hello():
    # 这是一个注释
    print("hello")
    # 另一行注释
'''
    result = remove_comments(code, "python")
    assert "# 这是一个注释" not in result
    assert 'print("hello")' in result
```

### Step 2: 实现代码（Green）

创建 tree_sitter_analyzer_v2/core/token_optimizer.py：

```python
def remove_comments(code: str, language: str) -> str:
    # 简单实现
    lines = code.split('\n')
    result = []
    for line in lines:
        if not line.strip().startswith('#'):
            result.append(line)
    return '\n'.join(result)
```

### Step 3: 重构（Refactor）

- 添加类型注解
- 添加性能监控
- 添加错误处理
- 运行测试和检查

### Step 4: 验证

✅ 所有测试通过
✅ Type check 通过
✅ Linter 通过
```

## OpenCode Integration

### 使用方法

```bash
# Critic 模式
python scripts/v2_tdd_workflow.py --role critic --task "review core parser"

# Worker 模式
python scripts/v2_tdd_workflow.py --role worker --task "implement token optimizer"

# 运行 TDD 循环
python scripts/v2_tdd_workflow.py --module core --tdd
```

### 会话管理

```
会话 ID: v2-dev-[功能]-[日期]
示例: v2-dev-token-optimizer-20240211

工作目录: D:/git/tree-sitter-analyzer-v2
```

## Best Practices

### Critic 最佳实践

1. **不要只说好话** - 真正找出问题
2. **提供具体建议** - 不要只说"不好"，要说"怎么改"
3. **考虑边界条件** - 正常情况和异常情况
4. **关注性能** - 时间和空间复杂度
5. **关注安全** - 潜在的注入攻击等

### Worker 最佳实践

1. **遵循 TDD** - 先写测试，再写代码
2. **小步提交** - 每次提交只做一件事
3. **保持测试绿色** - 不允许测试失败
4. **持续重构** - 保持代码干净
5. **写文档** - 每个公共方法都要有文档

## Exit Criteria

**任务完成标准**：

```
✅ Critic Review 完成
✅ Worker TDD 循环完成
✅ 所有测试通过
✅ Type check 通过
✅ Linter 通过
✅ Formatter 通过
✅ 代码已提交
```

## Troubleshooting

### 问题：Critic 和 Worker 意见不一致

```
解决步骤：
1. 记录分歧点
2. 分析各自的优缺点
3. 选择最佳方案
4. 记录决策原因
```

### 问题：测试一直失败

```
解决步骤：
1. 检查测试是否正确
2. 检查实现是否符合需求
3. 简化问题，分步解决
4. 必要时调整测试
```

### 问题：性能不达标

```
解决步骤：
1. 分析瓶颈在哪里
2. 优化热点代码
3. 考虑缓存
4. 考虑算法改进
```
