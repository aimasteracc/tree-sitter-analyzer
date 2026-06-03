# Reactive Push Spec — virtual-DOM last mile for TSA

> Status: **Draft** (2026-06-03). Spec-first per CLAUDE.md "plan complex features
> before implementing". Models mycelium's RFC-0106/0107/0108 (the user's own
> project, where push/subscribe already shipped) onto TSA's MCP + watch stack.

## 1. Motivation

TSA already has the **pull half** of the reactive ("virtual DOM") metaphor:
`IncrementalSync` (content-hash diff → rebuild only changed files, ~15ms over
997 files) + `FileWatcherDaemon` (background thread that re-syncs on change).
What's missing is the **push half**: when a file changes, the server should
proactively tell a subscribed agent "your query result changed" instead of the
agent having to poll.

This is the documented gap in `project_mycelium-ideas-as-tsa-chips` ("virtual
DOM 缺口：缺主动 push/subscription"). Closing it makes Hyphae selectors both
*queryable* and *subscribable*, and brings TSA to parity with mycelium's
reactive last mile.

## 2. Feasibility (confirmed)

The Python MCP SDK (`mcp.server.session.ServerSession`) exposes server-initiated
notifications: `send_resource_updated(uri)`, `send_resource_list_changed()`,
and a generic `send_notification(...)`. So out-of-band server→client push is
supported by the transport — the work is wiring, not protocol invention.

## 3. Design

### 3.1 Subscription model

- An agent subscribes a **Hyphae selector** (e.g. `.class:implements(#Writeable)`).
- The subscription is exposed as a **subscribable MCP resource** with a stable
  URI: `tsa://hyphae/{url-encoded-selector}`.
- `SubscriptionRegistry` holds, per subscription:
  `{ sub_id, selector_ast, last_result_keys: set[(name,file,line)],
     min_interval_s, session_ref }`.

### 3.2 Push mechanism

- On a relevant change, the server calls `session.send_resource_updated(uri)`
  (preferred — standard MCP, broad client support). The agent then re-reads the
  resource to get the new result set.
- Rationale for resource-updated over a custom `tsa/graphChanged` notification:
  standard notifications are understood by all MCP clients without bespoke
  handling; mycelium chose a custom method because its Rust client is bespoke.
- Delivery is **best-effort** (mirrors mycelium RFC-0106): a dead client's send
  failure marks the subscription for GC, never blocks the watch loop.

### 3.3 Delta computation

- `FileWatcherDaemon` change → `IncrementalSync.sync()` → for each active
  subscription whose changed files intersect the selector's candidate space,
  re-evaluate the selector.
- Compare `last_result_keys` vs `new_result_keys`:
  `delta = { added: [...], removed: [...] }`.
- Push only when `delta` is non-empty. Update `last_result_keys`.

### 3.4 Session lifecycle — capture at subscribe time

> **Constraint (Codex review, MCP SDK 1.17.0):** `Server.run()` constructs the
> `ServerSession` as a *local* and TSA's `_run_server_loop` just awaits that
> black-box call (`server.py` `_run_server_loop`). Neither the watcher callback
> nor a resource handler is handed a session object — so the registry CANNOT
> obtain the session from the run loop. A naïve "weakref from `server.run()`"
> is unimplementable.

- **Resolution — capture from the request context, not the run loop.** The
  `subscribe` call IS a tool-call request, so inside its handler
  `server.request_context.session` is populated (per-request contextvar). The
  session object is **per-connection** (all requests on one connection share
  it), so capturing it once at subscribe time yields a reference valid for the
  whole connection. Store that reference (weakref) + the running loop
  (`asyncio.get_running_loop()`, also captured in-handler) on the subscription.
- A subscription is GC'd when: (a) its captured session is gone / closed,
  (b) a send raises (dead client), or (c) a TTL elapses with no client read
  (defence-in-depth, mirrors RFC-0107 D3).
- If `server.request_context.session` is ever unavailable at subscribe time,
  `subscribe` fails fast with a clear error rather than registering a
  push-incapable subscription.

### 3.5 Watch → push bridge (the risk surface)

- `FileWatcherDaemon` runs on a background thread; MCP runs on an asyncio loop.
- Bridge: the watch callback schedules the push coroutine onto the **loop
  captured at subscribe time** (§3.4) via
  `asyncio.run_coroutine_threadsafe(push_coro, loop)`, calling
  `send_resource_updated` on the **session captured at subscribe time**. This
  sidesteps the run-loop's inaccessible local session entirely.
- Alternative considered: rewrite the watcher as a native asyncio task. Deferred
  — the threaded daemon already works; threadsafe scheduling is the smaller,
  lower-risk change.

### 3.6 Throttling

- Per-subscription `min_interval_s` (default 2s) coalesces bursts (editor
  save-all, git checkout). Mirrors mycelium RFC-0107 `min_interval`.

## 4. MCP surface

- `search action=subscribe` — params: `selector` (required), `min_interval`.
  Returns `{ sub_id, resource_uri }`.
- `search action=unsubscribe` — params: `sub_id`.
- Resource read on `tsa://hyphae/{selector}` — runs the selector, returns the
  current result set (same shape as `action=select`).

## 5. Failure modes

| Mode | Handling |
|---|---|
| Dead client (send raises) | Mark sub dead → GC; never block watch loop |
| Session leak after disconnect | WeakRef + TTL GC |
| Push lost (best-effort) | Acceptable; agent re-reads on next interaction |
| Re-eval storm (save-all) | `min_interval_s` throttle + coalesce |
| Selector errors at re-eval time | Log + keep sub; do not push garbage |

## 6. Implementation phases (each its own PR, TDD)

1. **Pure logic** (no async): `SubscriptionRegistry` + delta computation over a
   fake cache. Fully unit-testable.
2. **Resource handler**: register `tsa://hyphae/*` resource; read = run selector.
3. **Watch→push bridge**: threadsafe scheduling of `send_resource_updated`,
   loop-reference capture, min_interval throttle.
4. **Lifecycle/GC**: weakref sessions, dead-client detection, TTL sweep.
5. **Dogfood**: subscribe a selector, edit a file, assert the agent receives an
   update and re-reads the changed result.

Phases 1–2 are low-risk (pure + standard MCP). Phase 3 is the asyncio risk
surface and gets the most scrutiny.

## 7. Open questions (for review)

- `send_resource_updated` vs custom `tsa/graphChanged` — start with the former;
  revisit if clients need richer payloads.
- Threadsafe-schedule vs native-asyncio watcher — start with the former.
- Default `min_interval_s` — proposed 2s.
- Should the resource payload carry the delta, or just signal "re-read"? MCP
  resource-updated is a signal; the delta is recomputed on read. Start signal-only.

## 8. References

- mycelium RFC-0106 (push graphChanged), RFC-0107 (scoped delta subscribe),
  RFC-0108 (reactive query subscriptions) — the shipped Rust precedent.
- TSA `incremental_sync.py`, `file_watcher.py` — the existing pull half.
- TSA Hyphae (`tree_sitter_analyzer/hyphae/`) — the subscribable query layer.
