# Tree-Sitter Analyzer v2

> **Status**: 🚧 Alpha Development (v2.0.0-alpha.1)
> **Goal**: Complete architectural rewrite for simplicity, performance, and AI-first design

Enterprise-grade code analysis tool for the AI era. Built for AI assistants (Claude, GPT, Cursor) with token optimization, fast search, and multi-language support.

## 🎯 Project Vision

Tree-Sitter Analyzer v2 is a **ground-up rewrite** focusing on:

- **Simplicity**: Clean architecture, no over-engineering
- **Performance**: Fast analysis with fd/ripgrep integration
- **Token Efficiency**: TOON format for 70-80% token reduction
- **AI-First**: Built specifically for AI assistants

## ✨ Key Features

- **4 Language Support**: Python, TypeScript, JavaScript, Java (more languages planned)
- **MCP Integration**: Seamless integration with Claude Desktop, Cursor, Roo Code
- **Fast Search**: fd (file search) + ripgrep (content search) - 10-20x faster
- **Token Optimization**: TOON + Markdown output formats
- **Triple Interface**: CLI (testing) + API (Agent Skills) + MCP (AI integration)

## 🚀 Quick Start

### Prerequisites

- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) package manager
- [fd](https://github.com/sharkdp/fd) (optional but recommended)
- [ripgrep](https://github.com/BurntSushi/ripgrep) (optional but recommended)

### Installation

```bash
# Clone the repository
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
git checkout v2-rewrite

# Install v2
cd v2
uv pip install -e ".[dev]"

# Verify installation
uv run pytest tests/ -v
```

### 🎯 Use in Cursor (MCP Integration)

**Quick Setup (3 steps):**

1. **Install MCP dependencies:**
   ```bash
   uv pip install -e ".[mcp]"
   ```

2. **Add to Cursor MCP settings:**
   ```json
   {
     "mcpServers": {
       "tree-sitter-analyzer-v2": {
         "command": "uv",
         "args": ["run", "--directory", "YOUR_PROJECT_PATH", "python", "-m", "tree_sitter_analyzer_v2.mcp.server"],
         "env": {"TREE_SITTER_PROJECT_ROOT": "YOUR_PROJECT_PATH"}
       }
     }
   }
   ```

3. **Restart Cursor** and start using!

**📚 Detailed guides:**
- [快速配置.txt](./快速配置.txt) - Quick reference (Chinese)
- [CURSOR配置说明.md](./CURSOR配置说明.md) - Detailed setup guide (Chinese)
- [README_CURSOR_INTEGRATION.md](../README_CURSOR_INTEGRATION.md) - Complete integration guide (English)

**✅ Status:** MCP server tested and working with 11 tools available!

### Basic Usage

```python
# Python API
from tree_sitter_analyzer_v2.api import TreeSitterAnalyzerAPI

api = TreeSitterAnalyzerAPI(project_root="/path/to/project")

# Analyze a file
result = api.analyze_file("src/main.py", format="toon")
print(result)

# Search files
py_files = api.search_files(extensions=[".py"])

# Search content
matches = api.search_content("def main")
```

## 📊 Development Status

### Phase 0: Foundation (Week 1) - **IN PROGRESS**

- ✅ T0.1: Project Scaffold
- ✅ T0.2: Testing Framework
- ✅ T0.3: MCP Hello World
- ✅ T0.4: fd + ripgrep Detection
- ✅ T0.5: CI/CD Pipeline
- ✅ T0.6: Development Documentation

**Current Stats:**
- 1650+ tests passing
- 89% code coverage
- TDD methodology

### Upcoming Phases

- **Phase 1**: Core Parser + Search Engine (Week 2-3)
- **Phase 2**: Plugin System (Week 3-4)
- **Phase 3**: Output Formatters (Week 4)
- **Phase 4**: MCP Integration (Week 4-5)
- **Phase 5**: CLI + API (Week 5)
- **Phase 6**: Additional Languages (Week 6-7)
- **Phase 7**: Optimization (Week 7-8)

See [tasks.md](../.kiro/specs/v2-complete-rewrite/tasks.md) for detailed plan.

## 🧪 Testing

We follow **Test-Driven Development (TDD)** strictly. All code is written **tests-first**.

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ --cov=tree_sitter_analyzer_v2 --cov-report=html

# Run specific test category
uv run pytest tests/unit/ -v          # Unit tests
uv run pytest tests/integration/ -v   # Integration tests
uv run pytest tests/e2e/ -v           # End-to-end tests
```

**Coverage Targets:**
- Overall: 80% minimum
- Core modules: 90% minimum
- New code: 100% (all new code must have tests)

See [docs/tdd-workflow.md](docs/tdd-workflow.md) for detailed TDD guide.

## 🛠️ Development

### Project Structure

```
tree-sitter-analyzer-v2/
├── tree_sitter_analyzer_v2/     # Source code
│   ├── core/                    # Core parser and types
│   ├── languages/               # Language-specific parsers
│   ├── features/                # Analysis features
│   ├── formatters/              # TOON + Markdown output
│   ├── mcp/                     # MCP server and tools
│   ├── cli/                     # CLI interface
│   ├── api/                     # Python API
│   └── security/                # Security validation
├── tests/                       # Test suite
│   ├── unit/                    # Unit tests
│   ├── integration/             # Integration tests
│   └── fixtures/                # Test data
├── docs/                        # Documentation
└── examples/                    # Usage examples
```

### Code Quality

```bash
# Linting
uv run ruff check tree_sitter_analyzer_v2/

# Formatting
uv run ruff format tree_sitter_analyzer_v2/

# Type checking
uv run mypy tree_sitter_analyzer_v2/
```

## 📖 Documentation

- [Contributing Guide](CONTRIBUTING.md)
- [TDD Workflow](docs/tdd-workflow.md)
- [Code Conventions](docs/conventions.md)
- [Architecture Design](../.kiro/specs/v2-complete-rewrite/design.md)
- [Requirements](../.kiro/specs/v2-complete-rewrite/requirements.md)
- [Task Plan](../.kiro/specs/v2-complete-rewrite/tasks.md)

## 🎓 Design Principles

### 1. Simplicity First
- No file exceeds 300 lines
- One responsibility per module
- Real dependency injection or none at all

### 2. TDD Methodology
- Write tests FIRST, always
- RED → GREEN → REFACTOR
- 80%+ coverage enforced

### 3. Performance by Design
- fd + ripgrep for fast search
- Single unified cache
- Lazy loading where it makes sense

### 4. Type Safety
- 100% type hints
- No TYPE_CHECKING tricks
- Types match runtime reality

### 5. AI-First Output
- TOON format: 70-80% token reduction
- Markdown format: Human-readable
- No JSON bloat

## 🔧 Key Architectural Decisions

### What v2 Changes from v1

**Removed (over-engineered):**
- ❌ `AnalysisEngine` god object (800+ lines)
- ❌ Multiple conflicting cache layers
- ❌ TYPE_CHECKING circular dependency hacks
- ❌ Fake abstractions (ElementExtractor hierarchy)
- ❌ JSON output format

**Added (simplified):**
- ✅ Clean `CodeAnalyzer` (200 lines max)
- ✅ Single LRU cache strategy
- ✅ Clear dependency hierarchy
- ✅ Real plugin base class with 80% shared code
- ✅ TOON + Markdown output only

### What v2 Preserves from v1

- ✅ Multi-language support (4 languages currently, more planned)
- ✅ Tree-sitter query patterns
- ✅ fd + ripgrep integration
- ✅ MCP server capability
- ✅ TOON format optimization
- ✅ Security validation

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Before contributing:**
1. Read the [TDD Workflow](docs/tdd-workflow.md)
2. Follow [Code Conventions](docs/conventions.md)
3. Write tests FIRST
4. Ensure 80%+ coverage
5. Run quality checks

## 📝 License

MIT License - see [LICENSE](../LICENSE) for details.

## 🙏 Acknowledgments

- Built with [tree-sitter](https://tree-sitter.github.io/)
- Fast search powered by [fd](https://github.com/sharkdp/fd) and [ripgrep](https://github.com/BurntSushi/ripgrep)
- MCP protocol by [Anthropic](https://www.anthropic.com/)

---

**Note**: This is v2 alpha - a complete rewrite. For stable production use, see [v1.9.17.1](https://github.com/aimasteracc/tree-sitter-analyzer/releases/tag/v1.9.17.1).

**Goal**: Replace v1.9.17.1 with a cleaner, faster, simpler v2.0 by Week 8.
