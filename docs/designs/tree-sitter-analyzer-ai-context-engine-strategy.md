# Tree-Sitter-Analyzer: AI Context Engine Strategy

Status: Draft
Audience: Product, engineering, internal champions
Last Updated: 2026-03-26

## Executive Summary

Tree-Sitter-Analyzer should not be positioned as "a tree-sitter-based code analysis tool."

That framing undersells what already exists in this repository. The product already combines:

- Fast repository retrieval with `fd` and `ripgrep`
- AST-based structural analysis across 17 languages
- MCP delivery into Claude Desktop, Cursor, and Roo Code
- Project-boundary enforcement and local-only security controls
- Token-optimized workflows for large files and large repositories

The stronger category is:

`Tree-Sitter-Analyzer is a local-first code context engine for AI-assisted development.`

Its job is not just to parse code. Its job is to help humans and AI agents fetch only the code context they actually need, safely, quickly, and with structural precision.

## The Category We Should Own

### Weak framing

- Code analysis tool
- Tree-sitter utility
- Better grep for code
- MCP helper for large files

### Strong framing

- Local-first code context engine
- Secure context infrastructure for AI agents
- Retrieval + structure layer for large codebases
- AI-ready code understanding pipeline for enterprise repositories

## Why This Matters

The existing story is accurate but too small. It explains how the product was born, but not the size of the opportunity.

The real opportunity is larger:

1. AI coding tools still need search.
2. Large repositories still break naive "paste the whole file into the model" workflows.
3. Security-sensitive teams still cannot send source code to remote indexing services.
4. Fast text retrieval alone is not enough; AI also needs structural slicing and token discipline.

Tree-Sitter-Analyzer already sits at this intersection.

## Product Thesis

### One-sentence thesis

Tree-Sitter-Analyzer is a local-first code context engine that combines fast retrieval, AST-based structure, and secure delivery so AI tools can work effectively on large codebases.

### Expanded thesis

In modern AI-assisted development, the bottleneck is no longer only parsing code. The bottleneck is getting the right context to the model fast enough, safely enough, and in a shape the model can actually use.

Tree-Sitter-Analyzer solves that by turning repository exploration into a pipeline:

`find the right files -> find the right matches -> extract the right structure -> send only the right context`

That is a product category, not a utility feature.

## What Already Exists

The current repo already supports the core of this story.

### 1. Retrieval layer

- `list_files` for boundary-scoped file discovery
- `search_content` for content search
- `find_and_grep` for two-stage search workflows

### 2. Structural understanding layer

- AST-based analysis via tree-sitter
- Query-driven extraction of methods, classes, functions, imports, and other code elements
- Partial read and structure table outputs for large-file workflows

### 3. Delivery layer

- MCP server integration for Claude Desktop, Cursor, and Roo Code
- CLI and Python API as parallel surfaces over shared core capabilities

### 4. Security layer

- Project-boundary enforcement
- Path traversal prevention
- Input sanitization
- Error sanitization
- Local-first operational model

### 5. Token discipline layer

- `count_only`
- `summary_only`
- `group_by_file`
- `total_only`
- `suppress_output` plus `output_file`

This is already much closer to a context engine than to a parser wrapper.

## Strategic Reframe

### Current implied message

"We built a useful internal tool because other search tools were slow, unsafe, or incomplete."

### Better message

"We built a local-first code context engine because AI-assisted development breaks down on large, sensitive repositories unless retrieval, structure, and security are designed together."

That framing is more ambitious, more defensible, and more future-proof.

## Wedge, Expansion, and Endgame

### Initial wedge

Win first with the most painful use case:

- Large Java repositories
- Legacy or migrated systems such as COBOL-to-Java conversions
- Incident response and impact analysis
- AI coding assistants that need targeted context instead of raw file dumps

### Expansion path

After proving the wedge, expand the same engine into:

- General large-repo AI development
- Cross-language code navigation
- Enterprise-local AI workflows
- Secure MCP infrastructure for internal engineering teams

### Endgame

Become the standard local context layer that sits between codebases and AI agents.

The long-term competition is not "other tree-sitter tools." It is any system that tries to own how AI gets code context.

## Lessons From Fast Regex Search

The important lesson from Cursor's fast regex search direction is not "make `rg` faster at all costs."

The lesson is:

`search is not an accessory for AI agents; it is core infrastructure.`

Tree-Sitter-Analyzer should absorb that lesson without losing its differentiation.

### What to copy

- Treat retrieval latency as a first-class product concern
- Add a candidate-generation layer before exact regex scanning on very large repositories
- Keep the entire workflow local-first
- Optimize for the full AI workflow, not just isolated benchmark wins

### What not to copy

- Do not collapse the product into "faster regex search"
- Do not weaken project-boundary controls to chase global indexing
- Do not let lexical retrieval overshadow AST-based structural precision

## Product Architecture Direction

The current retrieval pipeline can be evolved instead of replaced.

### Current shape

`fd/list_files -> rg/search_content/find_and_grep -> tree-sitter query/partial read -> AI`

### Next shape

`boundary-scoped file set -> local text index candidate filter -> rg exact match -> tree-sitter structural extraction -> token-optimized AI context`

### New layer to introduce

Recommended service name:

- `CandidateSearchService`

Acceptable alternative:

- `TextIndexService`

### Role of the new layer

- Operate only inside project boundaries
- Build a local candidate set for large-repo search
- Feed exact-match tools instead of replacing them
- Reduce latency before AST extraction
- Preserve existing CLI and MCP behavior as the default path

## Three Concrete Product Bets

### Bet 1: Reposition the product

Change the primary narrative from "tree-sitter analysis" to "AI code context engine."

This is the highest-leverage move because it changes how every feature is understood.

### Bet 2: Add an optional candidate-generation layer

Introduce a local indexing or prefilter path ahead of `search_content` and `find_and_grep` for large repositories.

This should be additive, experimental, and optional at first.

### Bet 3: Turn SMART into product doctrine

The SMART workflow is not just documentation. It is the operating model:

`Set -> Map -> Analyze -> Retrieve -> Trace`

This is the most natural way to teach users, AI agents, and internal teams how to consume the platform.

## Messaging Pillars

### Pillar 1: Fast find

Find relevant files and matches quickly in large repositories without scanning the whole world blindly.

### Pillar 2: Precise read

Use AST-aware structure and targeted extraction instead of dumping full files into the model.

### Pillar 3: Local security

Keep code and analysis local, inside clear project boundaries, with enterprise-friendly safety controls.

## Recommended One-Line Description

Tree-Sitter-Analyzer is a local-first code context engine for AI-assisted development, combining fast repository retrieval, AST-based structural analysis, and secure MCP integration.

## Recommended Intro Copy

Tree-Sitter-Analyzer is a local-first code context engine for large and complex codebases. It helps developers and AI coding tools retrieve only the code context they actually need by combining fast search, AST-based structural analysis, and strict project-boundary controls.

It was born from a real constraint: extremely large Java files produced by COBOL-to-Java conversion could not be handed to AI models efficiently, and sending entire files created both token waste and context noise. Tree-Sitter-Analyzer solves this by breaking source code into meaningful structural units and enabling precise retrieval instead of raw file dumping.

Beyond parsing, Tree-Sitter-Analyzer unifies file discovery, content search, structural querying, and partial extraction into a single local-first workflow. This improves investigation speed, reduces AI token cost, and raises the quality of code understanding for incident response, impact analysis, legacy modernization, and AI-assisted development.

All processing runs locally. Source code and analysis results do not need to leave the environment, and search scope remains controllable inside project boundaries. This makes the product especially strong for enterprise and internal engineering environments.

## Proof Points We Can Defend

- 17-language support across enterprise, systems, web, data, and config domains
- MCP integration designed as a first-class interface, not an afterthought
- Two-stage search already exists in the product surface
- Token optimization is a documented product feature
- Security boundaries are explicit in both design and tests
- CLI, MCP, and Python API share a common platform core

## Messaging Risks

- Do not claim a single exact test count unless pulled from current CI
- Do not overclaim "semantic understanding" beyond structural analysis and retrieval
- Do not describe the product as replacing `ripgrep`; it orchestrates and upgrades the full workflow

## 90-Day Strategic Agenda

### Phase 1: Narrative correction

- Rewrite top-level product messaging in README and internal intro materials
- Separate "internal stable version" and "public latest version" language clearly
- Standardize category wording around "local-first code context engine"

### Phase 2: Architecture experiment

- Introduce `CandidateSearchService` as an experimental prefilter layer
- Wire it first into `search_content`
- Measure large-repo latency improvement before touching broader tool surfaces

### Phase 3: Platform consolidation

- Expose the retrieval pipeline more explicitly in docs and MCP guidance
- Make SMART the standard onboarding path
- Position the product as context infrastructure for AI agents, not just analysis tooling

## Commander's Intent

If the team remembers only one sentence, it should be this:

`We are not building a better parser. We are building the local context layer that makes AI usable on real codebases.`
when was that now where did statue