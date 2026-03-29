# CI 检查脚本

## 📁 文件说明

### local-ci-check.sh
**完整的本地 CI 检查，推送前运行**

运行所有 CI 检查（Ruff、MyPy、Bandit、Tests）：
```bash
.github/scripts/local-ci-check.sh
```

跳过测试（更快）：
```bash
SKIP_TESTS=1 .github/scripts/local-ci-check.sh
```

### pre-commit-check.sh
**Git pre-commit hook，每次提交前自动运行**

设置：
```bash
# 创建软链接（推荐）
ln -sf ../../.github/scripts/pre-commit-check.sh .git/hooks/pre-commit

# 或者复制文件
cp .github/scripts/pre-commit-check.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

只检查已 staged 的文件，速度快。

## 🚀 快速开始

### 方法 1：手动运行（推送前）
```bash
# 完整检查
.github/scripts/local-ci-check.sh

# 快速检查（跳过测试）
SKIP_TESTS=1 .github/scripts/local-ci-check.sh
```

### 方法 2：自动运行（推荐）
```bash
# 设置 pre-commit hook
ln -sf ../../.github/scripts/pre-commit-check.sh .git/hooks/pre-commit

# 现在每次 git commit 都会自动检查
git commit -m "your message"  # 自动运行检查
```

### 方法 3：手动检查单个文件
```bash
# Ruff + 自动修复
uv run ruff check path/to/file.py --fix

# MyPy 严格检查
uv run mypy path/to/file.py --strict
```

## ✅ 检查项目

| 检查 | 工具 | 说明 |
|------|------|------|
| Linting | Ruff | 代码风格、import 排序、未使用变量等 |
| Type Check | MyPy | 类型注解检查（仅 tree_sitter_analyzer/） |
| Security | Bandit | 安全漏洞扫描 |
| Tests | pytest | 单元测试（可选） |

## 🎯 最佳实践

1. **每次写完代码后**：立即运行 `ruff check --fix`
2. **提交前**：运行完整 CI 检查或使用 pre-commit hook
3. **推送前**：确保本地检查全部通过
4. **推送后**：查看 GitHub Actions 结果

## ⚡ 快捷命令

添加到 `~/.bashrc` 或 `~/.zshrc`：

```bash
# 快速 CI 检查
alias ci="cd /path/to/tree-sitter-analyzer && .github/scripts/local-ci-check.sh"

# 快速检查（跳过测试）
alias ci-fast="cd /path/to/tree-sitter-analyzer && SKIP_TESTS=1 .github/scripts/local-ci-check.sh"

# 检查单个文件
ci-file() {
    uv run ruff check "$1" --fix && \
    uv run mypy "$1" --strict
}
```

## 🔧 故障排除

### Ruff 错误
```bash
# 自动修复大部分问题
uv run ruff check . --fix

# 查看具体错误
uv run ruff check path/to/file.py
```

### MyPy 错误
```bash
# 检查特定文件
uv run mypy path/to/file.py --strict

# 显示详细错误信息
uv run mypy path/to/file.py --strict --show-error-codes
```

### Bandit 警告
Bandit 警告通常是误报。如果确认代码安全，可以添加 `# nosec` 注释：
```python
# nosec B110  # 跳过特定规则
```

## 📚 相关文档

- [AI 编码规则](../../docs/ai-coding-rules.md) - AI 必须遵守的编码规范
- [Ruff 规则](https://docs.astral.sh/ruff/rules/)
- [MyPy 文档](https://mypy.readthedocs.io/)
