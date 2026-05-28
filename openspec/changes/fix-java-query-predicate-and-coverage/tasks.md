# Tasks: Fix Java query_code #match? predicate

## Status: RESOLVED — no fix needed

Verified 2026-05-28 against tree-sitter 0.25.2:
- `QueryCursor.matches()` in tree-sitter 0.25.2 DOES apply `#match?` predicates correctly.
- Test: `spring_controller` query against @Controller + @RestController + @Service class
  → returns exactly 2 matches (Controller classes), @Service class filtered out ✓
- The comment in `java.py:153` ("applied manually by _execute_newest_api") was aspirational;
  the library now handles it natively.

## Action Taken

No code changes required. Proposal archived in-place.
The `execute_newest_api()` in `_tree_sitter_compat_helpers.py` passes `QueryCursor.matches()`
output through directly — predicates are applied by the library.
