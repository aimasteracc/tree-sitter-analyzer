# Spec: Java Annotation Extraction

**Change ID**: `fix-java-plugin-annotation-extraction`
**Spec ID**: `java-annotation-extraction`
**Status**: In Progress (v1 — 2026-03-11)

---

## Overview

Java classes, methods, and fields must correctly report their annotations after
`JavaPlugin.analyze_file()` or `JavaPlugin.extract_elements()` is called. This spec
defines the expected behavior and acceptance scenarios.

---

## Requirements

### Requirement 1: Class annotations are populated after extraction

**ID**: JAA-001
**Priority**: High

#### Scenario: Extract class with a single annotation

**Given** a Java file containing:
```java
@RestController
public class UserController {}
```
**When** `plugin.analyze_file()` is called
**Then** the extracted `UserController` class has:
- `annotations` list with at least one entry
- an annotation entry with `name` = `"RestController"`

#### Scenario: Extract class with multiple annotations

**Given** a Java file containing:
```java
@RestController
@RequestMapping("/api/users")
public class UserController {}
```
**When** `plugin.analyze_file()` is called
**Then** the extracted `UserController` class has `annotations` with 2 entries

---

### Requirement 2: Method annotations are populated after extraction

**ID**: JAA-002
**Priority**: High

#### Scenario: Extract method with marker annotation

**Given** a Java file containing:
```java
public class MyService {
    @Override
    public String toString() { return "MyService"; }
}
```
**When** `plugin.analyze_file()` is called
**Then** the extracted `toString` method has:
- `annotations` list with at least one entry
- an annotation entry with `name` = `"Override"`

---

### Requirement 3: Spring Framework annotations end-to-end

**ID**: JAA-003
**Priority**: High

#### Scenario: Spring controller with endpoint annotations

**Given** a Java file containing:
```java
@RestController
@RequestMapping("/api")
public class ApiController {
    @GetMapping("/users")
    public List<User> getUsers() { return null; }
}
```
**When** `plugin.analyze_file()` is called
**Then**:
- `ApiController` class has `annotations` containing `"RestController"` and `"RequestMapping"`
- `getUsers` method has `annotations` containing `"GetMapping"`
- Class and method annotations are correctly scoped (not mixed up)

---

### Requirement 4: _reset_caches() preserves business state

**ID**: JAA-004
**Priority**: High

#### Scenario: Annotations survive cache reset

**Given** a `JavaElementExtractor` instance with `self.annotations = [{"name": "Override", "line": 5}]`
**When** `_reset_caches()` is called
**Then** `self.annotations` still equals `[{"name": "Override", "line": 5}]`

#### Scenario: current_package survives cache reset

**Given** a `JavaElementExtractor` instance with `self.current_package = "com.example"`
**When** `_reset_caches()` is called
**Then** `self.current_package` still equals `"com.example"`

---

### Requirement 5: self.extractor is synced after analysis (align with GoPlugin)

**ID**: JAA-005
**Priority**: Medium

#### Scenario: plugin.extractor reflects latest analysis

**Given** a `JavaPlugin` instance
**When** `extract_elements()` is called with a Java file containing annotations
**Then** `plugin.extractor.annotations` is non-empty and reflects the extracted annotations

---

## Acceptance Criteria

- [ ] JAA-001: Class annotations populated after `analyze_file()`
- [ ] JAA-002: Method annotations populated after `analyze_file()`
- [ ] JAA-003: Spring framework end-to-end scenario passes
- [ ] JAA-004: `_reset_caches()` does not clear `self.annotations` or `self.current_package`
- [ ] JAA-005: `plugin.extractor.annotations` synced after `extract_elements()`
