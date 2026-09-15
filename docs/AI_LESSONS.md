# AI Lessons

## 2026-08 — Remove the legacy compact wire format

### Context

A pull request proposed switching the MCP default from the legacy compact wire
format to JSON. The first review rejected that change because repository
instructions still described the compact format as a user-locked default. A
later user decision explicitly changed the direction: remove that format
completely and use JSON everywhere.

### Lessons learned

1. **Closing a pull request is not completing a migration.** The rejected PR
   was only a partial implementation. README files, CLI schemas, MCP defaults,
   compatibility tests, examples, workflow lists, and codemaps still formed a
   second contract. Completion requires a repository-wide search and a runtime
   verification pass.
2. **Repository instructions are part of the product contract.** A locked
   design note in `CLAUDE.md` contradicted the new user decision. When the
   decision changes, update the instruction, implementation, tests, and docs
   together; leaving the old rule makes future agents undo the migration.
3. **Do not hide an absent implementation behind compatibility shims.** A
   pass-through function that still has the old format's name or schema keeps
   stale API surface alive. Removing the encoder also requires removing its
   flags, enum values, response fields, fixtures, and tests.
4. **CI failures must be separated from feature changes.** The dependency and
   Actions PRs exposed pre-existing flaky benchmark and Python-version contract
   failures. Those were fixed in a separate `fix/ci-runtime-contracts` change
   before re-evaluating the dependency work, rather than masking failures in
   Dependabot branches.
5. **Verify the layer users actually call.** Contract tests that only exercise
   inner tools missed envelope duplication and default drift. MCP boundary
   behavior and CLI behavior need direct JSON assertions.

### Required guardrail

For future format migrations, the definition of done is: no active source,
configuration, schema, test, example, codemap, or README references the removed
format; all MCP and CLI defaults agree; focused tests pass; and a final
case-insensitive repository search is reviewed. The codemap half of that search
is already executable as `scripts/codemap-sync-check.sh`, whose surface set is
described in `AGENTS.md`. Historical changelog and postmortem entries may remain
only when clearly marked as historical.

## 2026-09 — A changed tool schema has a generated projection

### Context

Adding one parameter (`limit`) to `codegraph_navigate` failed all four CI test
axes with `docs/api/facade-actions.md has drifted from the facade registry /
inner tool schemas`. The local command set used before pushing covered
`tests/unit/mcp` and `tests/governance` but not `tests/unit/docs/`, so the
drift was invisible until CI.

### Lessons learned

1. **Some docs are built from the code, not written beside it.** Tool schemas,
   the facade registry, the CLI parser, and the language plugins each project
   into a generated file. A change to the source half is incomplete until the
   generated half is regenerated in the same commit.
2. **A focused local check is only as good as its file set.** "The tests I ran
   passed" says nothing about the gates whose directories were not in the set.
   Choose the set from the surface touched, not from the directory that felt
   related.
3. **The gate message is the instruction.** This one names the exact command to
   run. Reading the CI failure line is cheaper than guessing at a fix.

### Required guardrail

After any change to a tool schema, the tool registry, or the CLI parser, run
`python scripts/generate_facade_actions_doc.py` and include `tests/unit/docs/`
in the focused pre-push set. The drift contract is
`tests/unit/docs/test_facade_actions_doc_drift.py`.

## 2026-09 — Patch coverage marks the claim that is not proven

### Context

`codecov/patch` failed a pull request with 14 uncovered lines. The lines were
not incidental: the change claimed to make two discovery paths honor
`.gitignore`, and the uncovered half was the indexer path — the one the linked
bug was actually about. Nothing in the suite exercised that path's new
behavior, so the fix was unverified where it mattered.

### Lessons learned

1. **Read the uncovered lines before writing tests for them.** A patch-coverage
   miss is a question about coverage; the answer is often about correctness. On
   this change the miss identified a claim the PR could not support.
2. **Do not add a test that merely executes a line.** A test written to color a
   line proves nothing about the behavior the line implements. The two modules
   here reached full coverage only once the tests asserted the rule matcher's
   contract and each path's pruning, skipping, and retention behavior.
3. **Prove the tests bite.** Temporarily neutralizing the change and confirming
   the new tests fail is what separates a regression test from decoration. Here
   13 tests failed against the pre-fix matcher.

### Required guardrail

Run the local patch gate from `AGENTS.md` before pushing, and treat each
reported miss as a question about the change rather than about the test file.
`tests/unit/test_index_ignore_rules.py` is the worked example.

## 2026-09 — A process-wide enumeration is not a product surface

### Context

A reachability gate enumerated `BaseMCPTool.__subclasses__()`. That call is
process-wide, so it also collected every test double whose module happened to be
imported — `_FakeInner`, `_StubTool`, and the probes in `test_facade_tool`. The
same tree yielded 87 classes in isolation and 98 under a full parallel run, and
the count depended on how xdist distributed work. The gate's author pinned exact
counts, hit CI variance, and reverted to `assert len(classes) > 20`, which the
weak-assertion ratchet then rejected.

### Lessons learned

1. **Scope an enumeration to a declared source, not to the interpreter.** The
   fix is to keep only classes the tool modules define at module level, so the
   answer describes the product rather than the process.
2. **Cross-check a dynamic walk against a static read of the same source.** Set
   equality against an AST scan of the declared surface is stronger than any
   size bound: it names the missing entry, the extra entry, and the fact that
   the two halves disagree.
3. **A lower bound hides exactly the failures the gate exists to catch.** `> 20`
   passes while the walk collapses to a quarter of its real size. When a count
   genuinely must change, pin it and say so in the message.

### Required guardrail

`tests/unit/mcp/test_registered_surface_reachability.py` compares the import
walk against `_declared_tool_class_names()`, and
`tests/governance/test_tool_validation_contract.py` pins its own survey count
so a walk that stops matching fails rather than passing vacuously.

## 2026-09 — Latency without its cache state is not a number

### Context

`health action=project` was reported at 49.1 s in a public issue comment. A
profiler run of the same call returned 5.2 s. Re-measuring gave 48.8 s with
`.ast-cache/health_scores.db` removed and 4.5 s with it warm. The number was
real but incomplete: it described a cold run and was presented as the steady
cost. The same issue's older 202,470 ms figure carried no cache state either,
and was probably the same shape of measurement.

### Lessons learned

1. **State the cache state with any latency claim.** Cold and warm differ by an
   order of magnitude here, and they describe different user situations — a
   fresh checkout, a CI run, and a new agent session all start cold.
2. **A first measurement is a hypothesis.** Profiling before publishing is what
   caught this; the instrumented run disagreed with the reported figure.
3. **Correct the public record.** The correction was posted as a reply on the
   same issue, and the title changed to the part that is still true, because a
   stale issue title keeps misinforming readers who never open the comments.

### Required guardrail

The Measurement And Claim Rules in `AGENTS.md` require the cache/index state,
the machine, and the corpus with every published figure, and require cold and
warm numbers to be reported as a pair.

## 2026-09 — A per-item guard does not guard a collection

### Context

`MAX_TOTAL_DEFINITION_LINES = 160` was intended to bound the total source lines
inlined into one `nav action=navigate` response. The consuming loop called a
helper that opened with `budget = [MAX_TOTAL_DEFINITION_LINES]` once per
definition, so a 50-definition navigation rebuilt the budget 50 times and
inlined 50 full bodies: 38,720 characters. The constant was unreachable code.
The sibling tiers did not have the defect — they build one budget and pass it
down the list — which is what made the full tier's shape easy to miss.

### Lessons learned

1. **A budget must be created once per response and passed down.** If a helper
   constructs the budget itself, calling it in a loop silently multiplies the
   cap by the number of items.
2. **Compare parallel tiers before trusting one.** Three tiers implement the
   same idea; two shared their budget and one did not. Unexplained asymmetry
   between parallel values is a defect signal, not a style difference.
3. **Assert the cap binds across the list, not per item.** The test that proves
   it feeds a list of over-capacity records and asserts the summed lines stay
   under the shared total — a per-item assertion passes while the collection is
   unbounded.

### Required guardrail

`tests/unit/mcp/tools/test_symbol_body_inline.py` asserts the shared budget
binds across a list, that the budget is per call rather than per process, and
that records past the cap keep their coordinates.

## 2026-09 — A declared precondition that is never invoked

### Context

`SymbolLineageTool` declared `validate_arguments` with a `"symbol is required"`
message and never called it; `execute` read `arguments["symbol"]` directly. The
tool therefore answered a missing symbol with `KeyError: 'symbol'` instead of
the message written for that case — and answered the documented `function_name`
alias the same way. `CodePatternsTool` had the identical shape for `file_path`.
`wrap_execute_with_strict_params` checks the declared schema, not this method,
so invoking the guard is the tool's own responsibility.

### Lessons learned

1. **A declared contract that nothing calls is not a contract.** Declaring
   `validate_arguments` reads like protection; only the call site makes it one.
2. **Prefer a gate over a sweep.** Hand-checking found 19 tool classes declaring
   the method without calling it, of which only two subscript a parameter their
   own guard describes. Deriving that set from the AST covers tools added later;
   a fixed list of the two would not.
3. **Make the gate prove it can fail.** The contract test asserts its own survey
   count, and a probe pins that the analysis rejects the exact source shape it
   was written for.

### Required guardrail

`tests/governance/test_tool_validation_contract.py` derives the unguarded set
from `tree_sitter_analyzer/mcp/tools/*.py` and fails on any tool that reads a
parameter its own `validate_arguments` guards without invoking it.

## 2026-09 — Assert the surface, not the source

### Context

Auditing the expensive-route cost warning, I read
`tree_sitter_analyzer/mcp/tools/project_health_tool.py` and found that the
description already carried "SLOW: scans every source file. Budget ~30s on <200
files, ~90s on <1k, ~4min on <3k", and that the response already carried
`agent_summary.budget_seconds`. I drafted a correction to my own earlier
statement, saying the requirement was already met and the issue was stale.

It was not. The health **facade** replaces that inner tool in the tool
definition, the inner tools are not separately registered, and the measured
client-visible surface was:

```
health.get_tool_definition()["description"]   279 chars, 'SLOW' -> False
health.full_description()  (action=help)     3347 chars, 'SLOW' -> False
```

A caller could not read the warning anywhere. The issue was right and the
correction would have been wrong.

The same session produced the same shape twice more: quoting `health
action=project` at 49.1 s when that was the cold run, and filing #1475 against
caller misattribution that four re-measurements disproved and a stale scratch
index explained.

### Lessons learned

1. **Read the surface the caller reaches, not the file that looks relevant.**
   For an MCP tool that is `get_tool_definition()`, what `tools/list` returns —
   not the inner class the facade wraps, and not the module the feature lives
   in. A capability that exists but is not on a reachable surface does not
   exist for its user.
2. **A document is not evidence about the system.** An issue body, a previous
   note, and a docstring each describe the system at the time they were
   written. Reproduce the claim from the running code before repeating it, and
   before contradicting it.
3. **A near-miss is worth recording.** The wrong correction was caught only
   because the facade was checked last. Nothing failed; the record exists
   because the cost of the same mistake landing is a public retraction.

### Required guardrail

`tests/unit/mcp/tools/test_facade_cost_surface.py` states its expectations
against `get_tool_definition()` and `full_description()` — the two surfaces a
client can actually read — rather than against the inner tools that produce the
text. The Measurement And Claim Rules in `AGENTS.md` carry the measurement half:
name the state, the machine, and the corpus before publishing a number.

## 2026-09 — A best-effort catch turns a contract break into silence

### Context

Hoisting the per-repo git probes out of the per-file path changed two
signatures: `calculate_git_hotspot` gained a keyword-only `context`, and
`score_git_hotspot` gained a second parameter. Eight tests in
`tests/unit/test_health_scorer.py` double those functions, and the doubles kept
the old signatures.

Four failed loudly. One, `def query(*args)`, failed **silently**: it accepts no
keyword arguments, so `calculate_git_hotspot(..., context=ctx)` raised
`TypeError`, which `score_git_hotspot`'s `except Exception: return None` turned
into a `None` hotspot score. The test still failed, but through an assertion
about cancellation that never fired — I spent a long detour reading pool
scheduling before tracing the call and finding that the double was never
invoked at all.

The catch is correct in production: a git failure must not fail a health scan.
The problem is that it also covers the programming errors that look identical
from inside it.

### Lessons learned

1. **"Best effort" and "cannot fail" are different claims.** A catch around an
   external dependency is justified; a catch that also absorbs `TypeError` from
   a caller's own signature is a defect detector that has been disabled.
2. **When a test fails at a place that cannot explain the failure, check that
   the subject was reached at all.** The assertion that failed was about
   worker scheduling; the cause was that the function under test never ran.
   Instrumenting the entry point — one print — settled in a minute what
   reasoning about thread timing had not.
3. **A silent `None` is worse than an exception here.** The scan reported a
   `git_hotspot` dimension as unavailable rather than wrong, which reads as a
   property of the repository rather than of the code.

### Required guardrail

Doubles for a helper that participates in a best-effort catch must accept the
helper's real signature, including keyword-only arguments; `**kwargs` in a
double hides the same class of drift the catch does. The tests that pin the
hoist are `tests/unit/test_health_git_context.py`, and the equivalence check
that the score is unchanged is its
`test_the_scan_still_scores_git_hotspot_inside_a_repository`.

## 2026-09 — 读前后相同不能证明中间读取可信

### Context

为 symbol search 添加索引后源码变化测试时，最初只比较请求前后的源码状态。若文件在正文读取
期间由 A 短暂变为 B，再恢复 A，两个检查都能通过，却可能把旧索引坐标和 B 的正文组合进响应。
后续测试又一度只钩住新安全读取 primitive；这能覆盖新实现，却不能证明旧 live reader 在修复前
确实会混读，因此不是同一条 RED 的可靠回放。

### Lessons learned

1. **读前与读后相等不排除 ABA。** 返回的字节必须来自与索引 record、期望 hash 相同的 owner
   capability，而不是再打开一次当前路径。
2. **新 seam 变绿不能证明旧缺陷被捕获。** 回归测试应保留旧 reader 的故障注入，并让它完成
   A→B→A；否则基线可能只是因为新 primitive 不存在或未调用而失败。
3. **降级结果需要正反两类 oracle。** 测试既要证明健康 owner 实际返回正文，也要证明后验认证
   失败前正文确实存在、失败后才被清除，避免从头 coordinate-only 的假绿。

### Required guardrail

`tests/unit/test_symbol_search_tool.py` 的 transient ABA、same-connection 与 post-read 测试分别固定
旧 reader 的 A→B→A 回放、所有搜索模式使用 owner connection，以及第二次 scope 认证失败前后
正文状态；`tests/unit/test_index_snapshot.py` 固定 owner 的平台支持面与请求级预算。

## 2026-09 — 最终异常断言不能证明修复分支被执行

### Context

认证查询的首个回归测试先删除 `ast_symbol_rows`，随后断言搜索抛出异常；但级联搜索在 exact
阶段就失败，FTS 方法也因测试缓存未启用 FTS 而走已有的线性路径。测试因此没有执行本次修改的
LIKE、fuzzy 或 FTS 异常传播分支，在旧实现上也可能通过。

### Lessons learned

1. **最终结果相同不等于覆盖故障点。** 回归测试必须把失败注入到修复处理的具体阶段，并允许
   之前的阶段正常完成。
2. **兼容路径与严格路径要在同一故障下对照。** 普通缓存返回空列表、认证适配器抛出异常的并列
   断言，才能证明行为差异来自严格模式。
3. **功能开关属于测试前提。** FTS 异常测试必须创建真实 FTS5 表并确认适配器选择 FTS 路径，
   不能让线性回退替代目标分支。
4. **每个认证适配器都必须显式选择严格语义。** 共用查询函数的默认值服务普通缓存；新增 owner
   适配器若遗漏严格参数，另一适配器的通过证据不能证明真实公共调用链也会传播异常。

### Required guardrail

`tests/unit/test_index_snapshot.py` 使用 SQLite authorizer 分别在 LIKE 与真实 FTS5 `bm25` 阶段
拒绝查询，并对照普通缓存和 `tree_sitter_analyzer/index_snapshot_query.py` 的认证适配器行为；
`tests/unit/test_certified_symbol_search_errors.py` 通过真实 search facade 固定公共适配器的严格参数、
坐标降级与 FTS 特殊字符兼容边界。
