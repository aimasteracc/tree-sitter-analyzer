# RFC-0038: Annotated receiver resolution

- **Status**: draft
- **Author(s)**: @aimasteracc (drafted with Claude Code)
- **Created**: 2026-10-18
- **Last updated**: 2026-10-18
- **Tracking issue**: #1618
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/receiver_hints.py`, `tree_sitter_analyzer/receiver_module_hints.py` (new: extractor-side hint collection)
  - `tree_sitter_analyzer/cache/extraction.py`, `tree_sitter_analyzer/cache/unresolved.py`
  - `tree_sitter_analyzer/function_extraction.py` (attaches hints to call sites)
  - `tree_sitter_analyzer/cache/call_edges.py`, `tree_sitter_analyzer/cache/write.py` (persist hints)
  - `tree_sitter_analyzer/synapse_resolver/_annotated.py` (new: resolution)
  - `tree_sitter_analyzer/synapse_resolver/__init__.py`, `tree_sitter_analyzer/cache/synapse.py`
  - `tree_sitter_analyzer/cached_edge_resolution.py`, `tree_sitter_analyzer/call_graph.py`
  - `tree_sitter_analyzer/graph/edge_store.py` (target-aware unresolved count)
  - `tree_sitter_analyzer/mcp/tools/callers_tool.py`, `tree_sitter_analyzer/mcp/tools/codegraph_relation_tool.py`
  - `tests/unit/test_annotated_receivers_1618.py`

## Summary

Resolve a method call `x.m()` to a project method when the type of `x` is
fixed by what the source already states. The sources are:
- a parameter annotation;
- an annotated local;
- a `self.x` attribute annotation or assignment;
- a module-level singleton;
- the return annotation of the function that produced `x`. An edge resolved this way gets a
new resolution kind, `annotated_receiver`, with its type source and a fixed
confidence. It adds a caller to the method the annotation names. It never
removes an unresolved site from any other method's completeness check, so it
cannot by itself turn an answer `complete`.

## Motivation

`nav callers` must be trusted like grep: it may be incomplete, but it never
says `complete` wrongly. Dogfood round 7 measured 0 wrong `complete` answers,
and #1645 made non-empty lists `complete` when they really are. The remaining
gap is recall, and its most common cause is a receiver whose type is stated
only by an annotation:

```python
store = project_store(root)        # def project_store(...) -> GenerationStore
store.publish(snapshot)            # not a caller of GenerationStore.publish today

def drain(registry: IndexSnapshotRegistry) -> None:
    registry.publish(entry)        # not a caller of IndexSnapshotRegistry.publish

class Owner:
    def __init__(self, store: GenerationStore) -> None:
        self._store = store
    def flush(self) -> None:
        self._store.publish()      # not a caller either
```

`IndexSnapshotRegistry.publish` finds 2 of about 30 callers. The answers are
honestly `incomplete`, but an agent then has to grep, which is what TSA exists
to avoid.

## Detailed design

### 1. Annotation sources, precedence and scope

Python only. All sources are syntactic, read from the file being indexed,
except the return annotation, which is read from the project definition the
factory call resolves to (cross-module through imports).

The extractor (`receiver_hints.py`) computes, per function, a hint for each
receiver name. The rules, in precedence order:

1. **Declared type.** A parameter annotation (`def f(x: T)`) or an annotated
   local (`x: T` / `x: T = ...`) declares the type for the whole function. This
   is the type checker's declared-type rule. If the function declares two
   different types for one name, it gets no hint.
2. **Factory call.** With no declared type, a name whose every binding in the
   function is `x = f(...)` (or `x = await f(...)`) with the same callee text
   `f`, optionally mixed with `x = None`, gets the hint "returns of `f`". `f`
   may be `name`, `module.name`, `self.name`, `cls.name` or `Class.name`.
3. **Attribute.** A call `self.a.m()` / `cls.a.m()` in a method of class `C`
   uses the attribute hint of `C.a`. It is collected from the class body and
   every method of `C`, in this order:
   - a declared annotation: a class-body `a: T`, `self.a: T = ...`, or a
     `@property` / `@cached_property` named `a` with return annotation `T`;
   - otherwise every assignment to `self.a` must agree, and `None` is ignored:
     `self.a = T(...)` (a constructor), `self.a = p` where `p` is a parameter
     of that method annotated `T`, or `self.a = f(...)` (a factory, as in rule 2).

4. **Module-level name.** A module-level name gets a hint when every
   top-level binding agrees on one type: an annotation, a constructor
   `NAME = T(...)`, or a factory call. `None` is ignored, and no function may
   rebind the name through `global`. The hint applies to three call shapes:
   - `NAME.m()` in the defining module, when no enclosing function binds `NAME`;
   - `alias.NAME.m()` after `import pkg.mod as alias`, at module level or
     inside the function;
   - `NAME.m()` after `from pkg.mod import NAME`.

   For the second and third shapes, the extractor records only where to look.
   The defining module's hints are persisted as `symbols_json.module_types`, and
   Synapse resolves them there, following re-exports. Imports from stdlib
   modules are skipped. This covers singletons such as
   `REGISTRY = IndexSnapshotRegistry(...)` used as `owner.REGISTRY.publish(...)`.

An existing local constructor binding (`x = T(...)`, RFC-0002) keeps its
current path. Its callee is rewritten to `T.m` and resolves as `project`.

**Scope and shadowing are conservative.** A name gets no hint if it is:
- bound by `global` / `nonlocal` / `del`;
- a comprehension target, a lambda parameter, or a `match` capture, because
  those shadow it in a nested scope;
- in rule 2, bound by anything else (another call, a loop or `with` target,
  tuple unpacking, augmented assignment, walrus, import, nested definition, an
  unannotated parameter).

A nested function computes its own hints; closure variables get none.
Attribute hints come from the enclosing class only. An assignment to `self.a`
in a subclass is not considered.

**Type text.** It is normalised before resolution:
- quotes are stripped (forward references);
- `Optional[T]`, `typing.Optional[T]`, `Union[T, None]` and `T | None` become
  `T`, because a method call on the value can only reach `T`;
- these get no hint: a union of two or more classes, any other subscript
  (`list[T]`, `type[T]`, `Callable[...]`), `Any`, `object`, and builtin names.

`Self` in a return annotation means the class that declares the method.

**Type resolution** is in the annotating file's context:
- a class defined in that file;
- a name imported with `from M import T [as A]` (following package
  re-exports, up to 4 hops);
- `alias.T` through a module import.

An external or unresolvable module stops resolution. There is no project-wide
"unique class name" fallback.

**Method lookup** looks in the class, then its project bases,
depth-first, left to right, up to 6 levels. #1699: when more than one distinct
base branch defines the method, the nearest definition in the C3 linearization
of the project bases wins, as at runtime. An inconsistent linearization is not
attributed. If the
type or the method cannot be found, the call falls through to the existing
cascade unchanged.

The annotated rule runs first for a Python call site that carries a hint. A
hinted local shadows a module alias of the same name, which is Python's
scoping rule. The rule is deterministic: no fixpoint, at most one level of
return annotation, and bounded hops.

### 2. Provenance on the edge

The Synapse UPDATE writes:

| Column / field | Value |
|---|---|
| `callee_resolution` | `annotated_receiver` |
| `callee_symbol_id` | the method's symbol row |
| `callee_resolved_file` | the method's file |
| `metadata.receiver_binding` | `{"source": "param"\|"local"\|"attribute"\|"return"\|"module", "type": "<declared type text>", "owner": "<class owning the method>", "line": <method definition line>, "confidence": 0.8}` |

`nav callers` entries for such an edge carry `resolution_kind:
"annotated_receiver"`, `receiver_type`, `type_source` and `confidence`.
`callee_resolution` keeps its existing local/project classification for
compatibility.

### 3. Confidence

`0.8`: below an import binding (`0.9`), above the global name fallback
(`0.5`). An annotation is a claim the runtime does not check. A subclass
instance, a test double or a cast can stand behind it. So it is evidence for
the declared method, not proof of the runtime target.

### 4. Interaction with completeness (RFC-0028 §1)

`annotated_receiver` is deliberately **not** in
`_RESOLVED_CALLEE_RESOLUTIONS`. Every completeness reader therefore keeps
treating the edge as unresolved, except for the one target it is bound to:

- `count_unresolved_callers(name, file, bound_targets=...)` and the
  declaring-file site guard count an `annotated_receiver` row as resolved only
  when its `receiver_binding` (file, line) is one of the definitions the query
  is about. `nav callers` passes them: the qualified graph targets, or every
  definition of the bare name in scope.
- For any other same-name target (an override `Sub.m`, an unrelated
  `Other.m`, a Protocol implementation) the edge stays an unresolved inbound
  edge, exactly as before this RFC. So annotation resolution never makes
  another answer `complete`.
- In the cached call graph, the bound method is the certain target. Every
  override of `m` in a transitive subclass of the declared type (the #1635
  `SubclassIndex`), and every other same-name candidate the name-based tier
  would have offered, is a `possible` target. So dead-code and impact
  over-approximation lose nothing, and the overrides answer `NAME_ONLY_INBOUND`.

The rule is: an annotated edge adds a caller to its bound target. That target
answers `complete` only if no other unresolved same-name site remains. For a
receiver typed `Base` calling `m`, `Base.m` gains the caller; `Sub.m` (an
override) stays non-complete because of it.

### 5. Re-index and versioning

Hints are new extractor output: in edge `metadata` and, for module-level
names, in `symbols_json.module_types`. There is no schema change. `_AST_CACHE_EXTRACTOR_VERSION` goes from 39 to 40 (`ast_cache.py` and
`cache/indexer.py`), so the next refresh re-extracts every file indexed by
older code. Until then, old rows have no hint and resolve as before, so they
can only be less complete, never wrongly complete. A cross-file edge is not
re-resolved when only the defining file changes. That is the same staleness
every `project` edge has today, and a dangling symbol id is still caught by
`call_graph_edges_are_consistent`.

## Three-Surface impact (CLI ↔ MCP parity)

There is no new flag or action. `nav action=callers` (MCP) and `--callers` (CLI)
share `CodeGraphCallersTool`, so both gain the callers and the new per-caller
fields.

## Drawbacks

- An annotation can lie (duck-typed fakes, `cast`). Completeness stays
  correct because the edge is unresolved for every other target. The caller
  list of the declared method can then hold a call that, at runtime, reaches a
  fake.
- Indexing parses each Python function once more for bindings, and the
  resolver parses `symbols_json` once more, lazily and only when a hint exists.
  The cost is measured in the dogfood gate.

## Alternatives

- **Run a type checker (pyright) at index time.** It would be more complete,
  but it is a heavy optional dependency, slow, and not deterministic across
  versions. It is used here only as an offline cross-check.
- **Treat `annotated_receiver` as globally resolved**, like `project`. That
  is simpler, but an override in a subclass, or a file-scoped bare query,
  could then answer `complete` while the call dispatches to it. Rejected.
- **Rewrite the callee to `T.m`** like the constructor path. That would lose
  the provenance and make the edge `project`. Rejected for the same reason.

## Prior art

- Pyright and mypy use declared-type semantics. This RFC adopts the declared
  type and drops their narrowing.
- Jedi and Sourcegraph's scip-python apply the same "parameter annotation
  fixes the receiver" heuristic.
- RFC-0002 (constructor typing), and #1635 for the override-as-possible rule.

## Test plan (RED-first)

`tests/unit/test_annotated_receivers_1618.py`, on indexed fixtures, through
`CodeGraphCallersTool`:

- each source adds the caller, with `resolution_kind` and `type_source`:
  - parameter, annotated local and `Optional[T]`;
  - `self.x: T`, `self.x = T(...)`, `self.x = param` and a property;
  - a factory return annotation across modules;
  - a module singleton (same module, `alias.NAME`, `from m import NAME`);
- negative controls: a wrong-type receiver is not attributed; a union of two
  classes is not attributed; an unannotated or rebound receiver stays
  unattributed; an override in a subclass is not `complete` because of an edge
  typed with the base class; an unrelated same-name method's completeness is
  unchanged;
- extractor version 40 is pinned.

The dogfood gate runs old vs new code on one index of this repository, with a
seeded sample and AST-based ground truth.

## Acceptance criteria

- [ ] All five sources resolve, with provenance, on indexed fixtures.
- [ ] Negative controls are green: no false caller, no wrong `complete`.
- [ ] Dogfood gate: recall up, 0 false callers (each explained otherwise), 0
      wrong `complete`; latency and index time reported.
- [ ] CLI↔MCP parity test green.
- [ ] CHANGELOG updated.

## What this RFC does NOT do (deferred)

- Languages other than Python: TypeScript and Java have explicit types and
  their own resolvers.
- Chained factories (`make().publish()`), closure variables, attribute types
  inherited from a base class, and generic substitution (`Repo[T].get`).
- Refining completeness for an unrelated class that is provably not a
  subtype of the declared type.

## Open questions

1. Should `receiver_binding.confidence` be lowered for a test-file caller,
   where fakes are common?
2. Should an external base class earlier in the MRO, which might define `m`,
   block attribution? Today it does not.
