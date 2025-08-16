## 10 术语与核心概念（Glossary）

- **Tree-sitter**：通用增量解析器框架，提供各语言语法与 AST。
- **Query（TS Query）**：基于 S 表达式的模式匹配语法，用于在 AST 中选择结构节点。
- **Plugin（语言插件）**：封装特定语言的解析与抽取逻辑，并向统一接口输出结构数据。
- **MCP（Model Context Protocol）**：面向 LLM 工具调用的协议，本项目提供 `check_code_scale`、`analyze_code_structure`、`extract_code_section` 等工具。
- **Project Root（项目根边界）**：安全边界，所有路径与读取必须在根内（或显式指定）。
- **Formatter（格式化器）**：将内部结构数据转换为表格/文本/JSON。
- **Strict Type（严格类型）**：mypy 严格模式，要求公开函数和复杂路径都有清晰注解。
- **Quality Gates（质量门槛）**：格式、静态检查、类型检查、测试、覆盖率、LLM 质量检查。




