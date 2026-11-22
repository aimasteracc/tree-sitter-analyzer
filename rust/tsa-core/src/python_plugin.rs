//! Python 单语言插件契约(SPEC §2.1(c)、§1.3 第一批范围)。
//!
//! 对照 Python 侧来源:
//! - `languages/python_plugin/plugin.py`(`PythonPlugin`:`language_name`、`file_extensions`、
//!   `supported_queries`、`element_categories`、`analyze_file`、`api_analyze_file`)
//! - `languages/python_plugin/extractor.py`(`PythonElementExtractor` 及各 mixin 的元素抽取)
//! - `analyze_file_api` 顶层入口(`api_analyze_file` 的 success / missing_file 两种结局)
//!
//! 黄金对照物:`rust/fixtures/python_plugin/*.json`(5 份)+ `snippets/*.py` 语料。
//! Stage 1:全部函数体为 `todo!()`,签名即 Stage 2-3 的实现契约。

#![allow(unused_variables, dead_code)]

use serde_json::Value;
use std::collections::BTreeMap;

/// 命名节点计数:`node_type -> 出现次数`。
///
/// 与 fixture `corpus_python_node_types.json` 的 `named_node_counts` 同构
/// (BTreeMap 保证按 key 排序输出,与 Python 侧 sorted dict 的规范化 JSON 一致)。
pub type NamedNodeCounts = BTreeMap<String, usize>;

/// 语言名:固定 `"python"`。
pub fn language_name() -> &'static str {
    todo!("Stage 2-3: Python language plugin not yet implemented in Rust")
}

/// 文件扩展名(含点前缀):`[".py", ".pyw", ".pyi"]`。
pub fn file_extensions() -> &'static [&'static str] {
    todo!("Stage 2-3: Python language plugin not yet implemented in Rust")
}

/// 支持的 query 列表(排序后共 16 个,返回形态为 list)。
///
/// 对照 fixture `corpus_python_plugin_analysis.json` 的
/// `plugin_metadata.supported_queries_sorted` / `supported_queries_return_form`。
pub fn supported_queries() -> Vec<String> {
    todo!("Stage 2-3: Python language plugin not yet implemented in Rust")
}

/// 元素类别表(单复数键值对,如 `function`/`functions`、`django_model`/`django_models`)。
///
/// 对照 fixture `plugin_metadata.element_categories`(37 个键)。
pub fn element_categories() -> Value {
    todo!("Stage 2-3: Python language plugin not yet implemented in Rust")
}

/// 统计 source 中全部命名节点的类型计数。
///
/// 对照 fixture `corpus_python_node_types.json`:`total_named_nodes`(1061)、
/// `distinct_named_node_types`(57)与 `named_node_counts` 逐项一致。
pub fn count_named_nodes(source: &str) -> NamedNodeCounts {
    todo!("Stage 2-3: Python language plugin not yet implemented in Rust")
}

/// `PythonPlugin.analyze_file` 的纯内存形态:解析 source 并抽取元素。
///
/// 对照 fixture `corpus_python_plugin_analysis.json` 的 `analysis`、`to_dict`、
/// `to_mcp_format`、`elements_by_type` 四个视图。
pub fn analyze_python_file(relative_path: &str, source: &str) -> Value {
    todo!("Stage 2-3: Python language plugin not yet implemented in Rust")
}

/// 顶层 `api_analyze_file(relative_path, language=None)` 入口。
///
/// success 结局返回完整响应(6 键:`success`/`file_info`/`language_info`/`ast_info`/
/// `elements`/`query_results`);文件不存在等失败结局返回 `Err(异常消息)`
/// (Python 侧 raise `FileNotFoundError`,对照 fixture `api_analyze_corpus_python.json`
/// 的 `missing_file_case`)。`language` 显式传入且与实际不符时应走语言不匹配错误路径。
pub fn api_analyze_file(relative_path: &str, language: Option<&str>) -> Result<Value, String> {
    todo!("Stage 2-3: Python language plugin not yet implemented in Rust")
}
