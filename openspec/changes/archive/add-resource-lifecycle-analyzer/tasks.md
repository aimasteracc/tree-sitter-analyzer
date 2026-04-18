# Resource Lifecycle Analyzer

## Goal
Detects resource management issues: missing context managers, unclosed resources, and missing cleanup in error paths.

## MVP Scope
- Detect `open()` calls without `with` statement (Python)
- Detect `new FileInputStream/Reader` without try-with-resources (Java)
- Detect missing `close()` calls on resources
- Detect resources acquired in try but not released in finally/catch
- Score: resource safety percentage
- Support Python, Java, TypeScript, C#
- 30+ tests

## Technical Approach
- Tree-sitter query based: look for open()/new FileInputStream() patterns
- Check if wrapped in `with` (Python) or try-with-resources (Java)
- Track variable assignments for resource acquisition
- Immutable result dataclasses
