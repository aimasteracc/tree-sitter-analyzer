# Test Flakiness Detector

## Goal
Detect code patterns in tests that cause unreliable/flaky test results.

## MVP Scope
- Detect: sleep/wait calls, random/uuid usage, time-dependent assertions, shared mutable state, test ordering dependencies
- Languages: Python, JavaScript/TypeScript, Java
- Distinguish from test_smells (code quality) vs this (runtime reliability)

## Technical Approach
- Standalone analyzer inheriting BaseAnalyzer
- Only analyze test files (test_*.py, *.test.js, *Test.java)
- Pattern-based detection: time.sleep, setTimeout, Math.random, datetime.now in assertions, mutable class vars in test classes
- Output: TestFlakinessResult with risk factors per test function
