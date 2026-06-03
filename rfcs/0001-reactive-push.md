# RFC-0001: Reactive push — virtual-DOM last mile

- **Status**: draft
- **Author(s)**: @aimasteracc
- **Created**: 2026-06-03
- **Last updated**: 2026-06-03
- **Tracking issue**: TBD
- **Affected source paths**:
  - `tree_sitter_analyzer/hyphae/` (subscribable query layer)
  - `tree_sitter_analyzer/file_watcher.py`, `tree_sitter_analyzer/incremental_sync.py` (the pull half)
  - `tree_sitter_analyzer/mcp/server.py`, `tree_sitter_analyzer/mcp/tools/search_facade.py` (subscribe/unsubscribe + resource)
  - `tests/unit/hyphae/`, `tests/e2e/`

## Summary

Add the **push half** of TSA's reactive ("virtual DOM") model: let an AI agent
subscribe a Hyphae selector, and have the server proactively notify it when a
file change alters that selector's result — instead of the agent polling. Models
the sibling [mycelium](https://github.com/aimasteracc/mycelium) project's shipped
RFC-0106/0107/0108 onto TSA's MCP + watch stack.

## Motivation

TSA already has the **pull half**: `IncrementalSync` (content-hash diff → rebuild
only changed files, ~15ms over 997 files) + `FileWatcherDaemon` (background
re-sync on change). The gap — documented in the mycelium-ideas notes as "virtual
DOM 缺口：缺主动 push/subscription" — is that a changed file never *reaches* the
agent; it must re-query. Closing this makes Hyphae selectors both *queryable* and
*subscribable*, reaching parity with mycelium's reactive last mile (the
differentiator: "看不见但谁动一下大家都能感觉到" — the "感觉到" is push).

## Detailed design

### MCP surface (facade + action)

- `search action=subscribe` — params: `selector` (required Hyphae string),
  `min_interval` (optional seconds, default 2). Returns `{ sub_id, resource_uri }`.
- `search action=unsubscribe` — params: `sub_id`.
- Resource read on `tsa://hyphae/{url-encoded-selector}` — runs the selector,
  returns the current result set (same shape as `action=select`).

### Data structures

`SubscriptionRegistry`, one entry per subscription:
`{ sub_id, selector_ast, last_result_keys: set[(name,file,line)], min_interval_s,
   session_ref: weakref, loop_ref }`.

### Push mechanism

On a relevant change the server calls `session.send_resource_updated(uri)`
(standard MCP, broad client support); the agent re-reads the resource for the new
set. Delivery is **best-effort** (mirrors mycelium RFC-0106): a dead client's
send failure marks the subscription for GC, never blocking the watch loop.

### Session acquisition — capture at subscribe time

> **Constraint (Codex review on the spec PR, MCP SDK 1.17.0):** `Server.run()`
> constructs the `ServerSession` as a *local*; TSA's `_run_server_loop` just
> awaits that black-box call. Neither the watcher callback nor a resource handler
> is handed a session — so the registry **cannot** obtain the session from the
> run loop. A "weakref from `server.run()`" is unimplementable.

**Resolution:** the `subscribe` call IS a tool-call request, so inside its
handler `server.request_context.session` is populated (per-request contextvar).
The session is **per-connection** (all requests on one connection share it), so
capturing it once at subscribe time gives a reference valid for the whole
connection. Also capture the loop via `asyncio.get_running_loop()` in-handler.
The watch→push bridge then uses these captured refs. `subscribe` fails fast if
the context session is unavailable.

### Watch → push bridge (the risk surface)

`FileWatcherDaemon` runs on a background thread; MCP on an asyncio loop. The
watch callback schedules the push coroutine onto the **captured loop** via
`asyncio.run_coroutine_threadsafe(push_coro, loop)`, calling
`send_resource_updated` on the **captured session**. Per change: re-eval each
subscription whose changed files intersect its candidate space, diff
`last_result_keys` vs new, push only on non-empty delta, update keys.

### Concurrency / throttling

Per-subscription `min_interval_s` coalesces bursts (save-all, git checkout).

## Three-Surface impact (CLI ↔ MCP parity)

Push is inherently a long-lived-connection concern, which the stateless CLI does
not have. CLI parity is satisfied by `mycelium`-style `watch --subscribe` only if
TSA grows a persistent CLI `watch` mode; until then, subscribe/unsubscribe are
**MCP-only by design** (documented asymmetry, like the TOON-vs-JSON default).
The underlying Hyphae query (`search action=select`) remains 1:1 across surfaces.

## Drawbacks

- Adds long-lived state (subscriptions, session refs) to an otherwise
  request-scoped server — leak risk, mitigated by weakref + TTL + dead-client GC.
- The watch-thread → asyncio-loop bridge is the most error-prone part (deadlock,
  lost pushes). Mitigated by `run_coroutine_threadsafe` + best-effort delivery.

## Alternatives

- **Custom `tsa/graphChanged` notification** (like mycelium's): richer payload,
  but needs bespoke client handling. *Rejected for v1* — `send_resource_updated`
  is standard and every MCP client understands it. Revisit if clients need the
  delta inline.
- **Native-asyncio watcher** (rewrite `FileWatcherDaemon`): cleaner than
  thread→loop bridging, but larger blast radius. *Deferred* — the threaded daemon
  works; threadsafe scheduling is the smaller change.
- **Polling helper** (agent re-queries on a timer): no server changes, but that
  is exactly the pull status quo this RFC removes.

## Prior art

- **mycelium RFC-0106/0107/0108** (the user's sibling project) — the shipped Rust
  precedent: `mycelium/graphChanged` push, scoped per-batch delta subscribe, and
  reactive query subscriptions. We adopt the model; we diverge on transport
  (standard `send_resource_updated` vs custom method) and session acquisition
  (capture-at-subscribe vs Rust's peer-capture).
- **LSP `textDocument/publishDiagnostics`** — server-initiated push over a
  long-lived connection; same shape (server notifies, client reacts).

## Test plan (RED-first)

- Unit: `SubscriptionRegistry` add/remove/GC; delta computation (added/removed)
  over a fake cache. Pure, no async.
- Unit: subscribe handler captures session + loop from `request_context`; fails
  fast when absent.
- Integration: a simulated file change re-evaluates the right subscriptions and
  computes the right delta.
- e2e/dogfood: subscribe a selector, edit a file, assert the agent receives a
  resource-updated and re-reads the changed result.

## Acceptance criteria

- [ ] `SubscriptionRegistry` + delta computation (pure, unit-tested)
- [ ] `search action=subscribe` / `unsubscribe` wired; captures session+loop from `request_context`
- [ ] `tsa://hyphae/{selector}` resource read runs the selector
- [ ] watch→push bridge: change → re-eval → delta → `send_resource_updated`
- [ ] throttle (`min_interval`) + GC (weakref session + dead-client + TTL)
- [ ] dogfood: edit-file → agent receives update → re-reads new result
- [ ] docs/CODEMAPS updated; RFC status → implemented

## What this RFC does NOT do (deferred)

- Persistent CLI `watch --subscribe` mode (revisit for full three-surface).
- Inline delta payloads (resource-updated is a signal; delta recomputed on read).
- Cross-connection / multi-client fan-out beyond per-connection subscriptions.

## Open questions

1. `send_resource_updated` vs custom `tsa/graphChanged` — start with the former?
2. Threadsafe-schedule vs native-asyncio watcher — start with the former?
3. Default `min_interval_s` — proposed 2s.
4. Should `subscribe` re-use the existing `FileWatcherDaemon` instance or start a
   scoped one per connection?
