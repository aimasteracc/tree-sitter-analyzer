# Fix Java: implements Generics Parsing + Annotation Attribution

## Overview

Two correctness bugs found via caffeine validation (ben-manes/caffeine, production-grade
caching library, 660 Java files). Both bugs cause `analyze_code_structure` to return
structurally incorrect data that misleads Claude when navigating complex Java codebases.

## Validation Project

**caffeine** — `BoundedLocalCache.java` (4770 lines, 34 inner classes, heavy generics)
- Industry-standard caching library; clean, well-structured Java
- Inner classes with generic interfaces expose both bugs clearly

---

## Bug 1: `implements` with Generic Type Arguments Split Incorrectly

### Observed (wrong)

```python
# BoundedLocalCache implements LocalCache<K, V>
"implements": ["LocalCache", "K", "V"]

# SizeLimiter implements Function<Stream<CacheEntry<K, V>>, Map<K, V>>
"implements": ["Function", "Stream", "CacheEntry", "K", "V", "Map", "K", "V"]
```

### Expected (correct)

```python
"implements": ["LocalCache<K, V>"]
"implements": ["Function<Stream<CacheEntry<K, V>>, Map<K, V>>"]
```

### Root Cause

The `implements_interfaces` extraction splits on `,` or whitespace without tracking
angle-bracket nesting depth. `LocalCache<K, V>` contains a comma inside `<>`, so the
parser incorrectly treats `K` and `V` as separate interface names.

### Impact

- `trace_impact` and `modification_guard` cannot correctly identify which interfaces
  a class implements — critical for Spring `@Component` hierarchy traversal
- Claude gets wrong structural information when navigating class hierarchies
- Token waste: Claude has to re-read source files to verify implements relationships

---

## Bug 2: `@Override` (and other method annotations) Attributed to Classes

### Observed (wrong)

```python
# BoundedEviction class — @Override should never appear on a class
"classes": [{"name": "BoundedEviction", "annotations": [{"name": "Override"}]}]

# BoundedExpireAfterAccess class
"classes": [{"name": "BoundedExpireAfterAccess", "annotations": ["SuppressWarnings", "Override"]}]
```

### Expected (correct)

```python
# @Override is NEVER valid on a class in Java — only on methods/fields
"classes": [{"name": "BoundedEviction", "annotations": []}]  # or only class-level annotations
"classes": [{"name": "BoundedExpireAfterAccess", "annotations": ["SuppressWarnings"]}]
```

### Root Cause

`_find_annotations_for_line_cached()` uses `abs(annotation.line - element.start_line) <= 2`
to attribute annotations to elements. When a class declaration immediately follows a method
with `@Override`, the `@Override` falls within the 2-line window of the class start and
gets incorrectly attributed.

Example (BoundedEviction starting at line N):
```java
    @Override  // line N-1 — this is the last method's annotation!
    public void someMethod() { ... }
}

@SuppressWarnings("unchecked")
class BoundedEviction ... {  // line N+1 — class starts here
```

The 2-line window `abs(N-1 - (N+1)) = 2` matches, so `@Override` is incorrectly attributed.

### Impact

- Completely wrong structural metadata for classes
- Claude cannot tell which classes are annotated with meaningful markers (`@Deprecated`,
  `@FunctionalInterface`) vs garbage method annotations (`@Override`, `@Test`)
- `modification_guard` impact analysis is distorted by false class annotations

---

## Success Criteria

1. `BoundedLocalCache implements LocalCache<K, V>` → `implements: ["LocalCache<K, V>"]`
2. `@Override` never appears in class or field annotations output
3. All 610+ existing Java tests pass
4. 10+ new TDD tests covering both bugs with caffeine real data
