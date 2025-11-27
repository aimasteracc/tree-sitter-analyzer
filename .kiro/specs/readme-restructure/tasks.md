# Implementation Plan

## 📋 Task Assignment

本任务由 **Kiro (Claude)** 独立完成。

### 执行顺序
1. Phase 1: 创建 docs/ 文档基础设施
2. Phase 2: 重构 README.md
3. Phase 3: 验证和测试
4. Phase 4: 更新多语言 README

### 参考文件
- `docs/new-language-support-checklist.md` - 现有文档结构参考
- 现有 README.md 内容作为迁移源

---

## Phase 1: Create Documentation Infrastructure

- [ ] 1. Set up docs/ directory structure
  - [ ] 1.1 Create docs/ directory with required subdirectories
    - Create `docs/` folder
    - Create `docs/assets/` folder for GIF and images
    - _Requirements: 1.4, 5.3_

  - [ ] 1.2 Create installation.md with detailed installation guide
    - Migrate content from README Prerequisites section
    - Include all platform-specific instructions (macOS, Windows, Linux)
    - Include uv, fd, ripgrep installation details
    - _Requirements: 1.2, 5.3_

  - [ ] 1.3 Create cli-reference.md with complete CLI documentation
    - Migrate all CLI commands from README
    - Include all query, filter, and search commands
    - Add output examples for each command
    - _Requirements: 3.2, 5.3_

  - [ ] 1.4 Create mcp-tools.md with MCP tool documentation
    - Migrate MCP tool list from README
    - Include detailed parameter descriptions
    - Add usage examples for each tool
    - _Requirements: 2.1, 5.3_

  - [ ] 1.5 Create smart-workflow.md with SMART workflow guide
    - Migrate SMART workflow content from README
    - Include step-by-step examples
    - Add best practices section
    - _Requirements: 1.4, 5.3_

  - [ ] 1.6 Create features.md with detailed feature documentation
    - Migrate feature tables from README
    - Include language-specific feature details
    - Add comparison tables
    - _Requirements: 6.2, 5.3_

  - [ ] 1.7 Create architecture.md with project architecture
    - Document plugin architecture
    - Document MCP integration architecture
    - Include component diagrams
    - _Requirements: 4.2, 5.3_

- [ ] 2. Checkpoint - Verify docs/ structure
  - Ensure all tests pass, ask the user if questions arise.

## Phase 2: Restructure README.md

- [ ] 3. Create new README.md structure
  - [ ] 3.1 Create Hero Section (lines 1-20)
    - Project name with emoji
    - Language switcher links
    - Badge row (Python, License, Tests, Coverage, PyPI, Version, Stars)
    - One-sentence value proposition
    - _Requirements: 1.1, 6.1_

  - [ ]* 3.2 Write property test for Hero Section position
    - **Property 2: Hero Section Position**
    - **Validates: Requirements 1.1**

  - [ ] 3.3 Create What's New section (max 10 lines)
    - Latest version highlights only
    - Link to CHANGELOG.md for full history
    - _Requirements: 7.1, 7.2, 7.3_

  - [ ]* 3.4 Write property test for What's New brevity
    - **Property 6: What's New Section Brevity**
    - **Validates: Requirements 7.3**

  - [ ] 3.5 Create Demo section with GIF placeholder
    - Add placeholder for demo.gif
    - Include brief description
    - _Requirements: 1.3_

  - [ ] 3.6 Create 5-Minute Quick Start section
    - Single installation command
    - Verification command
    - Link to docs/installation.md
    - _Requirements: 1.2_

  - [ ] 3.7 Create AI Integration section
    - Single MCP JSON configuration block
    - Verification command (`uv run tree-sitter-analyzer --version`)
    - Link to docs/mcp-tools.md
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ]* 3.8 Write property test for AI Integration position
    - **Property 8: AI Integration Section Position**
    - **Validates: Requirements 2.1**

  - [ ] 3.9 Create Common CLI Commands section
    - 5 most useful commands with collapsible output
    - Link to docs/cli-reference.md
    - _Requirements: 3.1, 3.2, 3.3_

  - [ ]* 3.10 Write property test for CLI Commands completeness
    - **Property 7: CLI Commands Section Completeness**
    - **Validates: Requirements 3.1**

  - [ ] 3.11 Create Supported Languages section
    - Concise language support table
    - Link to docs/features.md
    - _Requirements: 6.2_

  - [ ] 3.12 Create Features Overview section
    - Bullet points with key features
    - Links to detailed documentation
    - _Requirements: 6.2_

  - [ ] 3.13 Create Quality & Testing section
    - Test count badge
    - Coverage badge
    - Brief quality statement
    - _Requirements: 1.1_

  - [ ] 3.14 Create Development section
    - Clone, install, test commands
    - Link to CONTRIBUTING.md
    - _Requirements: 4.1, 4.3_

  - [ ] 3.15 Create Contributing & License section
    - Link to CONTRIBUTING.md
    - License information
    - _Requirements: 4.1_

  - [ ] 3.16 Create Documentation section
    - Links to all docs/ files
    - _Requirements: 1.4_

- [ ] 4. Checkpoint - Verify README structure
  - Ensure all tests pass, ask the user if questions arise.

## Phase 3: Validate and Test

- [ ] 5. Implement validation tests
  - [ ] 5.1 Create test_readme_structure.py
    - Test README line count < 500
    - Test required sections exist
    - Test section order
    - _Requirements: 6.3_

  - [ ]* 5.2 Write property test for README line count
    - **Property 1: README Line Count Constraint**
    - **Validates: Requirements 6.3**

  - [ ]* 5.3 Write property test for section header emoji
    - **Property 3: Section Header Emoji Consistency**
    - **Validates: Requirements 6.1**

  - [ ] 5.4 Create test_docs_links.py
    - Test all docs/ links are valid
    - Test referenced files exist
    - _Requirements: 5.3_

  - [ ]* 5.5 Write property test for documentation links validity
    - **Property 5: Documentation Links Validity**
    - **Validates: Requirements 5.3**

- [ ] 6. Checkpoint - Verify all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Phase 4: Multi-language README Updates

- [ ] 7. Update localized READMEs
  - [ ] 7.1 Update README_ja.md with same structure
    - Apply same section structure as README.md
    - Translate new sections to Japanese
    - Update links to docs/
    - _Requirements: 5.2_

  - [ ] 7.2 Update README_zh.md with same structure
    - Apply same section structure as README.md
    - Translate new sections to Chinese
    - Update links to docs/
    - _Requirements: 5.2_

  - [ ]* 7.3 Write property test for multi-language consistency
    - **Property 4: Multi-language README Structure Consistency**
    - **Validates: Requirements 5.2**

- [ ] 8. Update CONTRIBUTING.md
  - [ ] 8.1 Add multi-language README update responsibility
    - Add section about updating all localized READMEs
    - Include checklist for README changes
    - _Requirements: 5.4_

- [ ] 9. Final Checkpoint - Verify all tests pass
  - Ensure all tests pass, ask the user if questions arise.
