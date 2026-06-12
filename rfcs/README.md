# tree-sitter-analyzer RFCs

> Substantial changes to tree-sitter-analyzer (TSA) go through a Request for
> Comments (RFC) process. This directory holds them. Modeled on the sibling
> [mycelium](https://github.com/aimasteracc/mycelium) RFC process, adapted for
> TSA's Python / MCP stack.

## Why RFCs

TSA is built spec-driven and TDD-style. Before code, there is a contract. The
RFC is that contract — and, as we learned the hard way, **a spec reviewed
before implementation catches architecture-level dead-ends** (e.g. "this
design can't get a session object") that a loose `docs/*.md` would not.

## What needs an RFC

| Class of change | RFC required? |
|---|---|
| Bug fix | ❌ Issue + PR is enough |
| Internal refactor, no API/MCP impact | ❌ |
| New CLI flag / MCP action (behavior change) | 🟡 Lightweight RFC |
| Public API or MCP facade/tool addition | ✅ Yes |
| Public API / MCP surface change or removal | ✅ Yes |
| ast_cache schema change | ✅ Yes — with migration plan + schema version |
| New language plugin | ❌ Issue (follow the plugin contract) |
| Performance/SLA change | ✅ Yes |
| Cross-surface (CLI↔MCP) parity change | ✅ Yes |
| Locked design-decision change (TOON default, project_root, …) | ✅ Yes — needs explicit user approval (see CLAUDE.md) |

## Lifecycle

```
1. Draft         — copy 0000-template.md → NNNN-title.md, PR to develop
2. Discussion    — comments on the PR (Codex review included — never ignored)
3. FCP           — Final Comment Period, kicked off by a maintainer
4. Outcome       — Accepted | Rejected | Withdrawn
5. Implementation — tracking issue, one PR per phase, TDD
6. Shipped       — Status → 'shipped' / 'implemented' when impl merges; flip the
                   §"Acceptance criteria" checkboxes as each lands
```

After merge, RFCs are immutable except for status updates and clarifications.
To change an accepted RFC, write a new RFC that supersedes it (note the
supersede in both).

## Status values

`draft` → `accepted` → `implemented` (or `rejected` / `withdrawn` / `superseded`).
Put the status + the PR/version that shipped it on the RFC's `Status` line.

## Numbering

Zero-padded 4 digits, monotonic. `0000` is the template. Pick the next free
number; if two RFCs collide on a number in flight, the later-merged one renames.

## Index

| RFC | Title | Status |
|---|---|---|
| [0001](0001-reactive-push.md) | Reactive push — virtual-DOM last mile | implemented |
| [0002](0002-callee-resolution.md) | Callee resolution — bare names to resolved symbols | implemented |
| [0003](0003-coverage-aware-test-gap.md) | Coverage-aware test-gap analysis — consume coverage.json, graph-enrich gaps | implemented |
| [0004](0004-stdlib-method-resolution.md) | Stdlib method resolution — classify bare stdlib method names | implemented |
| [0005](0005-external-method-resolution.md) | External-library method resolution — classify bare external method names | implemented |
| [0006](0006-context-progressive-disclosure.md) | Context progressive disclosure — lean nav context, opt-in graph | implemented |
| [0007](0007-builtin-method-resolution.md) | Builtin method resolution — classify qualified-builtin method calls | implemented |
| [0008](0008-multilang-method-classification.md) | Multi-language method classification — beyond Python | implemented (Python+Java; Go/JS/TS/C++/Rust via RFC-0010 #346-#350) |
| [0009](0009-nav-context-self-sufficiency.md) | nav context self-sufficiency — answer in one call | accepted (A/B/C implemented #330/#331/#333; measured turn-drop pending) |
| [0010](0010-resolver-language-registry.md) | Resolver language registry — scale the correctness moat to N languages | implemented (foundation #345; first wave go/js/ts/cpp/rust #346-#350) |
| [0011](0011-miswire-audit.md) | Mis-Wire Audit — the run-on-your-repo correctness demo | accepted (console entrypoint shipped; CLI subcommand + pre-seed + README surgery tracked) |
| [0012](0012-toon-json-dedup.md) | Eliminate TOON/JSON metadata duplication in MCP responses | accepted (Phase 1 implemented; Phase 2 deferred) |
| [0013](0013-facade-dropped-param-visibility.md) | Facade dropped-parameter visibility — `ignored_params` surface | accepted |
| [0014](0014-instant-edit-safety.md) | Instant edit safety — test-noise partition, test-map, and co-change | accepted (Phase A #461; Phase B #463; Phase C #466; integration test + DF-16 dogfood deferred) |
| [0015](0015-instant-uml-family.md) | Instant UML family — scoping fixes + activity/state diagrams | implemented (Phase 1 #462; P2-A #472; P2-B #475; v1.23.0) |

## Roadmap

See [ROADMAP-beyond-codegraph.md](ROADMAP-beyond-codegraph.md) for planned future directions beyond the current correctness-moat work.
