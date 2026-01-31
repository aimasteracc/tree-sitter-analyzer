# Tree-sitter Analyzer v2.0 - Requirements Document

**Version**: 2.0
**Date**: 2026-01-31
**Status**: Draft - Requirements Gathering
**Author**: tree-sitter-analyzer team

---

## ⚠️ CRITICAL UPDATES (2026-01-31)

Based on user feedback, the following requirements supersede earlier drafts:

### 🔧 **Core Functionality Changes**
1. **PRESERVE fd + ripgrep Integration**: File and content search using fd and ripgrep must be retained from v1
   - fd for file discovery (10-20x faster than Python glob)
   - ripgrep for content search (5-10x faster than Python regex)
   - Critical for AI assistants analyzing large codebases

2. **OUTPUT FORMATS - TOON + Markdown ONLY**:
   - ✅ **TOON**: Token-optimized format (50-70% reduction) - PRIMARY for MCP tools
   - ✅ **Markdown**: Human-readable format - PRIMARY for CLI output
   - ❌ **JSON**: REMOVED (bloated, not needed)
   - Rationale: Two formats are sufficient; avoid over-engineering

3. **DUAL INTERFACE REQUIREMENT**:
   - ✅ **CLI**: For testing, debugging, human interaction
   - ✅ **Python API**: For Agent Skills, programmatic use, integration
   - ✅ **MCP Server**: For AI assistant integration (Claude Desktop, Cursor, etc.)

### 🎯 **Success Criteria Updated**
- Can fully replace v1.9.17.1 in production
- All v1 fd/rg functionality preserved
- TOON format 70-80% token reduction (improved from v1's 50-70%)
- Markdown output complete and human-readable
- CLI + API + MCP all production-ready

---

## Executive Summary

Tree-sitter Analyzer v2.0 represents a complete architectural rewrite focused on **AI-first design principles**, optimizing for token efficiency, response speed, and developer experience in AI-assisted workflows. This rewrite addresses fundamental limitations of v1.x and positions the tool as the **premier code analysis MCP server** for 2026 and beyond.

### Strategic Vision
- **Primary Users**: AI assistants (Claude, GPT, Cursor, etc.) as first-class citizens
- **Core Mission**: Enable AI assistants to understand code structure with minimal token overhead
- **Market Position**: The fastest, most token-efficient code analysis MCP server available
- **Production Goal**: Replace v1.9.17.1 with cleaner, simpler, faster v2.0

---

## 1. Market Analysis & Competitive Landscape

### 1.1 Best-in-Class MCP Servers (2026)

Based on research from [awesome-mcp-servers](https://github.com/wong2/awesome-mcp-servers) and [MCP Servers](https://mcpservers.org/), the leading MCP servers demonstrate:

#### **Sequential Thinking** (5,550+ uses)
- Dynamic problem-solving through thought sequences
- Real-time guidance generation
- **Lesson**: AI assistants value contextual guidance over raw data

#### **wcgw** (4,920+ uses)
- Shell and coding agent integration
- Direct execution capabilities
- **Lesson**: Execution + analysis = powerful combination

#### **Official Reference Servers**
- **Filesystem**: Secure file operations with configurable access controls
- **Git**: Read, search, and manipulate Git repositories
- **Memory**: Knowledge graph-based persistent memory
- **Lesson**: Security validation and boundary protection are critical

### 1.2 Competitive Code Analysis Tools

#### **wrale/mcp-server-tree-sitter**
- Provides AST-based code understanding
- Flexible code exploration at multiple granularities
- **Gap**: No token optimization, limited to basic tree-sitter queries

#### **code-to-tree**
- Syntactic analysis for LLMs
- 100% local execution
- **Gap**: Lacks semantic analysis, no filtering capabilities

#### **Traditional LSP Servers**
- Semantic analysis (types, scopes, cross-file references)
- **Limitations**:
  - Response time: 50-100ms+ latency ([source](https://lambdaland.org/posts/2026-01-21_tree-sitter_vs_lsp/))
  - Requires project-wide indexing
  - Not optimized for AI token windows

### 1.3 Tree-sitter Analyzer v1.x Strengths & Weaknesses

#### ✅ **Strengths**
- **17 language support**: Comprehensive coverage
- **TOON format**: 50-70% token reduction ([MCP Tools Spec](https://medium.com/@pierreyohann16/optimizing-token-efficiency-in-claude-code-workflows-managing-large-model-context-protocol-f41eafdab423))
- **8,405 tests**: Excellent quality baseline
- **Batch operations**: Efficient multi-file analysis
- **Security**: Project boundary protection

#### ❌ **Weaknesses**
- **Monolithic architecture**: Hard to extend
- **Inconsistent APIs**: 8 tools with different patterns
- **No streaming**: Large files consume entire context window
- **Limited filtering**: Basic name/type filters only
- **No incremental updates**: Full re-parse on every change
- **Missing features**: No AST navigation, no symbol search

### 1.4 Market Gaps We Can Fill

1. **Token-optimized streaming**: Deliver code structure incrementally
2. **Semantic filtering**: Filter by complexity, dependencies, annotations
3. **Cross-file analysis**: Import tracking, dependency graphs
4. **AI-guided workflows**: Built-in analysis strategies for different file sizes
5. **Hybrid approach**: Tree-sitter speed + LSP-like intelligence

---

## 2. User Personas & Use Cases

### 2.1 Primary Persona: AI Assistants (Claude, GPT, Cursor)

**Context Window Constraints (2026)**:
- Claude Opus 4.5: 1M tokens ([source](https://www.glbgpt.com/hub/claude-ai-pricing-2026-the-ultimate-guide-to-plans-api-costs-and-limits/))
- Claude Sonnet 4.5: 200K tokens
- GPT-5.2 Codex: 128K tokens

**Cost Sensitivity**:
- Average: $6/developer/day ([source](https://labs.adaline.ai/p/claude-code-vs-openai-codex))
- Token optimization = 50-70% cost reduction via caching ([source](https://www.glbgpt.com/hub/claude-ai-pricing-2026-the-ultimate-guide-to-plans-api-costs-and-limits/))

**Primary Needs**:
1. **Fast triage**: "Is this file too large to analyze fully?" (<1s response)
2. **Targeted extraction**: "Show me only public methods" (minimal tokens)
3. **Progressive disclosure**: "Start with summary, drill down on demand"
4. **Smart caching**: Reuse parsed results across queries

### 2.2 Secondary Persona: Human Developers

**Workflow Integration**:
- Pre-commit hooks for quality checks
- CI/CD pipeline analysis
- Code review automation
- Documentation generation

**Primary Needs**:
1. **Fast feedback**: <3s for most operations
2. **Actionable insights**: Complexity hotspots, refactoring candidates
3. **IDE integration**: LSP-compatible output
4. **Batch processing**: Analyze entire projects

---

## 3. Functional Requirements

### 3.1 MUST-HAVE Features (MVP)

#### **FR-1: Core Analysis Engine**
- **FR-1.1**: Support 17 languages (maintain v1.x parity)
- **FR-1.2**: Parse files <100ms for files <10KB
- **FR-1.3**: Incremental parsing for file changes
- **FR-1.4**: Parallel processing for batch operations

#### **FR-2: MCP Tools (Redesigned)**
- **FR-2.1**: `check_code_scale` - File metrics in <1s (KEEP)
- **FR-2.2**: `analyze_structure` - Stream-able structure analysis (ENHANCE)
- **FR-2.3**: `extract_section` - Line/symbol-based extraction (KEEP)
- **FR-2.4**: `query_code` - Advanced filtering with semantic predicates (ENHANCE)
- **FR-2.5**: `search_symbols` - Cross-file symbol search (NEW)
- **FR-2.6**: `analyze_dependencies` - Import/dependency graph (NEW)

#### **FR-3: Token Optimization**
- **FR-3.1**: TOON format 2.0 with 70-80% reduction
- **FR-3.2**: Streaming responses for large results
- **FR-3.3**: Smart truncation with summary preservation
- **FR-3.4**: Prompt caching headers for MCP responses

#### **FR-4: Security & Validation**
- **FR-4.1**: Project boundary enforcement (maintain v1.x)
- **FR-4.2**: Path traversal protection
- **FR-4.3**: ReDoS prevention for user queries
- **FR-4.4**: Input sanitization (max sizes, special chars)

### 3.2 SHOULD-HAVE Features (v2.1)

#### **FR-5: Advanced Analysis**
- **FR-5.1**: Complexity analysis (cyclomatic, cognitive)
- **FR-5.2**: Dead code detection
- **FR-5.3**: Code smell identification
- **FR-5.4**: Dependency cycle detection

#### **FR-6: AI Integration**
- **FR-6.1**: Analysis strategy recommendations based on file size
- **FR-6.2**: Token budget tracking for responses
- **FR-6.3**: Automatic result pagination
- **FR-6.4**: Context-aware filtering suggestions

#### **FR-7: Developer Experience**
- **FR-7.1**: CLI with rich formatting (maintain v1.x UX)
- **FR-7.2**: JSON Schema validation for all APIs
- **FR-7.3**: Detailed error messages with recovery suggestions
- **FR-7.4**: Performance profiling output

### 3.3 NICE-TO-HAVE Features (v2.2+)

#### **FR-8: Advanced Integrations**
- **FR-8.1**: LSP server mode for IDE integration
- **FR-8.2**: GitHub Actions integration
- **FR-8.3**: VS Code extension
- **FR-8.4**: Web-based visualization dashboard

#### **FR-9: Machine Learning**
- **FR-9.1**: Code pattern recognition
- **FR-9.2**: Refactoring suggestions
- **FR-9.3**: Test case generation hints

---

## 4. Non-Functional Requirements

### 4.1 Performance

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| **Cold start** | <500ms | Time to first MCP tool response |
| **File parse** | <100ms | Files <10KB, single language |
| **Batch analysis** | <3s | 50 files, metrics only |
| **Query execution** | <200ms | Simple filters, cached parse |
| **Streaming latency** | <50ms | Time to first chunk |
| **Memory usage** | <100MB | Base process, no cached files |
| **Cache hit rate** | >80% | For repeated file access |

### 4.2 Scalability

| Dimension | Requirement |
|-----------|-------------|
| **File size** | Support up to 10MB files (with streaming) |
| **Project size** | Handle 10,000+ files without degradation |
| **Concurrent requests** | 10 simultaneous MCP tool calls |
| **Batch limits** | 200 files per batch operation |
| **Token limits** | Configurable max response size (default: 50K tokens) |

### 4.3 Reliability

- **Uptime**: 99.9% availability for MCP server
- **Error recovery**: Graceful degradation on parse failures
- **Data integrity**: Consistent results across multiple runs
- **Backward compatibility**: v1.x API compatibility layer

### 4.4 Maintainability

- **Code coverage**: Maintain >80% test coverage
- **Documentation**: API docs for all public interfaces
- **Modularity**: Plugin architecture for language support
- **Versioning**: Semantic versioning for releases

### 4.5 Security

- **CVE response time**: <48 hours for critical vulnerabilities
- **Dependency scanning**: Automated vulnerability checks
- **Secrets detection**: Prevent hardcoded credentials in responses
- **Access control**: File system boundary enforcement

### 4.6 Platform Support

| Platform | Requirement |
|----------|-------------|
| **Python** | 3.10+ (maintain v1.x) |
| **OS** | Windows, macOS, Linux |
| **Package Manager** | uv (primary), pip (fallback) |
| **Dependencies** | Minimal external deps (<20 packages) |

---

## 5. Technical Architecture Requirements

### 5.1 Core Architecture

```
┌─────────────────────────────────────────────┐
│         MCP Server Interface                │
│  (stdio transport, JSON-RPC 2.0)            │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│         Tool Orchestrator                   │
│  - Request routing                          │
│  - Token budget tracking                    │
│  - Response streaming                       │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│         Analysis Engine                     │
│  - Parser manager (tree-sitter)             │
│  - Query executor (with caching)            │
│  - Semantic analyzer                        │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│         Language Plugins                    │
│  - 17 language extractors                   │
│  - Extensible plugin system                 │
└─────────────────────────────────────────────┘
```

### 5.2 Design Principles

1. **Lazy Initialization**: Load parsers on-demand
2. **Streaming First**: All large results streamable
3. **Cache Aggressively**: Parse results, query results, file metadata
4. **Fail Fast**: Validate inputs before expensive operations
5. **Plugin Architecture**: Easy to add new languages

### 5.3 Data Flow

```
Request → Validate → Check Cache → Parse (if needed) →
Query → Filter → Format (TOON) → Stream → Response
```

### 5.4 Technology Stack

- **Core**: Python 3.10+ with type hints
- **Parsing**: tree-sitter (maintain v1.x)
- **MCP**: mcp Python SDK
- **Async**: asyncio for concurrent operations
- **Testing**: pytest + hypothesis (property testing)
- **Packaging**: uv + pyproject.toml

---

## 6. Success Metrics

### 6.1 Adoption Metrics
- **Target**: 1,000 GitHub stars in 6 months
- **Target**: 500+ weekly PyPI downloads
- **Target**: 10+ community language plugins

### 6.2 Performance Metrics
- **Target**: 90th percentile response time <500ms
- **Target**: Token reduction >70% vs raw JSON
- **Target**: Cache hit rate >85%

### 6.3 Quality Metrics
- **Target**: 0 critical bugs in production
- **Target**: <24h bug triage time
- **Target**: 95% user satisfaction (GitHub surveys)

---

## 7. Out of Scope (v2.0)

The following features are explicitly **NOT** included in v2.0:

1. **❌ Full LSP Implementation**: Too complex, focus on MCP
2. **❌ Code Execution**: Security risks, leave to other tools
3. **❌ Code Generation**: AI assistants handle this
4. **❌ IDE Extensions**: Focus on MCP server first
5. **❌ Web UI**: CLI + MCP sufficient for MVP
6. **❌ Cloud Deployment**: Local execution only
7. **❌ Multi-language projects**: Single language per file
8. **❌ Real-time collaboration**: Not a primary use case
9. **❌ Custom query languages**: Stick to tree-sitter queries
10. **❌ Machine learning models**: Too heavy for v2.0

---

## 8. Migration Strategy (v1.x → v2.0)

### 8.1 Compatibility Layer
- **v1.x API**: Maintain compatibility wrapper for existing tools
- **Deprecation timeline**: 6 months warning before breaking changes
- **Migration guide**: Detailed documentation with examples

### 8.2 Feature Parity
- All v1.x MCP tools must have v2.0 equivalents
- TOON format must be backward compatible
- CLI commands maintain same interface

### 8.3 Testing Strategy
- Golden Master tests for v1.x regression detection
- Parallel testing: v1.x vs v2.0 comparison
- Performance benchmarks: v2.0 must be ≥2x faster

---

## 9. Risks & Mitigation

### 9.1 Technical Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **Tree-sitter breaking changes** | High | Medium | Pin versions, contribute upstream fixes |
| **MCP spec changes** | High | Low | Follow MCP development closely |
| **Performance regression** | Medium | Medium | Continuous benchmarking, profiling |
| **Memory leaks** | High | Low | Extensive stress testing |

### 9.2 Business Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **Low adoption** | High | Medium | Early user testing, community building |
| **Competitor emerges** | Medium | High | Focus on unique features (TOON, streaming) |
| **AI model changes** | Low | High | Model-agnostic design |

---

## 10. Glossary

- **TOON**: Token-Optimized Output Notation - proprietary format for compact data representation
- **MCP**: Model Context Protocol - protocol for AI assistant integration
- **LSP**: Language Server Protocol - protocol for IDE integration
- **Tree-sitter**: Incremental parsing library for syntax analysis
- **AST**: Abstract Syntax Tree - structured representation of code
- **Streaming**: Incremental delivery of large responses
- **Batch operation**: Processing multiple files in one request
- **Plugin**: Language-specific analyzer module
- **Golden Master**: Regression testing via output comparison

---

## 11. References

### Research Sources
1. [awesome-mcp-servers](https://github.com/wong2/awesome-mcp-servers) - Curated MCP server list
2. [MCP Official Examples](https://modelcontextprotocol.io/examples) - Reference implementations
3. [Tree-sitter vs LSP](https://lambdaland.org/posts/2026-01-21_tree-sitter_vs_lsp/) - Architecture comparison
4. [Claude Code Token Optimization](https://medium.com/@pierreyohann16/optimizing-token-efficiency-in-claude-code-workflows-managing-large-model-context-protocol-f41eafdab423) - Token efficiency strategies
5. [Claude API Pricing 2026](https://www.glbgpt.com/hub/claude-ai-pricing-2026-the-ultimate-guide-to-plans-api-costs-and-limits/) - Cost analysis
6. [Claude Code vs OpenAI Codex](https://labs.adaline.ai/p/claude-code-vs-openai-codex) - Competitive analysis

### Internal Documentation
- `tree_sitter_analyzer/mcp/tools/` - v1.x MCP tool implementations
- `docs/api/mcp_tools_specification.md` - v1.x API documentation
- `.kiro/project_map.toon` - Current architecture map
- `CLAUDE.md` - Project development guidelines

---

## 12. Next Steps

1. **Design Phase**: Create `design.md` with detailed architecture
2. **Prototyping**: Build core streaming engine
3. **Benchmarking**: Establish v2.0 performance baselines
4. **Community**: Gather feedback from early adopters
5. **Implementation**: Task breakdown in `tasks.md`

---

## Approval & Sign-off

| Role | Name | Date | Status |
|------|------|------|--------|
| **Product Owner** | TBD | 2026-01-31 | Draft |
| **Tech Lead** | TBD | 2026-01-31 | Draft |
| **Community** | TBD | 2026-01-31 | Pending feedback |

---

**Last Updated**: 2026-01-31
**Document Version**: 1.0
**Next Review**: Upon design completion
