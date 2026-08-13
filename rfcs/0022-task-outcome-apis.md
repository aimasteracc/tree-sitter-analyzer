# RFC-0022: Static task outcomes by primitive orchestration

- **Status**: draft; corrective design, no implementation
- **Author(s)**: project maintainers
- **Created**: 2026-08-08
- **Last updated**: 2026-08-13
- **Tracking issue**: TBD
- **Affected paths in later implementation only**: `tree_sitter_analyzer/task/`,
  existing `index`/`nav`/`edit` primitive adapters, their existing tests, and
  (only after the menu gate) MCP/CLI registries and codemaps.

## Summary

This RFC proposes three static outcomes over existing TSA facade actions:
`understand`, `plan_change`, and `assess_change`. The task layer validates,
routes, and normalizes primitive results; it never parses a patch or source,
resolves a symbol, builds a graph, evaluates a constraint, or runs a command.

The first implementation is deliberately not a ninth MCP facade. Phase A is an
internal Python API plus a non-registered experiment harness. Registration is
forbidden until the pre-registration tool-menu experiment in this RFC passes.
If it passes, MCP remains TOON-by-default and CLI JSON-by-default.

## Non-negotiable boundary

```text
internal Python / experiment request
  -> validate boundary and routing budget
  -> call existing routed facade action adapters, sequentially
  -> perform unconditional capability cleanup and record its fixed result
  -> freeze one TaskOutcome value
  -> serialize that value (JSON or TOON)
```

`tree_sitter_analyzer/task/` MUST NOT import analyzer internals or own a parser,
diff reader, filesystem/index scanner, identifier extractor, keyword router,
constraint engine, command runner, graph, or cache. It may perform schema
validation, stable sorting, caps, ID hashing, and table-driven aggregation only.
Task/diff text is untrusted data and never selects a callable or shell command.

## Phase 0: authoritative primitive capabilities (release prerequisite)

Phase A MUST NOT begin until these existing primitive adapters expose and test
all capabilities below. This is a prerequisite, not task-layer implementation.

### P0.1 Authoritative index snapshot oracle

`index.status` must return an opaque `snapshot_id`, an authoritative
`source_fingerprint`, `index_fingerprint`, `source_generation`, and
`completeness` (`complete`, `partial`, or `unknown`). `source_generation` is an
opaque token issued by the primitive-owned source oracle for the exact source
state certified by that index snapshot. Every graph-backed primitive echoes the
`snapshot_id` it actually read. Only primitive owners compute these values; a
task never scans or hashes the repository.

`nav.context` and `edit.safe` must accept the certified `snapshot_id` and
`source_generation` returned by `index.status`. Each revalidates both tokens
before and after reading, echoes both tokens actually used, and either serves all
graph and source bytes from that immutable snapshot or returns
`SOURCE_GENERATION_MISMATCH` without a result. In particular, `nav.context` may
not combine entry points from a cached graph with newer filesystem lines.
Absence, disagreement, or a changed token stops the task route; no later
`nav.context` or `edit.safe` call starts.

`edit.impact` must obtain a `source_generation` from that same oracle atomically
with diff capture and echo it. The task compares it byte-for-byte with the
`index.status` token; absence or mismatch is `SOURCE_GENERATION_MISMATCH`, stops
diff routing, and cannot produce fresh evidence. This binds the captured diff to
the certified source generation rather than merely comparing two internally
consistent but unrelated IDs. If any oracle field is absent, disagrees, or
completeness is not `complete`, freshness is `unknown` (or primitive-reported
`stale`) and graph-dependent status is at most `partial`; graph/source-consuming
task rows do not start without the two certified tokens. Time, mtimes, and a
task-computed hash are never freshness evidence.

The P0.1 registry is process-local and bounded to 16 live snapshots and 512 MiB
of charged snapshot bytes. An entry expires 35 seconds after its latest successful
publish or identity-matched reuse. A snapshot is pinned while a consumer is
active; capacity or size exhaustion fails closed rather than spilling to disk.
The registry owner schedules a monotonic expiry callback at every publish/reuse;
the callback carries the entry generation so a superseded timer is a no-op. Under
the registry lock it marks the matching entry expired, prevents new pins, and
immediately closes the connection and releases the slot/byte charge when the
active-consumer count is zero. If consumers remain, their final release performs
that close. Registry shutdown also cancels callbacks and closes every entry, so an
idle process cannot retain expired capacity.

### P0.2 Frozen workspace/staged diff snapshot

V1 accepts only `workspace` and `staged`. They map respectively to
`edit.impact(mode="diff", ...)` and `edit.impact(mode="staged", ...)`. Explicit
snapshot capture is POSIX-only in Phase 0: safely binding the root-to-leaf path
and Git-index identities requires `openat`/`O_NOFOLLOW`. Native Windows cannot
provide that binding for ancestor reparse points, so both inputs fail closed with
`DIFF_SNAPSHOT_WORKSPACE_UNSUPPORTED` before Git or file capture. A `ctypes`
handle or check-then-open fallback is forbidden because it would reintroduce
TOCTOU traversal. This restriction does not affect legacy staged change-impact
when `capture_diff_snapshot` is false; that existing Windows route remains
supported. Phase 0
`scope_paths` are literal repository-relative paths only: a leading `:` (Git
magic/pathspec syntax) fails before capture with the stable
`DIFF_SNAPSHOT_UNSUPPORTED_SCOPE` envelope; the runtime never consults live Git
to reinterpret scope against a frozen inventory.

Before Phase A, the edit-adapter runtime must own a process-local, non-persistent
snapshot registry. `edit.impact` atomically materializes the normalized patch and
all available old/new bytes into an immutable registry entry, then returns its
opaque `diff_snapshot_id`, `source_generation`, changed-file records (`path`,
`status`, old/new availability, binary flag, Git kind/mode/OID), and
`assessed_scope_paths`: the
primitive-normalized union of changed paths and impact-produced affected/blast-
radius paths. `edit.ast_diff` and `edit.classify` accept only that ID plus
`file_path`; they never reconstruct the captured input. The task only fans out
returned records in normalized path order.

The frozen registry configuration is part of the primitive contract: at most 16
live snapshots, 64 MiB total materialized bytes, and a 35-second hard lifetime.
An entry is pinned against ordinary eviction while its route lease is open;
capacity or size exhaustion fails `edit.impact` with
`DIFF_SNAPSHOT_CAPACITY` rather than writing to disk. Every snapshot-consuming
primitive atomically acquires its own active-consumer pin before reading. Hard
expiry marks the entry expired and forbids new pins, but cannot erase its bytes
or release its slot/byte charge while a consumer is active. The final consumer
release erases an expired entry; otherwise the orchestration host closes the
primitive-issued route lease in an outer `finally` after routed computation or
failure but before outcome freeze/return, and erasure occurs once both lease and
consumer counts reach zero. Thus an
overrunning call keeps valid bytes without ever allowing actual retained memory
or live-slot accounting to exceed the 16-entry/64 MiB budgets. The long-lived
MCP process exposes `edit(action="release_snapshot", diff_snapshot_id=id,
route_lease_id=lease)` so a successful route can close ownership early; repeating
the exact ID/token pair is idempotent, while a mismatched ownership token fails.
Access after expiry or lease close returns `DIFF_SNAPSHOT_EXPIRED`.

Phase 0 index, diff-snapshot, and route-lease IDs are deliberately process-local.
A one-shot CLI process dies before another invocation can safely consume or
release them, so there is intentionally no public `--snapshot-id`,
`--source-generation`, `--diff-snapshot-id`, or snapshot-release CLI flag.
Phase 0 parameter parity here applies to the existing inner adapters and their
registered MCP facade routes. Contract tests exercise the exact same-process
adapter sequence through a non-public CLI-handler bridge without publishing it.
Existing standalone CLI actions retain their legacy one-shot semantics and public
access paths. This RFC narrowly amends MCP/CLI parity for the process-local
`edit.release_snapshot` action and its opaque capability ID, generation, and
release-token controls: no Phase 0 CLI release operation or consumer-ID parameter
parity is claimed because it would be unusable after the producer process exits.
The implementation must update the parity contracts to encode exactly this action
and parameter exception; it cannot weaken discoverability or parity for any other
action or parameter. The test bridge is verification infrastructure, not a public
CLI path. This exception does not authorize a one-shot composition command. Cross-process persistence and
a one-shot task/orchestration facade are Phase A work behind the public-surface
gate.

Before every snapshot-consuming call (`constraints`, `ast_diff`, or `classify`),
its primitive owner acquires that pin, then reacquires and compares the shared-
oracle generation captured by `impact`; a changed source returns
`DIFF_SNAPSHOT_SOURCE_CHANGED`, emits no derived result, releases the pin, and
makes the task stop remaining diff fan-out. Consumer release is also in a
`finally` block. These stable errors are result data, not exceptions whose text
is serialized. No snapshot directory, temp file, DB, WAL, or implicit persistent
cache is permitted inside the project. Capture may use mode-0600 normal indexes
and a temporary object directory outside the project; these are request-scoped,
share the same deadline/budget, use the repository object store only as a read-only
alternate, and are unconditionally deleted. The first oracle pass freezes exact
stage entries plus HEAD/object-format identity. A missing index is explicitly
framed as missing and modeled as an empty staged index for both born and unborn
HEADs; the private environment creates it with ``read-tree --empty``, so a born
HEAD reports every HEAD entry as a staged deletion. All patch/status/numstat/blob reads
are then bound to rebuilt temporary indexes, never the live index or worktree.
Arbitrary Git path bytes use the lossless ``git-path-b64:<urlsafe-base64>`` wire
codec (literal names with that prefix are encoded too). Tool cache exclusions
match ASCII ``.ast-cache`` and ``.tree-sitter-cache`` raw path segments before
wire encoding, including descendants whose remaining bytes are not UTF-8; scope,
reporting, and queue accounting all use that same filtered identity set. Every snapshot-owned Git
command (oracle generation, HEAD/index enumeration, config/attribute capture,
hashing, diffing, and request-scoped temporary/shadow plumbing) runs with
``GIT_ATTR_NOSYSTEM=1`` and ``GIT_NO_REPLACE_OBJECTS=1``. Replacement refs are
mutable name-resolution policy and are never consulted: oracle identities, old
entries, patches, and records all use the original HEAD object graph. External
``diff.orderFile`` is likewise policy, not snapshot input: effective-config
capture, serialization, and fingerprints discard that key, while every oracle,
payload, and pre/post verification Git command overrides it with a validated
request-scoped empty regular file outside the project (never ``/dev/null``).
Changing the referenced external file is therefore transient and cannot change
snapshot identity, patch, or record order. Records are finally sorted by
normalized internal raw destination bytes with status and raw source bytes as
stable ties, independently of Git output order. P0.2
therefore deliberately excludes machine system attributes: payload and oracle
use the same deterministic attribute policy, while repository/info and captured
``core.attributesFile`` inputs remain frozen. Worktree attribute sources are not
discovered by a filesystem walk: root and per-directory ``.gitattributes``
candidates are derived from every bounded index/untracked target path, safely
read without following links (including ignored candidates), framed into the
source generation, and materialized in the isolated shadow. Git's built-in text/eol/autocrlf
conversion is supported; an active ``filter`` attribute (boolean ``set`` or a
driver value, including LFS) fails before any ``hash-object`` with
``DIFF_SNAPSHOT_UNSUPPORTED_FILTER`` so no external clean driver executes.
Strict AST/classification consumers infer language only from the captured
normalized path extension; a caller language override conflicts, and an unknown
extension returns ``DIFF_SNAPSHOT_UNSUPPORTED_LANGUAGE``.

Because ``edit.impact`` conditionally allocates a fresh snapshot ID, lease, slot,
and byte charge, its MCP annotation is conservatively mixed/non-idempotent
(``idempotentHint=false``), even when capture is not requested.

Rename, add, delete, multi-file, binary, capacity, expiry, lease cleanup, and
mid-route workspace mutation are primitive contract tests. Today these adapters
do not share such an artifact, so no diff outcome may ship until P0.2 lands.
`inline`, `stdin`, arbitrary patch content, branch, and PR are not V1 inputs.

### P0.3 Read-only constraint evaluation

Before Phase A, `edit.constraints` must support `persist=false`, perform no
DB/file write, and have a corrected MCP side-effect annotation. After successful
impact, every diff route invokes it with `diff_snapshot_id=id` and
`scope_paths=impact.assessed_scope_paths` before fan-out. It evaluates and returns
only violations whose location intersects that frozen scope; project-wide debt
outside it MUST NOT contribute a verdict. The task passes the primitive-owned
list exactly and never widens or derives it. The primitive owns config discovery
and returns `state=not_applicable`, `reason=NO_CONFIG` when none exists. That row
contributes no verdict. Request rejection, impact failure, deadline expiry, or a
missing/mismatched/changed generation or snapshot detected after impact can
prevent the reserved call and produce `unknown`; no other condition can. P0.3 is
a release prerequisite; there is no capability fallback or task-owned evaluator.

### P0.4 Read-only/open-existing mode for every routed adapter

Every routed adapter (`index.status`, `nav.context`, `edit.safe`, `edit.impact`,
`edit.ast_diff`, `edit.classify`, and `edit.constraints`) must expose a tested
`access_mode="read_existing"` used by Phase A. It may open a compatible existing
index/cache read-only, but must not create a directory, DB, journal/WAL, schema,
index, migration, lock file, snapshot file, or temp file. The prohibition is
literal for both producers and consumers: the request-scoped pathname-backed Git
index/object/shadow plumbing permitted by P0.2 remains valid for legacy explicit
capture, but `edit.impact(access_mode="read_existing")` and every subsequent
snapshot revalidation must use a separately tested zero-filesystem-write backend.
They may not relocate, allowlist, or write-then-delete that plumbing.

This is a capability gate, not permission to weaken P0.2. Before Phase A, the
primitive owner must demonstrate a concrete backend that reproduces the complete
P0.2 patch, status, blob, config, attribute, ordering, and source-generation
semantics from safely opened immutable inputs without invoking any operation that
is write-capable for its supplied arguments and captured state. It must not invoke
ordinary Git plumbing unless the exact invocation set is proved by the P0.4
monitor to need no pathname-backed index, object directory, shadow worktree, lock, config, attributes, or order file and to
make no write attempt. If no backend passes both the P0.2 golden corpus and P0.4
monitor, read-existing diff capture is unsupported and Phase A remains blocked;
legacy capture, live Git/worktree reads, weakened semantics, relocation, and
write-then-delete are forbidden fallbacks.

In this mode `edit.impact` is unconditionally the P0.2 producer: accepting
`access_mode="read_existing"` for `mode="diff"` or `mode="staged"` must atomically
create the bounded in-memory diff snapshot and route lease or fail.
`capture_diff_snapshot` is forbidden whenever `access_mode="read_existing"` is
present, including when supplied as `false`, and must be rejected before capture;
omission of `access_mode` preserves the legacy
`capture_diff_snapshot=true|false` contract. A successful read-existing result
must contain `diff_snapshot_id`, `route_lease_id`, `source_generation`, changed-
file records, and `assessed_scope_paths`; absence of any field invalidates the
result and stops the route. The primitive owner retains an internal cleanup
handle until it has validated and atomically published the complete pair; every
path that does not publish both IDs revokes the reservation/lease internally.
The host closes in `finally` only after receiving both validated tokens, so a
malformed wire result cannot retain capacity. `edit.ast_diff`, `edit.classify`,
and `edit.constraints` consume that same-process ID only. `nav.context`,
`edit.safe`, and graph-backed `edit.constraints` require the certified P0.1
`snapshot_id` and `source_generation`. Constraints acquire that exact pair only
after captured config proves graph rules are applicable; `NO_CONFIG` does not
open or cite an index capability. No live-cache, live-file, migration, or
parser/index fallback is allowed when a required capability is absent or
disagrees.

Every classified action-level result adds the exact P0.4 access-evidence fields
`access_mode`, `access_state`, `access_reason`, and `source_snapshots` without
retyping action-specific fields such as the constraints result's existing
`state="applicable"`. `access_state` is one of `available`, `missing`, `unknown`,
or `not_applicable`; `access_reason` is null only for `available` and otherwise is
a stable primitive-owned reason. `source_snapshots` is a stable list of exact
records `{kind, snapshot_id, source_generation}`; `kind` is `index` for P0.1 or
`diff` for P0.2, and records sort by `(kind, snapshot_id, source_generation)`. After a
capability is acquired, every access state cites every primitive identity
actually read, including `not_applicable`/`NO_CONFIG` and a later `unknown`; the
list is empty only when no capability was acquired. Thus applicable graph-backed
constraints cite both their P0.2 diff and P0.1 index snapshots, while `NO_CONFIG`
cites the acquired diff that owns the config probe. An old or incompatible schema
is exactly `access_state="unknown", access_reason="INCOMPATIBLE_SCHEMA"`. Each
acquired action-specific `snapshot_id` or `diff_snapshot_id` and
`source_generation` must match a corresponding generic record; multiple distinct
records are not required to share an ID. Successful classification of an
unavailable capability may retain `success=true`; Phase A branches on
`access_state` and `access_reason`, not on `success` or an action-specific `state`
alone. Validation or internal execution failure remains `success=false`. The task
creates or repairs none of these fields. P0.5 owns version fields, fragment
propagation, and evidence-identity participation; it does not retroactively
synthesize P0.4 access evidence.

The P0.1 index-snapshot and bounded P0.2 diff-snapshot primitive-owned in-memory
capability registries are the only reusable ephemeral capability state allowed in
this mode; ordinary request-local values are not persistence. No pathname-backed
private copy is an in-memory exception. Missing cache/index/snapshot returns
`missing` or `unknown` without initialization, and incompatible state never
triggers migration.

Primitive acceptance fixtures cover (1) a clean repository with no cache, (2) a
repository with an old schema, and (3) a read-only filesystem. Each adapter and
composed route runs in a fresh subprocess with isolated empty `HOME`,
`XDG_CACHE_HOME`, and `TMPDIR` directories. The platform write monitor/sandbox is
active from subprocess entry, before imports, facade/adapter construction, and
the call, and fails on every filesystem write attempt by the process or its
descendants, including write-then-delete attempts, native-library writes, or
writes through an absolute path. Before/after tree, identity, and content-hash
comparisons additionally require the project, cache, isolated home/cache/temp
roots, and every pre-existing DB or sidecar to be exactly unchanged. This catches
user-cache and system-temporary writes rather than merely relocating them.
Interpreter bytecode caches are disabled.

Every certified supported-platform acceptance axis must run a descendant-aware
native authority that records every write attempt from target exec until every
thread and descendant exits and makes any such event fail the gate. Read-only
filesystems and before/after hashes are supplemental on every OS and cannot
certify an axis alone; absence,
attach/start failure, truncation or event loss, parser failure, an unknown relevant
operation, or a surviving descendant fails closed rather than skipping. A deny
sandbox that cannot report an ignored or swallowed denial is insufficient. An OS
without this authority must return a stable unsupported result for read-existing
mode and cannot be listed as certified support.

The mandatory initial authority is a pinned Linux CI job on the supported runner
or container with `strace` present at a pinned minimum version. It launches the
adapter subprocess as trace root with `strace -ff`, closes non-stdio inherited
file descriptors, and records every thread and descendant until all traced
processes exit. A checked-in parser and exact allow/deny policy classify write
intent by syscall, flags, mapping protections, file-descriptor provenance, and
resolved target. It classifies as a gate violation every filesystem mutation,
write-capable file open, mapping capable of writing through to a backing file (for example,
`MAP_SHARED|PROT_WRITE`, not loader-required `MAP_PRIVATE` copy-on-write), write
through an inherited descriptor, and asynchronous filesystem write such as
`io_uring`, including failed attempts and write-then-delete. The policy
distinguishes non-filesystem IPC descriptors; it has no writable-filesystem
allowlist. Positive-control fixtures require the exact recorded events for native
and descendant create/unlink, truncate/restore, rename/restore, mkdir/rmdir,
SQLite-sidecar, absolute-path, failed-denial, and write-then-delete attempts. macOS
and Windows must pass the identical semantic adapter/route corpus under their
separately pinned native authority before being certified. Replacing or adding an
authority requires an RFC amendment and exact contract tests; “equivalent” is
not an inline escape hatch.
In-process monkeypatches and final-tree hashing alone are never write-attempt
authority.

### P0.5 Authoritative wire owner and versions

Every routed result fragment must echo its adapter-owned stable `action_version`.
A fragment derived by a primitive rule must also echo its primitive facade,
action, `producer_rule_id`, and `producer_rule_version`. A general generated
action registry may detect and diagnose disagreement, but it is never a fallback
source for evidence fields. Task code may not insert, default, or pin them.
Missing or disagreement makes that contribution `unknown` and issues no evidence
ID. The task adapter canonicalizes and hashes the exact received wire fragment;
the primitive does not supply that digest. Contract tests prove action/rule
version changes alter the exact wire bytes and therefore evidence identity.

## Internal Python contract

```python
@dataclass(frozen=True)
class Budget:
    profile: Literal["compact", "standard"] = "standard"
    max_primitive_calls: int | None = None
    max_evidence_items: int | None = None
    routing_deadline_ms: int | None = None

@dataclass(frozen=True)
class DiffInput:
    source: Literal["workspace", "staged"]
    scope_paths: tuple[str, ...] = ()

@dataclass(frozen=True)
class UnderstandRequest:
    task: str
    budget: Budget = Budget()

@dataclass(frozen=True)
class PlanChangeRequest:
    task: str | None = None
    diff: DiffInput | None = None
    budget: Budget = Budget()

@dataclass(frozen=True)
class AssessChangeRequest:
    diff: DiffInput
    budget: Budget = Budget()

async def understand(request: UnderstandRequest) -> TaskOutcome: ...
async def plan_change(request: PlanChangeRequest) -> TaskOutcome: ...
async def assess_change(request: AssessChangeRequest) -> TaskOutcome: ...
```

Decoded mappings reject unknown fields rather than ignoring them.
`UnderstandRequest` accepts one non-empty `task` and rejects `diff` and
`scope_paths`. `PlanChangeRequest` has an exact one-of: one non-empty `task` with
`diff=null`, or `task=null` with one `DiffInput`; task mode has no scope.
`AssessChangeRequest` requires exactly one `DiffInput` and rejects `task`.
Consequently `understand(diff)` and `assess_change(task)` are invalid, while
`plan_change(diff)` and `assess_change(diff)` are the two diff operations.

Every accepted task must be valid Unicode, contain 1..16,384 UTF-8 bytes, and
contain no NUL; size is checked before any normalization. Diff `scope_paths` has
at most 128 items; each is valid Unicode, relative, NUL-free, and at most 1,024
UTF-8 bytes, and the sum of encoded path bytes is at most 32,768. Counts include
duplicates and raw bytes are measured before path normalization. An omitted or
empty tuple means project scope. Excess, malformed, or forbidden fields produce
`INVALID_REQUEST`, make zero primitive calls, and are never echoed. Valid
`DiffInput.scope_paths` is passed unchanged only to `edit.impact`; boundary
validation always precedes primitive work.

Pinned profiles are:

| profile | primitive calls | evidence items | routing deadline |
|---|---:|---:|---:|
| compact | 4 | 15 | 5,000 ms |
| standard | 12 | 50 | 30,000 ms |

Explicit values may only lower a profile value. A diff request requires
`max_primitive_calls >= 3` for `index.status`, `edit.impact`, and the reserved
`edit.constraints` call. A lower explicit value is `BUDGET_INVALID`, rejected
before any primitive call. File fan-out may still be omitted by the remaining
budget and then contributes partial. `routing_deadline_ms` is a routing deadline,
**not a wall-time SLA or resource cap**. V1 calls primitives
sequentially and checks the deadline before starting each call. A non-cancellable
running primitive may finish after it; `consumed.routing_wall_ms` may therefore
exceed the limit, with `deadline_overrun_ms` reported exactly. No new routed call
starts after the deadline. Primitive-owned consumer-pin release remains inside
the owning primitive call. The host's validated `edit.release_snapshot` runs in
an outer `finally` as unconditional cleanup, not a routed call: it bypasses route
call/deadline admission and runs even after overrun. The host first captures
routed success/failure in a mutable draft, then performs cleanup, records the
fixed fields `consumed.cleanup_calls` (zero or one),
`consumed.cleanup_wall_ms`, `consumed.cleanup_status`
(`not_required|succeeded|failed`), and `consumed.cleanup_error_code` (null or
`DIFF_SNAPSHOT_CLEANUP_FAILED`), and only then freezes/returns the
outcome. Cleanup does not change `consumed.primitive_calls`. Failure appends only
the stable cleanup code to `errors`, forces `success=false`, `status=unknown`, and
`verdict=ERROR`, while hard expiry still bounds the lease. Safe cancellation
needs a separate primitive contract.

## Complete V1 route decision table

There is no task-layer keyword, regex, identifier, intent, or LLM router. Free
text is passed unchanged to the already-existing `nav.context` primitive, which
is the sole owner of natural-language symbol inference. Parameters not shown are
not sent; primitive output format is JSON internally.

### Common routing rules

1. Validate request and paths. On failure, make zero calls.
2. Before each row, stop if call/deadline budget is exhausted. For a diff route,
   validate the three-call minimum at the boundary and reserve the constraints
   slot **before** starting impact. A successful impact is followed immediately
   by constraints, before file fan-out; fan-out cannot consume the reserved slot.
3. Call rows in displayed order. Fan-out lists are de-duplicated and sorted by
   `(path, symbol)` before their pinned cap is applied.
4. Never substitute a failed/unsupported action. Record `unknown`/`not_run`.
5. Compare only primitive-issued tokens. Task routes pass the certified index
   `snapshot_id` and `source_generation` into every `nav.context`/`edit.safe`
   call and every graph-applicable constraints call, then compare the matching
   echoed tokens/source record. Immediately after impact, compare its
   `source_generation` with the index oracle before constraints or fan-out.
6. Stop on an absent task-route token, generation/snapshot disagreement, expiry,
   or source change; retain earlier evidence as partial and make no further
   graph-, source-, or snapshot-dependent calls.

| operation/input | condition | facade action and exact semantic parameters | stop/degrade rule |
|---|---|---|---|
| all | always | `index.status(access_mode="read_existing", output_format="json")` | missing oracle => freshness unknown; task rows stop, while a diff may call impact but stops before constraints/fan-out |
| `understand(task)` | valid task and certified index tokens | `nav.context(task=task, snapshot_id=index.snapshot_id, source_generation=index.source_generation, max_nodes=12/30, max_code_blocks=3/5, include_graph=false, access_mode="read_existing", output_format="json")` | missing/mismatched echoed token or failure => unknown and stop; success ends route |
| `plan_change(task)` | valid task and certified index tokens | same `nav.context` call | missing/mismatched echoed token or failure => unknown and stop |
| `plan_change(task)` | each distinct existing path explicitly returned in generation-matched `code_blocks`, max 2/5 | `edit.safe(file_path=path, edit_type="refactor", snapshot_id=index.snapshot_id, source_generation=index.source_generation, access_mode="read_existing", output_format="json")` | missing path is not inferred; token mismatch stops route; other per-call failure is partial |
| diff operation | valid diff | `edit.impact(mode="diff"|"staged", scope_paths=diff.scope_paths, include_tests=true, resource_profile="local_low_impact", access_mode="read_existing", output_format="json")` | `access_mode` mandates zero-write P0.2 capture and `capture_diff_snapshot` is forbidden; missing lease/ID/generation/records/assessed scope or generation mismatch => unknown and stop; an unpublished/malformed pair is owner-revoked, otherwise the orchestration host closes the validated pair in `finally` on every exit as unconditional, separately-accounted cleanup |
| diff operation | successful, generation-matched impact; reserved before fan-out | `edit.constraints(diff_snapshot_id=id, snapshot_id=index.snapshot_id, source_generation=index.source_generation, scope_paths=impact.assessed_scope_paths, persist=false, access_mode="read_existing", output_format="json")` | `NO_CONFIG` returns diff-only provenance; applicable graph rules must echo matching diff+index records; missing/mismatched index record or token stops remaining fan-out; only in-scope violations count |
| diff operation | each non-binary changed record with old/new material available | `edit.ast_diff(diff_snapshot_id=id, file_path=path, access_mode="read_existing", output_format="json")` | unsupported add/delete/rename is explicit `not_run`, never locally reconstructed |
| diff operation | same eligible records | `edit.classify(diff_snapshot_id=id, file_path=path, access_mode="read_existing", output_format="json")` | per-file failure => partial |

The compact/standard values in a cell are selected only by `Budget.profile`.
`plan_steps` are read-only preparation/review steps, not edit instructions or
implementation authorization. Each has exactly `{ordinal, kind, path, symbol,
evidence_ids}`. The table-driven projection emits one step per successful exact
primitive fragment in this group order, then sorts within a group by
`(path|nulls-first, symbol|nulls-first, locator)` and assigns 1-based ordinals:

| route/source fragment | fixed `kind` | copied fields |
|---|---|---|
| task `nav.context.code_blocks[]` | `inspect_context` | emitted path/symbol or null |
| task `edit.safe` result | `check_file_safety` | requested emitted path; symbol null |
| diff `impact.changed_files[]` | `review_changed_file` | emitted path; symbol null |
| diff in-scope constraint violation | `check_constraint` | emitted path/symbol or null |
| diff `ast_diff` result | `review_structure` | requested changed path; emitted symbol or null |
| diff `classify` result | `review_classification` | requested changed path; emitted symbol or null |

Fields are copied, never inferred; `evidence_ids` contains only that fragment's
ID. Failed, malformed, `NO_CONFIG`, and omitted fragments emit no step and are
represented by `unknowns`/status. Thus identical wires yield identical ordered
steps without choosing a modification kind. `assess_change` uses the same route
but leaves `plan_steps=[]`; neither operation performs or authorizes an edit.

Required static questions are: context for task-understanding; context plus all
selected file-safety checks for task-planning; and impact, every eligible
structural/classification result, plus one unconditional constraints invocation
for diff operations. `not_applicable:NO_CONFIG` is a completed constraints row.
Budget omission makes the result partial, not a shorter definition of required.

### `tsa_explore` disposition

`mcp/tsa_explore.py` remains non-production today. Phase 0 marks it retired and
migrates any benchmark fixtures, then deletes it before a task route is added.
It is never registered. Its keyword inference, `_extract_symbol`, and `_ROUTING`
MUST NOT be copied or imported. This RFC's fixed table plus `nav.context` is the
only task routing path, preventing a second orchestration/inference engine.

## Fixed `task-outcome/v1` semantics

The fixed model keeps these required top-level keys:

```jsonc
{
  "schema": "task-outcome/v1",
  "success": true,
  "operation": "understand|plan_change|assess_change",
  "status": "complete|partial|unknown",
  "verdict": "SAFE|CAUTION|REVIEW|UNSAFE|INFO|WARN|NOT_FOUND|ERROR",
  "subject": {"task": null, "diff": {"source": "workspace|staged", "snapshot_id": "opaque", "changed_paths": []}},
  "claims": [], "artifacts": {"relevant_symbols": [], "relevant_paths": [], "plan_steps": [], "verification": [], "edge_collections": []},
  "evidence": [], "provenance": [], "freshness": [], "unknowns": [], "errors": [],
  "budget": {}, "truncation": {}, "next_step": null, "agent_summary": {}
}
```

Arrays stay present when empty. `artifacts.edge_collections` is required and is
an empty array when RFC-0023 edge evidence is unused. This field is incorporated
while `task-outcome/v1` is still an unimplemented draft: earlier draft fixtures
must be regenerated, and no deployed V1 compatibility promise is affected. After
V1 implementation, removing or retyping it requires a negotiated V2. Strict
clients reject unknown enum values.

Untrusted task text is input-only and is deterministically omitted, not
best-effort scrubbed: `subject.task` is always `null`, the frozen model contains
no raw or normalized task field, and experiment artifacts/logs store only an
opaque corpus case ID. Task-mode provenance hashes the canonical request shape
with the fixed scalar `"task":"TASK_TEXT_OMITTED"`, never the task bytes. Routed
adapters must not echo their query; the task projection accepts only the pinned
result fields in this RFC and drops diagnostic, request, query, stderr, body, and
other unlisted fields before freeze. Primitive-owned bounded excerpt redaction
remains mandatory. Canary contract tests put credentials, environment values,
and absolute host paths in otherwise-valid tasks and prove none of their bytes
appear in the model, JSON, TOON, logs, or experiment artifacts.

Request/internal failures stay inside `task-outcome/v1`, use `success=false` and
required verdict `ERROR`, and follow TSA envelope conventions with stable codes
`INVALID_REQUEST`, `OUTSIDE_PROJECT`, `BUDGET_INVALID`,
`UNSUPPORTED_DIFF_SOURCE`, `DIFF_SNAPSHOT_CLEANUP_FAILED`, and `INTERNAL_ERROR`.
`ERROR` is forbidden when
`success=true`. Absolute host paths, bodies, secrets, environment values, stderr,
and traces are not serialized.

### Evidence and provenance identity

Every supported/contradicted claim cites evidence; unknown claims cite an
unknown. Evidence IDs are:

```text
evidence:sha256(canonical_json({
  primitive_facade, action, action_version,
  normalized_result_sha256, source_snapshots, locator
}))
```

`source_snapshots` is the exact stable P0.4 list received for that fragment; a
constraint contribution therefore binds both the diff/config and graph-index
identities it read.

The normalized result hash covers the canonical bytes of the exact primitive wire
fragment supporting the claim. That wire already contains its primitive facade,
action, action version, and, when rule-derived, producer rule ID/version. The task
adapter only validates, canonicalizes, and hashes those exact bytes; it never
inserts owner fields and the primitive never supplies the digest. A registry may
diagnose mismatch but cannot repair missing edge-evidence ownership. Missing or
disagreement makes the contribution `unknown` and mints no evidence ID. Locator
alone never identifies or deduplicates evidence. Provenance records the same
owner/version fields, request hash, result hash, source-snapshot list, success,
verdict, truncation, and input evidence IDs. RFC-0023's specialized edge formulas and
strict artifacts refine this generic identity without changing the owner flow.

### Freshness and snapshot truth

Freshness states are `fresh|stale|missing|not_applicable|unknown`. `fresh` is
allowed only when the authoritative oracle is complete and every graph result
echoes its token. Without that oracle, repository/index fingerprints are null,
reason is `AUTHORITATIVE_SNAPSHOT_UNAVAILABLE`, and graph-dependent status is at
most partial. Diff evidence cites the primitive-owned `diff_snapshot_id`.
Outcomes never claim a mixed snapshot is complete.

### Static verification truth table

The old name `verify_change` is removed because no command is executed.
`assess_change` fixes `completeness_scope=static` and `runtime_status=not_run`.
Each required invocation produces exactly one contribution from this table;
`finding` is the normalized primitive result, never task inference.

| invocation | finding | freshness | truncation | status contribution | verdict contribution |
|---|---|---|---|---|---|
| not required (runtime, binary structural/classification) | none | not_applicable | false | ignored | none |
| not called (budget/deadline) | unknown | unknown | unknown | unknown | none |
| failed/unsupported/expired/source changed | unknown | unknown | false | unknown | none |
| succeeded | unknown/malformed | any | any | unknown | none |
| succeeded | none | fresh | false | complete | primitive non-risk verdict (`SAFE`, `INFO`, or conclusive `NOT_FOUND`) |
| succeeded | risk | fresh | false | complete | primitive risk verdict (`WARN`, `CAUTION`, `REVIEW`, or `UNSAFE`) |
| succeeded structural | invalid | fresh | false | complete | primitive `REVIEW` or `UNSAFE` |
| succeeded constraints | violation | fresh | false | complete | validated primitive verdict: error => `UNSAFE`, warning-only => `CAUTION`, informational-only => `SAFE` |
| succeeded constraints | `NO_CONFIG` | not_applicable | false | complete | none |
| succeeded | none/risk/invalid/violation | stale/missing/unknown | false | partial | `degrade(primitive verdict)` |
| succeeded | none/risk/invalid/violation | any | true/unknown | partial | `degrade(primitive verdict)` |

The table is ordered: the first matching row wins, so truncation overrides a
fresh success and malformed finding overrides freshness. `any` is a wildcard;
any tuple matching no row is invalid primitive output and canonicalizes to
`(succeeded, malformed, unknown, unknown)` before a second, final lookup. Thus
every input tuple has exactly one contribution. Impact not invoked or
failed with no decision evidence therefore yields `unknown`; successful fresh,
untruncated impact with a risk finding is `complete` and contributes its risk
verdict; the same success with no finding is `complete` and contributes its
non-risk verdict. Structural invalidity and constraint violation explicitly
permit `complete + REVIEW/UNSAFE`: completeness describes observation, not safety.
Classification risk likewise does not make invocation failure. Constraint
aggregation preserves `ConstraintCheckTool`'s authoritative primitive verdict;
the task never turns every violation into `UNSAFE`. `degrade(v)` preserves
`UNSAFE|WARN|REVIEW|CAUTION` and maps `SAFE|INFO|NOT_FOUND` to `WARN`; stale or
truncated evidence therefore never contributes `SAFE`.

Aggregate status is deterministic: remove ignored rows; `complete` requires all
remaining contributions to be complete; `partial` requires at least one useful
complete/partial contribution and at least one non-complete contribution;
otherwise status is `unknown`. Runtime never enters this aggregation. A
primitive-provided verification command is inert suggested text, never evidence.
Verdicts use TSA's canonical severity order `UNSAFE > WARN > REVIEW > CAUTION >
SAFE > INFO > NOT_FOUND`; no contribution is not a verdict, and incompleteness
never downgrades an existing risk verdict. Zero verdict contributions resolve to
`WARN`, including an outcome whose required rows all failed, were skipped, or
were malformed. Conclusive `NOT_FOUND` requires known scope and fresh,
untruncated success. As a final fail-closed rule, if status is `partial|unknown`,
candidate `SAFE|NOT_FOUND` becomes `WARN`; incomplete evidence cannot assert
either result.

### Budget and truncation

Failed attempts consume calls. Primitive truncation and orchestration omission
are separate dimensions. Unknown totals are `null` with
`total_count_state=unknown`; “N of N” is forbidden unless the primitive provides
an exact total. Omitted decision-relevant evidence forces partial plus
`BUDGET_EXHAUSTED` or `TRUNCATED`. Routing order, paths, symbols, locators,
claims, and evidence are stable-sorted before the frozen model is created.

## Determinism and serializer parity

One execution creates one immutable/frozen `TaskOutcome`, including timestamps,
durations, result hashes, and snapshot IDs. The parity oracle serializes **that
same object** through JSON and TOON, decodes both, and requires exact model
equality. It never compares two live executions, whose clocks or snapshots may
differ. Transport metadata is outside the semantic model.

MCP's default remains TOON and CLI's default remains JSON. Payload stays on
stdout and diagnostics on stderr. If/when public surfaces land, both handlers
must call the same Python API and the same serializers; explicit JSON/TOON are
available on both. No default is flipped to manufacture parity.

## Public surface and ninth-facade gate

### Phase A — internal experiment only

- After Phase 0 passes, implement frozen models, validators, the fixed router,
  and serializers behind `tree_sitter_analyzer.task` internal/experimental imports.
- Exercise them through a benchmark harness, not `_tool_registry.py`, MCP server,
  facade schemas, main CLI flags, or codemaps.
- Existing public surface remains exactly eight facades plus infrastructure.

### Pre-registration gate

A checked-in experiment manifest must freeze task corpus, agent/model/config,
randomization, sample size, success rubric, and tool definitions before running.
The paired live-agent A/B compares the existing menu with the candidate ninth
facade. Registration requires all of:

1. exact corpus completion and raw, task-text-omitting artifacts are published;
2. task-facade discovery rate and end-to-end task success show the manifest's
   predeclared measurable improvement, with no material primitive-discovery loss;
3. exact serialized tool-definition bytes and tokenizer counts are pinned for
   both menus, and the candidate stays within the predeclared menu budget;
4. before execution, the manifest pins numeric maximums for candidate median
   turns, median execution input tokens, and median output tokens, plus a
   relative non-regression threshold of `1.00` against each corresponding
   existing-menu median; registration requires every candidate median to be at
   or below both its absolute maximum and `baseline * 1.00`;
5. the signed artifact reports those turn/token measurements and the executable
   gate fails, rather than merely reporting, any threshold regression; and
6. a rerunnable executable gate validates the signed result artifact.

An RFC/self-test is E0 design evidence and cannot satisfy this gate. Failure or
an inconclusive result means no registration. A new menu experiment must be
approved rather than silently moving the actions onto another facade.

### Phase B — conditional public registration

Only after the gate passes may one `task` facade be registered with actions
`understand`, `plan_change`, and `assess_change`. Its CLI equivalents land in
the same change, along with registry/facade counts, MCP/CLI parity tests, and
both codemaps. If the gate does not pass, the outcome API remains experimental
Python-only. This RFC does not pre-authorize a ninth facade.

## Executable value and cost invariants

Later implementation tests must use one frozen fixture and pin exact byte/token
counts for each serializer/profile. They also assert these differential facts:

- compact model bytes and tokens are strictly less than standard;
- TOON bytes and the repository-pinned tokenizer count do not exceed JSON for
  the same frozen model;
- decoding JSON and TOON yields exactly the same frozen model;
- adding the candidate facade changes menu bytes/tokens by the exact reviewed
  delta in the experiment artifact.

Any claim about size, token cost, latency, discovery, or success is removed from
documentation unless its executable measurement is checked in. Timing tests use
an injected clock for exact routing decisions; a blocking fake proves deadline
overrun reporting and proves that no later call starts.

## Security and compatibility

All paths pass the existing `ProjectBoundaryManager`; absolute, `..`, symlink,
submodule, and out-of-root paths fail before calls. No implicit index build,
network, shell, edit, git mutation, or persistence is permitted. Excerpts use
existing bounded/redacted primitive results. This RFC does not change
`BaseMCPTool` root canonicalization, index storage, or primitive behavior except
the separately tested Phase 0 capabilities.

The Phase 0 compatibility exception covers both the adapter parameter extensions
and the P0.4 response-schema additions specified above. Those four generic access
evidence fields are mandatory only when `access_mode="read_existing"` is present;
legacy calls that omit it retain their exact response schemas. Apart from those
additions and the narrow parity exception, the existing eight facades, legacy
shim, CLI flags, schemas, and defaults remain unchanged in Phase A.
`task-outcome/v1` fields are not removed or retyped within V1. A future version
requires explicit negotiation and overlap.

## RED-first acceptance plan

1. Phase 0 tests prove authoritative snapshot/version propagation, bind
   `nav.context`/`edit.safe` to the certified generation, keep overrunning active
   consumers pinned and charged, and cover cleanup/mutation and workspace/staged
   mappings.
2. Adapter and route fixtures prove exact zero writes on clean, old-schema, and
   read-only filesystems under isolated `HOME`/cache/`TMPDIR` plus a write monitor,
   and cover scoped `constraints(persist=false)` and `NO_CONFIG`.
3. Route tests pin all three request shapes, their one-of rejection cases, every
   row, parameter, fan-out order/cap, generation stop (including zero constraints
   calls), and prove no analyzer import, `tsa_explore` reuse, mutating action, or
   fallback.
4. Schema/evidence tests pin key sets, evidence identity inputs, dangling-link
   rejection, same-locator non-dedup, canonical severity, constraint-severity
   preservation, zero-contribution `WARN`, and conservative aggregation.
5. Freshness tests prove absent oracle is unknown/partial and snapshot mismatch
   stops graph routing.
6. Static truth-table tests cover every passed/failed/not-run/unknown cell and
   prove runtime stays not-run without reducing static completeness.
7. Budget tests pin profile values, sequential routing, exact overrun, unknown
   totals, and decision-relevant truncation.
8. Security tests prove fail-closed validation, zero calls after rejection,
   deterministic task omission with secret canaries, error redaction, and zero
   monitored project/home/cache/temp writes for every outcome.
9. Serializer tests use one frozen result for exact JSON/TOON equality and the
   executable cost invariants above.
10. The pre-registration live menu experiment and artifact validator pass before
   any registry/CLI/codemap change.
11. Conditional Phase B tests prove real handler parity, locked defaults, stdout/
    stderr separation, and compatibility of every pre-existing facade/action.

All deterministic counts use exact assertions and each test covers one behavior.
Regression tests cite their issue/incident. Later Python changes must follow
change-impact and patch-coverage gates. This RFC branch is docs-only.

## Deferred and rejected

- Inline/stdin/branch/PR diffs, runtime execution, cancellation, sessions,
  persistence, LLM planning, and cursors are deferred.
- Task-owned parsing/fingerprinting/classification/graph/routing/constraints are rejected.
- `tsa_explore` reuse or ninth-facade registration before the gate is rejected.
- Constraints without `persist=false` and static `verify_change` are rejected.

## Open questions
1. Should runtime verification be a separate sandboxed API?
2. After a failed gate, should task outcomes remain Python-only or test an existing facade?
