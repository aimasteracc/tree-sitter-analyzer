//! MCP facade 分发契约(SPEC §2.1(b))。
//!
//! 对照 Python 侧来源:
//! - `mcp/facade_map.py`:`FACADE_NAMES`(8)、`SET_PROJECT_PATH_TOOL_NAME`、`REMOVED_TOOL_NAMES`(5)、
//!   `LEGACY_TOOL_MAP`(62)、`NEW_ACTION_PARITY`(21)
//! - `mcp/_tool_registry.py`:facade 注册顺序(`_FACADE_REGISTRATIONS`,search/index 接受 lifecycle_manager)
//! - `mcp/tools/facade_tool.py`:`FacadeTool.execute` 分发序、参数校验/投影(F4)、
//!   符号别名(R3)、`action=help`、difflib 拼写建议、`INVALID_ARGUMENT` 错误信封
//!
//! 黄金对照物:`rust/fixtures/facade/facade_registry.json` 与 `facade_dispatch.json`。
//! Stage 1:全部函数体为 `todo!()`,签名即 Stage 2-3 的实现契约。

#![allow(unused_variables, dead_code)]

use serde_json::Value;

/// `NEW_ACTION_PARITY` 单条对照:`(facade, action, legacy_tool, legacy_action)`。
///
/// 与 fixture `facade_registry.json` 的 `facade_map.NEW_ACTION_PARITY` 一一对应(21 条)。
pub type ActionParity = (&'static str, &'static str, &'static str, &'static str);

/// `legacy_to_facade` 的映射结果:`(facade_name, action)`。
///
/// action 为空串表示该 legacy 工具没有 action 级投影(整体映射到 facade 默认行为)。
pub type FacadeRoute = (&'static str, &'static str);

/// 8 个 facade 名(`FACADE_NAMES`,顺序即注册顺序 `registry_order`):
/// `["search", "nav", "structure", "health", "edit", "project", "index", "viz"]`。
pub fn facade_names() -> &'static [&'static str] {
    todo!("Stage 2-3: MCP facade dispatch not yet implemented in Rust")
}

/// 唯一保留独立注册的工具名(`SET_PROJECT_PATH_TOOL_NAME`)。
pub fn set_project_path_tool_name() -> &'static str {
    todo!("Stage 2-3: MCP facade dispatch not yet implemented in Rust")
}

/// 5 个已移除、不再接受调用的工具名(`REMOVED_TOOL_NAMES`)。
pub fn removed_tool_names() -> &'static [&'static str] {
    todo!("Stage 2-3: MCP facade dispatch not yet implemented in Rust")
}

/// `LEGACY_TOOL_MAP` 查表:legacy 工具名 → `(facade, action)`(共 62 条)。
///
/// 未收录的名字返回 `None`(调用方据此走拼写建议 / `INVALID_ARGUMENT` 信封)。
pub fn legacy_to_facade(old_name: &str) -> Option<FacadeRoute> {
    todo!("Stage 2-3: MCP facade dispatch not yet implemented in Rust")
}

/// 名字是否属于 8 个 facade 之一。
pub fn is_facade_name(name: &str) -> bool {
    todo!("Stage 2-3: MCP facade dispatch not yet implemented in Rust")
}

/// 名字是否属于 62 个 legacy 工具之一(即可走 `dispatch_legacy` 兼容路径)。
pub fn is_legacy_name(name: &str) -> bool {
    todo!("Stage 2-3: MCP facade dispatch not yet implemented in Rust")
}

/// `NEW_ACTION_PARITY`(21 条):每个新增 action 与 legacy 工具/action 的对照行。
///
/// Stage 2-3 需保证逐条与 fixture `facade_map.NEW_ACTION_PARITY` 一致。
pub fn new_action_parity() -> Vec<ActionParity> {
    todo!("Stage 2-3: MCP facade dispatch not yet implemented in Rust")
}

/// facade 工具定义表(8 个 facade + `set_project_path` 的 name/description/inputSchema)。
///
/// 对照 fixture `facade_registry.json` 的 `facades` 与 `set_project_path_tool_definition`。
pub fn facade_definitions() -> Value {
    todo!("Stage 2-3: MCP facade dispatch not yet implemented in Rust")
}

/// `FacadeTool.execute` 的 facade 主分发入口。
///
/// 分发序:参数校验/投影(F4)→ 符号别名(R3)→ `action=help` → 真实 action;
/// 未知名走 difflib 拼写建议 + `INVALID_ARGUMENT` 错误信封。
/// 返回值始终是 envelope(错误也不抛异常,直接返回错误信封)。
/// 对照 fixture `facade_dispatch.json` 全部 15 个 case。
pub fn dispatch_facade(facade: &str, arguments: &Value, project_root: &str) -> Value {
    todo!("Stage 2-3: MCP facade dispatch not yet implemented in Rust")
}

/// legacy 工具名兼容分发:先 `legacy_to_facade` 查表,再复用 facade 分发。
///
/// 查表失败返回 `Err(错误消息)`(调用方包装为错误信封)。
pub fn dispatch_legacy(
    old_name: &str,
    arguments: &Value,
    project_root: &str,
) -> Result<Value, String> {
    todo!("Stage 2-3: MCP facade dispatch not yet implemented in Rust")
}
