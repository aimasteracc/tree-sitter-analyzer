//! Stage 1 fixtures 冒烟测试(SPEC §5.2)。
//!
//! 验证 `rust/fixtures/` 下全部 13 份规范化 JSON(Python 侧 v3.1.2 真实输出):
//! 可读取、可被 serde_json 解析、顶层结构与 MANIFEST 声明的形状一致。
//! 本测试只看「数据在、形状对」,不做行为对照——行为断言属于 Stage 2-3 的红灯契约测试。

use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};

/// fixtures 根目录:相对 crate 清单定位(`rust/tsa-core` → `rust/fixtures`),与 cwd 无关。
fn fixtures_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../fixtures")
}

/// 读取并解析一份 fixture;失败即 panic(冒烟测试不该静默跳过)。
fn load(rel_path: &str) -> Value {
    let path = fixtures_dir().join(rel_path);
    let raw = fs::read_to_string(&path)
        .unwrap_or_else(|err| panic!("无法读取 fixture {}: {err}", path.display()));
    serde_json::from_str(&raw)
        .unwrap_or_else(|err| panic!("fixture 不是合法 JSON {}: {err}", path.display()))
}

/// 取顶层字段且断言为对象。
fn obj<'a>(payload: &'a Value, key: &str) -> &'a serde_json::Map<String, Value> {
    payload
        .get(key)
        .unwrap_or_else(|| panic!("缺少顶层字段 `{key}`"))
        .as_object()
        .unwrap_or_else(|| panic!("顶层字段 `{key}` 不是对象"))
}

/// 取顶层字段且断言为数组,返回其长度。
fn arr(payload: &Value, key: &str) -> usize {
    payload
        .get(key)
        .unwrap_or_else(|| panic!("缺少顶层字段 `{key}`"))
        .as_array()
        .unwrap_or_else(|| panic!("顶层字段 `{key}` 不是数组"))
        .len()
}

/// 取顶层字段且断言为字符串。
fn str_field<'a>(payload: &'a Value, key: &str) -> &'a str {
    payload
        .get(key)
        .unwrap_or_else(|| panic!("缺少顶层字段 `{key}`"))
        .as_str()
        .unwrap_or_else(|| panic!("顶层字段 `{key}` 不是字符串"))
}

/// 在已取出的 JSON 对象内取字符串字段。
fn map_str<'a>(map: &'a serde_json::Map<String, Value>, key: &str) -> &'a str {
    map.get(key)
        .unwrap_or_else(|| panic!("缺少字段 `{key}`"))
        .as_str()
        .unwrap_or_else(|| panic!("字段 `{key}` 不是字符串"))
}

/// 递归统计 fixtures 目录下的 .json 文件数;防止 fixture 静默增删而不更新本测试。
#[test]
fn fixtures_directory_contains_exactly_13_json_files() {
    let mut count = 0usize;
    collect_json_files(&fixtures_dir(), &mut count);
    assert_eq!(count, 13, "fixtures 目录应恰好包含 13 份 JSON(现状见 MANIFEST.json)");
}

fn collect_json_files(dir: &Path, count: &mut usize) {
    let entries = fs::read_dir(dir)
        .unwrap_or_else(|err| panic!("无法列举目录 {}: {err}", dir.display()));
    for entry in entries {
        let entry = entry.expect("目录项读取失败");
        let path = entry.path();
        if path.is_dir() {
            collect_json_files(&path, count);
        } else if path.extension().is_some_and(|ext| ext == "json") {
            *count += 1;
        }
    }
}

#[test]
fn manifest_has_expected_top_level_structure() {
    let manifest = load("MANIFEST.json");
    assert_eq!(str_field(&manifest, "tsa_version"), "3.1.2");
    assert!(!str_field(&manifest, "git_commit").is_empty());
    assert!(!str_field(&manifest, "generated_at_jst").is_empty());
    // generator / grammar_versions / pip_freeze 三个元数据块
    for block in ["generator", "grammar_versions", "pip_freeze"] {
        assert!(manifest.get(block).is_some_and(Value::is_object), "缺少块 `{block}`");
    }
    assert_eq!(arr(&manifest, "normalization_rules"), 5);
    assert_eq!(arr(&manifest, "files"), 22);
    // pip_freeze.packages 也是数组
    assert!(obj(&manifest, "pip_freeze").get("packages").is_some_and(Value::is_array));
}

#[test]
fn cli_outputs_has_expected_top_level_structure() {
    let cli = load("cli/cli_outputs.json");
    assert!(cli.get("meta").is_some_and(Value::is_object));
    let cases = cli
        .get("cases")
        .and_then(Value::as_array)
        .expect("缺少 `cases` 数组");
    assert_eq!(cases.len(), 4);
    let names: Vec<&str> = cases
        .iter()
        .map(|case| case.get("name").and_then(Value::as_str).expect("case 缺少 `name`"))
        .collect();
    assert_eq!(names, ["structure", "table_full", "outline", "missing_file"]);
    for case in cases {
        for key in [
            "name",
            "argv",
            "cwd",
            "exit_code",
            "stdout_parse_ok",
            "stdout_json",
            "timing_keys_nulled",
            "stderr",
            "stdout_raw_if_unparseable",
        ] {
            assert!(case.get(key).is_some(), "case `{}` 缺少字段 `{key}`", names[0]);
        }
    }
}

// ---------- envelope(4 份)----------

#[test]
fn envelope_response_builder_valid_has_expected_structure() {
    let fixture = load("envelope/response_builder_valid.json");
    assert!(fixture.get("meta").is_some_and(Value::is_object));
    let verdicts = fixture
        .get("canonical_verdicts")
        .and_then(Value::as_array)
        .expect("缺少 `canonical_verdicts`");
    let verdict_strs: Vec<&str> = verdicts
        .iter()
        .map(|v| v.as_str().expect("verdict 不是字符串"))
        .collect();
    assert_eq!(
        verdict_strs,
        ["CAUTION", "ERROR", "INFO", "NOT_FOUND", "REVIEW", "SAFE", "UNSAFE", "WARN"]
    );
    assert_eq!(arr(&fixture, "build_response_all_verdicts"), 8);
    assert_eq!(arr(&fixture, "build_response_warnings_variants"), 3);
    assert_eq!(arr(&fixture, "build_error"), 2);
    assert_eq!(arr(&fixture, "build_error_response"), 2);
    assert_eq!(arr(&fixture, "build_success_response"), 2);
    assert_eq!(arr(&fixture, "build_agent_summary"), 2);
}

#[test]
fn envelope_response_builder_invalid_has_expected_structure() {
    let fixture = load("envelope/response_builder_invalid.json");
    assert!(fixture.get("meta").is_some_and(Value::is_object));
    let invalid = fixture
        .get("invalid_verdicts")
        .and_then(Value::as_array)
        .expect("缺少 `invalid_verdicts`");
    assert_eq!(invalid.len(), 9);
    let canonical = [
        "SAFE", "REVIEW", "CAUTION", "UNSAFE", "INFO", "WARN", "ERROR", "NOT_FOUND",
    ];
    // 9 个非法样本:每个都是 InvalidVerdictError(ValueError 子类),消息含非法值与 canonical 全集
    for entry in invalid {
        let entry = entry.as_object().expect("invalid_verdicts 项不是对象");
        let input = entry.get("input").and_then(Value::as_str).expect("缺少 `input`");
        assert!(!canonical.contains(&input), "`{input}` 不应出现在 invalid_verdicts");
        assert_eq!(entry.get("exc_type"), Some(&Value::String("InvalidVerdictError".into())));
        assert_eq!(entry.get("is_value_error"), Some(&Value::Bool(true)));
        let message = entry.get("message").and_then(Value::as_str).expect("缺少 `message`");
        assert!(message.contains(input), "消息应回显非法值 `{input}`");
        for verdict in canonical {
            assert!(message.contains(verdict), "消息应含 canonical 集合中的 `{verdict}`");
        }
    }
}

#[test]
fn envelope_validation_has_expected_structure() {
    let fixture = load("envelope/envelope_validation.json");
    assert!(fixture.get("meta").is_some_and(Value::is_object));
    assert_eq!(arr(&fixture, "canonical_verdicts"), 8);
    assert_eq!(arr(&fixture, "envelope_rules"), 11);
    assert_eq!(arr(&fixture, "rules_actually_fired"), 11);
    assert_eq!(arr(&fixture, "valid"), 5);
    assert_eq!(arr(&fixture, "invalid"), 17);
    // 已知 completeness reason 闭集规模 + 抽样
    assert!(fixture.get("known_completeness_reasons_count").is_some_and(Value::is_i64));
    assert!(fixture
        .get("known_completeness_reasons_sample")
        .is_some_and(Value::is_array));
}

#[test]
fn envelope_error_recovery_has_expected_structure() {
    let fixture = load("envelope/error_recovery.json");
    assert!(fixture.get("meta").is_some_and(Value::is_object));
    assert_eq!(arr(&fixture, "error_cases"), 12);
    for block in [
        "error_envelope_preserves_preset_fields",
        "error_envelope_derives_identity",
        "k12_path_normalization",
        "m14_language_echo",
    ] {
        assert!(fixture.get(block).is_some_and(Value::is_object), "缺少块 `{block}`");
    }
    // 两个补全入口的样本都必须是失败信封
    for block in ["error_envelope_preserves_preset_fields", "error_envelope_derives_identity"] {
        assert_eq!(obj(&fixture, block).get("success"), Some(&Value::Bool(false)));
    }
    // k12 直测样本:输入 → 输出
    let k12 = obj(&fixture, "k12_path_normalization");
    assert!(k12.get("normalize_path_string_direct").is_some_and(Value::is_object));
}

// ---------- facade(2 份)----------

#[test]
fn facade_registry_has_expected_structure() {
    let fixture = load("facade/facade_registry.json");
    let facade_map = obj(&fixture, "facade_map");
    let names: Vec<&str> = facade_map
        .get("FACADE_NAMES")
        .and_then(Value::as_array)
        .expect("缺少 `FACADE_NAMES`")
        .iter()
        .map(|v| v.as_str().expect("facade 名不是字符串"))
        .collect();
    assert_eq!(
        names,
        ["search", "nav", "structure", "health", "edit", "project", "index", "viz"]
    );
    assert_eq!(facade_map.get("SET_PROJECT_PATH_TOOL_NAME"), Some(&Value::String("set_project_path".into())));
    assert_eq!(
        facade_map
            .get("REMOVED_TOOL_NAMES")
            .and_then(Value::as_array)
            .expect("缺少 `REMOVED_TOOL_NAMES`")
            .len(),
        5
    );
    assert_eq!(
        facade_map
            .get("LEGACY_TOOL_MAP")
            .and_then(Value::as_object)
            .expect("缺少 `LEGACY_TOOL_MAP`")
            .len(),
        62
    );
    assert_eq!(
        facade_map
            .get("NEW_ACTION_PARITY")
            .and_then(Value::as_object)
            .expect("缺少 `NEW_ACTION_PARITY`")
            .len(),
        21
    );
    assert_eq!(arr(&fixture, "facades"), 8);
    // set_project_path 工具定义:name / description / inputSchema
    let definition = obj(&fixture, "set_project_path_tool_definition");
    assert_eq!(definition.get("name"), Some(&Value::String("set_project_path".into())));
    assert!(definition.get("description").is_some_and(Value::is_string));
    assert!(definition.get("inputSchema").is_some_and(Value::is_object));
}

#[test]
fn facade_dispatch_has_expected_structure() {
    let fixture = load("facade/facade_dispatch.json");
    for key in ["corpus", "generator", "package_version", "project_root", "runner"] {
        assert!(!str_field(&fixture, key).is_empty(), "`{key}` 应为非空字符串");
    }
    let order: Vec<&str> = fixture
        .get("registry_order")
        .and_then(Value::as_array)
        .expect("缺少 `registry_order`")
        .iter()
        .map(|v| v.as_str().expect("registry_order 项不是字符串"))
        .collect();
    assert_eq!(
        order,
        ["search", "nav", "structure", "health", "edit", "project", "index", "viz"]
    );
    let cases = fixture
        .get("cases")
        .and_then(Value::as_array)
        .expect("缺少 `cases` 数组");
    assert_eq!(cases.len(), 15);
    // 每个案例都有 `case` + `input`;结局二选一:`result`(信封)或 `exception_*`(抛异常)
    let mut with_result = 0usize;
    let mut with_exception = 0usize;
    for case in cases {
        let name = case.get("case").and_then(Value::as_str).expect("case 缺少 `case`");
        assert!(case.get("input").is_some(), "case `{name}` 缺少字段 `input`");
        let has_result = case.get("result").is_some();
        let has_exception = case.get("exception_type").is_some()
            && case.get("exception_message").is_some();
        assert!(
            has_result ^ has_exception,
            "case `{name}` 应恰有 `result` 或 `exception_*` 之一"
        );
        if has_result {
            with_result += 1;
        } else {
            with_exception += 1;
        }
    }
    assert_eq!((with_result, with_exception), (14, 1));
    // legacy 兼容案例额外携带去弃用信息与转发目标
    let legacy = cases
        .iter()
        .find(|c| c.get("case").and_then(Value::as_str) == Some("legacy_codegraph_call_graph"))
        .expect("缺少 legacy_codegraph_call_graph 案例");
    assert!(legacy.get("deprecation").is_some_and(Value::is_object));
    assert!(legacy.get("forwarded_to_nav").is_some_and(Value::is_object));
}

// ---------- python_plugin(5 份)----------

#[test]
fn python_plugin_corpus_expected_has_expected_structure() {
    let fixture = load("python_plugin/corpus_python_expected.json");
    assert_eq!(str_field(&fixture, "language"), "python");
    let node_types = obj(&fixture, "node_types");
    // 9 个关键节点类型的期望计数(基线冻结值)
    let expected = [
        ("function_definition", 28),
        ("class_definition", 8),
        ("decorated_definition", 7),
        ("lambda", 5),
        ("list_comprehension", 1),
        ("dictionary_comprehension", 1),
        ("set_comprehension", 1),
        ("generator_expression", 2),
        ("yield", 3),
    ];
    assert_eq!(node_types.len(), expected.len());
    for (node, count) in expected {
        assert_eq!(
            node_types.get(node).and_then(Value::as_i64),
            Some(count),
            "节点 `{node}` 计数不符"
        );
    }
}

#[test]
fn python_plugin_node_types_has_expected_structure() {
    let fixture = load("python_plugin/corpus_python_node_types.json");
    for key in ["source_file", "description", "parser"] {
        assert!(!str_field(&fixture, key).is_empty());
    }
    let versions = obj(&fixture, "versions");
    assert_eq!(versions.get("tree_sitter"), Some(&Value::String("0.26.1".into())));
    assert_eq!(
        versions.get("tree_sitter_python"),
        Some(&Value::String("0.23.6".into()))
    );
    let counts = obj(&fixture, "named_node_counts");
    let total: i64 = counts
        .values()
        .map(|v| v.as_i64().expect("named_node_counts 值不是整数"))
        .sum();
    let total_field = fixture
        .get("total_named_nodes")
        .and_then(Value::as_i64)
        .expect("缺少 `total_named_nodes`");
    assert_eq!(total_field, 1061);
    assert_eq!(total, total_field, "named_node_counts 求和应等于 total_named_nodes");
    assert_eq!(
        fixture.get("distinct_named_node_types").and_then(Value::as_i64),
        Some(counts.len() as i64),
        "distinct_named_node_types 应等于 named_node_counts 键数"
    );
}

#[test]
fn python_plugin_analysis_has_expected_structure() {
    let fixture = load("python_plugin/corpus_python_plugin_analysis.json");
    assert!(fixture.get("request").is_some_and(Value::is_object));
    let metadata = obj(&fixture, "plugin_metadata");
    assert_eq!(metadata.get("language_name"), Some(&Value::String("python".into())));
    let extensions: Vec<&str> = metadata
        .get("file_extensions")
        .and_then(Value::as_array)
        .expect("缺少 `file_extensions`")
        .iter()
        .map(|v| v.as_str().expect("扩展名不是字符串"))
        .collect();
    assert_eq!(extensions, [".py", ".pyw", ".pyi"]);
    assert_eq!(metadata.get("supported_queries_count"), Some(&Value::from(16)));
    assert_eq!(map_str(metadata, "supported_queries_return_form"), "list");
    assert_eq!(
        metadata.get("supported_queries_sorted").and_then(Value::as_array).map(Vec::len),
        Some(16)
    );
    assert!(metadata.get("element_categories").is_some_and(Value::is_object));
    for block in ["analysis", "to_dict", "to_mcp_format"] {
        assert!(fixture.get(block).is_some_and(Value::is_object), "缺少块 `{block}`");
    }
    // elements_by_type 恰好四类,均为列表
    let by_type = obj(&fixture, "elements_by_type");
    let mut keys: Vec<&str> = by_type.keys().map(String::as_str).collect();
    keys.sort_unstable();
    assert_eq!(keys, ["class", "function", "import", "variable"]);
    for (key, value) in by_type {
        assert!(value.is_array(), "`elements_by_type.{key}` 应为列表");
    }
}

#[test]
fn python_plugin_edge_cases_has_expected_structure() {
    let fixture = load("python_plugin/edge_cases_analysis.json");
    assert!(!str_field(&fixture, "description").is_empty());
    assert!(fixture.get("request").is_some_and(Value::is_object));
    let versions = obj(&fixture, "versions");
    assert!(versions.get("tree_sitter").is_some_and(Value::is_string));
    assert!(versions.get("tree_sitter_python").is_some_and(Value::is_string));
    assert_eq!(arr(&fixture, "cases"), 5);
}

#[test]
fn python_plugin_api_analyze_has_expected_structure() {
    let fixture = load("python_plugin/api_analyze_corpus_python.json");
    assert!(fixture.get("request").is_some_and(Value::is_object));
    let success = obj(&fixture, "success_case");
    assert!(success.get("file_path").is_some_and(Value::is_string));
    let result = success
        .get("result")
        .and_then(Value::as_object)
        .expect("`success_case.result` 应为对象");
    let mut keys: Vec<&str> = result.keys().map(String::as_str).collect();
    keys.sort_unstable();
    assert_eq!(
        keys,
        ["ast_info", "elements", "file_info", "language_info", "query_results", "success"]
    );
    let missing = obj(&fixture, "missing_file_case");
    assert_eq!(missing.get("raised"), Some(&Value::Bool(true)));
    assert_eq!(
        missing.get("exception_type"),
        Some(&Value::String("FileNotFoundError".into()))
    );
    assert!(missing.get("exception_message").is_some_and(Value::is_string));
    assert!(missing.get("exception_repr").is_some_and(Value::is_string));
}
