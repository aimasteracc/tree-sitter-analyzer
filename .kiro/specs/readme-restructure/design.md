# Design Document: README Restructure

## Overview

本设计文档描述了 Tree-sitter Analyzer 项目 README 重构的技术方案。目标是将当前约 980 行的 README 精简到 500 行以内，同时保持信息的完整性和可访问性。通过创建 docs/ 目录下的详细文档，实现内容分层，让不同用户群体能快速找到所需信息。

## Architecture

### 文档层次结构

```
项目根目录/
├── README.md                    # 精简版（<500行）- 入口点
├── README_ja.md                 # 日语版（结构一致）
├── README_zh.md                 # 中文版（结构一致）
├── CHANGELOG.md                 # 完整版本历史
├── CONTRIBUTING.md              # 贡献指南（更新）
└── docs/
    ├── installation.md          # 详细安装指南
    ├── cli-reference.md         # 完整 CLI 命令参考
    ├── mcp-tools.md             # MCP 工具详细文档
    ├── smart-workflow.md        # SMART 工作流详解
    ├── features.md              # 功能特性详解
    ├── architecture.md          # 项目架构文档
    └── assets/
        └── demo.gif             # 演示动画
```

### README 新结构

```markdown
# 🌳 Tree-sitter Analyzer                    (~20 lines)
[Hero Section: 徽章、一句话价值主张、语言切换]

## ✨ What's New in vX.X                      (~10 lines)
[最新版本亮点，链接到 CHANGELOG.md]

## 🎬 See It In Action                        (~5 lines)
[GIF 动画展示]

## 🚀 5-Minute Quick Start                    (~30 lines)
[最简安装命令，链接到详细安装指南]

## 🤖 AI Integration                          (~50 lines)
[MCP 配置块，验证命令，链接到详细文档]

## 💻 Common CLI Commands                     (~60 lines)
[5个常用命令，可折叠输出，链接到完整参考]

## 🌍 Supported Languages                     (~30 lines)
[语言支持表格，链接到详细特性]

## 📊 Features Overview                       (~40 lines)
[核心功能要点，链接到详细文档]

## 🏆 Quality & Testing                       (~20 lines)
[测试统计徽章，覆盖率]

## 🛠️ Development                             (~30 lines)
[开发环境设置，测试命令]

## 🤝 Contributing & License                  (~20 lines)
[贡献链接，许可证信息]

## 📚 Documentation                           (~15 lines)
[文档目录链接]

总计: ~330 lines (目标 <500 lines)
```

## Components and Interfaces

### 1. Hero Section Component

```markdown
# 🌳 Tree-sitter Analyzer

**English** | **[日本語](README_ja.md)** | **[简体中文](README_zh.md)**

[![Python](badge)][...badges...]

> 🚀 AI 时代的企业级代码分析工具 - 深度 AI 集成 · 多语言支持 · 智能代码分析
```

### 2. Collapsible Output Component

```markdown
<details>
<summary>📋 查看输出示例</summary>

\`\`\`json
{
  "file_path": "example.java",
  "language": "java",
  "metrics": { ... }
}
\`\`\`

</details>
```

### 3. Quick Link Component

```markdown
> 📖 **详细文档**: [安装指南](docs/installation.md) | [CLI 参考](docs/cli-reference.md) | [MCP 工具](docs/mcp-tools.md)
```

## Data Models

### README Section Model

| Section | Max Lines | Required Elements |
|---------|-----------|-------------------|
| Hero | 20 | 项目名、徽章、价值主张、语言切换 |
| What's New | 10 | 版本号、3-5个亮点、CHANGELOG链接 |
| Demo | 5 | GIF 图片、简短说明 |
| Quick Start | 30 | 安装命令、验证命令、详细文档链接 |
| AI Integration | 50 | MCP JSON 配置、验证步骤、文档链接 |
| CLI Commands | 60 | 5个命令、可折叠输出、参考链接 |
| Languages | 30 | 语言表格、支持级别 |
| Features | 40 | 功能要点、文档链接 |
| Quality | 20 | 测试徽章、覆盖率 |
| Development | 30 | 克隆、安装、测试命令 |
| Contributing | 20 | CONTRIBUTING链接、LICENSE |
| Documentation | 15 | docs/目录链接列表 |

### docs/ File Model

| File | Content | Source | Action |
|------|---------|--------|--------|
| installation.md | 完整安装指南（所有平台、所有方式） | README 2.📋 Prerequisites | 新建 |
| cli-reference.md | 完整 CLI 命令参考 | README 6.⚡ Complete CLI Commands | 新建 |
| api/mcp_tools_specification.md | MCP 工具详细文档 | 现有文档 + README 5.🤖 | 更新扩展 |
| smart-workflow.md | SMART 工作流详解 | README 4.📖 Usage Workflow | 新建 |
| features.md | 功能特性详解 | README 7.🛠️ Core Features | 更新扩展 |
| architecture.md | 项目架构文档 | 新建 | 新建 |

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: README Line Count Constraint
*For any* valid README.md file, the total line count SHALL be less than 500 lines.
**Validates: Requirements 6.3**

### Property 2: Hero Section Position
*For any* valid README.md file, the hero section (project name, badges, value proposition) SHALL appear within the first 20 lines.
**Validates: Requirements 1.1**

### Property 3: Section Header Emoji Consistency
*For any* section header in README.md, the header SHALL contain at least one emoji character for visual navigation.
**Validates: Requirements 6.1**

### Property 4: Multi-language README Structure Consistency
*For any* section header in README.md, the same section header (with translated text) SHALL exist in README_ja.md and README_zh.md.
**Validates: Requirements 5.2**

### Property 5: Documentation Links Validity
*For any* link to docs/ directory in README.md, the referenced file SHALL exist in the docs/ directory.
**Validates: Requirements 5.3**

### Property 6: What's New Section Brevity
*For any* "What's New" section in README.md, the section content SHALL be limited to 10 lines or fewer.
**Validates: Requirements 7.3**

### Property 7: CLI Commands Section Completeness
*For any* "Common CLI Commands" section in README.md, the section SHALL contain at least 5 distinct command examples.
**Validates: Requirements 3.1**

### Property 8: AI Integration Section Position
*For any* valid README.md file, the "AI Integration" section SHALL appear within the first 50% of the document's total lines.
**Validates: Requirements 2.1**

## Error Handling

### Missing Documentation Files
- 如果 docs/ 中的文件不存在，README 中的链接应使用相对路径，便于后续创建
- CI/CD 应检查所有文档链接的有效性

### Multi-language Sync Issues
- 使用 section 标记注释帮助维护者同步更新
- CONTRIBUTING.md 明确说明多语言更新责任

### GIF Asset Missing
- 如果 GIF 尚未创建，使用占位符图片或文字说明
- 提供创建 GIF 的工具和步骤说明

## Testing Strategy

### Unit Testing
- 验证 README 行数 < 500
- 验证必需 section 存在
- 验证链接格式正确

### Property-Based Testing
使用 **hypothesis** 库进行属性测试：

1. **Line Count Property Test**: 验证 README 行数约束
2. **Section Structure Property Test**: 验证 section 结构一致性
3. **Link Validity Property Test**: 验证文档链接有效性
4. **Multi-language Consistency Property Test**: 验证多语言结构一致性

### Integration Testing
- 验证所有 docs/ 文件存在且可访问
- 验证 GIF 文件存在且可显示
- 验证多语言 README 结构一致

### Test File Location
```
tests/
└── test_readme/
    ├── test_readme_structure.py      # 结构验证测试
    ├── test_readme_properties.py     # 属性测试
    └── test_docs_links.py            # 文档链接测试
```

### Property Test Annotation Format
每个属性测试必须使用以下格式注释：
```python
# **Feature: readme-restructure, Property 1: README Line Count Constraint**
# **Validates: Requirements 6.3**
```
