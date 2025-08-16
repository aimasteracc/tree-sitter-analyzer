## 06 质量工作流（本地与CI一致）

目标：保证任何改动都可被快速验证、可回归、可发布。

### 基本指令

```powershell
# 代码格式与静态检查
uv run black .
uv run isort .
uv run ruff check . --fix

# 类型检查（严格）
uv run mypy tree_sitter_analyzer/

# 测试与覆盖率
uv run pytest -q
uv run pytest --cov=tree_sitter_analyzer --cov-report=html

# LLM 专用检查
uv run python check_quality.py --new-code-only
uv run python llm_code_checker.py --check-all
```

### PR 检查清单（建议模板）

- [ ] 新/改动的公开函数具备完整类型注解与文档字符串
- [ ] 错误处理使用项目自定义异常（参考 `AI_COLLABORATION_GUIDE.md`）
- [ ] 新增/改动代码通过 `mypy` 与 `ruff`
- [ ] 测试覆盖关键路径，新增代码覆盖率 ≥ 90%
- [ ] 运行 `check_quality.py` 与 `llm_code_checker.py`

### 常见质量问题

- 捕获宽泛异常或缺少上下文
- 未按既有数据结构返回导致下游格式化/工具失败
- 忽略项目根边界与路径安全




