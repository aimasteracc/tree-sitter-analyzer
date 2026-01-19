# Design - Plugin Contract Alignment

## Technology Choices
- **Analysis Method**: Compare TOON structure of `base.py` vs all `(lang)_plugin.py`.
- **Validation**: Project's own TOON map and unit tests.

## Implementation Strategy
1. **Define Contract**: Read TOON summary of `tree_sitter_analyzer/plugins/base.py` to list all public methods of `LanguagePlugin`.
2. **Audit Script**: Use a simple grep/awk or Python script to parse the `project_map.toon` and identify plugins missing any of the required methods.
3. **Refactoring**: 
    - For missing methods: Add default/empty implementations with a `# TODO: Implement logic` comment.
    - For misnamed methods: Rename to match the base contract.
4. **Core Cleanup**: Once plugins are aligned, remove redundant `hasattr` or `try-except` checks in `analysis_engine.py`.

## Success Criteria
- All files in `tree_sitter_analyzer/languages/` contain all methods defined in the `LanguagePlugin` base class.
- TOON map shows identical method lists for all plugins.
