# Requirements - Project indexing with TOON

## Current State Analysis
The project is a complex multi-language analyzer with many modules. Navigating the codebase requires frequent file reads, which consumes significant time and tokens.

## Problem Identification
- High token cost when reading full source files for context.
- Lack of a centralized, machine-readable "map" of the project structure.
- Difficulty in performing cross-module structural consistency checks.

## Goals & Objectives
- Generate a comprehensive structural map of the project using the **TOON (Token-Optimized Output Notation)** format.
- Store the map in `.kiro/project_map.toon` for future Agent reference.
- Identify "structural debt" (empty methods, inconsistent visibility) using the generated map.

## Non-functional Requirements
- **Token Efficiency**: Use TOON format to minimize map size.
- **Persistence**: The map must be saved to disk.
- **Automation**: The process should be scriptable for periodic updates.
