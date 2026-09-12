# TSA 价值体检报告（2026-09-05）

总裁决（5 行）：
1. **投**：跨语言解析核心（护城河，已稳定，边际投入小收益大）＋ 智能体集成（13 skills + CODEMAPS + dogfood 环，自用复利最高）。
2. **冻结/砍候选**：no1 系信任实验收口、非全调用图语言层冻结新投入、viz 系不再扩。（hyphae 与 legacy 表格经复核升格为资产，见文末勘误。）
3. **维持**：MCP 表面、CLI、测试资产、发布机器——都已进入「改得动、跑得快」的稳态。
4. 最大意外：护城河核心文件近 90 天几乎零改动（call_graph 2 / import_graph 0 / project_graph 1），最热的反而是 mcp/（165）和 tests（415）——维护黑洞在表面和测试，不在核心。
5. 最大风险：bus factor 1（90 天 883 commits 来自一人）。PyPI 实页已随 v1.29.0 更新为 8 工具口径（pepy.tech 显示的旧文案是其缓存过期，勿被误导）。

判据说明：判决三档＝资产/存疑/死重量；证据＝亲手跑出的命令（标「实测」）或仓库文档（标「文档」）。成本＝行数/测试数/近 90 天改动次数。

---

## 1. 核心索引＋跨语言解析 —— 资产
- 证据（实测）：synapse_resolver/languages/ 下 12 个语言文件＋Python＝13 语言全调用图，与 README 声称一致；mis-wire 对比报告存在（benchmarks/codegraph_compare/REPORT-v1.21.0.md，文档）；全量测试 21,115 通过/78 跳过/77.69s。
- 成本：synapse_resolver 6,718 行/15 commits；call_graph.py 2、import_graph.py 0、project_graph.py 1、ast_cache.py 21。
- 动作：继续投语言解析质量，这是 390× 差异化的载体；核心已稳定，投入集中在新增 resolver 而非重写。

## 2. MCP 表面（mcp/ 65,169 行）—— 资产（带复杂度风险）
- 证据（实测）：README「8 个 MCP 工具」与注册表口径一致性契约测试通过（2 passed）；65K 行实现 8 个门面工具，内部是 55+ 工具收敛后的深度。
- 成本：65,169 行 / 90 天 165 commits——全仓库最热区。
- 动作：维持；这是产品表面，但复杂度集中，警惕 facade 后面继续膨胀。

## 3. 语言插件（README 口径 22 个分层）—— 资产与门面两极
- 证据（实测＋README 分层表）：README 口径 22 个语言插件＝13 全调用图＋2 symbol 待接线（Bash/Scala）＋5 单文件 CLI（HTML/CSS/Markdown/SQL/YAML）＋2 脚手架（JSON/Lua）；languages/ 目录实测 28 个含 plugin 字样条目，6 个差额为 README 未分层的在途/内部目录。13 个全调用图语言是 390× 差异化的载体（资产）；其余对外撑「20+ languages」门面，自用价值低。
- 成本：33,879 行 / 85 commits。
- 动作：13 个全调用图语言＝资产继续维护；非全调用图层冻结新投入，不再扩语言。

## 4. CLI（12,843 行）—— 资产
- 证据（实测）：MCP/CLI 对等契约测试存在且通过；`--structure --format json` 实测可用；v1.29 的 --doctor 直击安装摩擦。
- 成本：12,843 行 / 56 commits。
- 动作：维持。CLI 是 MCP 用户的逃生通道，也是对等契约的另一半。

## 5. formatters（15,451 行）—— 资产（偏重）
- 证据（实测＋复核）：`legacy_table_formatter.py` 是壳模块、整包重导出 `formatters/legacy/*`——它是 CLI `--table full/compact/detail` 的承载引擎（README 首推 `--table full`），不是死代码；TOON 是 MCP 侧的当前主张（体积约省一半）。
- 成本：15,451 行 / 19 commits。
- 动作：维持，不做大手术；15K 行偏重，触碰时顺手瘦身，不单独立项。

## 6. 智能体集成（skills/CODEMAPS/AGENTS 反馈环）—— 资产（自用价值第一）
- 证据（实测）：.claude/skills/ 13 个 tsa-* skills；docs/CODEMAPS/ 6 张地图＋同步契约；AGENTS.md 强制 dogfood 流程；TOON＋verdict 信封为 agent 设计。
- 成本：文档与流程为主，代码摊在其他区。
- 动作：投。这是「自己每天用、别人最难抄」的部分，也是外部叙事（agent-native）的证据来源。

## 7. knowledge_graph＋UML/可视化（2,940 行）—— 存疑
- 证据（实测）：90 天仅 5 commits；35 个 UML 测试文件＋HTML viewer；README 演示价值。
- 成本：2,940 行＋静态资产 / 5 commits。
- 动作：维持现状（演示与差异化展示），不投新人力。

## 8. hyphae 查询语言＋watch 推送 —— 资产（差异化卖点，低活跃）
- 证据（实测＋README）：README 明确以它为卖点——「Reactive push / subscription（RFC-0001, implemented）…CodeGraph has no push or subscription channel」；MCP select/subscribe 工具链依赖它；90 天 1 commit 属「已交付、稳定冻结」，非废弃。
- 成本：lexer/parser/evaluator 全套 DSL / 1 commit。
- 动作：维持现状；保留对外差异化叙事，不投新特性。

## 9. 测试资产（940 文件 / 21,330 条）—— 资产
- 证据（实测）：全量 77.69s 全绿，远快于 5 分钟契约；跳过 78/21,330＝0.37%，健康；契约/治理测试（runtime contract、parity、postmortem guards）防住过真实事故（v1.13 postmortem）。
- 成本：415 commits/90 天——第一维护黑洞。
- 动作：维持并用 scripts/check_loose_assertions.py 持续瘦身；测试改动占 commits 比例值得每季度看一次。

## 10. 发布与信任机器（CI/GitFlow/108 tags/benchmarks）—— 资产＋存疑
- 证据（实测）：108 个 tag，v1.25→v1.29 流水线顺畅；PyPI 实测 81.4k 累计下载、近 30 天 4.0k（pepy.tech，含 CI 流量）；no1 系信任实验（benchmarks 约 6K 行）投入大、产出未见于对外叙事。
- 成本：benchmarks 12 commits/90 天；GitFlow/CI 治理已成体系。
- 动作：发布机器维持；no1 实验收口成对外可引用的报告或冻结。

---

## 横断发现
- 勘误（2026-09-05 复核）：PyPI 实页（v1.29.0，2026-07-04 发布）已是「8 facade MCP tools」新文案，且有契约测试 test_pyproject_description_truth.py 守护；pepy.tech 显示的「58 tools / 1.14.0」是其自身缓存过期，无需动作。真正残留的旧文案在 pyproject `[tool.mcp].description`（「AI-era enterprise-grade…HTML/CSS support」）——一行修正候选，走 GitFlow PR。
- 外部用户真实存在且在升级（1.29.0 占近 90 天下载 17.8%）——「对外价值」不是零，值得每月看一次 pepy。
- bus factor 1：全部价值都压在单人维护上，文档/契约/测试体系是对冲，但无第二人。
