# Fix Java query_code: #match? predicate + Missing Query Types

## Overview

Two distinct issues found via systematic validation of all Java `query_code` queries
against spring-petclinic, spring-framework, caffeine, and netty.

## Validation Method

Ran `query_code` for all 40+ Java query types against real production Java files.
Cross-checked results against `rg` ground truth.

---

## Issue 1: #match? Predicate Silently Returns 0 Results (CRITICAL)

### Affected Queries

All queries using `#match?` custom predicate return 0 results:
- `spring_controller`, `spring_service`, `spring_repository`
- `jpa_entity`, `jpa_id_field`
- `method_with_annotations` (partial)

### Root Cause

In tree-sitter-python 0.25+, `QueryCursor.matches()` returns raw AST matches
WITHOUT applying custom predicates (like `#match?`, `#not-match?`). Built-in
predicates (`#eq?`, `#is?`, `#is-not?`) ARE applied, but custom string-matching
predicates are not.

The `_execute_newest_api()` in `tree_sitter_compat.py` calls:
```python
cursor = tree_sitter.QueryCursor(query)
matches = cursor.matches(root_node)
# ← #match? predicates are NOT filtered here
```

So a query like:
```scheme
(class_declaration
  (modifiers (annotation
    name: (identifier) @ann
    (#match? @ann "Controller|RestController")))
  name: (identifier) @name) @class
```
returns ALL classes (ignoring the `#match?` filter) or, in some implementations,
returns 0 because the predicate is unrecognized. Actual result: 0 matches.

### Impact

`spring_controller`, `jpa_entity`, etc. are the highest-value queries for
Spring/JPA codebases. They're broken on any installation using tree-sitter 0.25+.
`query_code` cannot filter classes by annotation — the primary use case.

### Fix Options

**Option A (Recommended):** Post-filter matches in `_execute_newest_api()` by
manually applying `#match?` predicates using Python `re.search()`.

**Option B:** Rewrite affected queries to use structural matching instead of
`#match?`. For example, instead of `(#match? @ann "Controller")`, capture the
annotation name and let the caller filter — but this changes the query API.

**Option C:** Use `QueryCursor` with `node_predicate` callback (if supported).

Option A is backward-compatible and requires no query changes.

### Algorithm for Option A

```python
import re

def _apply_match_predicates(query, matches):
    """Filter matches by #match? predicates manually."""
    filtered = []
    for pattern_idx, capture_dict in matches:
        if _check_match_predicates(query, pattern_idx, capture_dict):
            filtered.append((pattern_idx, capture_dict))
    return filtered

def _check_match_predicates(query, pattern_idx, capture_dict):
    """Return True if all #match? predicates pass for this match."""
    # Extract predicates from query string (parse from query.string_value)
    # For each (#match? @capture_name "pattern"):
    #   check re.search(pattern, node.text) for the captured node
    ...
```

---

## Issue 2: Missing Query Types for Modern Java and Spring

### Missing Queries (High Priority)

#### Java 16+ Language Features
- `record_declaration` — Java 16 records (used in Spring 6+)
- `sealed_class` — Java 17 sealed classes + `permits`
- `pattern_matching_instanceof` — Java 16 `instanceof Foo f`
- `switch_expression` — Java 14+ `switch` as expression

#### Spring Ecosystem (Critical Gaps)
- `spring_bean` — `@Bean` methods in `@Configuration` classes
- `spring_configuration` — `@Configuration` classes
- `spring_component` — generic `@Component` annotated classes
- `spring_transactional` — `@Transactional` methods/classes
- `spring_autowired` — `@Autowired` injection points
- `spring_request_mapping` — all HTTP mapping annotations (`@GetMapping`, `@PostMapping`, etc.)
- `spring_event_listener` — `@EventListener` methods
- `spring_scheduled` — `@Scheduled` methods

#### Testing (High Value for AI-Assisted Development)
- `junit5_test` — `@Test` methods
- `junit5_lifecycle` — `@BeforeEach`, `@AfterEach`, `@BeforeAll`, `@AfterAll`
- `spring_mock_bean` — `@MockBean`, `@SpyBean`
- `parameterized_test` — `@ParameterizedTest` with `@ValueSource`/`@CsvSource`

#### Concurrency and Async
- `volatile_field` — `volatile` modified fields
- `spring_async` — `@Async` annotated methods
- `synchronized_method` — methods with `synchronized` modifier

#### Exception Handling
- `throws_declaration` — methods with `throws` clause
- `custom_exception` — exception class declarations

### Validation Projects

- `spring_bean`, `spring_configuration` → spring-framework `spring-context/`
- `spring_transactional` → spring-framework `spring-tx/`
- `record_declaration` → spring-framework 6 uses records
- `junit5_test` → spring-framework's own test suite (9225 Java files)
- `volatile_field` → caffeine's `BoundedLocalCache.java`

---

## Success Criteria

1. `query_code("spring_controller")` on spring-petclinic OwnerController.java → 1 result
2. `query_code("jpa_entity")` on spring-petclinic Vet.java → 1 result
3. All `#match?` predicates correctly filter results
4. `query_code("spring_bean")` on ProxyCachingConfiguration.java → 3 results
5. `query_code("junit5_test")` on any Spring test file → N results
6. `query_code("record_declaration")` on a Java 16 record → 1 result
7. New queries validated against caffeine/netty/spring-framework
8. All existing tests pass; 20+ new TDD tests added
