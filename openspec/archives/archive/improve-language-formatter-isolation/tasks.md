# Tasks: Improve Language Formatter Isolation

**Change ID**: improve-language-formatter-isolation  
**Status**: Ready for Implementation  
**Estimated Effort**: 3-5 days

## Implementation Tasks

### Phase 1: Infrastructure Setup (Day 1)

- [ ] **Task 1.1**: Create plugin system infrastructure
  - [ ] Create `FormatterPlugin` protocol in `tree_sitter_analyzer/formatters/plugin_protocol.py`
  - [ ] Implement `FormatterPluginMeta` metaclass for auto-registration
  - [ ] Create `BaseFormatterPlugin` abstract base class
  - [ ] Add type hints and documentation
  - **Validation**: Protocol can be imported and used correctly

- [ ] **Task 1.2**: Implement Language Formatter Registry
  - [ ] Create `LanguageFormatterRegistry` class in `tree_sitter_analyzer/formatters/registry.py`
  - [ ] Implement plugin registration mechanism
  - [ ] Add priority-based plugin selection
  - [ ] Implement caching for performance
  - **Validation**: Registry can register and retrieve plugins correctly

- [ ] **Task 1.3**: Create compatibility layer
  - [ ] Update `language_formatter_factory.py` to use new registry
  - [ ] Maintain backward compatibility with existing `create_language_formatter()` function
  - [ ] Add deprecation warnings for old usage patterns
  - **Validation**: Existing code continues to work without changes

### Phase 2: Formatter Migration (Day 2-3)

- [ ] **Task 2.1**: Convert Java formatter to plugin
  - [ ] Update `JavaTableFormatter` to inherit from `BaseFormatterPlugin`
  - [ ] Implement required plugin methods
  - [ ] Add comprehensive tests
  - **Validation**: Java formatting works identically to before

- [ ] **Task 2.2**: Convert Python formatter to plugin
  - [ ] Update `PythonTableFormatter` to inherit from `BaseFormatterPlugin`
  - [ ] Implement required plugin methods
  - [ ] Add comprehensive tests
  - **Validation**: Python formatting works identically to before

- [ ] **Task 2.3**: Convert JavaScript formatter to plugin
  - [ ] Update `JavaScriptTableFormatter` to inherit from `BaseFormatterPlugin`
  - [ ] Implement required plugin methods
  - [ ] Add comprehensive tests
  - **Validation**: JavaScript formatting works identically to before

- [ ] **Task 2.4**: Convert TypeScript formatter to plugin
  - [ ] Update `TypeScriptTableFormatter` to inherit from `BaseFormatterPlugin`
  - [ ] Implement required plugin methods
  - [ ] Add comprehensive tests
  - **Validation**: TypeScript formatting works identically to before

- [ ] **Task 2.5**: Convert SQL formatter to plugin
  - [ ] Update `SQLFormatterWrapper` to inherit from `BaseFormatterPlugin`
  - [ ] Implement required plugin methods
  - [ ] Add comprehensive tests
  - **Validation**: SQL formatting works identically to before

- [ ] **Task 2.6**: Convert HTML formatter to plugin
  - [ ] Update `HtmlFormatter` to inherit from `BaseFormatterPlugin`
  - [ ] Implement required plugin methods
  - [ ] Add comprehensive tests
  - **Validation**: HTML formatting works identically to before

- [ ] **Task 2.7**: Convert CSS formatter to plugin
  - [ ] Update CSS formatter (currently using `HtmlFormatter`) to inherit from `BaseFormatterPlugin`
  - [ ] Implement required plugin methods
  - [ ] Add comprehensive tests
  - **Validation**: CSS formatting works identically to before

- [ ] **Task 2.8**: Convert Markdown formatter to plugin
  - [ ] Update `MarkdownFormatter` to inherit from `BaseFormatterPlugin`
  - [ ] Implement required plugin methods
  - [ ] Add comprehensive tests
  - **Validation**: Markdown formatting works identically to before

### Phase 3: TableCommand Integration (Day 3)

- [ ] **Task 3.1**: Update TableCommand to use registry
  - [ ] Modify `execute_async()` method to use `LanguageFormatterRegistry`
  - [ ] Implement proper error handling for missing formatters
  - [ ] Maintain fallback to legacy system during transition
  - **Validation**: All table commands work correctly

- [ ] **Task 3.2**: Fix method interface inconsistencies
  - [ ] Ensure all formatters implement `format_analysis_result()` method
  - [ ] Remove dependency on non-existent `format_table()` method
  - [ ] Add proper type checking
  - **Validation**: No method call errors occur

### Phase 4: Comprehensive Testing (Day 4)

- [ ] **Task 4.1**: Create plugin registration tests
  - [ ] Test auto-registration mechanism
  - [ ] Test priority-based selection
  - [ ] Test cache functionality
  - **Validation**: All plugin registration scenarios work correctly

- [ ] **Task 4.2**: Create language isolation tests
  - [ ] Test that adding new language doesn't affect existing ones
  - [ ] Test formatter independence
  - [ ] Test concurrent access to registry
  - **Validation**: Language isolation is guaranteed

- [ ] **Task 4.3**: Create comprehensive regression tests
  - [ ] Test all languages after new language addition
  - [ ] Test golden master compatibility
  - [ ] Test performance impact
  - **Validation**: No regressions in existing functionality

- [ ] **Task 4.4**: Create integration tests
  - [ ] Test full CLI workflow with new system
  - [ ] Test MCP integration compatibility
  - [ ] Test error handling scenarios
  - **Validation**: End-to-end functionality works correctly

### Phase 5: Documentation and Cleanup (Day 5)

- [ ] **Task 5.1**: Update documentation
  - [ ] Create plugin development guide
  - [ ] Update API documentation
  - [ ] Add migration guide for existing formatters
  - **Validation**: Documentation is complete and accurate

- [ ] **Task 5.2**: Performance optimization
  - [ ] Profile plugin system performance
  - [ ] Optimize registry lookup performance
  - [ ] Add performance benchmarks
  - **Validation**: Performance meets or exceeds current system

- [ ] **Task 5.3**: Final validation
  - [ ] Run full test suite
  - [ ] Verify all golden masters pass
  - [ ] Test with real-world examples
  - **Validation**: System is production-ready

## Validation Criteria

### Functional Requirements
- [ ] All existing languages continue to work without changes
- [ ] New languages can be added without affecting existing ones
- [ ] Plugin system provides type safety
- [ ] Performance is maintained or improved

### Quality Requirements
- [ ] 100% test coverage for new plugin system
- [ ] All existing tests continue to pass
- [ ] No mypy type errors
- [ ] All pre-commit hooks pass

### Integration Requirements
- [ ] CLI commands work identically to before
- [ ] MCP tools continue to function
- [ ] Golden master tests pass
- [ ] No breaking changes for end users

## Risk Mitigation

### High Risk Items
- [ ] **Breaking Changes**: Maintain strict backward compatibility
- [ ] **Performance Regression**: Implement comprehensive benchmarks
- [ ] **Type Safety**: Use mypy for static type checking
- [ ] **Test Coverage**: Achieve 100% coverage for new code

### Rollback Plan
- [ ] Keep old factory system as fallback
- [ ] Feature flag for new plugin system
- [ ] Ability to disable auto-registration if needed
- [ ] Comprehensive rollback testing

## Dependencies

### Internal Dependencies
- Current formatter system must remain functional during migration
- Test infrastructure must support both old and new systems
- Documentation system must be updated

### External Dependencies
- No external dependencies required
- Python 3.10+ type system features used
- Existing tree-sitter integration maintained

## Success Metrics

1. **Zero Regressions**: All existing functionality works identically
2. **Language Isolation**: New languages don't affect existing ones
3. **Type Safety**: 100% mypy compliance
4. **Test Coverage**: >95% coverage for new plugin system
5. **Performance**: <5% performance impact
6. **Developer Experience**: Easier to add new language formatters

## Completion Checklist

- [ ] All tasks completed and validated
- [ ] Full test suite passes
- [ ] Documentation updated
- [ ] Performance benchmarks meet criteria
- [ ] Code review completed
- [ ] Ready for production deployment
