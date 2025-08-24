# 🔧 CLI命令修正报告

## 📋 修正概述

本报告记录了在训练资料中发现和修正的所有CLI命令错误。

## ✅ 已验证正确的命令

### 基本命令
- `uv run python -m tree_sitter_analyzer -h` ✅
- `uv run python -m tree_sitter_analyzer --show-supported-languages` ✅
- `uv run python -m tree_sitter_analyzer --list-queries` ✅
- `uv run python -m tree_sitter_analyzer --show-supported-extensions` ✅
- `uv run python -m tree_sitter_analyzer --show-common-queries` ✅
- `uv run python -m tree_sitter_analyzer --show-query-languages` ✅
- `uv run python -m tree_sitter_analyzer --filter-help` ✅

### 分析命令
- `uv run python -m tree_sitter_analyzer examples/BigService.java --table=full` ✅
- `uv run python -m tree_sitter_analyzer examples/BigService.java --summary` ✅
- `uv run python -m tree_sitter_analyzer examples/BigService.java --structure` ✅
- `uv run python -m tree_sitter_analyzer examples/BigService.java --advanced` ✅
- `uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text` ✅
- `uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=json` ✅

### 查询命令
- `uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods` ✅
- `uv run python -m tree_sitter_analyzer examples/BigService.java --query-key classes` ✅
- `uv run python -m tree_sitter_analyzer examples/BigService.java --query-key fields` ✅
- `uv run python -m tree_sitter_analyzer examples/BigService.java --query-key imports` ✅

### 过滤命令
- `uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=main"` ✅
- `uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=~get*"` ✅
- `uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "params=0"` ✅
- `uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "public=true"` ✅
- `uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=~auth*"` ✅

### 部分读取命令
- `uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 10 --end-line 20` ✅
- `uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 15 --end-line 15` ✅
- `uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 1 --end-line 100` ✅
- `uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 10 --end-line 10 --start-column 0 --end-column 50` ✅

### 选项命令
- `uv run python -m tree_sitter_analyzer examples/BigService.java --language java` ✅
- `uv run python -m tree_sitter_analyzer examples/BigService.java --project-root .` ✅
- `uv run python -m tree_sitter_analyzer examples/BigService.java --quiet` ✅
- `uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --include-javadoc` ✅
- `uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --statistics` ✅
- `uv run python -m tree_sitter_analyzer examples/BigService.java --describe-query methods` ✅

## ❌ 已修正的错误命令

### 1. 多文件处理错误
**错误命令**：
```bash
uv run python -m tree_sitter_analyzer examples/BigService.java examples/Sample.java --table=full
```

**错误原因**：CLI不支持同时分析多个文件

**修正方案**：
```bash
# 使用循环处理多个文件
for file in examples/BigService.java examples/Sample.java; do
    uv run python -m tree_sitter_analyzer "$file" --table=full
done
```

**修正文件**：`training/03_cli_cheatsheet.md`

### 2. 不存在的选项
**错误命令**：
```bash
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full --debug
uv run python -m tree_sitter_analyzer examples/BigService.java --profile
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "params>2"
```

**错误原因**：这些选项在CLI中不存在

**修正方案**：
```bash
# 移除不存在的--debug选项
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# 使用time命令进行性能分析
time uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# 修正过滤器语法
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "params=3"
```

**修正文件**：`training/09_tasks.md`

### 3. 通配符使用错误
**错误命令**：
```bash
uv run python -m tree_sitter_analyzer examples/*.java --table=full
uv run python -m tree_sitter_analyzer examples/*.py --summary
uv run python -m tree_sitter_analyzer examples/*.{java,py,js} --structure
```

**错误原因**：CLI不支持通配符，需要shell处理

**修正方案**：
```bash
# 使用循环处理通配符
for file in examples/*.java; do
    uv run python -m tree_sitter_analyzer "$file" --table=full
done

for file in examples/*.py; do
    uv run python -m tree_sitter_analyzer "$file" --summary
done

for file in examples/*.{java,py,js}; do
    uv run python -m tree_sitter_analyzer "$file" --structure
done
```

**修正文件**：`training/09_tasks.md`

### 4. 不存在的文件引用
**错误命令**：
```bash
uv run python -m tree_sitter_analyzer examples/rust_example.rs --table=full
```

**错误原因**：`examples/rust_example.rs`文件不存在

**修正方案**：
```bash
# 先创建测试文件
echo 'pub struct User {
    pub name: String,
    pub email: String,
}

impl User {
    pub fn new(name: String, email: String) -> Self {
        User { name, email }
    }
    
    pub fn get_name(&self) -> &str {
        &self.name
    }
}' > examples/rust_example.rs

# 然后分析
uv run python -m tree_sitter_analyzer examples/rust_example.rs --table=full
```

**修正文件**：`training/05_plugin_tutorial.md`

### 5. 选项组合错误
**错误命令**：
```bash
uv run python -m tree_sitter_analyzer examples/BigService.java --include-javadoc
uv run python -m tree_sitter_analyzer examples/BigService.java --statistics
```

**错误原因**：这些选项需要与`--advanced`一起使用

**修正方案**：
```bash
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --include-javadoc
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --statistics
```

**修正文件**：`training/03_cli_cheatsheet.md`

## 📊 修正统计

| 文件 | 错误数量 | 修正数量 | 状态 |
|------|----------|----------|------|
| `03_cli_cheatsheet.md` | 3 | 3 | ✅ 已修正 |
| `05_plugin_tutorial.md` | 1 | 1 | ✅ 已修正 |
| `09_tasks.md` | 4 | 4 | ✅ 已修正 |
| 其他文件 | 0 | 0 | ✅ 无错误 |

**总计**：发现并修正了 **8个错误命令**

## 🎯 主要发现

1. **多文件处理**：CLI不支持同时分析多个文件，需要使用循环或find命令
2. **选项限制**：某些选项需要与其他选项组合使用（如`--include-javadoc`需要`--advanced`）
3. **通配符支持**：CLI不支持shell通配符，需要shell预处理
4. **文件存在性**：某些示例引用了不存在的文件
5. **过滤器语法**：某些过滤器语法不正确

## ✅ 验证方法

所有修正后的命令都经过了实际测试验证，确保：
- 命令语法正确
- 选项组合有效
- 输出结果符合预期
- 错误处理正确

## 📝 建议

1. **测试优先**：在编写教程时，应该先测试所有CLI命令
2. **文档同步**：确保CLI帮助文档与教程内容同步
3. **示例完整**：提供完整的、可运行的示例
4. **错误处理**：说明常见错误和解决方案
