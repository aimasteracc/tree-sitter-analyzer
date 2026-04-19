# Mutable Multiplication Detector

## Goal
Detect `[[]] * n` patterns that create shared references

## MVP Scope
- Python-only
- Detect list/tuple multiplication with mutable children (list, dict, set, constructors)
- Exclude safe multiplication with immutable values

## Technical Approach
- Walk binary_operator nodes with `*` operator
- Check left operand for mutable children types
