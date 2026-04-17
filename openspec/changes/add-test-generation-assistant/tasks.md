# Test Generation Assistant - OpenSpec Change

## Goal

Generate pytest test skeletons from Python functions using static analysis. Reduce the "blank page anxiety" of writing tests from scratch.

## Inspiration

From office-hours design discussion: "The 'whoa' moment is pointing at a file and getting 80% of the tedious test work done in seconds."

## MVP Scope

1. **Python-only** - Single language for MVP (expand if successful)
2. **Functions only** - No classes, no async (MVP scope)
3. **pytest format** - Industry standard for Python testing
4. **Placeholder assertions** - Developer fills in expected values
5. **CLI + MCP Tool** - Both interfaces for accessibility

## Technical Approach

### Sprint Breakdown

**Sprint 1: Core Test Generation Engine (1-2 days)**
- [ ] Create `tree_sitter_analyzer/test_gen/__init__.py`
- [ ] Create `tree_sitter_analyzer/test_gen/generator.py`
- [ ] Implement FuncInfo extraction from Python AST
- [ ] Implement cyclomatic complexity calculation
- [ ] Implement test case generation algorithm (happy path + edge cases + exceptions)
- [ ] Write 25+ unit tests

**Sprint 2: Pytest Renderer (1 day)**
- [ ] Create `tree_sitter_analyzer/test_gen/renderer.py`
- [ ] Implement pytest template rendering
- [ ] Add import generation (from module import func)
- [ ] Handle edge cases (None, empty strings, boundaries)
- [ ] Add decorator handling (include with warning if not testable)
- [ ] Write 15+ unit tests

**Sprint 3: CLI + MCP Integration (1 day)**
- [ ] Create `cli/commands/test_gen_command.py`
- [ ] Add `tree-sitter generate-tests` CLI command
- [ ] Create `mcp/tools/test_generation_tool.py`
- [ ] Register generate_tests MCP tool (testing toolset)
- [ ] Add error handling (parse failures, invalid functions)
- [ ] Write 10+ integration tests

## Success Criteria

- [ ] `tree-sitter generate-tests file.py` generates test_skeleton.py
- [ ] Generated tests follow pytest conventions (function names, fixtures)
- [ ] 80%+ of generated tests are syntactically valid (verified via `python -m py_compile`)
- [ ] Happy path + 1-5 edge cases per function (based on complexity)
- [ ] Exception tests for each explicitly raised exception type
- [ ] Parse failure handling (skip with warning, not crash)
- [ ] 50+ unit tests for the test generator itself
- [ ] CLI + MCP tool integration
- [ ] Documentation with 5+ examples

## Design Doc

Design: /Users/aisheng.yu/.gstack/projects/aimasteracc-tree-sitter-analyzer/aisheng.yu-feat_autonomous_dev-design-20260417-220835.md

Quality Score: 9/10 (2 rounds of adversarial review)

## Dependencies

- tree-sitter (existing)
- python_plugin.py (existing)
- complexity_analysis.py (existing, or inline if not available)
- pytest (for generated tests, developer-side dependency)

## References

- Design doc: `~/.gstack/projects/aimasteracc-tree-sitter-analyzer/aisheng.yu-feat_autonomous_dev-design-20260417-220835.md`
- Incremental Analysis Cache (similar Sprint structure)
- Test Coverage Analyzer (existing module for coverage gaps)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
