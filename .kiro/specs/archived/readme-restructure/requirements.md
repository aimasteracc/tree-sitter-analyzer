# Requirements Document

## Introduction

本功能旨在重构 Tree-sitter Analyzer 项目的 README 文档结构，使其更加简洁、易于导航，并提升新用户的上手体验。当前 README 约 980 行，信息量大但可能让新用户感到压倒。通过重构，将核心信息保留在 README 中，详细文档移至 docs/ 目录，并添加视觉元素（GIF 动画）来展示核心功能。

### Content Migration Strategy

| 当前 README 内容 | 迁移目标 | 说明 |
|-----------------|---------|------|
| Hero Section + 徽章 | 保留在 README | 精简为 20 行以内 |
| 项目特性表格 | docs/features.md | README 保留高层次要点列表 |
| 前置条件安装 | docs/installation.md | README 仅保留一行命令 |
| AI 用户配置 | 保留在 README | 简化为单个配置块 |
| CLI 用户指南 | docs/cli-reference.md | README 保留 5 个常用命令 |
| SMART 工作流详解 | docs/smart-workflow.md | README 保留概念介绍 |
| 完整 MCP 工具列表 | docs/mcp-tools.md | README 保留工具数量统计 |
| 完整 CLI 命令列表 | docs/cli-reference.md | README 链接到详细文档 |
| 核心功能详解 | docs/features.md | README 保留简化表格 |
| What's New 历史版本 | CHANGELOG.md | README 仅保留最新版本 |
| 质量保证 | 保留在 README | 简化为徽章展示 |
| 贡献指南 | CONTRIBUTING.md | README 仅链接 |

### GIF Animation Specification

GIF 动画应展示 **AI 集成场景**（高价值演示）：
- 内容：展示与 AI 助手（Claude/Cursor）使用 SMART 工作流的交互
- 时长：15-30 秒
- 分辨率：800x600 或更高
- 展示步骤：设置项目路径 → 分析文件结构 → 提取代码片段

备选方案（CLI 演示，更易创建）：
- 内容：终端录制，展示分析大文件并生成结构表格
- 工具：使用 asciinema 或 terminalizer 录制

## Glossary

- **README**: 项目根目录的主要文档文件，是用户了解项目的第一入口
- **Quick Start**: 快速入门指南，帮助用户在 5 分钟内开始使用项目
- **SMART Workflow**: Set-Map-Analyze-Retrieve-Trace 的 AI 辅助代码分析工作流
- **MCP**: Model Context Protocol，AI 助手集成协议
- **Hero Section**: README 顶部的核心展示区域，包含项目名称、徽章和核心价值主张
- **Collapsible Section**: 使用 `<details>` 标签创建的可折叠内容区域

## Requirements

### Requirement 1

**User Story:** As a new user, I want to quickly understand what this project does and how to get started, so that I can evaluate if it meets my needs within 2 minutes.

#### Acceptance Criteria

1. WHEN a user opens the README THEN the system SHALL display a concise hero section with project name, badges, and a one-sentence value proposition within the first 20 lines
2. WHEN a user looks for installation instructions THEN the system SHALL provide a "5-minute Quick Start" section with copy-paste commands for the most common use case
3. WHEN a user wants to see the project in action THEN the system SHALL include one GIF animation demonstrating AI integration with SMART workflow or CLI power usage
4. WHEN a user needs detailed documentation THEN the system SHALL provide clear links to the docs/ directory for comprehensive guides

### Requirement 2

**User Story:** As an AI tool user (Claude Desktop, Cursor), I want to find MCP configuration quickly, so that I can integrate the analyzer with my AI assistant immediately.

#### Acceptance Criteria

1. WHEN a user searches for AI integration THEN the system SHALL provide a dedicated "AI Integration" section within the first half of the README
2. WHEN a user needs MCP configuration THEN the system SHALL display a single, copy-paste ready JSON configuration block
3. WHEN a user wants to verify the installation THEN the system SHALL provide a command like `uv run tree-sitter-analyzer --version` and explain that final confirmation happens within the AI tool itself

### Requirement 3

**User Story:** As a CLI user, I want to find command examples quickly, so that I can start analyzing code without reading extensive documentation.

#### Acceptance Criteria

1. WHEN a user looks for CLI usage THEN the system SHALL provide a "Common Commands" section with the 5 most useful commands
2. WHEN a user needs more commands THEN the system SHALL link to a comprehensive CLI reference in docs/cli-reference.md
3. WHEN a user wants to see command output THEN the system SHALL use collapsible `<details>` blocks to show expected output format without cluttering the view

### Requirement 4

**User Story:** As a potential contributor, I want to understand the project structure and how to contribute, so that I can start contributing effectively.

#### Acceptance Criteria

1. WHEN a contributor looks for contribution guidelines THEN the system SHALL provide a clear link to CONTRIBUTING.md
2. WHEN a contributor wants to understand the architecture THEN the system SHALL link to docs/architecture.md
3. WHEN a contributor wants to run tests THEN the system SHALL provide test commands in a "Development" section

### Requirement 5

**User Story:** As a project maintainer, I want the README to be maintainable and consistent across languages, so that updates can be made efficiently.

#### Acceptance Criteria

1. WHEN the README is updated THEN the system SHALL maintain a modular structure that allows easy updates to individual sections
2. WHEN multi-language READMEs exist THEN the system SHALL keep the same structure across README.md, README_ja.md, and README_zh.md
3. WHEN detailed content is moved to docs/ THEN the system SHALL create corresponding files in docs/ directory with proper cross-references
4. WHEN a structural change is made to README.md THEN the CONTRIBUTING.md guide SHALL state that the contributor is responsible for updating the structure of all localized READMEs

### Requirement 6

**User Story:** As a user browsing on mobile or with limited time, I want a scannable README, so that I can find relevant information quickly.

#### Acceptance Criteria

1. WHEN a user scans the README THEN the system SHALL use clear section headers with emoji icons for visual navigation
2. WHEN a user looks at feature lists THEN the system SHALL use concise bullet points with links to detailed docs/features.md
3. WHEN the README is viewed THEN the system SHALL keep the total length under 500 lines by moving detailed content to docs/

### Requirement 7

**User Story:** As a user interested in version history, I want to see what's new without scrolling through extensive changelogs, so that I can quickly understand recent improvements.

#### Acceptance Criteria

1. WHEN a user looks for version information THEN the system SHALL display only the latest version's highlights in the README
2. WHEN a user needs full version history THEN the system SHALL provide a prominent link to CHANGELOG.md
3. WHEN new features are announced THEN the system SHALL use a concise "What's New in vX.X" section limited to 10 lines
