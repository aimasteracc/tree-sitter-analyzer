# Await-in-Loop Detector

## Goal
Detect `await` inside for/while loops — serial async that should be parallelized

## MVP Scope
- Python + JavaScript/TypeScript
- Report per innermost containing loop
- Exclude nested functions (their awaits are their own concern)

## Technical Approach
- Walk AST for for_statement/while_statement nodes
- Check body for await_expression/await nodes
- Stop at nested loop or function boundaries
