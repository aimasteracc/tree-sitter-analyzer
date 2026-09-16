# RFC-0035: Reactive subscription lifecycle ownership

- **Status**: implemented
- **Author(s)**: Codex
- **Created**: 2026-09-14
- **Last updated**: 2026-09-16
- **Implementation**: PR #1492, merged as `1b69997c`
- **Baseline**: `develop@7e1ed4f571c9180ebdf42d1ef6153bed4222587f`
- **Affected source paths**:
  - `tree_sitter_analyzer/mcp/subscription_lifecycle.py`
  - `tree_sitter_analyzer/mcp/server.py`
  - `tree_sitter_analyzer/mcp/watch_push_bridge.py`
  - `tree_sitter_analyzer/mcp/tools/ast_cache_tool.py`
  - `tree_sitter_analyzer/mcp/tools/hyphae_subscribe_tool.py`
  - `tree_sitter_analyzer/mcp/_tool_registry.py`
  - `tree_sitter_analyzer/mcp/tools/index_facade.py`
  - `tree_sitter_analyzer/mcp/tools/search_facade.py`

## Summary

Hyphae subscriptions must belong to the MCP connection, application run,
project epoch, selector incarnation, and watcher that created them. R1a binds
subscribe and unsubscribe operations to the SDK `ServerSession`. R1b adds an
application-owned lifecycle manager that retires subscriptions and pending
delivery work when their run, project, selector incarnation, or watch token is
no longer current.

This is an internal correctness repair. It does not add an MCP tool, action,
schema, URI, CLI flag, dependency, or public response field.

## Motivation

The original implementation derived a subscription identifier from the current
asyncio task. A single MCP connection can execute consecutive requests in
different tasks, while unrelated requests can run in the same task. Task
identity therefore cannot prove connection ownership.

Connection identity alone is also insufficient. Two server applications using
the same raw project root must not share subscriptions. A completed run must
not leave live records, and callbacks or sends created for an old project,
selector incarnation, or watcher must not update a replacement subscription.

The existing evaluation-failure isolation change is a semantic prerequisite:
failed evaluations must not be converted into empty results before lifecycle
code validates and commits a snapshot.

## Detailed design

### R1a: connection ownership

`subscribe` and `unsubscribe` read `request_ctx.get().session` once during the
tool request. Missing request context fails before any registry or transport
mutation. The connection-level opaque `sub_id` is derived from that live
session while the implementation retains a strong reference to it.

All requests on one connection reuse the same identifier; different
connections remain isolated. An explicit foreign `sub_id` is rejected before
mutation. Selector-only unsubscribe removes one selector and retains the
session, loop, and interval maps while sibling selectors remain. Removing the
last selector, or unsubscribing the whole session, clears all connection state.

Transport state is installed before the subscription is published to the
registry. A watcher can therefore never observe a registered subscription with
missing session, loop, or interval state.

### R1b: application and run ownership

Each `TreeSitterAnalyzerMCPServer` owns one
`SubscriptionLifecycleManager`. The canonical SDK server installs its public
lifespan callback. Each lifespan entry creates a unique run owner, which the
SDK exposes to request handlers through `request_ctx.lifespan_context`.
Subscribe and unsubscribe require both that owner and the real session.

The manager issues immutable subscription tickets containing:

- application identity;
- run owner;
- project root and monotonically increasing project epoch;
- connection identifier and selector incarnation;
- real session and event loop;
- the current revocable watch token.

Two applications remain isolated even when their raw roots are equal. Retiring
a run removes only that run's records and pending delivery work. Rebinding a
project advances the epoch before facade propagation or watcher cleanup, so
old callbacks become invalid immediately. Removing and recreating a selector
uses a new incarnation, preventing completion from the removed subscription
from advancing its replacement.

The watcher belongs to the application. Starting a watcher reserves the exact
raw root, epoch, cache source, and token before constructing or starting the
daemon outside the manager lock. A starting watcher retains ownership even
before `is_running()` becomes true. Stop, rebind, startup failure, and
application shutdown revoke the exact token. A timed-out stop retains pending
ownership and blocks replacement until cleanup completes.

### Delivery validation and concurrency

The bridge snapshots tickets under the manager lock, evaluates selectors
outside it, and then revalidates the complete ticket before committing the
registry delta. It schedules a send only for a still-current ticket.

Thread-to-loop handoff uses `loop.call_soon_threadsafe` with a synchronous
starter. The starter revalidates ownership before creating the coroutine and
task. Pending handles and tasks are tracked by ticket incarnation and removed
only when the same pending object completes. Cancellation and completion never
delete a replacement record.

No manager lock spans selector evaluation, an `await`, event-loop handoff,
task creation, cancellation callback, daemon start or stop, or thread join.
The lock order for state commit is manager then registry.

The SDK has no public immediate raw-disconnect hook. The contract therefore
covers cooperative run cleanup and lifespan `finally`; it does not claim
instant cleanup at socket EOF. A completed local SDK send also does not prove
that the client received or reread the resource.

## Three-Surface impact (CLI ↔ MCP parity)

The existing `search` facade subscribe and unsubscribe actions retain their
names, parameters, response shapes, resource URI, and JSON behavior. No CLI or
MCP surface is added or removed, so the registered tool and CLI flag sets stay
unchanged.

## Drawbacks

The lifecycle manager adds internal state and coordination around watcher
startup, project rebinding, and delivery. It deliberately rejects subscriptions
created outside a valid SDK request and application lifespan. Embedders that
call the tool directly must provide those real SDK contexts.

The design provides local scheduling and cleanup guarantees. It does not add a
delivery acknowledgement protocol.

## Alternatives

- Keep asyncio task identity: rejected because requests and connections do not
  have a one-to-one task relationship.
- Use only `ServerSession` identity: rejected because it cannot fence
  application, run, project, watcher, or replacement-selector lifetimes.
- Store the current run owner on shared tool instances: rejected because tool
  instances outlive and can serve multiple runs.
- Hold one lock through evaluation and sending: rejected because evaluator,
  event-loop, and daemon operations can block or re-enter lifecycle code.

## Prior art

This repair preserves the notification and registry behavior defined by
[RFC-0001](0001-reactive-push.md). It applies the same explicit ownership and
obsolete-candidate fencing principles used by
[RFC-0032](0032-index-writer-ownership.md) to subscriptions and watcher
callbacks.

## Test plan (RED-first)

R1a tests use SDK `RequestContext` and real connected in-memory MCP sessions to
prove:

1. one connection keeps its identifier across request tasks;
2. different connections are isolated;
3. missing context and foreign identifiers fail before mutation;
4. partial and final unsubscribe have distinct cleanup behavior;
5. transport state exists before registry publication.

R1b tests prove:

1. application, run, epoch, incarnation, and watch-token isolation;
2. run retirement, project rebind, watch stop, startup failure, and application
   shutdown cleanup;
3. stale callbacks and completion handlers cannot mutate replacements;
4. enqueue, task-creation, closed-loop, cancellation, and stop-timeout races
   leave no orphan pending state;
5. a valid owner and real SDK session complete an actual send, observed through
   an `Event` barrier.

Run the focused change-impact suite with four work-stealing workers and reruns
disabled. Then run the default quick gate and patch coverage against the actual
PR base.

## Acceptance criteria

- [x] Real SDK connections provide stable, isolated subscription ownership.
- [x] Invalid context and foreign ownership fail before mutation.
- [x] Application, run, project, selector, and watcher lifetimes fence all
  registry commits and scheduled sends.
- [x] Cleanup races preserve replacements and leave no orphan pending work.
- [x] Existing MCP, CLI, schema, URI, and response surfaces remain unchanged.
- [x] Focused tests, quick gate, Ruff, MyPy, build, and patch coverage pass on
  the final source candidate.
- [x] Codex review findings are triaged before merge.

PR #1492 completed R1a/R1b and passed the Linux, macOS, Windows, MCP E2E,
regression, SQL compatibility, patch coverage, and Codex review gates on its
final head. The deferred delivery features below remain outside this RFC's
implemented boundary.

## What this RFC does NOT do (deferred)

Delivery retries, trailing-edge coalescing, client acknowledgements, certified
resource reads, CLI transport work, and broader feedback-loop features remain
separate changes. This RFC neither specifies nor implements them.

## Open questions

None for the R1a/R1b implementation boundary.
