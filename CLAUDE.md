# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Tree-sitter Analyzer is an enterprise-grade code analysis tool for the AI era that supports 17 programming languages. It provides deep code structure analysis through Tree-sitter parsing and integrates with AI assistants via the Model Context Protocol (MCP).

**Key Features:**
- Multi-language support: Java, Python, TypeScript/JavaScript, C/C++, C#, Go, Rust, Kotlin, PHP, Ruby, SQL, HTML, CSS, YAML, Markdown
- MCP server integration for AI assistants (Claude Desktop, Cursor, Roo Code)
- Token optimization (50-70% reduction via TOON format)
- Plugin-based architecture for language extensibility
- File search (fd) and content search (ripgrep) capabilities

## Development Commands

### Environment Setup
```bash
# Install with all dependencies
uv sync --extra all --extra mcp

# Verify installation
uv run tree-sitter-analyzer --show-supported-languages
```

### Testing
```bash
# Run all tests (8,405+ tests)
uv run pytest tests/ -v

# Run specific test categories
uv run pytest tests/unit/ -v              # Unit tests
uv run pytest tests/integration/ -v       # Integration tests
uv run pytest tests/regression/ -m regression  # Regression tests
uv run pytest tests/benchmarks/ -v        # Performance benchmarks

# Run tests with coverage report
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html

# Run single test file
uv run pytest tests/test_api.py -v
```

### Quality Checks
```bash
# Run quality checks (linting, type checking)
uv run python check_quality.py --new-code-only

# AI-powered code checking
uv run python llm_code_checker.py --check-all

# Type checking with mypy
uv run mypy tree_sitter_analyzer/
```

### CLI Usage
```bash
# Analyze file structure (full output)
uv run tree-sitter-analyzer examples/BigService.java --table full

# Quick summary
uv run tree-sitter-analyzer examples/BigService.java --summary

# Extract code section (partial read)
uv run tree-sitter-analyzer examples/BigService.java --partial-read --start-line 93 --end-line 106

# Query specific elements
uv run tree-sitter-analyzer examples/Sample.java --query-key methods --filter "public=true"

# Find files and search content
uv run find-and-grep --roots . --query "class.*Service" --extensions java
```

### MCP Server
```bash
# Start MCP server (for AI integration)
uvx --from "tree-sitter-analyzer[mcp]" tree-sitter-analyzer-mcp
```

## Architecture

### High-Level Structure

```
tree_sitter_analyzer/
├── core/                    # Core analysis engine
│   ├── analysis_engine.py  # UnifiedAnalysisEngine - central orchestrator
│   ├── parser.py           # Tree-sitter parsing
│   ├── query.py            # Query execution engine
│   ├── cache_service.py    # Analysis result caching
│   └── engine_manager.py   # Engine lifecycle management
├── plugins/                 # Language plugin system
│   ├── base.py             # Base classes: LanguagePlugin, ElementExtractor
│   ├── manager.py          # PluginManager - plugin discovery & registration
│   └── (language)_plugin.py # Language-specific implementations
├── languages/               # Language-specific plugins (17 languages)
│   ├── java_plugin.py
│   ├── python_plugin.py
│   ├── typescript_plugin.py
│   └── ...
├── formatters/              # Output formatting system
│   ├── formatter_registry.py  # Central formatter registry
│   ├── base_formatter.py      # Abstract formatter interface
│   ├── toon_formatter.py      # TOON format (token optimization)
│   └── (language)_formatter.py # Language-specific formatters
├── mcp/                     # MCP server implementation
│   ├── server.py           # TreeSitterAnalyzerMCPServer
│   ├── tools/              # MCP tool implementations
│   │   ├── analyze_scale_tool.py       # check_code_scale
│   │   ├── analyze_code_structure_tool.py  # analyze_code_structure
│   │   ├── read_partial_tool.py        # extract_code_section
│   │   ├── query_tool.py               # query_code
│   │   ├── list_files_tool.py          # list_files
│   │   ├── search_content_tool.py      # search_content
│   │   └── find_and_grep_tool.py       # find_and_grep
│   └── resources/          # MCP resources
├── cli/                     # CLI interface
│   └── commands/           # Command implementations
└── security/               # Security validation & boundary checks
```

### Core Design Patterns

**1. Plugin Architecture**
- Each language has a dedicated plugin implementing `LanguagePlugin` protocol
- Plugins define language-specific tree-sitter queries and element extraction logic
- `PluginManager` handles plugin discovery and registration at startup
- New languages can be added by creating a plugin in `languages/` directory

**2. Unified Analysis Engine**
- `UnifiedAnalysisEngine` is the central orchestrator (singleton per project root)
- Coordinates between parsers, plugins, formatters, and cache
- Lazy initialization pattern: components loaded only when first used
- Shared by CLI, MCP server, and Python API

**3. Lazy Initialization**
- Heavy imports deferred until first actual use (`_ensure_initialized()`)
- Tree-sitter parsers loaded on-demand per language
- Reduces startup time significantly

**4. Two-Level Caching**
- File-level cache: Parse results cached by file path + modification time
- Query-level cache: Query results cached to avoid redundant tree traversal

**5. TOON Format**
- Token-Optimized Output Notation: reduces token usage by 50-70%
- Compact representation of structured data
- Preserves full information while minimizing tokens
- Implemented in `formatters/toon_formatter.py`

## Key Architectural Principles

### Plugin System
- All plugins inherit from `LanguagePlugin` (protocol) in `plugins/base.py`
- Each plugin must implement:
  - `analyze_file(file_path, request)` → Returns `AnalysisResult`
  - `get_language_name()` → Language identifier
  - `get_supported_extensions()` → File extensions
- Plugins automatically discovered by `PluginManager` on initialization
- Language detection via file extension → `LanguageDetector`

### MCP Tools
- Each MCP tool inherits from `BaseTool` in `mcp/tools/base_tool.py`
- Tools use shared `UnifiedAnalysisEngine` instance
- Security validation via `SecurityValidator` ensures project boundary enforcement
- All tools support `output_format` parameter: `json` (default) or `toon`

### Testing Strategy
- **Unit tests** (2,087): Test individual components in isolation
- **Integration tests** (187): Test component interactions
- **Regression tests** (70): Ensure backward compatibility via Golden Master methodology
- **Property tests** (75): Hypothesis-based testing
- **Benchmarks** (20): Performance monitoring
- Test files located in `tests/` with corresponding structure

### Error Handling
- Security violations raise `SecurityViolationError`
- Unsupported languages raise `UnsupportedLanguageError`
- File access errors handled gracefully with detailed messages
- All errors logged via `utils/logger.py`

## Important Considerations

### Language Support
When adding new language support:
1. Create plugin in `languages/(language)_plugin.py`
2. Create formatter in `formatters/(language)_formatter.py`
3. Add tree-sitter dependency to `pyproject.toml`
4. Add language to `LanguageDetector` extension mapping
5. Create test files in `tests/test_languages/`

### MCP Tool Development
When creating new MCP tools:
1. Inherit from `BaseTool` in `mcp/tools/base_tool.py`
2. Implement `get_tool_definition()` returning MCP Tool schema
3. Implement `execute(arguments)` with argument validation
4. Add tool to `TreeSitterAnalyzerMCPServer` in `mcp/server.py`
5. Support both `json` and `toon` output formats
6. Include comprehensive docstrings for AI assistant context

### Security
- All file access goes through `SecurityValidator`
- Project root boundary enforced (prevents path traversal)
- Regex patterns validated for safety (ReDoS prevention)
- Secrets detection via `detect-secrets` library

### Performance
- Cache aggressively: file modifications tracked via mtime
- Use lazy initialization for expensive operations
- Prefer streaming for large file operations
- Monitor via `PerformanceMonitor` for optimization opportunities

### Windows Compatibility
- Use `pathlib.Path` for path operations
- File paths normalized via `Path.resolve()`
- Test on Windows explicitly due to path separator differences

## Test Baseline System

The `.cursorrules` file contains a comprehensive regression testing system with 43 test cases. When modifications affect core functionality:

1. Load baseline: `.cursor/test_baseline/.test_baseline.json`
2. Execute all test cases via MCP tools
3. Compare key metrics (success, counts, hashes)
4. Generate comparison report
5. Save results to `test_results.json`

**Known Limitations:**
- Test 13-15: `fields` query key and some filters may not work as expected
- Test 25-26: `list_files` sort parameter not implemented
- These are documented limitations, not regressions

## Code Quality Standards

- **Type Safety**: 100% mypy compliance required
- **Test Coverage**: Maintain >80% coverage
- **Linting**: Use ruff for code formatting and linting
- **Documentation**: Docstrings required for all public APIs
- **Performance**: No regression on benchmark tests

## Common Patterns

### Analyzing a File
```python
from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine
from tree_sitter_analyzer.core.request import AnalysisRequest

engine = get_analysis_engine(project_root="/path/to/project")
request = AnalysisRequest(
    file_path="example.java",
    include_complexity=True
)
result = await engine.analyze_file("example.java", request)
```

### Creating a New Language Plugin
```python
from tree_sitter_analyzer.plugins import LanguagePlugin, ElementExtractor

class MyLanguagePlugin(LanguagePlugin):
    def get_language_name(self) -> str:
        return "mylang"

    def get_supported_extensions(self) -> list[str]:
        return [".mylang"]

    async def analyze_file(self, file_path: str, request: AnalysisRequest):
        # Implementation here
        pass
```

## Documentation References

- **README.md**: User-facing documentation, installation, quick start
- **docs/architecture.md**: Detailed architecture documentation
- **docs/test-writing-guide.md**: Comprehensive testing guidelines
- **docs/regression-testing-guide.md**: Golden Master methodology
- **docs/api/mcp_tools_specification.md**: MCP API reference
- **CHANGELOG.md**: Version history and release notes

## Platform & Environment

- **Python Version**: 3.10+
- **Package Manager**: uv (required)
- **Required Tools**: fd, ripgrep (for search features)
- **Operating Systems**: Windows, macOS, Linux

---

## Project-Specific Development Workflow

### Planning with Files (.kiro Structure)

**CRITICAL**: This project uses a structured planning approach with persistent markdown files. ALL complex features (>5 tool calls, multi-step tasks, research) MUST follow the `.kiro` directory structure.

### Directory Structure

```
.kiro/
├── specs/                      # Active specifications
│   └── {feature-name}/        # One directory per feature
│       ├── requirements.md    # 需求定义、现状分析、目标
│       ├── design.md          # 设计方案、技术选型、架构图
│       ├── tasks.md           # 任务拆解、验收点、进度状态
│       └── progress.md        # 实施日志、会话记录（可选）
├── specs/archived/            # Completed/deprecated specs
│   └── {feature-name}/        # Same structure as active specs
├── settings/                  # Project configurations
│   └── mcp.json              # MCP server configuration
└── steering/                  # High-level project direction
    ├── product.md            # Product roadmap
    ├── tech.md               # Technical decisions
    └── structure.md          # Project structure guidelines
```

### Mandatory Workflow for New Features

**Step 1: Create Spec Directory**
```bash
.kiro/specs/{feature-name}/
```

Use kebab-case for feature names (e.g., `mcp-tool-efficiency`, `yaml-language-support`).

**Step 2: Initialize Planning Files**

Create the following files IN ORDER:

1. **requirements.md**
   - 现状分析（Current State Analysis）
   - 问题识别（Problem Identification）
   - 目标定义（Goals & Objectives）
   - 非功能性要求（Non-functional Requirements）
   - 用例场景（Use Cases）
   - 术语表（Glossary）

2. **design.md**
   - 技术选型（Technology Choices）
   - 架构设计（Architecture Design）
   - 数据流图（Data Flow - use Mermaid）
   - API 设计（API Design）
   - 实现细节（Implementation Details）
   - 边界情况处理（Edge Cases）

3. **tasks.md**
   - 任务拆解（Work Breakdown Structure）
   - 每个任务包含：
     - 目标（Objective）
     - 验收标准（Acceptance Criteria）
     - 状态标记（Status: pending/in_progress/completed）
     - 预计文件改动（Files to Modify）
   - 依赖关系（Dependencies）
   - 测试计划（Testing Plan）

4. **progress.md** (Optional but Recommended)
   - 会话日志（Session Log）
   - 遇到的问题（Issues Encountered）
   - 解决方案（Solutions Applied）
   - 测试结果（Test Results）
   - 待办事项（TODOs）

**Step 3: Phase-Based Organization**

For complex features with multiple phases:
```
.kiro/specs/{feature-name}/
├── requirements.md
├── design-phase1-{component}.md
├── design-phase2-{component}.md
├── task-phase1-{component}.md
├── task-phase2-{component}.md
└── progress.md
```

Example: `mcp-tool-efficiency` has multiple design/task files per phase.

**Step 4: Track Progress**

- Update `tasks.md` status markers: `pending` → `in_progress` → `completed`
- Log errors and solutions in `progress.md`
- Re-read planning files before making major decisions
- Update design documents when implementation reveals new insights

**Step 5: Archive When Complete**

When feature is fully implemented and tested:
```bash
mv .kiro/specs/{feature-name} .kiro/specs/archived/{feature-name}
```

### File-Based Planning Rules

**MANDATORY PRACTICES:**

1. **Create Plan First**
   - NEVER start implementing a complex feature without creating spec directory
   - Planning files are NOT optional for multi-step tasks

2. **The 2-Action Rule**
   - After every 2 file reads/searches, IMMEDIATELY update findings to `design.md` or `progress.md`
   - Prevents loss of discovered information

3. **Read Before Decide**
   - Before making architectural decisions, re-read relevant planning files
   - Keeps goals in attention window

4. **Update After Act**
   - After completing any task in `tasks.md`, mark status as `completed`
   - Log any errors encountered in `progress.md`
   - Note files created/modified

5. **Log ALL Errors**
   - Every error goes in `progress.md` under "Issues Encountered"
   - Prevents repeating same mistakes
   - Example format:
     ```markdown
     ## Issues Encountered
     | Error | Attempt | Resolution |
     |-------|---------|------------|
     | FileNotFoundError | 1 | Created default config |
     ```

6. **Never Repeat Failures**
   - If an action failed, next action MUST be different
   - Track what was tried in `progress.md`
   - Mutate the approach, don't retry blindly

### Language Preferences

- **Primary Language**: English for code, docstrings, comments
- **Documentation Language**: Mixed (English/Chinese/Japanese acceptable in planning files)
- **Design Documents**: Can use native language for clarity (见 mcp-tool-efficiency 示例)

### When to Use This Workflow

**ALWAYS use .kiro structure for:**
- New language support
- MCP tool development
- Architectural changes
- Performance optimization
- Feature additions requiring >3 files
- Bug fixes requiring design analysis

**Can skip for:**
- Typo fixes
- Single-line changes
- Documentation updates
- Test additions for existing code

### Integration with planning-with-files Skill (Global)

When using the globally installed `planning-with-files` skill, the following rules apply to maintain consistency with the `.kiro` structure:

**1. File Mapping (Mandatory)**
To ensure compatibility with the project's existing structure, the skill's templates are mapped to `.kiro` files as follows:
- `task_plan.md`  → `.kiro/specs/{feature}/tasks.md`
- `findings.md`   → `.kiro/specs/{feature}/design.md`
- `progress.md`   → `.kiro/specs/{feature}/progress.md`

**2. Automated Script Usage**
Leverage scripts from `~/.config/opencode/skills/planning-with-files/scripts/` to manage task state:
- **Initialization**: Use `init-session.ps1` (Windows) to scaffold the mapped `.kiro` structure.
- **Context Recovery**: Use `session-catchup.py` at the start of every session to sync progress from `.kiro/specs/`.
- **Validation**: Use `check-complete.ps1` before marking any task as `completed`.

**3. The 2-Action Rule (Strict Enforcement)**
- Every 2 non-trivial tool calls (Read/Grep/Bash) MUST be followed by an update to `design.md` (via findings) or `progress.md`.
- This ensures no discovered context is lost and the planning remains "live".

**4. Error Handling**
- All errors MUST be logged in `progress.md` using the "Log ALL Errors" table format from the skill's templates.
- If a task fails 3 times, revert changes and consult `oracle` using the failure context from `progress.md`.

### Example: Starting a New Feature

```bash
# User requests: "Add GraphQL language support"

# Step 1: Create spec directory
.kiro/specs/graphql-language-support/

# Step 2: Create requirements.md
# - Analyze current language plugin architecture
# - Define GraphQL-specific requirements
# - Identify tree-sitter-graphql integration points

# Step 3: Create design.md
# - Plugin class design
# - Query definitions
# - Formatter implementation
# - Integration with PluginManager

# Step 4: Create tasks.md
# - T1: Add tree-sitter-graphql dependency
# - T2: Implement GraphQLPlugin class
# - T3: Create GraphQLFormatter
# - T4: Add tests
# - T5: Update documentation

# Step 5: Implement following tasks.md order
# Step 6: Update progress.md with each session
# Step 7: Archive when complete
```

### Verification Before Implementing

Before writing code for a complex feature, Claude MUST:
1. ✅ Create `.kiro/specs/{feature-name}/` directory
2. ✅ Write `requirements.md` with current state analysis
3. ✅ Write `design.md` with technical approach
4. ✅ Write `tasks.md` with breakdown and acceptance criteria
5. ✅ Confirm with user if approach is acceptable

This prevents wasted effort and ensures alignment.
