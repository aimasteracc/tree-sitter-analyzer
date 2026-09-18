# RFC-0037: Live text search action

- **Status**: implemented for v2.2.0 — owner direction 2026-09-19
- **Created**: 2026-09-19
- **Tracking**: TSA standard agent search surface; extends RFC-0033 and leaves RFC-0034 qualification gates intact
- **Affected source paths**: `text_search.py`, `mcp/tools/{search_facade,text_search_tool}.py`, `cli/`, `mcp/facade_map.py`, search tests, codemaps, generated facade docs, `skills/tsa-find/`

## Summary

TSA 增加无索引、实时源码、字面量检索入口 `search action=text`，CLI 对应
`--text-search`。它补齐当前搜索门面在任意文本、错误消息、配置键和未索引文档上的
空洞，使代理无需退回宿主 grep 才能完成精确定位。

首个公开版本只有原生 Python 权威实现，不要求或调用 ripgrep/fd，不读取或写入
AST 索引。可选 ripgrep 后端继续由 RFC-0034 管理；只有跨平台语义等价、安全和完整
任务收益门全部通过后，才能另案接入。此 RFC 不恢复 `search_content`、
`find_and_grep`、`batch_search`、`list_files`、`check_tools` 或它们的通用参数包装层。

## Motivation

当前 `search` 门面可以查符号、AST、图和可选语义向量，却不能查任意字面文本。
内置 `tsa-find` 因而把这类任务交回宿主搜索。实际 dogfood 已见以下断层：

- 猜错文件名时，结构读取只能返回文件不存在，不能恢复到正确文件；
- 已退役的 batch-search CLI 不再可用；
- FTS symbol 只查符号，不能证明任意文本不存在，并可能因索引并发写入而 fail closed；
- 首次项目索引对精确文本查询是不必要成本。

zvec-grep 的可取之处是把索引检索和无索引精确检索放在同一产品边界，并统一紧凑、
带源码坐标的结果。TSA 采用这个边界，但不复制它的依赖栈、daemon、自动建索引、
文本 chunk corpus 或 RRF 排名。

## Public contract

### MCP request

```json
{
  "action": "text",
  "query": "literal text",
  "root": ".",
  "case_mode": "smart",
  "word_match": false,
  "include_globs": [],
  "exclude_globs": [],
  "limit": 100,
  "output_format": "json"
}
```

- `query` 必填，UTF-8 长度 1–4096 bytes；拒绝 NUL、CR、LF。
- `root` 是单个项目内目录，默认项目根；必须经过现有项目边界验证。
- `case_mode` 是 `smart|sensitive|insensitive`。`smart` 在 query 含任意 Unicode
  大写字符时区分大小写，否则不区分。
- `word_match` 使用现有 Unicode `\w` 边界规则。
- include/exclude glob 各最多 64 项，每项最多 256 bytes，按 root 相对 POSIX path
  判断；exclude 优先。glob 只能缩小基础 admission 集，不能复活已忽略文件。
- `limit` 范围 1–1000，只限制展示，不中断扫描或改变完整计数。
- `output_format` 首期只接受 `json`。

首期没有 regex、上下文行、hidden/no-ignore/follow、任意后端选择、任意外部程序参数
或多查询批处理。正则继续使用宿主检索，直到后续 RFC 固定语义和安全预算。

### CLI twin

```text
--text-search QUERY
--text-search-root ROOT
--text-search-case {smart,sensitive,insensitive}
--text-search-word
--text-search-include GLOB
--text-search-exclude GLOB
--text-search-limit N
```

CLI 和 MCP 调用同一个 `TextSearchTool`，不建立第二套扫描器。`facade_map.py` 的
`NEW_ACTION_PARITY` 增加：

```python
"search_text": ("search", "text", "--text-search")
```

旧工具名不加入 legacy map，退役契约继续拒绝它们。

### Response

```json
{
  "success": true,
  "verdict": "INFO",
  "query": "needle",
  "match_mode": "literal",
  "effective_case_sensitive": false,
  "data_source": "live_source",
  "engine_used": "native",
  "source_evidence": {
    "consistency": "per_file_live",
    "index_used": false,
    "scan_complete": true
  },
  "total_count": 23,
  "displayed_count": 10,
  "file_count": 4,
  "listed_cap": 10,
  "truncated": true,
  "truncation_reason": "limit",
  "results": [
    {"file": "src/a.py", "line": 12, "column": 5, "text": "    needle = 1"}
  ]
}
```

固定语义：

- 一行最多一个 result；多次 occurrence 仍按一个命中行计数。
- `column` 是该行首个命中的 1-based Unicode code-point 列。
- `file` 是 project-relative POSIX path。
- 结果按 `(file, line, column)` 稳定排序。
- `text` 是完整逻辑行；响应预算不足时整次失败，不静默裁剪行。
- `total_count` 与 `file_count` 来自完整扫描，`limit` 后才生成展示列表。
- 完整扫描且零命中返回 `success=true, verdict=NOT_FOUND`。
- 读取、文件变化、预算、超时、worker 或 cleanup 失败返回
  `success=false, verdict=ERROR, results=[]`，不得返回部分成功或伪装为 NOT_FOUND。
- `per_file_live` 明确表示逐文件认证读取，不宣称仓库级原子 snapshot。

## Engine and safety boundary

新增两个小模块：

- `tree_sitter_analyzer/text_search.py`：冻结 request/hit/report DTO、原生扫描、worker
  JSON 协议；
- `tree_sitter_analyzer/mcp/tools/text_search_tool.py`：schema、参数校验、项目边界、
  async 调度和标准 envelope。

实现复用以下现有权威能力，不复制逻辑：

- `index_candidate_walker.walk_candidate_entries` 的有界、ignore-aware、no-follow
  admission；
- `ignore_rules.py` 的 `.gitignore` / `.ignore` / `.rgignore` 语义；
- `source_oracle.py` 的 descriptor-pinned、读取后身份核验和项目边界；
- `indexing_snapshot.decode_index_source` 的编码/换行规范；
- `source_lines.py` 已验证的隔离 worker、deadline、kill/reap、响应预算和
  “错误不等于空结果”模式。

`source_lines.workspace_files` 与较新的 candidate walker 有重复发现实现，不能直接成为
新公开动作的权威遍历器。新动作不访问 `.ast-cache`，不调用 certified index read，
也不缓存源码答案。

基础 admission 始终排除隐藏路径、已忽略路径、依赖/构建缓存、symlink、非普通文件
和含 NUL 的二进制文件。单文件过大、总字节、目录项、命中数、截止时间或响应大小
超限均 fail closed。读取时若 identity、size 或 mtime 改变，返回
`SOURCE_FILE_CHANGED`。

## Optional ripgrep boundary

RFC-0034 继续拥有可选后端资格。未来 rg 只有同时满足以下条件才可进入生产：

1. Python 先验证 root，并生成唯一 authoritative admitted-file scope；rg 不递归决定
   文件集合。
2. 采用固定 argv、`--no-config --json -F --`，不走 shell，不继承配置，不转发任意
   flags，不自动安装。
3. rg 只能接收已验证的显式输入；若文件替换/链接竞态无法证明安全，则不接入。
4. canonical rows、排序、完整计数、截断和输出均由 TSA 定义。
5. 仅核验正命中不能证明无漏报；未通过完整等价矩阵的后端不得产生 NOT_FOUND 或
   authoritative total count。
6. 核心 PATH 隔离测试必须证明 rg/fd 均不存在时 MCP 与 CLI 仍返回相同结果。

首期不公开 `engine` 参数，也不包含任何 rg 生产代码。

## TDD plan

先提交会失败的 public-contract 测试，再实现最小纵向切片：

1. facade enum/help 包含 `text` 并严格拒绝 typo；退役 action 仍不存在。
2. CLI flags 精确映射同一 inner tool；MCP/CLI canonical JSON 相同。
3. 无 `.ast-cache`、不可写 `.ast-cache`、并发 index writer 时结果不变且不创建索引。
4. literal metacharacters、smart/sensitive/insensitive、word boundary、Unicode、
   CR/LF/CRLF 和 invalid UTF-8 的精确命中行。
5. 嵌套 ignore/反规则、隐藏路径、symlink、重叠 root、越界 root、缺失 root、二进制
   与非普通文件。
6. 乱序创建文件仍按 project-relative path/line/column 排序。
7. `limit` 后仍有精确 `total_count`/`file_count`，且 `truncated` 只表示展示截断。
8. 读取拒绝、文件替换、单文件/总量/目录项/命中/响应预算、timeout 和 worker
   cleanup 全部 fail closed，results 为空。
9. 真实 CLI smoke：无 rg/fd、无 index 时 `--text-search` 返回当前源码命中。
10. facade action 数、MCP/CLI parity、codemap 自检和旧接口删除治理测试同步更新。

Python 变更按仓库契约运行 focused coverage 和 patch gate；随后执行 change-impact 给出的
命令与 quick gate。

## Performance qualification

首期性能目标是可测的非回退，不写未经验证的速度宣传：

- 固定 corpus SHA、OS、Python、文件/字节数量、query class、冷/热状态；
- 与现有 bounded native scanner 对比相同 admitted-file 集合和 literal workload；
- 新引擎 p50 不高于现有实现 1.10 倍，p95 不高于 1.20 倍；worker startup 单列；
- 任何结果集、失败分类、计数、排序或边界差异均优先判失败。

未来 rg 仍使用 RFC-0034 预注册的完整任务门，不以孤立扫描 benchmark 代替 agent
端到端收益。

## Delivery

1. 本 RFC 独立合入 `develop`，锁定 public contract。
2. native vertical slice：engine、tool、facade、CLI、parity、codemap、生成文档与
   `tsa-find`；不含 rg/regex。
3. 后续 hardening 可让 `nav.trace` 在不改变其过滤语义的前提下共享新的认证发现/读取
   primitives。
4. RFC-0034 阶段 A 单独运行 pinned rg 差异和任务基准；通过后再提可选 adapter RFC/PR。

## Acceptance criteria

- [x] `search action=text` 与 `--text-search` 的最小 schema、结果和错误语义固定
- [x] native-only 首期与 rg/fd 非依赖固定
- [x] 不恢复退役包装层或外部程序参数转发
- [x] zvec-grep 可借鉴与不采用的边界固定
- [ ] native engine、MCP action 与 CLI twin 实现
- [ ] no-index / no-rg / no-fd 的真实调用通过
- [ ] MCP↔CLI canonical parity、codemap 自检、patch coverage 与 quick gate 通过
- [ ] RFC-0034 资格门通过前无生产 rg 后端
