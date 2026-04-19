# Reflection Usage Detector

## Goal
Detect reflection and dynamic code execution patterns that make code hard to audit, test, and secure.

## MVP Scope
- Detect eval/exec/getattr/compile in Python
- Detect eval/Function/new Function in JS/TS
- Detect Class.forName/Method.invoke/.newInstance in Java
- Detect reflect.DeepEqual/ValueOf/TypeOf in Go
- Report findings with severity levels (high for eval/exec, medium for reflection)
- 35+ tests

## Technical Approach
- Pure AST pattern matching via BaseAnalyzer
- Walk call expressions, match function/object.name patterns
- Severity: eval/exec = high, getattr/setattr = medium, reflection = medium
- 4 languages: Python, JS/TS, Java, Go
