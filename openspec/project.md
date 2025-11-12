# OpenSpec Project Metadata

**Project Name**: Tree-sitter Analyzer  
**OpenSpec Version**: 1.0  
**Last Updated**: 2025-11-12

---

## Overview

Tree-sitter Analyzer is an AI-era enterprise-grade code analysis tool with comprehensive HTML/CSS support, dynamic plugin architecture, and MCP (Model Context Protocol) integration.

---

## Change Management

This project uses a **two-tier change management approach**:

1. **Strategic Layer (PMP)**: Project-level direction and quality standards
   - Managed through: `docs/ja/project-management/` documents
   - Update frequency: Quarterly / Major changes

2. **Tactical Layer (OpenSpec)**: Individual feature changes and implementation
   - Managed through: `openspec/changes/` directory
   - Update frequency: Continuous (synchronized with development cycle)

For details, see: `docs/ja/project-management/05_変更管理方針.md`

---

## Project Structure

```
tree-sitter-analyzer/
├── openspec/                          # OpenSpec documentation
│   ├── project.md                     # This file
│   └── changes/                       # Individual change proposals
│       └── integrate-v1-6-1-x-releases/  # Example change
│           ├── proposal.md
│           ├── tasks.md
│           └── design.md (optional)
│
├── docs/                              # Project documentation
│   ├── ja/                            # Japanese documentation
│   │   ├── project-management/        # PMP-compliant documents
│   │   └── test-management/           # Test management documents
│   └── ...
│
├── tree_sitter_analyzer/              # Source code
│   ├── mcp/                           # MCP tools and server
│   ├── security/                      # Security validation
│   ├── languages/                     # Language plugins
│   └── ...
│
├── tests/                             # Test suite
└── CHANGELOG.md                       # Version history
```

---

## Quality Standards

### Code Quality
- **Type Safety**: 100% mypy compliance (zero type errors)
- **Test Coverage**: >80% code coverage
- **Test Count**: 3,370+ tests (100% pass rate)
- **Code Style**: Black, Ruff, isort compliant
- **Security**: Bandit security checks passing

### Documentation
- **Multi-language**: English, Japanese, Chinese
- **Completeness**: All features documented
- **Change Tracking**: OpenSpec + CHANGELOG.md

### Development Process
- **GitFlow**: Develop → Release → Main
- **CI/CD**: GitHub Actions (Windows, macOS, Linux)
- **Version Control**: Semantic versioning

---

## Current Status

**Version**: 1.9.3  
**Status**: Active Development  
**Python Support**: 3.10, 3.11, 3.12, 3.13  
**Platforms**: Windows, macOS, Linux

---

## Key Features

### Language Support
- Python, Java, JavaScript, TypeScript
- HTML, CSS, Markdown
- SQL (NEW)
- Extensible plugin architecture

### MCP Integration
- 12 MCP tools for code analysis
- AI assistant integration (Cursor, Claude Desktop, Roo Code)
- Token-efficient search and analysis

### Security
- 7-layer path validation system
- Project boundary management
- ReDoS attack prevention

### Performance
- 15,000 lines/second analysis speed
- Streaming file reading for large files
- Smart caching for repeated operations

---

## Change Workflow

### For OpenSpec Changes

1. **Propose**: Create change proposal in `openspec/changes/<change-id>/`
2. **Design**: Document architecture and technical decisions
3. **Implement**: Code changes with comprehensive tests
4. **Validate**: Run tests, verify quality standards
5. **Document**: Update CHANGELOG.md and related docs
6. **Review**: Get approvals according to PM-005

### For Documentation Changes

1. Direct PR for minor changes (typos, formatting)
2. OpenSpec proposal for major documentation restructuring
3. PMP update for strategic documentation changes

---

## Related Documents

### Project Management
- `docs/ja/project-management/00_プロジェクト憲章.md` (PM-001)
- `docs/ja/project-management/01_スコープ定義書.md` (PM-002)
- `docs/ja/project-management/02_WBS.md` (PM-003)
- `docs/ja/project-management/03_品質管理計画.md` (PM-004)
- `docs/ja/project-management/05_変更管理方針.md` (PM-005)

### Test Management
- `docs/ja/test-management/00_テスト戦略.md` (TEST-001)
- `docs/ja/test-management/01_テストケース一覧.md` (TEST-002)

### Development
- `CHANGELOG.md` - Version history
- `README.md` - Project overview (English)
- `README_ja.md` - Project overview (Japanese)
- `README_zh.md` - Project overview (Chinese)

---

## Contact

**Project Owner**: aisheng.yu  
**Email**: aimasteracc@gmail.com  
**GitHub**: https://github.com/aimasteracc/tree-sitter-analyzer
