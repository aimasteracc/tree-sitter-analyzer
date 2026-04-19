# Data Clump Detector

## Goal
Detect parameter groups (3+) that appear together across multiple functions — they should be extracted into a class.

## MVP Scope
- Detect parameter groups of 3+ appearing in 2+ functions
- Filter out self/this/cls parameters
- 4 languages: Python, JS/TS, Java, Go
- 30+ tests
- MCP tool integration

## Technical Approach
- Pure AST traversal, single-file scope
- Collect function parameters, build Counter of param sets
- Report sets appearing ≥ threshold times (default 2)
- Follows existing 63-analyzer architecture exactly
- No new dependencies

## Issue Types
1. data_clump - parameter group of 3+ appearing in 2+ functions
