# Test Smell Detector

## Goal
Detect anti-patterns in test code that make tests unreliable or useless.

One-line: "Tell developers their tests are lying."

## MVP Scope
- Empty test body detection (no assertions)
- Broad exception catch (except Exception, catch(e) in tests)
- Sleep in tests (time.sleep, setTimeout in test functions)
- Low assertion count (<1 per test)

## Technical Approach
- Analysis engine: tree_sitter_analyzer/analysis/test_smells.py
- MCP tool: tree_sitter_analyzer/mcp/tools/test_smells_tool.py
- Pattern: manual AST walking (consistent with nesting_depth, i18n_strings)
- 4 languages: Python, JS/TS, Java, Go
- Category: quality
- Toolset: analysis

## Sprint Plan
- Sprint 1: Core detection engine (Python) + unit tests
- Sprint 2: Multi-language support (JS/TS, Java, Go)
- Sprint 3: MCP tool integration + registration
