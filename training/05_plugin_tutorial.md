## 05 新增语言插件最小闭环教程

目标：在不破坏现有架构的情况下，为新语言接入最小可用的结构分析（类/函数/导入），并通过测试与质量门槛。

### 1. 了解插件注册

- 入口：`pyproject.toml` → `[project.entry-points."tree_sitter_analyzer.plugins"]`
- 现有示例：`languages/java_plugin.py`、`languages/python_plugin.py`、`languages/javascript_plugin.py`

### 2. 最小实现步骤

1) 安装对应 tree-sitter 语言包（在 `pyproject.toml` 可选依赖中添加或直接安装）
2) 在 `tree_sitter_analyzer/languages/` 新建 `{lang}_plugin.py`
3) 仿照现有插件：
   - 初始化 parser（绑定语法）
   - 实现结构抽取（函数/类/导入）
   - 提供统一的数据模型给 `table_formatter` 与 CLI/MCP
4) 在 `pyproject.toml` 注册 entry point
5) 补充 `queries/{lang}.py`（如需）

### 3. 最小模板（伪代码）

```python
from tree_sitter_analyzer.plugins.base import BaseLanguagePlugin
from tree_sitter import Language, Parser

class NewLangPlugin(BaseLanguagePlugin):
    key = "newlang"
    extensions = [".nl"]

    def __init__(self) -> None:
        self.parser = Parser()
        # 绑定语法（示例）
        # self.parser.set_language(Language("build/my-languages.so", "newlang"))

    def analyze(self, code: str, file_path: str) -> dict:
        # 解析 → 构建抽象结构 → 返回统一字典
        return {
            "language": self.key,
            "summary": {"classes": 0, "methods": 0, "fields": 0},
            "elements": {"classes": [], "methods": [], "fields": []},
        }
```

### 4. 本地验证

```powershell
uv run python -m tree_sitter_analyzer examples/Sample.newlang --table=full
```

### 5. 质量门槛

```powershell
uv run black . && uv run isort . && uv run ruff check . --fix
uv run mypy tree_sitter_analyzer/
uv run pytest -q
```

### 6. 常见陷阱

- 返回数据结构字段缺失导致 `table_formatter` 报错
- 未正确注册 entry point 导致插件不可见
- 类型注解缺失触发 mypy 严格模式失败




