# RFC-0031: 有界验证命令与计划重建执行

- **Status**: draft
- **Author(s)**: @aimasteracc / Codex
- **Created**: 2026-09-08
- **Last updated**: 2026-09-08
- **Tracking issue**: PR #1407 的 aggregate-command P2
- **Affected source paths**:
  - `tree_sitter_analyzer/mcp/tools/utils/verification_command.py`
  - `tree_sitter_analyzer/mcp/tools/utils/change_impact_analysis.py`
  - `tree_sitter_analyzer/mcp/tools/utils/change_impact_response.py`
  - `tree_sitter_analyzer/mcp/tools/change_impact_tool.py`
  - `tree_sitter_analyzer/verification_runner.py`（拟新增执行器）
  - `tree_sitter_analyzer/mcp/tools/edit_facade.py`
  - `tree_sitter_analyzer/mcp/tools/edit_facade_schema.py`
  - `tree_sitter_analyzer/cli/commands/mcp_commands/`
  - `tests/unit/mcp/test_verification_command.py`
  - `tests/unit/test_verification_runner.py`（新执行器对应测试）
  - `tests/contracts/test_mcp_cli_parity_contract.py`
  - `docs/CODEMAPS/cli.md`、`docs/CODEMAPS/mcp-tools.md`

## Summary

保留完整 `verification_steps`，把过长的可复制命令改为携带小型重建描述符的执行入口。
执行器重新分析同一项目、同一范围，核对完整计划摘要，然后以参数数组依次启动原来的
有界测试批次。分析阶段不写计划文件、不启动测试；执行阶段不从 token 接受任意命令。

这是设计草案，当前 PR 的超长命令缺陷尚未修复，也不能用本 RFC 代替实现验收。

## Motivation

2026-09-08 在 `c43d47c2` 实测：1,000 个 `tests/unit/test_feature_0000.py` 形状
的路径被分成 50 批，每批最大 656 UTF-8 字节，拼接后的 PowerShell 命令却有
37,704 个 UTF-16 code units。短路径 `tests/test_0000.py` 的同规模结果是 24,704，
所以不能声称“所有 1,000 路径都超限”，也不能只按目标数量判断。

Windows `CreateProcessW` 的命令行上限为 32,767 字符，包含终止空字符
（[官方文档](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)）。
每个子进程有界并不能证明启动整个计划的进程有界。调用者被明确要求执行
`verification_command`，仅建议其改用 `verification_steps` 不满足该承诺。

## Detailed design

### 重建描述符

版本 1 的 JSON 描述符包含：

- `version=1`、分析 `mode`（diff / staged / branch / pr）；
- 完整 `scope_paths`、`include_tests`、`resource_profile`、所选 `stage`；
- PR 模式的规范化 `pr_url` 及当次读取的 PR head/base identity；
- 当前项目根标识摘要、变更路径集合摘要、完整有序执行计划 SHA-256；
- 分析策略版本、执行总超时（默认 900 秒，可显式配置）。

不携带测试路径列表、shell 文本、任意 argv、回调或序列化 Python 对象。
描述符使用规范 JSON + base64url；摘要覆盖版本、runner、所有目标、顺序、重复次数、
资源参数以及所选阶段的默认门禁。不能对预览或截断列表计算摘要。

`stage` 区分完整验证、本地降载、CI 门禁和仅聚焦测试。公开的各命令字段必须明确
对应其原有阶段；高风险默认门禁不可因分批或选择短启动命令而丢失。

### 生成命令

拟新增 CLI：

```text
uv run python -m tree_sitter_analyzer --verify-plan <base64url-descriptor>
```

短单步命令保持现有行为。需要间接执行时，生成器检查**最终外层命令**的 UTF-8
字节数及 UTF-16 code units，二者均不超过 6,000，包含所有前缀和引用字符。
测试目标增加不能增加描述符中的路径列表：目标由同一分析算法重新发现。

描述符本身若因超大的用户范围参数而不能放入预算，返回明确的
`VERIFICATION_REQUEST_TOO_LARGE`，保留完整结构化计划作为诊断；不得省略范围、
换成默认套件或返回不可执行的成功命令。这个错误必须与“测试失败”区分。
后续如需文件或 stdin 输入，必须显式指定输入，不能在只读分析中暗写清单。

### 重建与校验

1. 严格验证 token 版本、字段、类型、编码和预算；拒绝未知执行字段。
2. 校验当前项目根标识，恢复原分析模式与完整范围。
3. 用同一计划编译器重建结构化步骤，禁止通过解析已渲染的 PowerShell 链恢复 argv。
4. 比较变更路径集合、PR 身份和完整计划摘要；不一致则返回
   `VERIFICATION_PLAN_CHANGED`，测试启动次数必须为零。
5. 校验所有批次的实际 argv 长度，保持现有目标数与进程预算约束。
6. 顺序执行；任一步失败、超时或取消即停止，后续批次及默认门禁均不启动。

计划摘要证明“将执行同一测试计划”，不证明源码在测试期间被冻结，也不签发 fresh
源码证据。报告不得把计划一致性升级为源码快照认证。

重建时必须直接调用无命令渲染递归的计划编译器。不能再次调用返回同一长启动命令的
完整 CLI 再执行其 `verification_command`，否则会形成递归或重复副作用。

### 执行与结果

MCP 拟使用 `edit(action="verify", request=<descriptor>)`，只在明确调用执行 action
时启动测试。`edit.impact` 仍只生成计划；`read_existing`、快照租约和 RFC-0022 的
进程内例外均不扩大。无法跨进程重建的快照描述符必须明确拒绝，不伪造可重放 token。

结果至少包含：计划摘要、阶段、总步骤数、已执行步骤及其退出码、首个失败步骤、
未执行步骤数、`passed / failed / changed / timeout / cancelled / error` 状态。
输出日志按显式预算截断并标记；截断日志不能截断测试集合或把未知结果计为通过。
本地阶段成功不能声称 CI 阶段已通过。CLI 的非零退出码必须反映失败或拒绝状态。

总超时、取消及启动失败必须回收所拥有的子进程树；不能只终止最外层 Python。
现有 `git_subprocess.py` 有进程组及 taskkill 清理，但带 Git 专用环境和输出限制；
`mutation_probe/runner.py` 会改变 pytest 配置，不能直接复用其测试启动命令。实现应
抽取或采用经过原生验证的通用进程所有权部分，保留 Python 3.10 支持，不能把现有
Git 的 best-effort 清理文字当成验证执行器已具备完整子进程回收的证据。

## Three-Surface impact (CLI ↔ MCP parity)

| Surface | Proposed access |
|---|---|
| CLI | `--verify-plan <descriptor>` |
| MCP | `edit(action="verify", request=<descriptor>)` |
| Python | `run_verification_request(request, project_root)`，共用同一校验和执行实现 |

CLI 与 MCP 必须支持相同模式、范围、阶段、超时和错误。action 参数须更新真实 facade
注册 owner、CLI dispatch、帮助及 codemap，运行真实 CLI smoke 和 parity contracts。
目前尚未新增这些入口；表格是待实现契约。

2026-09-08 合入 develop `a89d7229` 后重新核对：`edit_facade_schema.py` 已因
rename/apply 声明 `readOnlyHint=False`、`destructiveHint=True`，原草案所述
`destructiveHint=False` 已过时。本草案选择沿用现有 `edit(action="verify")`，
不新增独立工具、不扩大八个 facade 的注册集合。执行 action 仍需新增 CLI 对等路径。

现有 `openWorldHint=False` 不能覆盖任意项目测试：用户测试可能联网。注册执行 action
时应将整个混合 facade 的 `openWorldHint` 改为 `True`，并更新描述与 contract；
不能因为 TSA 自身快速套件排除了 network 标记就推断所有用户测试都是封闭的。
这属于本 RFC 的待评审元数据变更，当前代码尚未注册该 action。

### 完整计划摘要的边界

完整步骤先表示为带角色的参数数组记录：`focused`、`default_gate`、`non_test_check`。
阶段选择、资源降载和追加检查都在该结构上完成，最后才渲染 shell 文本。不能只给
`build_test_argv_batches` 的聚焦批次计算摘要后声称覆盖完整验证计划。

摘要输入使用固定版本的规范 JSON，字段包含 runner、stage、resource_profile 和完整
有序步骤。每一步的角色、可执行文件、参数顺序、重复参数、Unicode 和空参数都进入
SHA-256；不排序或去重步骤，不纳入计时、日志或显示截断。默认门禁被移除、阶段被替换、
末尾追加检查改变，必须得到不同摘要。项目根、模式、范围和 PR 身份另由描述符完整绑定，
再分析生成的这两部分均匹配才允许启动第一个子进程。

`80d33fb9` 已实现纯 argv 聚焦批次编译并接入命令渲染，测试覆盖重复/Unicode 参数及
Windows 实际启动引用预算。它没有实现上述完整阶段计划、摘要或执行器，验收项保持未勾选。

### PR 模式的 checkout 约束

当前 `_execute_pr_analysis` 只获取变更路径与 diff stat，没有把 PR head/base SHA
传入 `ChangeImpactRequest`。执行描述符生成前必须补齐这项事实，不能从 PR URL 推断
本地 checkout 正确。

PR 执行描述符绑定规范仓库与编号、当次远端 head/base SHA、本地 HEAD。生成和重建时均
要求本地 HEAD 等于远端 PR head，且已跟踪文件的暂存/未暂存差异为空；不自动 checkout、
reset 或修改用户文件。GitHub 合成 merge checkout 或其他提交明确返回 checkout 不匹配，
不能把它冒充 PR head。后续若要支持 merge checkout，必须单独定义并验证其双亲身份。

重建时重新查询远端 head/base，任一变化或查询失败均拒绝执行。该约束只证明启动前的
PR checkout 身份与计划一致，不证明运行期间源码被冻结。diff/staged/branch 模式仍使用
各自现有差异语义，不继承 PR 模式的干净工作区要求。

## Drawbacks

重建增加一次分析成本。Git、PR 或索引状态改变会使旧 token 失效，需要重新分析。
新增执行 action 扩大运行测试的入口面，因此 token 不能承载任意命令，且测试执行
与只读分析必须清晰分开。大型用户范围参数仍受启动输入预算约束，不能无限内联。

## Alternatives

- 继续拼接批次：已被实测否定，外层启动仍可能超限。
- gzip/base64 内联全部目标：常见路径能压缩，但随机路径与更大集合仍无界。
- 只返回结构化步骤：不能兑现当前可复制 `verification_command` 的完整执行承诺。
- 自动写临时清单：容易实现，但与显式只读分析冲突，并引入生命周期和清单替换问题。
- 只运行默认套件：已知目标可能在默认 quick gate 之外，会重新引入漏测。

## Prior art

沿用本项目的有界 subprocess 批次、计划与展示分离、源码认证不从观察推断等原则。
借鉴 Windows 原生进程输入上限作为启动预算证据，不以某个 shell 恰好接受输入来证明
所有调用方式可执行。外部产品优劣不由本 RFC 评判。

## Test plan (RED-first)

- 固定上述 1,000 路径反例；外层命令与每批 argv 同时满足预算，最后一个目标确实执行。
- 10,000 个随机长路径的计划不向启动命令内联路径集合，无遗漏、重复或次序变化。
- 真正执行生成命令：晚批次失败、默认门禁失败、全通过三种情况都有准确退出状态。
- 计划、范围、项目根、PR 身份改变时不启动任何测试；畸形 token 不能执行任意 argv。
- diff、staged、branch、pr，以及默认/本地降载/CI 阶段均校验真实重建请求。
- 分析只读场景前后比较文件及缓存写入；生成命令不得新增计划文件。
- Windows PowerShell 5.1、POSIX shell、带空格/单引号/Unicode 的路径通过原生执行。
- 超时/取消杀死拥有的整个进程树；日志截断不影响步骤计数与失败传播。

## Acceptance criteria

- [ ] 重建描述符与完整步骤摘要实现并通过 RED-first 用例。
- [ ] `verification_command`、test/pytest aliases 及阶段命令都受外层预算保护。
- [ ] 所有现有分析模式完整支持，计划变化明确拒绝且无测试副作用。
- [ ] 大目标集合真实执行与默认门禁不遗漏。
- [ ] 只读分析、进程树回收、Windows 原生验证通过。
- [ ] CLI↔MCP parity、codemap、自测及补丁覆盖门禁通过。
- [ ] PR 审查关闭超长命令问题；实现合并后才更新状态。

## What this RFC does NOT do (deferred)

不改变测试发现算法，不承诺冻结运行中的用户源码，不把验证通过等同于产品无缺陷，
不以新入口替代 No.1 评估、冷启动成本或实时反馈性能验证。

## Open questions

1. 是否接受现有 edit facade 的 verify action 及 `openWorldHint=True` 元数据调整？
   本草案已选择该方案供 RFC 评审，不再保留基于旧 destructive 注解的独立工具分支。
2. 第一版严格要求 PR head checkout；是否另行支持 GitHub 合成 merge checkout？
   在双亲与工作区验证契约通过前，不能放宽为任意本地 HEAD。
3. 对超大的用户范围描述符，是否增加显式文件输入；这不能成为默认只读分析的隐式写入。
