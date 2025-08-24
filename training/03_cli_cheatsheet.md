# ⚡ 03 CLI 大师级速查

> **掌握Tree-sitter Analyzer命令行工具的所有技巧和最佳实践**

![难度](https://img.shields.io/badge/难度-⭐⭐-blue)
![时间](https://img.shields.io/badge/时间-30--60分钟-orange)
![实用](https://img.shields.io/badge/实用-100%25-green)

## 🎯 学习目标

通过本教程，您将：
- ⚡ **掌握基础命令**：熟练使用所有常用CLI命令
- 🔍 **理解高级选项**：掌握查询、过滤和格式化选项
- 🎯 **学会组合使用**：将多个命令组合解决复杂问题
- 📊 **优化输出格式**：选择最适合的输出格式
- 🚀 **提高工作效率**：使用快捷键和别名提升效率

## 📋 命令概览

### 基础命令结构

```bash
uv run python -m tree_sitter_analyzer [文件路径] [选项]
```

### 常用选项分类

| 类别 | 选项 | 用途 |
|------|------|------|
| **输出格式** | `--table`, `--summary`, `--structure` | 控制输出格式 |
| **查询功能** | `--query-key`, `--query-string`, `--filter` | 执行代码查询 |
| **范围控制** | `--partial-read`, `--start-line`, `--end-line` | 控制分析范围 |
| **语言指定** | `--language` | 显式指定编程语言 |
| **安全控制** | `--project-root` | 设置安全边界 |
| **信息显示** | `--list-queries`, `--show-supported-languages` | 显示系统信息 |

## 🔧 基础命令速查

### 1. 帮助和系统信息

```bash
# 查看完整帮助
uv run python -m tree_sitter_analyzer -h

# 列出支持的查询键
uv run python -m tree_sitter_analyzer --list-queries

# 显示支持的语言
uv run python -m tree_sitter_analyzer --show-supported-languages

# 显示支持的扩展名
uv run python -m tree_sitter_analyzer --show-supported-extensions

# 显示通用查询
uv run python -m tree_sitter_analyzer --show-common-queries

# 显示查询语言支持
uv run python -m tree_sitter_analyzer --show-query-languages

# 查看过滤语法帮助
uv run python -m tree_sitter_analyzer --filter-help

# 描述特定查询
uv run python -m tree_sitter_analyzer --describe-query methods
```

### 2. 单文件分析

```bash
# 基础分析（自动检测语言）
uv run python -m tree_sitter_analyzer examples/BigService.java

# 显式指定语言
uv run python -m tree_sitter_analyzer examples/BigService.java --language java

# 静默模式（仅输出结果）
uv run python -m tree_sitter_analyzer examples/BigService.java --quiet

# 包含JavaDoc注释
uv run python -m tree_sitter_analyzer examples/BigService.java --include-javadoc
```

## 📊 输出格式详解

### 1. 表格格式

```bash
# 完整表格（默认）
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# 紧凑表格
uv run python -m tree_sitter_analyzer examples/BigService.java --table=compact

# CSV格式（适合数据处理）
uv run python -m tree_sitter_analyzer examples/BigService.java --table=csv
```

**表格格式对比**：

| 格式 | 适用场景 | 特点 |
|------|----------|------|
| `full` | 详细分析 | 包含所有信息，可读性好 |
| `compact` | 快速浏览 | 简洁，适合大量文件 |
| `csv` | 数据处理 | 结构化，适合脚本处理 |

### 2. JSON格式

```bash
# 摘要JSON
uv run python -m tree_sitter_analyzer examples/BigService.java --summary

# 详细结构JSON
uv run python -m tree_sitter_analyzer examples/BigService.java --structure

# 高级信息JSON
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced

# 统计信息
uv run python -m tree_sitter_analyzer examples/BigService.java --statistics
```

### 3. 文本格式

```bash
# 文本模式
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# JSON格式
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=json
```

## 🔍 查询功能详解

### 1. 预定义查询

```bash
# 查询所有方法
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods

# 查询所有类
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key classes

# 查询所有字段
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key fields

# 查询所有导入
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key imports

# 查询所有函数（Python）
uv run python -m tree_sitter_analyzer examples/sample.py --query-key functions
```

### 2. 自定义查询

```bash
# 查询特定语法结构
uv run python -m tree_sitter_analyzer examples/BigService.java --query-string "(method_declaration name: (identifier) @name)"

# 查询带参数的方法
uv run python -m tree_sitter_analyzer examples/BigService.java --query-string "(method_declaration parameters: (formal_parameters) @params)"

# 查询公开方法
uv run python -m tree_sitter_analyzer examples/BigService.java --query-string "(method_declaration (modifiers) @modifiers)"
```

### 3. 结果过滤

```bash
# 按名称过滤
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=main"

# 按名称模式过滤
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=~get*"

# 按参数数量过滤
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "params=0"

# 按访问修饰符过滤
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "public=true"

# 组合过滤条件
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=~get*,params=0,public=true"
```

## 📍 精确代码提取

### 1. 行范围提取

```bash
# 提取指定行范围
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 10 --end-line 20

# 提取单行
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 15 --end-line 15

# 提取大范围（适合大文件）
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 1 --end-line 100
```

### 2. 列范围提取

```bash
# 提取指定列范围
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 10 --end-line 10 --start-column 0 --end-column 50

# 提取特定区域
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 15 --end-line 25 --start-column 10 --end-column 80
```

## 🌍 多文件处理

### 1. 批量分析

```bash
# 分析多个文件（不支持）
# 注意：CLI不支持同时分析多个文件，需要使用循环或find命令
for file in examples/BigService.java examples/Sample.java; do
    uv run python -m tree_sitter_analyzer "$file" --table=full
done

# 使用通配符（需要shell支持）
for file in examples/*.java; do
    uv run python -m tree_sitter_analyzer "$file" --table=compact
done

# 分析不同语言文件
for file in examples/*.{java,py,js}; do
    uv run python -m tree_sitter_analyzer "$file" --summary
done
```

### 2. 目录分析（使用find命令）

```bash
# 分析整个目录
find examples/ -name "*.java" -exec uv run python -m tree_sitter_analyzer {} --table=full \;

# 递归分析子目录
find . -name "*.java" -exec uv run python -m tree_sitter_analyzer {} --table=compact \;

# 排除特定文件
find examples/ -name "*.java" ! -name "*Test.java" -exec uv run python -m tree_sitter_analyzer {} --table=full \;
```

## 🛡️ 安全和控制

### 1. 项目根设置

```bash
# 设置项目根目录
uv run python -m tree_sitter_analyzer examples/BigService.java --project-root /path/to/project

# 使用当前目录作为项目根
uv run python -m tree_sitter_analyzer examples/BigService.java --project-root .
```

### 2. 语言指定

```bash
# 显式指定Java语言
uv run python -m tree_sitter_analyzer examples/BigService.java --language java

# 显式指定Python语言
uv run python -m tree_sitter_analyzer examples/sample.py --language python

# 显式指定JavaScript语言
uv run python -m tree_sitter_analyzer examples/script.js --language javascript
```

## 🚀 高级技巧

### 1. 命令组合

```bash
# 分析并保存结果到文件
uv run python -m tree_sitter_analyzer examples/BigService.java --structure > analysis.json

# 分析并过滤结果
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "public=true" | grep "main"

# 批量分析并生成报告
for file in examples/*.java; do
    echo "=== $file ==="
    uv run python -m tree_sitter_analyzer "$file" --summary
done > report.txt
```

### 2. 性能优化

```bash
# 使用静默模式减少输出
uv run python -m tree_sitter_analyzer examples/BigService.java --quiet --table=compact

# 批量处理时使用紧凑格式
find examples/ -name "*.java" -exec uv run python -m tree_sitter_analyzer {} --quiet --table=compact \;

# 使用部分读取处理大文件
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 1 --end-line 50
```

### 3. 调试和故障排除

```bash
# 检查文件是否存在
ls -la examples/BigService.java

# 验证语言支持
uv run python -m tree_sitter_analyzer --show-supported-languages

# 检查查询键支持
uv run python -m tree_sitter_analyzer --list-queries

# 测试基本功能
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full
```

## 📝 实用脚本示例

### 1. 代码统计脚本

```bash
#!/bin/bash
# 统计项目中的方法数量

echo "=== 项目代码统计 ==="
echo "文件数量: $(find . -name "*.java" | wc -l)"
echo ""

for file in $(find . -name "*.java"); do
    echo "=== $file ==="
    uv run python -m tree_sitter_analyzer "$file" --summary | grep "methods"
done
```

### 2. 代码质量检查脚本

```bash
#!/bin/bash
# 检查代码质量指标

echo "=== 代码质量检查 ==="

for file in $(find . -name "*.java"); do
    echo "检查: $file"
    
    # 检查方法数量
    method_count=$(uv run python -m tree_sitter_analyzer "$file" --query-key methods --filter "public=true" | wc -l)
    echo "  公开方法数量: $method_count"
    
    # 检查类数量
    class_count=$(uv run python -m tree_sitter_analyzer "$file" --query-key classes | wc -l)
    echo "  类数量: $class_count"
    
    echo ""
done
```

### 3. 代码搜索脚本

```bash
#!/bin/bash
# 搜索特定模式的代码

pattern=$1
if [ -z "$pattern" ]; then
    echo "用法: $0 <搜索模式>"
    exit 1
fi

echo "搜索模式: $pattern"
echo ""

for file in $(find . -name "*.java"); do
    echo "=== $file ==="
    uv run python -m tree_sitter_analyzer "$file" --query-key methods --filter "name=~$pattern"
    echo ""
done
```

## 🎯 最佳实践

### 1. 选择合适的输出格式

- **快速浏览**：使用 `--table=compact`
- **详细分析**：使用 `--table=full`
- **数据处理**：使用 `--table=csv` 或 `--structure`
- **脚本集成**：使用 `--summary` 或 `--structure`

### 2. 优化查询性能

- 使用预定义查询键而不是自定义查询字符串
- 合理使用过滤条件减少结果集
- 对于大文件使用 `--partial-read`
- 批量处理时使用 `--quiet` 模式

### 3. 安全使用

- 始终设置 `--project-root` 防止访问敏感文件
- 使用 `--language` 显式指定语言避免误判
- 在生产环境中使用 `--quiet` 模式

## ✅ 验证学习成果

### 自我评估

- [ ] 我能够使用所有基础CLI命令
- [ ] 我理解不同输出格式的适用场景
- [ ] 我能够使用查询和过滤功能
- [ ] 我能够编写实用的脚本
- [ ] 我了解安全使用的最佳实践

### 实战练习

1. **基础练习**：分析一个Java文件，使用不同的输出格式
2. **查询练习**：查找所有公开的方法
3. **过滤练习**：查找名称包含"get"的方法
4. **脚本练习**：编写一个统计项目代码的脚本
5. **高级练习**：使用自定义查询查找特定语法结构

## 🚀 下一步

继续您的CLI学习之旅：

1. **🔌 [MCP集成专家](04_mcp_cheatsheet.md)** - 学习AI工具集成
2. **🔧 [插件开发实战](05_plugin_tutorial.md)** - 开发自定义插件
3. **✅ [质量保证体系](06_quality_workflow.md)** - 掌握开发工作流

---

**⚡ 恭喜！您已经掌握了CLI工具的高级用法！**

**👉 继续学习：[04 MCP集成专家](04_mcp_cheatsheet.md)**



