//! Stage 1 红灯契约测试:`tsa_core::python_plugin` 对照黄金 fixtures(Python v3.1.2 真实输出)。
//!
//! 黄金对照物(`rust/fixtures/python_plugin/`):
//! - `corpus_python_expected.json` —— 语料 9 个关键节点类型的冻结计数;
//! - `corpus_python_node_types.json` —— 语料全部命名节点计数(57 类型 / 1061 个);
//! - `corpus_python_plugin_analysis.json` —— `analyze_file` 的 analysis / to_dict /
//!   to_mcp_format / elements_by_type 四视图;
//! - `api_analyze_corpus_python.json` —— 顶层 `api_analyze_file` 的 success / missing_file 结局;
//! - `edge_cases_analysis.json` —— 5 个聚焦片段的同套视图。
//!
//! 语料本体:`<repo>/tests/golden/corpus_python.py`(经 `../../` 从 crate 清单定位,与 cwd 无关)。
//!
//! Stage 1 验收判据:本文件全部测试因 `todo!("not yet implemented")` 而红、编译零警告
//! (SPEC §5.2);Stage 2-3 实现后同一批测试转绿,断言不变。
//!
//! 计时字段约定:`analysis_time` 在黄金数据中已归一化为 `null`,实现若产出实测耗时,
//! 对照前同样归一化为 `null`(本文件 `normalize_analysis_time`)。

use serde_json::Value;
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use tsa_core::python_plugin;

// ---------- 定位与加载辅助 ----------

/// crate 清单目录(`rust/tsa-core`)。
fn manifest_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

/// 仓库根(`rust/tsa-core` → 仓库根),语料 `tests/golden/corpus_python.py` 在此之下。
fn repo_root() -> PathBuf {
    manifest_dir().join("../..")
}

/// fixtures 根目录(`rust/tsa-core` → `rust/fixtures`),与 cwd 无关。
fn fixtures_dir() -> PathBuf {
    manifest_dir().join("../fixtures")
}

/// 读取并解析一份黄金 fixture;失败即 panic(契约测试不该静默跳过)。
fn load_fixture(rel_path: &str) -> Value {
    let path = fixtures_dir().join(rel_path);
    let raw = fs::read_to_string(&path)
        .unwrap_or_else(|err| panic!("无法读取 fixture {}: {err}", path.display()));
    serde_json::from_str(&raw)
        .unwrap_or_else(|err| panic!("fixture 不是合法 JSON {}: {err}", path.display()))
}

/// 读取文本源码;失败即 panic。
fn read_text(path: &Path) -> String {
    fs::read_to_string(path)
        .unwrap_or_else(|err| panic!("无法读取源码 {}: {err}", path.display()))
}

/// 黄金语料全文(`tests/golden/corpus_python.py`)。
fn corpus_source() -> String {
    read_text(&repo_root().join("tests/golden/corpus_python.py"))
}

/// 语料在黄金数据中的相对路径(to_dict.file_path 的冻结值)。
const CORPUS_RELATIVE_PATH: &str = "tests/golden/corpus_python.py";

/// 允许 `obj` / `int` 同时接受 `&Value` 与 `&Map<String, Value>` 两种载荷形态。
trait FieldLookup {
    fn field(&self, key: &str) -> Option<&Value>;
}

impl FieldLookup for Value {
    fn field(&self, key: &str) -> Option<&Value> {
        self.get(key)
    }
}

impl FieldLookup for serde_json::Map<String, Value> {
    fn field(&self, key: &str) -> Option<&Value> {
        self.get(key)
    }
}

/// 取对象字段的 JSON 对象形态。
fn obj<'a, P: FieldLookup>(payload: &'a P, key: &str) -> &'a serde_json::Map<String, Value> {
    payload
        .field(key)
        .unwrap_or_else(|| panic!("缺少字段 `{key}`"))
        .as_object()
        .unwrap_or_else(|| panic!("字段 `{key}` 不是对象"))
}

/// 取对象字段中的 i64。
fn int<P: FieldLookup>(payload: &P, key: &str) -> i64 {
    payload
        .field(key)
        .and_then(Value::as_i64)
        .unwrap_or_else(|| panic!("字段 `{key}` 缺失或不是整数"))
}

/// `analysis_time` 归一化:实测耗时(数值)统一置为 `null`,与黄金数据对齐。
fn normalize_analysis_time(view: &mut Value) {
    if let Some(map) = view.as_object_mut() {
        if map.get("analysis_time").is_some_and(|t| !t.is_null()) {
            map.insert("analysis_time".to_string(), Value::Null);
        }
    }
}

/// 逐视图对照 `analyze_python_file` 返回值与黄金数据。
///
/// 返回值形状契约:对象,恰含 `analysis` / `to_dict` / `to_mcp_format` / `elements_by_type`
/// 四个键。黄金侧存在的视图逐一精确对照(to_dict 与 to_mcp_format.metadata 的
/// `analysis_time` 归一化后对照;边缘片段 fixture 不含 to_mcp_format,则跳过该视图)。
fn assert_analysis_views_match(result: &Value, golden: &Value, ctx: &str) {
    let result_map = result
        .as_object()
        .unwrap_or_else(|| panic!("{ctx}: analyze_python_file 返回值应为 JSON 对象"));
    let mut keys: Vec<&str> = result_map.keys().map(String::as_str).collect();
    keys.sort_unstable();
    assert_eq!(
        keys,
        ["analysis", "elements_by_type", "to_dict", "to_mcp_format"],
        "{ctx}: 返回值应恰含四个视图键"
    );

    // analysis 视图:line_count / node_count / success / error_message 精确一致。
    assert_eq!(
        result_map.get("analysis"),
        golden.get("analysis"),
        "{ctx}: analysis 视图与黄金不符"
    );

    // to_dict 视图:analysis_time 归一化后精确一致。
    let mut actual_dict = result_map
        .get("to_dict")
        .cloned()
        .unwrap_or_else(|| panic!("{ctx}: 返回值缺少 to_dict 视图"));
    normalize_analysis_time(&mut actual_dict);
    let golden_dict = golden
        .get("to_dict")
        .cloned()
        .unwrap_or_else(|| panic!("{ctx}: 黄金数据缺少 to_dict 视图"));
    assert_eq!(actual_dict, golden_dict, "{ctx}: to_dict 视图(analysis_time 归一化后)与黄金不符");

    // to_mcp_format 视图:metadata.analysis_time 归一化后精确一致(黄金侧可能缺席)。
    if let Some(golden_mcp) = golden.get("to_mcp_format") {
        let mut actual_mcp = result_map
            .get("to_mcp_format")
            .cloned()
            .unwrap_or_else(|| panic!("{ctx}: 返回值缺少 to_mcp_format 视图"));
        if let Some(metadata) = actual_mcp.get_mut("metadata") {
            normalize_analysis_time(metadata);
        }
        assert_eq!(
            &actual_mcp, golden_mcp,
            "{ctx}: to_mcp_format 视图(metadata.analysis_time 归一化后)与黄金不符"
        );
    }

    // elements_by_type 视图:分类键集、元素逐字段精确一致(黄金侧可能缺席)。
    if let Some(golden_by_type) = golden.get("elements_by_type") {
        assert_eq!(
            result_map.get("elements_by_type"),
            Some(golden_by_type),
            "{ctx}: elements_by_type 视图与黄金不符"
        );
    }
}

/// 对照命名节点计数与黄金 `named_node_counts`:键数一致、逐键计数一致。
fn assert_named_counts_match(
    counts: &BTreeMap<String, usize>,
    golden_counts: &serde_json::Map<String, Value>,
    ctx: &str,
) {
    assert_eq!(counts.len(), golden_counts.len(), "{ctx}: 命名节点类型数不符");
    for (node, expected) in golden_counts {
        let expected = expected.as_i64().unwrap_or_else(|| panic!("{ctx}: 黄金计数 `{node}` 不是整数"))
            as usize;
        assert_eq!(
            counts.get(node),
            Some(&expected),
            "{ctx}: 节点类型 `{node}` 计数不符"
        );
    }
}

// ---------- 1. 插件元数据 ----------

/// 元数据契约:language_name / file_extensions / 16 个 supported_queries / element_categories。
///
/// 注:element_categories 的黄金键数为 **35**(17 对单/复数别名 + `all_elements`,
/// 见 `rust/SPEC.md` §166 与 fixture);`src/python_plugin.rs` docstring 中的「37 个键」
/// 与黄金数据不符,以 fixtures 为准。
#[test]
fn test_python_plugin_metadata() {
    assert_eq!(python_plugin::language_name(), "python");

    let extensions = python_plugin::file_extensions();
    assert_eq!(extensions, [".py", ".pyw", ".pyi"].as_slice());

    let fixture = load_fixture("python_plugin/corpus_python_plugin_analysis.json");
    let metadata = obj(&fixture, "plugin_metadata");

    // 黄金侧 language_name / file_extensions 与实现一致。
    assert_eq!(
        metadata.get("language_name").and_then(Value::as_str),
        Some(python_plugin::language_name())
    );
    let golden_ext: Vec<&str> = metadata
        .get("file_extensions")
        .and_then(Value::as_array)
        .expect("黄金缺少 `file_extensions`")
        .iter()
        .map(|v| v.as_str().expect("扩展名不是字符串"))
        .collect();
    assert_eq!(golden_ext, [".py", ".pyw", ".pyi"]);

    // supported_queries:恰 16 个、严格升序、返回形态为 list,与黄金一致。
    let queries = python_plugin::supported_queries();
    assert_eq!(
        int(metadata, "supported_queries_count"),
        queries.len() as i64,
        "supported_queries 数量应与黄金 supported_queries_count 一致"
    );
    assert_eq!(queries.len(), 16, "supported_queries 应恰为 16 个");
    let mut sorted_queries = queries.clone();
    sorted_queries.sort();
    assert_eq!(queries, sorted_queries, "supported_queries 应为升序");
    assert_eq!(
        metadata.get("supported_queries_return_form").and_then(Value::as_str),
        Some("list"),
        "supported_queries 的返回形态应为 list"
    );
    let golden_queries: Vec<String> = metadata
        .get("supported_queries_sorted")
        .and_then(Value::as_array)
        .expect("黄金缺少 `supported_queries_sorted`")
        .iter()
        .map(|v| v.as_str().expect("query 不是字符串").to_string())
        .collect();
    assert_eq!(queries, golden_queries, "supported_queries 应与黄金逐项一致");

    // element_categories:与黄金逐键一致;35 键 = 17 对单/复数 + all_elements。
    let categories = python_plugin::element_categories();
    let categories_map = categories
        .as_object()
        .expect("element_categories 应为 JSON 对象");
    let golden_categories = obj(metadata, "element_categories");
    assert_eq!(
        categories_map, golden_categories,
        "element_categories 应与黄金逐键逐值一致"
    );
    assert_eq!(categories_map.len(), 35, "element_categories 应恰为 35 个键(17 对单复数 + all_elements)");
    assert!(categories_map.contains_key("all_elements"), "element_categories 应含 all_elements");
    assert_eq!(
        (categories_map.len() - 1) % 2,
        0,
        "除 all_elements 外的键应单/复数成对"
    );
    // 16 个 query 名称都应是 element_categories 的单数键。
    for query in &queries {
        assert!(
            categories_map.contains_key(query),
            "query `{query}` 应出现在 element_categories 键中"
        );
    }
}

// ---------- 2. 语料 9 个冻结节点类型计数 ----------

/// `corpus_python_expected.json` 契约:9 个关键节点类型在语料上的冻结计数。
#[test]
fn test_corpus_python_expected_9_locked_node_types() {
    let fixture = load_fixture("python_plugin/corpus_python_expected.json");
    assert_eq!(
        fixture.get("language").and_then(Value::as_str),
        Some("python"),
        "黄金 fixture 的 language 应为 python"
    );
    let golden_types = obj(&fixture, "node_types");
    assert_eq!(golden_types.len(), 9, "黄金 node_types 应恰含 9 个节点类型");

    // 首个插件调用即触发 Stage 1 的 todo!() 红灯。
    let counts = python_plugin::count_named_nodes(&corpus_source());
    for (node, expected) in golden_types {
        let expected = expected.as_i64().expect("黄金计数不是整数") as usize;
        assert_eq!(
            counts.get(node),
            Some(&expected),
            "冻结节点类型 `{node}` 的计数不符"
        );
    }
}

// ---------- 3. 语料全部 57 类命名节点计数 ----------

/// `corpus_python_node_types.json` 契约:57 种命名节点类型、合计 1061 个,逐键一致。
#[test]
fn test_corpus_python_all_57_named_node_counts() {
    let fixture = load_fixture("python_plugin/corpus_python_node_types.json");
    let golden_counts = obj(&fixture, "named_node_counts");
    let golden_total = int(&fixture, "total_named_nodes");
    let golden_distinct = int(&fixture, "distinct_named_node_types");

    // 首个插件调用即触发 Stage 1 的 todo!() 红灯。
    let counts = python_plugin::count_named_nodes(&corpus_source());

    assert_eq!(golden_distinct, 57, "黄金 distinct_named_node_types 应为 57");
    assert_eq!(counts.len(), 57, "语料命名节点类型数应为 57");
    assert_named_counts_match(&counts, golden_counts, "corpus_python.py");

    let total: usize = counts.values().sum();
    assert_eq!(golden_total, 1061, "黄金 total_named_nodes 应为 1061");
    assert_eq!(total, 1061, "语料命名节点总数应为 1061");
    assert_eq!(
        total as i64, golden_total,
        "实现计数总和应等于黄金 total_named_nodes"
    );
}

// ---------- 4. 语料 analyze_file 四视图 ----------

/// `corpus_python_plugin_analysis.json` 契约:analysis / to_dict / to_mcp_format /
/// elements_by_type 四视图精确对照(analysis_time 归一化)。
#[test]
fn test_corpus_python_analyze_result_and_elements() {
    let source = corpus_source();
    // 首个插件调用即触发 Stage 1 的 todo!() 红灯。
    let result = python_plugin::analyze_python_file(CORPUS_RELATIVE_PATH, &source);

    // analysis 视图冻结值:257 行 / 1518 节点 / 成功无错。
    let analysis = result
        .get("analysis")
        .expect("返回值缺少 analysis 视图");
    assert_eq!(int(analysis, "line_count"), 257, "语料行数应为 257");
    assert_eq!(int(analysis, "node_count"), 1518, "语料 AST 节点总数应为 1518");
    assert_eq!(analysis.get("success"), Some(&Value::Bool(true)));
    assert_eq!(analysis.get("error_message"), Some(&Value::Null));

    // to_dict 视图冻结值:4 导入 / 8 类 / 28 方法 / 1 字段 / 0 注解。
    let to_dict = result.get("to_dict").expect("返回值缺少 to_dict 视图");
    assert_eq!(int(to_dict, "line_count"), 257);
    for (key, count) in [("imports", 4), ("classes", 8), ("methods", 28), ("fields", 1), ("annotations", 0)] {
        assert_eq!(
            to_dict.get(key).and_then(Value::as_array).map(Vec::len),
            Some(count),
            "to_dict.{key} 应恰为 {count} 项"
        );
    }

    // to_mcp_format.metadata 冻结值:派生计数与 success 一致。
    let mcp_metadata = result
        .get("to_mcp_format")
        .and_then(|v| v.get("metadata"))
        .expect("返回值缺少 to_mcp_format.metadata");
    for (key, count) in [
        ("line_count", 257),
        ("class_count", 8),
        ("method_count", 28),
        ("field_count", 1),
        ("import_count", 4),
        ("annotation_count", 0),
    ] {
        assert_eq!(int(mcp_metadata, key), count, "to_mcp_format.metadata.{key} 应为 {count}");
    }
    assert_eq!(mcp_metadata.get("success"), Some(&Value::Bool(true)));

    // elements_by_type 冻结值:恰四类,8/28/4/1。
    let by_type = result
        .get("elements_by_type")
        .and_then(Value::as_object)
        .expect("返回值缺少 elements_by_type 视图");
    let mut keys: Vec<&str> = by_type.keys().map(String::as_str).collect();
    keys.sort_unstable();
    assert_eq!(keys, ["class", "function", "import", "variable"]);
    for (key, count) in [("class", 8), ("function", 28), ("import", 4), ("variable", 1)] {
        assert_eq!(
            by_type.get(key).and_then(Value::as_array).map(Vec::len),
            Some(count),
            "elements_by_type.{key} 应恰为 {count} 个元素"
        );
    }

    // 与黄金四视图整体精确对照(analysis_time 归一化)。
    let fixture = load_fixture("python_plugin/corpus_python_plugin_analysis.json");
    assert_analysis_views_match(&result, &fixture, CORPUS_RELATIVE_PATH);
}

// ---------- 5. 顶层 api_analyze_file:success 与 missing_file ----------

/// `api_analyze_corpus_python.json` 契约:success 结局六键响应与黄金逐字段一致;
/// 文件不存在时返回 Err,错误消息与黄金 FileNotFoundError 一致。
#[test]
fn test_api_analyze_file_success_and_missing_file_error() {
    let fixture = load_fixture("python_plugin/api_analyze_corpus_python.json");

    // success 结局:语料绝对路径(与 cwd 无关),显式 language="python"。
    let corpus = repo_root().join("tests/golden/corpus_python.py");
    let result = python_plugin::api_analyze_file(
        corpus.to_str().expect("语料路径应为合法 UTF-8"),
        Some("python"),
    )
    .expect("api_analyze_file 对存在的语料应返回 Ok");

    // 顶层恰六键。
    let result_map = result.as_object().expect("响应应为 JSON 对象");
    let mut keys: Vec<&str> = result_map.keys().map(String::as_str).collect();
    keys.sort_unstable();
    assert_eq!(
        keys,
        ["ast_info", "elements", "file_info", "language_info", "query_results", "success"],
        "api_analyze_file 响应应恰含 6 个顶层键"
    );
    assert_eq!(result_map.get("success"), Some(&Value::Bool(true)));

    // file_info:文件存在;path 回显语料路径(允许绝对/规范化形态)。
    let file_info = obj(&result, "file_info");
    assert_eq!(file_info.get("exists"), Some(&Value::Bool(true)));
    let path = file_info
        .get("path")
        .and_then(Value::as_str)
        .expect("file_info.path 应为字符串");
    assert!(
        path.ends_with("tests/golden/corpus_python.py"),
        "file_info.path 应回显语料路径,实际为 {path}"
    );

    // 其余三块与黄金精确一致:显式传入 language 时 detected=false。
    let golden_result = obj(obj(&fixture, "success_case"), "result");
    assert_eq!(result_map.get("language_info"), golden_result.get("language_info"));
    assert_eq!(result_map.get("ast_info"), golden_result.get("ast_info"));
    let golden_elements = golden_result
        .get("elements")
        .and_then(Value::as_array)
        .expect("黄金缺少 elements 数组");
    assert_eq!(golden_elements.len(), 41, "黄金 elements 应恰为 41 个");
    assert_eq!(
        result_map.get("elements"),
        golden_result.get("elements"),
        "elements 应与黄金逐元素一致"
    );
    assert_eq!(result_map.get("query_results"), golden_result.get("query_results"));

    // missing_file 结局:黄金同一路径,Err 消息与 FileNotFoundError 一致。
    let missing = obj(&fixture, "missing_file_case");
    assert_eq!(missing.get("exception_type"), Some(&Value::String("FileNotFoundError".into())));
    let missing_path = missing
        .get("file_path")
        .and_then(Value::as_str)
        .expect("黄金 missing_file_case 缺少 file_path");
    let err = python_plugin::api_analyze_file(missing_path, None)
        .expect_err("文件不存在时 api_analyze_file 应返回 Err");
    let expected_message = missing
        .get("exception_message")
        .and_then(Value::as_str)
        .expect("黄金 missing_file_case 缺少 exception_message");
    assert_eq!(err, expected_message, "Err 消息应与黄金 FileNotFoundError 消息一致");
}

// ---------- 6. 边缘片段(5 个)全量对照 ----------

/// `edge_cases_analysis.json` 契约:abc_exceptions / async_gen / complexity /
/// decorators_class / imports_constants 五片段的 analysis / to_dict / elements_by_type
/// 三视图与命名节点计数逐项对照。
#[test]
fn test_python_edge_case_snippets_all_5() {
    let fixture = load_fixture("python_plugin/edge_cases_analysis.json");
    let cases = fixture
        .get("cases")
        .and_then(Value::as_array)
        .expect("缺少 `cases` 数组");
    assert_eq!(cases.len(), 5, "边缘片段应恰为 5 个");

    let snippets_dir = fixtures_dir().join("python_plugin/snippets");
    let mut seen: Vec<String> = Vec::new();
    for case in cases {
        let file = case
            .get("file")
            .and_then(Value::as_str)
            .expect("case 缺少 `file` 字段");
        let name = file.rsplit('/').next().expect("`file` 应含路径分隔符");
        seen.push(name.to_string());
        let source = read_text(&snippets_dir.join(name));

        // 首个插件调用即触发 Stage 1 的 todo!() 红灯。
        let result = python_plugin::analyze_python_file(file, &source);
        assert_analysis_views_match(&result, case, file);

        // 命名节点计数对照:键数、逐键计数、总和与黄金一致。
        let counts = python_plugin::count_named_nodes(&source);
        let golden_counts = obj(case, "named_node_counts");
        assert_named_counts_match(&counts, golden_counts, file);
        let total: usize = counts.values().sum();
        assert_eq!(
            total as i64,
            int(case, "total_named_nodes"),
            "{file}: 命名节点总数应与黄金 total_named_nodes 一致"
        );
    }

    // 恰为任务指定的 5 个片段,无增删。
    let mut sorted_seen = seen.clone();
    sorted_seen.sort();
    assert_eq!(
        sorted_seen,
        [
            "abc_exceptions.py",
            "async_gen.py",
            "complexity.py",
            "decorators_class.py",
            "imports_constants.py",
        ],
        "边缘片段集合应恰为指定的 5 个"
    );
}
