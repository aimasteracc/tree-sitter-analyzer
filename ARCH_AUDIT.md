# 代码与测试架构体检报告（2026-09-05，main@915eb0de）

总裁决（5 行）：
1. **代码架构：方向极干净，体积失守**——三条铁律 16.9 万条依赖边零违规（实测+契约双验证），但 mcp/ 巨石 6.5 万行、树根散件 52 个、约束 DSL 只锁了 31 个包中的 3 条方向。
2. **测试架构：分层名存实亡**——unit 层 817 文件占 87%，其中 38 个"单元"测试在起子进程；巨文件债三个月翻三倍（13→36 个超 800 行）。
3. **最大隐患**：快速门分裂——同一条 `pytest -q` 在 main 是全量 21k/84 秒、在 develop 是精选 20 文件/37 秒，跨分支工作的 agent 必被咬（本会话已实际中招一次）。
4. 最不能碰的：契约测试体系（3 条铁律+runtime contract+GitFlow guard）——它们是分层干净的唯一原因。
5. 下一刀优先级：①统一快速门语义（或改名显式化）②unit 层去子进程化 ③mcp/tools 巨文件按 facade 拆包。

---

## 一、代码架构

### 做对的（有实测背书）
- **分层方向零违规**：约束 DSL 3 条（mcp↛cli、core↛mcp、languages↛mcp）经 `--check-constraints` 在 169,288 条边上实测通过；AST 级 import 矩阵实测同样干净（cli→mcp 59 处单向、mcp→cache 12、synapse_resolver→languages 10，无反向）。
- 31 个包职责命名清晰（cache/graph/registry/serialization/encoding/exceptions 的拆分是近期偿债成果）。

### 问题（按严重度）
1. **【高】mcp/ 巨石**：65,169 行（占全库 1/3）、近 90 天 165 commits（最热区）；TOP10 巨文件有 6 个在 mcp/tools/（symbol_lineage 1174、codegraph_context 1155、get_code_outline 1131、analyze_scale_helpers 1028、change_impact_analysis 1017、trace_impact_tool 1015）。8 个 facade 门面下藏着单体引擎室。
2. **【高】树根散件堆场**：52 个根级 .py 与 31 个包并存（ast_cache.py 976 行、uml_export.py 972 行……）——包体系外的法外之地；develop 在拆（cache/ 包化）但根目录仍在生长。
3. **【中】约束 DSL 覆盖率 3/31**：formatters→mcp、knowledge_graph→cli、hyphae→cli 等方向今天没人违反，但也没有契约拦——分层干净目前靠自觉+巧合，不靠制度。
4. **【中】scala_plugin.py 1389 行**：自家「禁止新增单文件插件」棘轮的活化石（最大单文件，grandfathered）。
5. **【低】plugins/__init__.py 零引用重复 ABC**（develop 亦在）；cache/extraction.py 1273 行待拆。

## 二、测试架构

### 做对的
- 分层目录齐全：unit/integration/contracts/governance/e2e/property/benchmarks/golden/regression；conftest 仅 6 个（克制）。
- 契约+治理测试是真实资产（防过真事故）；变异测试基建已修复可用（v1.29.2 起）。

### 问题（按严重度）
1. **【高】快速门分裂（跨谱系陷阱）**：main 裸 `pytest -q`＝全量 21,330/84s（pytest.ini 无 testpaths 策略）；develop 裸 `pytest -q`＝精选 20 文件/37s（pytest.ini testpaths 白名单）。同一命令两种语义——文档、CI、agent 的心智模型必然错位（v1.29.2 mergeback 假绿事故的直接根因）。
2. **【高】unit 层失守**：817 文件占全部测试 87%；38 个「unit」测试文件在起子进程（subprocess/create_subprocess）——本该属 integration/e2e 的内容混进 unit，层标签失真，隔离承诺（快速、无环境依赖）名存实亡。
3. **【高】巨文件债恶化中**：>800 行测试文件 36 个（6 月自审时 13 个，三个月 ×2.8）；最大 test_knowledge_graph.py 2167 行。6 月审计定的「触碰时拆分」纪律未被执行——债务在复利。
4. **【中】测试侧散件堆场**：53 个 `_` 开头助手文件（6 月 48 个，在涨）；tests/unit/mcp 独占 219 文件（6 月口径）。
5. **【低】目录语义混杂**：tests/test_data/ 里有测试文件；tests/effectiveness/ 只有 BASELINE.md 文档；tests/golden_masters 与 tests/golden 并存两个 golden 目录。
6. **【低】变异测量盲区**：RFC-0017 只盖 5 个模块，其余 ~740 个源文件的测试有效性无测量（scoreboard 无法外推）。

## 三、下一刀清单（执行型任务候选）
1. 统一快速门：要么 main 也上 curated 白名单，要么 develop 改成显式 `pytest tests/…` 别名/脚本——消灭同命令双语义（小改动，高价值）。
2. unit 去子进程化：38 个文件迁 integration/e2e 层＋加 marker，恢复 unit 层承诺。
3. mcp/tools 拆包：按 8 个 facade 对应拆（nav/structure/edit/health/…），每个 <10K 行。
4. 巨测试文件拆分批次（36 个 >800 行，按触碰频率排）。
5. 约束 DSL 扩到 ~10 条方向铁律（把实测干净的方向固化成制度）。

数据来源：2026-09-05 main@915eb0de 实测（AST import 矩阵、--check-constraints、目录普查）＋ tests/TEST_ARCHITECTURE_AUDIT.md（2026-06-20 自审基线）＋本会话此前审计存量。

---

## 勘误与深化（2026-09-06，P1-1 执行时修正）

1. **「unit 层 38 个子进程文件＝层泄漏」系过度指控**：分类后约 25 个
   diff_snapshot/temporal/oracle 系测试起 git 正是被测功能本身（git 耦合
   是产品核心），属合法 unit；真·环境级泄漏（mutmut 探针、no1_010b 的
   uv、benchmark harness、自主脚本）合计约 13 秒且全部高速 mock——
   大规模迁移＝高扰动零收益，**降级为可选**，不建议执行。
2. **巨文件债务比本报告初版更严重**：>800 行文件实为 **52 个**（初版
   快照漏计 develop 新增），最大单文件 16,567 行（test_benchmark_harness），
   是初版榜首的 7.6 倍。800 行清单原是无牙齿的手工快照，现已改为
   活契约（tests/contracts/test_large_test_file_inventory.py）——
   清单与现实漂移即 CI 红。三大巨无霸拆分立案 #1376。
