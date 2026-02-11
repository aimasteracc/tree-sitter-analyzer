# Roadmap

> Last updated: 2026-02-11

## Vision

Make tree-sitter-analyzer the **de facto standard** for AI-assisted code analysis.
Every AI coding assistant should use tree-sitter-analyzer for understanding codebases.

## Current Status: v2.0.0-alpha.1

| Metric | Value |
|--------|-------|
| Tests | 903 passing, 4 skipped |
| Coverage | 91% |
| Languages | Python, Java, TypeScript/JavaScript |
| Lint | 0 errors (ruff) |
| Types | 0 errors (mypy) |

## Milestones

### v2.0.0-alpha.2 (Sprint 1) - Project Polish

**Goal**: Make the project presentable to the open source community.

- [x] Update README with accurate stats, badges, and examples
- [x] Create CHANGELOG.md
- [x] Fix CI/CD to install language packages
- [x] Add PR template
- [x] Add runnable examples in `examples/`
- [x] Improve test coverage to 90%+ (achieved: 91%)

### v2.0.0-alpha.3 (Sprint 2) - More Languages

**Goal**: Expand language support from 3 to 8 languages.

- [ ] C/C++ language parser
- [ ] Go language parser
- [ ] Rust language parser
- [ ] C# language parser
- [ ] Kotlin language parser

### v2.0.0-beta.1 (Sprint 3) - MCP Production Ready

**Goal**: MCP server ready for real-world AI assistant usage.

- [ ] MCP server stability and error handling
- [ ] Performance optimization for large codebases (>100K LOC)
- [ ] Rate limiting and resource management
- [ ] MCP tool documentation with real-world examples

### v2.0.0-beta.2 (Sprint 4) - Plugin System

**Goal**: Allow third-party language plugins.

- [ ] Plugin discovery and registration API
- [ ] Plugin development guide
- [ ] Plugin template/scaffolding tool
- [ ] Community plugin repository

### v2.0.0-rc.1 (Sprint 5) - All 17 Languages

**Goal**: Parity with v1 language support.

- [ ] PHP, Ruby, SQL parsers
- [ ] HTML, CSS, YAML, Markdown parsers
- [ ] Migration guide from v1 to v2
- [ ] Performance benchmark suite

### v2.0.0 (Sprint 6) - General Availability

**Goal**: Stable release ready for production use.

- [ ] PyPI package publishing
- [ ] Docker image
- [ ] Comprehensive documentation site
- [ ] VS Code extension (optional)

## Competitive Analysis

| Feature | tree-sitter-analyzer | ast-grep | semgrep |
|---------|---------------------|----------|---------|
| AI-optimized output | **Yes (TOON)** | No | No |
| MCP integration | **Yes** | No | No |
| Token reduction | **50-70%** | N/A | N/A |
| Code graph analysis | **Yes** | No | Limited |
| Language count | 3 (target: 17) | 20+ | 30+ |
| Speed | Fast (fd+rg) | Fast | Moderate |
| PyPI package | Planned | Yes | Yes |

## How to Contribute

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. Priority areas for contribution:

1. **Language plugins** - Add support for new languages
2. **Performance** - Optimize parsing and analysis
3. **Documentation** - Improve docs and examples
4. **Testing** - Increase coverage and add edge case tests
