# Lazy Class Detector

## Goal
Detect classes with too few methods or members that may not justify their existence

## MVP Scope
- Count methods and fields per class
- Flag classes with 0-1 methods and 0-2 fields
- 4 languages: Python, JS/TS, Java, Go
- Report with class name and member counts

## Technical Approach
- AST traversal: find class/struct/interface declarations
- Count method definitions and field/property declarations
- Python: class_definition > function_definition
- JS/TS: class_declaration > method_definition
- Java: class_declaration > method_declaration, field_declaration
- Go: type_declaration with struct
