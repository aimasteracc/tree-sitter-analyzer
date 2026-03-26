# Tree-Sitter-Analyzer: Strategy Update
# (Bilingual: English for AI / 中文供人阅读)

Status: Draft — Extends tree-sitter-analyzer-ai-context-engine-strategy.md
Last Updated: 2026-03-26
Research basis: Call Graph Analyzer (internal, closed-source), PageIndex, GitNexus,
Evolver, CLI-Anything, CocoIndex Code

---

# PART A — ENGLISH (for AI context)

## Purpose of This Document

This document extends the existing strategy document
`tree-sitter-analyzer-ai-context-engine-strategy.md`. That document established the
correct category framing: Tree-Sitter-Analyzer (TSA) is a local-first code context
engine, not a parser wrapper.

This update incorporates two new research inputs:

1. Internal competitive analysis: Call Graph Analyzer (CGA), a closed-source internal
   project with broader enterprise adoption than TSA.
2. Open-source landscape analysis: five relevant open-source projects (PageIndex,
   GitNexus, Evolver, CLI-Anything, CocoIndex Code).

## Competitive Landscape: Who TSA Is Competing Against

### Internal closed-source competitor: Call Graph Analyzer (CGA)

CGA is an internal tool built after TSA. It uses tree-sitter for Java parsing and
stores results in Neo4j. It has broader internal market adoption. Its capabilities
include:

- Method call graph visualization (call tree, sequence diagram, class diagram)
- SQL/CRUD auto-extraction from Java source code
- JCL batch job flow analysis (mainframe job dependency graphs)
- COBOL-origin variable tracking ("Hensu" search)
- DB schema to code correlation
- Graph database persistence via Neo4j
- Batch Excel/CSV/HTML export
- Web-based interactive UI
- Deployed on AWS, accessed via VPN

CGA does NOT have: multi-language support beyond Java/XML/SQL, MCP delivery to AI
tools, token discipline features, project-boundary security enforcement, or local-first
operational model.

CGA's roadmap: Q3 FY26 adds AI integration — natural language interface, LLM
integration, impact analysis report generation, test case auto-generation. This is
TSA's current value proposition applied to CGA's graph data. If both teams build AI
integration independently, the company ends up with two overlapping AI interfaces
backed by different data models.

TSA and CGA share a tree-sitter parsing foundation. This is an integration seam, not
a coincidence.

### Open-source peer: GitNexus

GitNexus (github.com/abhigyanpatwari/GitNexus) is the most strategically significant
open-source project in this landscape. It is the closest functional mirror to TSA's
architecture and roadmap:

- Uses tree-sitter for parsing (same foundation as TSA)
- Delivers context via MCP (7 MCP tools vs TSA's current set)
- Processes 14+ languages
- Local-first, privacy-preserving
- Precomputes relational intelligence: call chains, import graphs, community clusters,
  execution flows
- Key MCP tools TSA does not have: `impact` (change impact analysis), `detect_changes`
  (incremental indexing), `context` (full dependency context in one call), `cypher`
  (graph query)
- Uses hybrid search: BM25 + semantic + reciprocal rank fusion

GitNexus does NOT have: project-boundary security enforcement, token discipline
features (count_only / summary_only etc.), enterprise safety controls, COBOL/Java
legacy system specialization, or CGA integration path.

GitNexus is open source. It is a peer, not a vendor. TSA can study its architecture,
contribute to it, or differentiate against it — but cannot ignore it.

### Open-source peer: CocoIndex Code

CocoIndex Code (github.com/aimasteracc/cocoindex-code) competes directly with TSA's
search layer. Key properties:

- AST-based semantic code search
- Built on Rust (performance advantage)
- Background daemon for warm-state indexing
- Claims 70% token reduction in AI coding workflows
- Local-first, zero API key required
- 28+ file type support
- MCP integration

CocoIndex does NOT have: structural extraction (methods, classes, call graphs),
security boundary enforcement, or large-file partial-read workflows.

### Open-source reference: PageIndex

PageIndex (github.com/VectifyAI/PageIndex) is a RAG system for long structured
documents. Its architecture is directly relevant to TSA's large-file problem:

- Converts documents into hierarchical outline trees (table of contents)
- LLM reasons about which branch to explore before retrieving content
- Vectorless: no embedding database required
- Achieves 98.7% accuracy on FinanceBench
- Explainable retrieval with traceable page references

The key lesson for TSA: outline-first retrieval is superior to flat chunking for
structured documents. Source code files have the same property — they are hierarchical
(package → class → method), and an AI should navigate the outline before retrieving
the body.

### Open-source reference: CLI-Anything

CLI-Anything (github.com/aimasteracc/CLI-Anything) automates the conversion of
any software into AI-agent-controllable CLI tools. The relevant pattern for TSA:

- SKILL.md generation: machine-readable tool discovery files for AI agents
- Intent-based naming: tool names describe what the AI wants to accomplish, not how
  the tool works internally
- Structured JSON output flags on all commands for machine consumption

### Open-source reference: Evolver

Evolver (github.com/EvoMap/evolver) is an auditable AI agent self-evolution engine.
The relevant concept for TSA:

- Analysis sessions as auditable, traceable artifacts
- Protocol-bound outputs with full provenance
- Governance over what AI agents did and why

## Updated Capability Gap Analysis

The following capabilities are present in the competitive landscape but absent in TSA.
They are listed in priority order based on customer value and implementation feasibility.

### Gap 1: Call graph and impact analysis (CRITICAL)

Present in: CGA (Java), GitNexus (14 languages)
What it enables: "If I change method X, what breaks?" and "What calls method X?"
TSA has method extraction but not method-to-method relationship tracking.
This is the single most requested capability class for AI-assisted code investigation.

### Gap 2: Outline-first retrieval (HIGH)

Present in: PageIndex (documents), GitNexus (code)
What it enables: AI navigates a structural outline before requesting content, reducing
token consumption by 60-80% compared to flat content extraction.
TSA has partial-read and structure tables, but no explicit outline-first protocol.

### Gap 3: Warm-state daemon / incremental indexing (MEDIUM)

Present in: CocoIndex Code, GitNexus
What it enables: Large-repo search responds in milliseconds instead of seconds because
the index is maintained in the background rather than computed per-request.
TSA recomputes on every call.

### Gap 4: Concrete token reduction benchmark (MEDIUM)

Present in: CocoIndex Code ("70% token reduction")
What it enables: A single defensible number that communicates TSA's value to engineers
who have not used it. TSA has the token discipline features but no published benchmark.

### Gap 5: Intent-based MCP tool naming (LOW, HIGH LEVERAGE)

Present in: GitNexus (`impact`, `context`, `detect_changes`)
What it enables: AI agents select the correct tool more reliably when names describe
intent rather than implementation. TSA's current names (`find_and_grep`, `list_files`)
describe mechanism, not outcome.

## TSA's Durable Differentiators

These are capabilities TSA has that no open-source peer currently matches:

1. Project-boundary enforcement with path traversal prevention — enterprise security
   requirement; neither GitNexus nor CocoIndex has this.
2. Token discipline feature suite (count_only, summary_only, group_by_file,
   total_only, suppress_output + output_file) — purpose-built for large-file and
   large-repo AI workflows.
3. COBOL-to-Java legacy system specialization — original wedge use case; still
   unmatched by general-purpose tools.
4. CGA integration path — only TSA shares a tree-sitter foundation with CGA and
   can serve as CGA's AI delivery layer. GitNexus has no path to CGA integration.
5. 17-language breadth — wider than GitNexus (14) and CocoIndex (28 file types but
   no structural extraction for most).

## Updated Architecture Direction

The original strategy document described this evolution:

```
Current:
  fd/list_files -> rg/search_content/find_and_grep
    -> tree-sitter query/partial read -> AI

Next (from original doc):
  boundary-scoped file set -> CandidateSearchService (local text index prefilter)
    -> rg exact match -> tree-sitter structural extraction
    -> token-optimized AI context
```

This update adds two new layers informed by the landscape analysis:

```
Extended next shape:
  boundary-scoped file set
    -> CandidateSearchService (local prefilter, warm daemon)
    -> rg exact match
    -> outline-first structural map (package -> class -> method tree)
    -> AI navigation: which branch?
    -> targeted structural extraction (method body, call graph, SQL refs)
    -> token-optimized delivery via MCP
    -> optional: CGA graph adapter (Neo4j query for Java call graphs)
```

New named services to introduce (in addition to CandidateSearchService):

- `OutlineService` — builds and serves the hierarchical code outline for a file or
  package, enabling outline-first AI navigation
- `CallGraphService` — tracks method-to-method call relationships, initially for
  Java; feeds the `impact` MCP tool
- `CGAAdapter` (optional, additive) — queries CGA's Neo4j instance when available,
  falling back to CallGraphService when not

## Updated MCP Tool Inventory

Current tools describe mechanism. Proposed additions and renames describe intent.

Existing tools (keep, consider renaming):
- `list_files` → consider alias `map_project_structure`
- `search_content` → consider alias `locate_usage`
- `find_and_grep` → consider alias `find_impacted_files`
- `analyze_file` → keep; add outline mode

New tools to add (modeled on GitNexus gaps + CGA integration):
- `get_code_outline` — returns hierarchical outline of a file or module without
  content; enables outline-first navigation
- `trace_impact` — given a method or class name, returns all callers and callees;
  answers "what breaks if I change X?"
- `get_call_chain` — traces execution path from an entry point to a target method
- `map_sql_usage` — returns all SQL operations in scope, mapped to their calling
  methods (Java focus initially)

## Updated SMART Workflow Mapping

The SMART workflow now maps explicitly to tool responsibilities:

```
Set     -> list_files / map_project_structure
           (establish project boundary, enumerate file scope)

Map     -> get_code_outline
           (build hierarchical structure map; AI navigates before retrieving)

Analyze -> trace_impact / map_sql_usage / CallGraphService
           (dependency analysis, impact scope, SQL/DB surface)

Retrieve -> analyze_file / search_content / find_and_grep
            (targeted extraction of exactly what the AI needs)

Trace   -> get_call_chain / sequence diagram (via CGA adapter if available)
           (execution path tracing, call sequence reconstruction)
```

## Updated Strategic Bets

The original document proposed three bets. This update adds two more.

### Bet 1 (unchanged): Reposition the product

Change the primary narrative from "tree-sitter analysis" to "AI code context engine."

### Bet 2 (unchanged): Add CandidateSearchService

Introduce a local indexing prefilter for large-repository search. Additive,
experimental, optional at first.

### Bet 3 (unchanged): Turn SMART into product doctrine

SMART is the operating model. Make it the standard onboarding path.

### Bet 4 (new): Add outline-first retrieval

Introduce `get_code_outline` as a first-class MCP tool. This is the single change
that most directly competes with GitNexus's precomputed graph approach while
remaining fully consistent with TSA's AST-based foundation. It costs one new tool
and enables a qualitatively different AI navigation pattern.

### Bet 5 (new): Ship a benchmark number

Measure token consumption for a representative large Java file under three conditions:
(a) naive full-file dump, (b) TSA structural extraction, (c) TSA outline-first
navigation. Publish the ratio in the README first sentence. This converts TSA's token
discipline story from a feature description into a defensible claim.

## Updated One-Line Description

Tree-Sitter-Analyzer is a local-first code context engine for AI-assisted development,
combining fast retrieval, AST-based structural analysis, and secure MCP integration —
with outline-first navigation and impact analysis for large and complex codebases.

## Updated Commander's Intent

We are not building a better parser. We are not building a visualization tool.
We are building the secure local context layer that makes AI usable on real codebases —
and the integration layer that connects closed-source graph tools like CGA with
open AI agents.

## Updated 90-Day Agenda

### Phase 0 (immediate, before anything else): Establish CGA collaboration

- Contact CGA team (NTA 区分6)
- Propose: TSA owns AI delivery (MCP), CGA owns graph analysis (Neo4j)
- Specific ask: CGA exposes a read API from Neo4j; TSA builds CGAAdapter
- Rationale: CGA Q3 AI integration is 1-2 quarters away; this window closes soon
- If CGA declines: TSA builds CallGraphService independently; the capability is
  needed regardless

### Phase 1 (weeks 1-4): Narrative correction (from original doc, unchanged)

- Rewrite README with updated one-line description
- Add benchmark number (token reduction measurement)
- Standardize category wording

### Phase 2 (weeks 4-8): Architecture additions

- Ship `get_code_outline` MCP tool
- Introduce CandidateSearchService (from original doc)
- Measure latency improvement on large repos

### Phase 3 (weeks 8-12): Platform consolidation

- Ship `trace_impact` MCP tool (CallGraphService or CGAAdapter)
- Make SMART the standard onboarding path with explicit tool mapping
- Publish SKILL.md for each MCP tool (agent-discoverable documentation)

## Proof Points Updated

Original proof points remain valid. Add:

- Impact analysis capability via `trace_impact` (new)
- Outline-first navigation via `get_code_outline` (new)
- Quantified token reduction benchmark (new — number TBD from measurement)
- CGA integration path (new — if collaboration agreed)
- Open-source positioning: security + enterprise controls unavailable in GitNexus
  or CocoIndex (new)

---