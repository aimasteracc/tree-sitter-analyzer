# AI Lessons

## 2026-09 — A green suite can still retain request-owned resources

### Context

Issue #1402 的一次完整 macOS 验证全部通过，但 `gw1` 在测试边界仍持有 329 个
文件描述符，其中包括 78 个 `routes.db`、78 个 `routes.db-wal` 和 69 个
`routes.db-shm`；随后一次垃圾回收把描述符数从 328 降到 19。实现检查发现
`RouteCache` 没有关闭接口，`RouteDetectorTool` 切换项目根时也只是丢弃旧对象。
测试结果为绿色，只能证明垃圾回收在低文件描述符用例运行前恰好发生，不能证明
连接所有权正确。

### Lessons learned

1. 持有 SQLite、文件或线程句柄的对象必须提供幂等的显式关闭接口；垃圾回收不是生命周期协议。
2. 使用线程局部连接时，关闭动作必须覆盖所有曾经创建连接的线程，并让后续访问按新代次惰性重建。
3. 长生命周期工具在项目根切换时必须先释放旧项目资源；一次性采集器要在成功和异常路径都关闭请求拥有的对象。
4. 全套测试通过不能抵消资源高水位证据；应同时验证旧句柄已经不可用，而不只验证返回值。

### Required guardrail

`tests/unit/test_route_detector_cache.py` 验证当前线程和工作线程的连接都会被关闭，
并验证项目根切换立即释放旧缓存；`tests/unit/test_codegraph_metrics_tool.py` 验证
一次性路由指标采集在成功和异常路径都调用关闭接口。

## 2026-09 — A gate must observe every route around the invariant

### Context

The dogfood claim `test_full_index_uses_one_filesystem_walk_for_all_index_phases`
failed after candidate discovery moved from `cache.indexer._walk_source_files`
to the certified candidate walker. The first repair changed the mock to the new
facade alias and restored 38 passing claim tests, but it still observed only the
expected initial walk. If either the AST or incremental phase stopped accepting
the shared snapshot, that phase could perform an extra walk through its own
imported alias while the test still counted exactly one facade call.
The repaired assertion then remained outside every pull-request gate because its
module carried both `benchmark` and `full_language`, while dogfood selected
`claims_benchmark and not full_language` and the coverage axis selected
`not benchmark`.

### Lessons learned

1. **Counting the intended route does not exclude hidden fallback routes.** A
   one-call assertion proves that the primary entry point ran once; it does not
   prove that another alias did not repeat the same I/O.
2. **Patch where each consumer resolves the symbol.** Python imports bind local
   aliases, and the AST runner additionally rebinds orchestration code to the
   indexer facade globals. A probe on the defining module alone cannot see those
   calls.
3. **A performance invariant needs positive and negative evidence.** The test
   must count the one authorized discovery and fail immediately if either phase
   invokes a candidate-less fallback walker.
4. **A guard outside CI is documentation, not enforcement.** Put a fast
   correctness invariant in the ordinary unit boundary even when the defect was
   first noticed through a benchmark claim.

### Required guardrail

`tests/unit/test_codegraph_full_index_tool.py` wraps the authorized
candidate walker exported by `tree_sitter_analyzer/mcp/tools/full_index_tool.py`
and installs failing probes on the AST and incremental fallback aliases. The same
test requires one primary walk, zero fallback walks, and the exact two-file
discovery and processing totals.

## 2026-09 — CI contracts must measure policy at the right granularity

### Context

A Dependabot pull request correctly moved `actions/upload-artifact` from major
version 6 to 7, but a diagnostics behavior test required the incidental literal
`v7.0.1` and rejected Dependabot's `v7` selector. A Windows CI replay-policy
test exceeded its per-test budget because the marker-policy check resolved the
same parent directory once for every one of 1,000 sibling test targets; the
original observation did not preserve enough runner metadata for a reproducible
latency claim, so this record remains qualitative. The first focused
qualification for the cache fix omitted the existing verification-command
contract. PR #1489 Windows job `104322614714` then ran
`uv run pytest tests/unit/mcp/test_verification_command.py -q --reruns 0
--tb=long` on Microsoft Windows Server 2025, Python 3.11.15, and reported both
resolution-exception parameters failing within its 42-case file run because the
synthetic failure hook still targeted the leaf resolution removed by the
optimization, rather than the parent resolution the new algorithm requires.

### Lessons learned

1. A behavior test should assert the action identity and supported major
   version it relies on; patch-selector policy belongs in a dedicated policy
   contract when the repository actually requires it.
2. Collection validation must cache work by the property being validated. The
   pytest selection policy belongs to a target's parent directories, so sibling
   files must share one resolution and configuration walk.
3. Performance fixes must retain boundary checks. Caching the resolved parent
   preserves traversal and symlink containment checks while removing duplicate
   filesystem calls.
4. A focused set derived only from changed-file suggestions can miss callers
   whose contracts depend on an internal operation. Search the changed symbol's
   direct tests and include their existing contract file in qualification.
5. Directory enumeration is not a bounded substitute for repeated target
   resolution: it retains unrelated siblings and can disagree with the host
   filesystem's case semantics. Cache the shared parent, then query only each
   requested leaf through filesystem-aware operations.

### Required guardrail

`tests/unit/test_classify_windows_pytest_failure.py` checks the diagnostics
action at its compatibility boundary, and
`tests/unit/test_verification_plan.py` requires 1,000 sibling targets to resolve
their shared parent only once while retaining replay-policy invalidation.
`tests/unit/mcp/test_verification_command.py` injects both supported resolution
exceptions at the required parent-resolution boundary and verifies fail-closed
command generation. `tests/unit/test_verification_plan.py` also forbids sibling
enumeration and exercises native Windows case-insensitive directory lookup.

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
`tests/unit/test_symbol_search_conceptual_demotion.py` 通过真实 search facade 固定公共适配器的严格参数、
坐标降级与 FTS 特殊字符兼容边界。

## 2026-09 — 源码扫描不能证明公共边界行为

### Context

PR #1491 将 symbol search 的实现拆到 `_execute_search` 后，一个测试仍用
`inspect.getsource(execute)` 查找提示字符串，四个 CI 轴都失败。与此同时，三个 Windows
正文恢复测试暴露了另一条平台边界：认证读取无条件调用只支持 POSIX `dir_fd` 与
`O_NOFOLLOW` 的 reader，因此 Windows 健康索引也只能返回坐标。

### Lessons learned

1. **实现文本不是行为契约。** 重构可移动字符串而不改变输出；测试必须调用用户实际调用的
   `execute` 边界并精确断言响应。
2. **分支前提必须由 fixture 固定。** next step 测试要强制“有结果、未截断、无正文”，否则
   空结果或正文 deterrent 会绕过目标分支形成假绿。
3. **平台能力必须逐层闭合。** Windows 能捕获索引数据库并不代表它能认证工作区源码；恢复
   正文还需要同样防重解析点、固定身份、限额和 deadline 的原生读取能力。
4. **认证成本应跟实际返回的证据成正比。** 导航查询可复用进程内固定的数据库能力，并只对本次
   响应真正返回的源码逐文件校验索引摘要；每次查询重新复制数据库并四次扫描仓库既慢，也扩大
   了 deadline 与并发漂移的故障面。
5. **SQLite progress handler 只有一个槽位。** 内层 call-graph 探针若安装再清空自己的 handler，
   会无意删除外层请求的绝对 deadline；嵌套读取必须显式复用外层 handler 所有权。

### Required guardrail

`tests/unit/mcp/test_runtime_guidance_facade_names.py` 通过公开 `execute` 固定精确 facade 提示。
Windows 正文恢复现由 `tree_sitter_analyzer/index_snapshot_windows.py` 的原生只读句柄完成，并在
`tests/unit/test_index_snapshot_windows.py` 证明完整 File ID、重解析点拒绝、层级固定、预算、
deadline、读取后复核与清理契约。`tests/unit/test_index_snapshot.py` 还固定数据库能力复用、逐文件
摘要认证和外层 progress handler 所有权；`tests/unit/test_codegraph_navigate_tool.py`、
`tests/unit/test_codegraph_callees_tool.py` 与 `tests/unit/mcp/tools/test_call_path_enrich.py` 固定 SQLite
中断只降级正文而不击穿公开工具，并继续作为跨平台正文恢复资格门槛。原有
`tests/unit/test_callers_callees_tools.py` 的正文恢复测试保留同一资格证据。

## 2026-09 — 求值失败不是空结果

### Context

2026-09-14 核验已有 watcher、generation 路由和订阅是否构成可信反馈时，发现
实际运行路径在 Hyphae 求值器外捕获所有 `Exception` 并返回 `[]`；随后 delta
计算把临时缓存、解析或求值失败当作全部结果被删除，覆盖最后有效快照并更新时间。
原实现上的针对性回归测试得到 7 个失败、4 个通过：直接收集路径抛出异常，而真实
桥接路径的三类故障和缺少 `project_root` 都产生了伪删除推送。

### Lessons learned

1. **空集是业务结果，异常是运行状态。** 只有成功求值的空列表能证明真实删除；
   把异常转换为空列表会同时伪造通知并破坏恢复时的比较基线。
2. **“已有组件”不证明端到端语义。** watcher、版本路由和订阅各自存在，仍须从
   保存回调的真实入口注入故障，观察实际快照、节流时间和推送行为。
3. **故障隔离应放在单个工作单元边界。** 每个订阅对各自捕获普通异常，既保留其
   最后有效状态，也允许同轮其他健康订阅继续求值；不能用整轮捕获掩盖注册表缺陷。

### Required guardrail

`tests/unit/mcp/test_watch_push_bridge.py` 从真实 `make_on_sync_callback` 路径注入
缓存构造、选择器解析和 Evaluator 求值失败，并固定失败后相同结果不通知、
新结果产生 delta、成功空集产生删除以及缺少项目根不改写状态的契约。

## 2026-09 — 请求任务不是连接身份

### Context

2026-09-14 检查 Hyphae 订阅所有权时，原实现使用当前 asyncio task 的地址生成
`sub_id`，并在取不到 task 时回退到进程内共享字符串。同一真实 MCP 内存连接的
连续工具请求由不同 task 处理，因而得到不同 ID；两个连接若调用恰在同一 task，
又会得到相同 ID。原实现的针对性测试为 6 个失败、6 个通过，并复现了退订一个
selector 就提前删除整个连接传输状态的行为。

### Lessons learned

1. **请求执行单元不等于连接所有者。** task、线程或默认字符串都不能代替 SDK
   已提供的 `ServerSession`；所有权必须从真实请求上下文获得。
2. **发布订阅有初始化边界。** watcher 能看到 registry 条目之前，session、loop
   和间隔映射必须完整，否则同步观察者会把半初始化订阅当作死亡连接。
3. **退订要先验证调用者，再按剩余 selector 清理。** 外来句柄必须在写入前拒绝；
   只有最后一项或整会话退订才可移除连接级传输状态。

### Required guardrail

`tests/unit/mcp/test_hyphae_push_wiring.py` 使用 SDK `RequestContext` 和真实内存流，
固定同连接跨请求 task 的稳定 ID、连接隔离、发布顺序、所有权拒绝、部分与最终
清理及幂等行为；`tests/benchmarks/claims/test_reactive_push_e2e.py` 保证既有声明
夹具也遵守请求上下文契约。

## 2026-09 — 有连接身份不等于有运行所有权

### Context

2026-09-14 在 MCP SDK 1.17.0 的真实内存连接上扩展 reactive 生命周期测试时，
R0/R1a 基线只固定了 session 身份，遗漏 application、run、project epoch 和 selector
incarnation。两个相同 raw root 的应用会交叉求值，一个 run 关闭后仍留下订阅；旧结果
或完成回调也可能推进 replacement。另一个测试把过期 ticket 送到入口，入口直接 no-op，
却没有证明有效 owner 的真实 completion 路径执行过。

### Lessons learned

1. **资源相同不代表所有权相同。** application token、run owner、project epoch 和
   selector incarnation 必须共同参与有效性判断；相同 root 不能合并应用边界。
2. **启动状态仍携带清理责任。** watcher 已进入 starting 后不能按 stopped 处理；重绑
   项目时必须保留启动所有权，直到原 daemon 和 callback 被确切撤销或完成清理。
3. **入口拒绝只能证明失效路径。** 过期 ticket 在调度入口被丢弃不会执行 completion；
   有效路径测试必须使用合法 owner、真实 SDK session 和 `Event` barrier 观察发送完成。

### Required guardrail

`rfcs/0035-trusted-reactive-feedback.md` 固定 R1b 的 ticket 与清理顺序；
`tests/unit/mcp/test_hyphae_push_wiring.py` 固定 owner、epoch、incarnation 和有效发送路径，
`tests/unit/mcp/test_mcp_server.py` 固定两应用、两 run、重绑及应用退出边界，
`tests/unit/mcp/test_watch_push_bridge.py` 固定旧 callback 不污染 replacement。

## 2026-09 — A historical qualification claim needs a reproducible receipt

### Context

The roadmap repeated a historical report of 429 passing tests and labeled it
`LOCAL_GO`. The current workspace contains no reproducible selection command,
exact collected and executed nodeids, or durable receipt for that run. The
count may describe a run that happened, but it cannot reveal which semantics
were exercised and therefore cannot serve as a semantic baseline or
qualification evidence. The roadmap was corrected, and this lesson records the
same correction so a later agent does not promote the orphaned count again.

### Lessons learned

1. **A published historical count is not a trusted baseline by itself.** A
   qualification claim must carry enough identity to reproduce the same
   selection against the same source, not only a total and a status label.
2. **Exact nodeids define the tested semantics.** The selector command and the
   complete nodeid manifest, including parameter IDs, distinguish the intended
   suite from a similarly sized but different selection.
3. **Evidence must outlive the workspace.** A durable receipt must bind the
   source identity, selector, nodeids, and item results; a local terminal report
   or remembered total cannot be upgraded later.
4. **Correct the lesson with the roadmap.** When a published qualification
   statement is withdrawn or narrowed, update the reusable lesson in the same
   change so the stale claim does not return through future planning work.

### Required guardrail

Any qualification statement in `rfcs/ROADMAP-no1-agent-trust.md` must either
link a durable receipt that binds the exact source identity, reproducible
selector, exact nodeids, and item results, or explicitly state that it is not a
semantic baseline or qualification evidence. The synchronized correction lives
in `docs/AI_LESSONS.md`, and
`tests/contracts/test_agent_docs_contract.py` pins the exact lesson-entry count
and required structure.

## 2026-09 — 容量必须约束相关证据，而不是全局支持表

### Context

这些计数来自 `aimasteracc/tree-sitter-analyzer` 提交
`355f1657fa5618d5fbb67c7bc0ffc2af1792e28e`：在 macOS 26.6.2 arm64、Python 3.14.3
上，以仓库默认排除规则和语言插件建立全量项目索引，再用仓库的
`architectural-constraints.yml` 执行约束检查。该索引有 25,628 条 `ast_imports`，但约束
查询只有 10,823 条 SQL 候选边、211 个候选调用文件和 2,247 条相关导入。原求值器先把
整个导入表物化，再检查调用边，因此固定的
10,000 项响应容量在读取无关证据时耗尽，真实 `--check-constraints` 以
`CONSTRAINT_EVALUATION_CAPACITY` 失败。首次修复把容量移到近似 SQL 候选上，又暴露了
无字面前缀 glob、重复边与缺少导入表三条边界。

### Lessons learned

1. **容量边界必须跟用户请求的相关集合对齐。** 全局支持表可以很大；只有通过规则 glob、
   scope 和 exception 的调用方及其导入行才应消耗本次求值的物化容量。
2. **SQL 预过滤不是精确资格。** 没有字面前缀的 glob 会保留全部边；在正则和 scope 前
   限制唯一调用方，会让完全无匹配的请求也失败。
3. **数据库内部去重会隐藏截止时间。** `SELECT DISTINCT` 可在 Python 重新获得控制前扫描
   大量重复行；需要流式读取并在 Python 去重，才能持续执行 deadline callback。
4. **兼容回退不能支付无用预扫描。** `ast_imports` 不存在时不会使用候选调用方集合，必须先
   检查证据表，再决定是否进行第二次边扫描。

### Required guardrail

`tests/unit/test_evaluator_bounds.py` 固定无关导入不耗尽容量、无前缀 glob 只计算
精确候选、重复候选持续检查 deadline，以及缺少导入表时只扫描一次 edge；约束求值的
focused patch-coverage gate 必须覆盖这些边界。真实全量索引 dogfood 还必须返回三条规则、
零违规和非零 evaluated-edge 计数，不能用空索引的 SAFE 替代。
## 2026-09 — 验证命令必须能选中它声称验证的目标

### Context

`change-impact` 为 benchmark claim 文件生成了精确测试路径，却同时保留默认的
`-m 'not network and not benchmark'`。目标文件带 `benchmark` marker，命令因此成功启动
pytest 但选中零项，给 agent 一个看似可执行、实际永远无法验证改动的建议。

### Lessons learned

1. **测试路径和 marker 是同一个选择表达式。** 单独验证路径存在不够；最终组合后的选择器
   必须至少能触达目标语义。
2. **只移除造成矛盾的精确项。** benchmark claim 目标只应移除精确的 `not benchmark`，继续
   保留 `not network` 等独立安全边界，不能为了让测试运行而清空全部 marker 约束。
3. **命令成功不等于验证成功。** 零收集、全跳过或目标 marker 被排除都应视为验证计划缺陷，
   不能成为 green evidence。
4. **路径表示法属于契约。** POSIX、Windows 分隔符和 pytest nodeid 后缀必须得到同一修正，
   普通 benchmark 目录仍应保持默认排除。

### Required guardrail

`tests/unit/mcp/test_verification_command.py` 固定 benchmark claim 的 POSIX、Windows 和 nodeid
路径会删除且只删除 `not benchmark`，并固定普通 benchmark 路径仍受默认 marker 排除；
生成命令的测试必须断言最终 marker 与目标可达性，不能只比较字符串片段。
