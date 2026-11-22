//! Stage 1 红灯契约测试(SPEC §2.1(b) / §5.2):`tsa_core::facade` 对照黄金 fixtures。
//!
//! 对照物:
//! - `fixtures/facade/facade_registry.json`:`facade_map`(FACADE_NAMES 8 / SET_PROJECT_PATH_TOOL_NAME /
//!   REMOVED_TOOL_NAMES 5 / LEGACY_TOOL_MAP 62 / NEW_ACTION_PARITY 21)、`facades`(8 个定义)、
//!   `set_project_path_tool_definition`
//! - `fixtures/facade/facade_dispatch.json`:`registry_order` + 15 个分发案例
//!   (14 个 `result` 信封 + 1 个 `exception_*` 案例)
//!
//! Stage 1 状态:`tsa_core::facade` 全部函数体为 `todo!()`,本文件必须能编译(无告警),
//! 运行时逐个 panic —— 这就是红灯。Stage 2-3 实现完成后本文件应当全绿且不再改动断言口径。
//!
//! 归一化口径:对比 `result` 前剔除易变字段(见 `normalize`),
//! 使黄金对比与运行时长/缓存年龄/世代号无关。

use serde_json::Value;
use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};

// ---------- fixture 装载(与 fixtures_smoke.rs 同一套口径)----------

/// fixtures 根目录:相对 crate 清单定位(`rust/tsa-core` → `rust/fixtures`),与 cwd 无关。
fn fixtures_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../fixtures")
}

/// 读取并解析一份 fixture;失败即 panic(契约测试不该静默跳过)。
fn load(rel_path: &str) -> Value {
    let path = fixtures_dir().join(rel_path);
    let raw = fs::read_to_string(&path)
        .unwrap_or_else(|err| panic!("无法读取 fixture {}: {err}", path.display()));
    serde_json::from_str(&raw)
        .unwrap_or_else(|err| panic!("fixture 不是合法 JSON {}: {err}", path.display()))
}

/// `facade_registry.json`(facade_map + 8 个定义 + set_project_path 定义)。
fn registry() -> Value {
    load("facade/facade_registry.json")
}

/// `facade_dispatch.json`(15 个分发案例)。
fn dispatch_fixture() -> Value {
    load("facade/facade_dispatch.json")
}

/// 取顶层字段且断言为对象。
fn obj<'a>(payload: &'a Value, key: &str) -> &'a serde_json::Map<String, Value> {
    payload
        .get(key)
        .unwrap_or_else(|| panic!("缺少顶层字段 `{key}`"))
        .as_object()
        .unwrap_or_else(|| panic!("顶层字段 `{key}` 不是对象"))
}

/// 取顶层字段且断言为数组(返回切片)。
fn arr<'a>(payload: &'a Value, key: &str) -> &'a [Value] {
    payload
        .get(key)
        .unwrap_or_else(|| panic!("缺少顶层字段 `{key}`"))
        .as_array()
        .map(Vec::as_slice)
        .unwrap_or_else(|| panic!("顶层字段 `{key}` 不是数组"))
}

/// 在已取出的 JSON 对象内取对象字段。
fn map_obj<'a>(
    map: &'a serde_json::Map<String, Value>,
    key: &str,
) -> &'a serde_json::Map<String, Value> {
    map.get(key)
        .unwrap_or_else(|| panic!("缺少字段 `{key}`"))
        .as_object()
        .unwrap_or_else(|| panic!("字段 `{key}` 不是对象"))
}

/// 在已取出的 JSON 对象内取字符串字段。
fn map_str<'a>(map: &'a serde_json::Map<String, Value>, key: &str) -> &'a str {
    map.get(key)
        .unwrap_or_else(|| panic!("缺少字段 `{key}`"))
        .as_str()
        .unwrap_or_else(|| panic!("字段 `{key}` 不是字符串"))
}

/// 把一个 JSON 数组值收敛为 `Vec<&str>`(元素必须是字符串)。
fn str_array(value: &Value) -> Vec<&str> {
    value
        .as_array()
        .unwrap_or_else(|| panic!("期望 JSON 数组,实际是 {value}"))
        .iter()
        .map(|v| v.as_str().unwrap_or_else(|| panic!("数组元素不是字符串: {v}")))
        .collect()
}

/// 在 registry fixture 中按名取 facade 定义对象。
fn facade_entry<'a>(reg: &'a Value, name: &str) -> &'a serde_json::Map<String, Value> {
    arr(reg, "facades")
        .iter()
        .map(|f| f.as_object().expect("facades 项不是对象"))
        .find(|m| m.get("name").and_then(Value::as_str) == Some(name))
        .unwrap_or_else(|| panic!("registry 中不存在 facade `{name}`"))
}

/// 某 facade 对外可见的 action全集 = `actions` ∪ `bespoke_actions`(排序后),
/// 即错误/帮助信封里 `available_actions` 的期望口径。
fn available_actions<'a>(reg: &'a Value, facade: &str) -> Vec<&'a str> {
    let entry = facade_entry(reg, facade);
    let mut pool = str_array(entry.get("actions").expect("缺少 `actions`"));
    pool.extend(str_array(entry.get("bespoke_actions").expect("缺少 `bespoke_actions`")));
    pool.sort_unstable();
    pool.dedup();
    pool
}

/// 在 dispatch fixture 中按 `case` 名取案例对象。
fn case<'a>(fx: &'a Value, name: &str) -> &'a serde_json::Map<String, Value> {
    dispatch_cases(fx)
        .iter()
        .map(|c| c.as_object().expect("case 项不是对象"))
        .find(|c| c.get("case").and_then(Value::as_str) == Some(name))
        .unwrap_or_else(|| panic!("dispatch fixture 中不存在案例 `{name}`"))
}

fn dispatch_cases(fx: &Value) -> &[Value] {
    let cases = arr(fx, "cases");
    assert_eq!(cases.len(), 15, "facade_dispatch.json 应恰好包含 15 个案例");
    cases
}

/// TSA 仓库根(`rust/tsa-core` → 仓库根),dispatch 的 project_root 基准;
/// fixture 中的相对 `file_path`(如 `tests/golden/corpus_python.py`)据此解析。
fn repo_root() -> String {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    fs::canonicalize(&path)
        .unwrap_or_else(|err| panic!("无法定位仓库根 {}: {err}", path.display()))
        .to_string_lossy()
        .into_owned()
}

// ---------- 易变字段归一化 ----------

/// 剔除易变字段后再做黄金对比:
/// - 任意层级的 `analysis_time` / `duration_ms` / `elapsed_ms` / `cache_age_s`
/// - 仅 `provenance` 对象内的 `generation` / `producer_version`
///
/// 两边(实际与期望)都过同一函数,所以剔除是语义中立的。
fn normalize(value: &Value, parent_key: &str) -> Value {
    match value {
        Value::Object(map) => {
            let mut out = serde_json::Map::new();
            for (key, val) in map {
                let volatile = matches!(
                    key.as_str(),
                    "analysis_time" | "duration_ms" | "elapsed_ms" | "cache_age_s"
                ) || (parent_key == "provenance"
                    && matches!(key.as_str(), "generation" | "producer_version"));
                if volatile {
                    continue;
                }
                out.insert(key.clone(), normalize(val, key));
            }
            Value::Object(out)
        }
        Value::Array(items) => {
            Value::Array(items.iter().map(|item| normalize(item, parent_key)).collect())
        }
        other => other.clone(),
    }
}

/// 归一化入口:与父键上下文无关地归一化一个完整信封。
fn normalized(value: &Value) -> Value {
    normalize(value, "")
}

// ---------- 分发案例断言 ----------

/// 调 `dispatch_facade` 并把结果与 fixture 的 `result` 做归一化深对比;返回实际信封供定点断言。
fn assert_dispatch_case(fx: &Value, name: &str, facade: &str, project_root: &str) -> Value {
    let c = case(fx, name);
    let input = c
        .get("input")
        .unwrap_or_else(|| panic!("case `{name}` 缺少 `input`"));
    let expected = c
        .get("result")
        .unwrap_or_else(|| panic!("case `{name}` 缺少 `result`(异常案例请走专属断言)"));
    let actual = tsa_core::facade::dispatch_facade(facade, input, project_root);
    assert_eq!(
        normalized(&actual),
        normalized(expected),
        "case `{name}`:`dispatch_facade(\"{facade}\", ...)` 结果与黄金 fixture 归一化后不一致"
    );
    actual
}

// =====================================================================
// 1. facade 名录(顺序 = 注册顺序)
// =====================================================================

#[test]
fn test_facade_names_order_and_count() {
    let reg = registry();
    let expected = str_array(
        obj(&reg, "facade_map")
            .get("FACADE_NAMES")
            .expect("缺少 `FACADE_NAMES`"),
    );
    // 锁死顺序:顺序即 MCP 注册顺序(registry_order)
    assert_eq!(
        expected,
        ["search", "nav", "structure", "health", "edit", "project", "index", "viz"]
    );
    let names = tsa_core::facade::facade_names();
    assert_eq!(names.len(), 8, "FACADE_NAMES 应为 8 个");
    assert_eq!(names.to_vec(), expected, "facade_names() 应与 fixture 逐项同序");
    for name in names {
        assert!(tsa_core::facade::is_facade_name(name), "`{name}` 应被识别为 facade 名");
    }
    // 反例:保留工具名 / legacy 名 / 未知名 都不是 facade
    for not_facade in ["set_project_path", "get_code_outline", "no_such_facade"] {
        assert!(
            !tsa_core::facade::is_facade_name(not_facade),
            "`{not_facade}` 不应被识别为 facade 名"
        );
    }
}

// =====================================================================
// 2. set_project_path 保留工具 + 5 个已移除工具
// =====================================================================

#[test]
fn test_set_project_path_and_removed_tools() {
    let reg = registry();
    let fm = obj(&reg, "facade_map");
    assert_eq!(
        tsa_core::facade::set_project_path_tool_name(),
        map_str(fm, "SET_PROJECT_PATH_TOOL_NAME")
    );
    assert_eq!(
        tsa_core::facade::set_project_path_tool_name(),
        "set_project_path",
        "唯一保留独立注册的工具名固定为 set_project_path"
    );

    let expected_removed = str_array(
        fm.get("REMOVED_TOOL_NAMES")
            .expect("缺少 `REMOVED_TOOL_NAMES`"),
    );
    assert_eq!(expected_removed.len(), 5, "REMOVED_TOOL_NAMES 应为 5 个");
    let removed = tsa_core::facade::removed_tool_names();
    assert_eq!(removed.to_vec(), expected_removed, "removed_tool_names() 应与 fixture 一致");

    // 不变量:已移除的工具不得再有任何分发入口 —— 既不是 facade,
    // 也不得混进 62 条 legacy 兼容表(否则 dispatch_legacy 会复活它们)。
    let legacy_keys: HashSet<&str> = map_obj(fm, "LEGACY_TOOL_MAP")
        .keys()
        .map(String::as_str)
        .collect();
    for name in removed {
        assert!(!tsa_core::facade::is_facade_name(name), "已移除的 `{name}` 不应是 facade 名");
        assert!(!legacy_keys.contains(name), "已移除的 `{name}` 不得出现在 LEGACY_TOOL_MAP");
        assert!(
            !tsa_core::facade::is_legacy_name(name),
            "已移除的 `{name}` 不得被 is_legacy_name 判定为可兼容分发"
        );
    }
}

// =====================================================================
// 3. LEGACY_TOOL_MAP 全量 62 条路由
// =====================================================================

#[test]
fn test_legacy_tool_map_all_62_entries() {
    let reg = registry();
    let fm = obj(&reg, "facade_map");
    let ltm = map_obj(fm, "LEGACY_TOOL_MAP");
    assert_eq!(ltm.len(), 62, "LEGACY_TOOL_MAP 应恰好 62 条");

    for (old_name, route) in ltm {
        let pair = route
            .as_array()
            .unwrap_or_else(|| panic!("legacy `{old_name}` 的路由不是数组"));
        assert_eq!(pair.len(), 2, "legacy `{old_name}` 的路由应为 [facade, action]");
        let facade = pair[0].as_str().unwrap_or_else(|| panic!("legacy `{old_name}` 的 facade 不是字符串"));
        let action = pair[1].as_str().unwrap_or_else(|| panic!("legacy `{old_name}` 的 action 不是字符串"));
        assert_eq!(
            tsa_core::facade::legacy_to_facade(old_name),
            Some((facade, action)),
            "legacy `{old_name}` 的查表结果与 fixture 不一致"
        );
        assert!(tsa_core::facade::is_legacy_name(old_name), "`{old_name}` 应被识别为 legacy 名");
        assert!(tsa_core::facade::is_facade_name(facade), "`{old_name}` 路由到了未知 facade `{facade}`");
        // fixture 现状:62 条全部带非空 action 级投影
        assert!(!action.is_empty(), "legacy `{old_name}` 的 action 不应为空串");
        // 路由目标必须是该 facade 真实存在的 action(含 bespoke)
        let pool = available_actions(&reg, facade);
        assert!(
            pool.contains(&action),
            "legacy `{old_name}` 路由到 `{facade}.{action}`,但该 action 不在 facade 的 action 全集中"
        );
    }

    // 反向:未收录的名字必须查表失败(facade 名 / 保留工具名 / 已移除名 / 纯未知名)
    for unknown in ["structure", "set_project_path", "batch_search", "no_such_tool"] {
        assert!(
            tsa_core::facade::legacy_to_facade(unknown).is_none(),
            "未收录名 `{unknown}` 不应查到 legacy 路由"
        );
        assert!(!tsa_core::facade::is_legacy_name(unknown), "`{unknown}` 不应被识别为 legacy 名");
    }
}

// =====================================================================
// 4. NEW_ACTION_PARITY 全量 21 条
// =====================================================================

#[test]
fn test_new_action_parity_all_21_entries() {
    let reg = registry();
    let fm = obj(&reg, "facade_map");
    let nap = map_obj(fm, "NEW_ACTION_PARITY");
    assert_eq!(nap.len(), 21, "NEW_ACTION_PARITY 应恰好 21 条");

    let rows = tsa_core::facade::new_action_parity();
    assert_eq!(rows.len(), 21, "new_action_parity() 应返回 21 条");

    // 逐条对照:元组口径为 (capability_key, facade, action, cli_flag),
    // 与 fixture 的 capability_key -> [facade, action, cli_flag] 一一对应。
    let mut seen: HashSet<&str> = HashSet::new();
    for &(key, facade, action, cli_flag) in &rows {
        assert!(seen.insert(key), "capability_key `{key}` 重复出现");
        let triple = nap
            .get(key)
            .unwrap_or_else(|| panic!("Rust 侧的 capability_key `{key}` 不在 fixture 中"))
            .as_array()
            .unwrap_or_else(|| panic!("parity `{key}` 的对照行不是数组"));
        assert_eq!(triple.len(), 3, "parity `{key}` 的对照行应为 [facade, action, cli_flag]");
        assert_eq!(
            (facade, action, cli_flag),
            (
                triple[0].as_str().unwrap_or_else(|| panic!("parity `{key}` 的 facade 不是字符串")),
                triple[1].as_str().unwrap_or_else(|| panic!("parity `{key}` 的 action 不是字符串")),
                triple[2].as_str().unwrap_or_else(|| panic!("parity `{key}` 的 cli_flag 不是字符串")),
            ),
            "parity `{key}` 与 fixture 不一致"
        );
        assert!(tsa_core::facade::is_facade_name(facade), "parity `{key}` 指向未知 facade `{facade}`");
        assert!(cli_flag.starts_with("--"), "parity `{key}` 的 cli_flag `{cli_flag}` 应以 `--` 开头");
        // 新增 action 必须真实挂在该 facade 的 action 全集上(含 bespoke)
        let pool = available_actions(&reg, facade);
        assert!(
            pool.contains(&action),
            "parity `{key}` 的 `{facade}.{action}` 不在 facade 的 action 全集中"
        );
    }

    // 键集合恰好覆盖 fixture 的 21 个 capability_key:不多、不少、不重
    let fixture_keys: HashSet<&str> = nap.keys().map(String::as_str).collect();
    let got_keys: HashSet<&str> = rows.iter().map(|row| row.0).collect();
    assert_eq!(got_keys, fixture_keys, "new_action_parity() 的 capability_key 集合应与 fixture 完全一致");
}

// =====================================================================
// 5. facade 工具定义与 schema
// =====================================================================

#[test]
fn test_facade_definitions_and_schemas() {
    let reg = registry();
    let defs = tsa_core::facade::facade_definitions();
    let defs_obj = defs
        .as_object()
        .expect("facade_definitions() 应返回对象(含 `facades` 与 `set_project_path_tool_definition`)");

    let expected_names = str_array(
        obj(&reg, "facade_map")
            .get("FACADE_NAMES")
            .expect("缺少 `FACADE_NAMES`"),
    );
    let got_facades = defs_obj
        .get("facades")
        .and_then(Value::as_array)
        .expect("facade_definitions() 缺少 `facades` 数组");
    let want_facades = arr(&reg, "facades");
    assert_eq!(got_facades.len(), 8, "定义数应为 8");

    for (idx, (got, want)) in got_facades.iter().zip(want_facades.iter()).enumerate() {
        let got = got.as_object().unwrap_or_else(|| panic!("定义 #{idx} 不是对象"));
        let want = want.as_object().unwrap_or_else(|| panic!("fixture 定义 #{idx} 不是对象"));
        // 顺序即注册顺序(FACADE_NAMES)
        assert_eq!(
            map_str(got, "name"),
            expected_names[idx],
            "定义 #{idx} 的 name 应与 FACADE_NAMES 同序"
        );
        assert_eq!(map_str(got, "name"), map_str(want, "name"), "定义 #{idx} 的 name 与 fixture 不一致");
        // search/index 接受 lifecycle_manager,其余为 false
        assert_eq!(
            got.get("takes_lifecycle_manager"),
            want.get("takes_lifecycle_manager"),
            "facade `{}` 的 takes_lifecycle_manager 与 fixture 不一致",
            map_str(want, "name")
        );
        // actions / bespoke_actions 全量一致(顺序敏感:即该 facade 的 action 枚举序)
        assert_eq!(
            got.get("actions"),
            want.get("actions"),
            "facade `{}` 的 actions 与 fixture 不一致",
            map_str(want, "name")
        );
        assert_eq!(
            got.get("bespoke_actions"),
            want.get("bespoke_actions"),
            "facade `{}` 的 bespoke_actions 与 fixture 不一致",
            map_str(want, "name")
        );
        // tool_definition 整体深对比:name / annotations / required / action_enum / additionalProperties
        assert_eq!(
            got.get("tool_definition"),
            want.get("tool_definition"),
            "facade `{}` 的 tool_definition 与 fixture 不一致",
            map_str(want, "name")
        );
    }

    // set_project_path 定义:name / description / inputSchema 与 fixture 一致
    let got_spp = defs_obj
        .get("set_project_path_tool_definition")
        .and_then(Value::as_object)
        .expect("facade_definitions() 缺少 `set_project_path_tool_definition`");
    let want_spp = obj(&reg, "set_project_path_tool_definition");
    assert_eq!(got_spp.get("name"), want_spp.get("name"), "set_project_path 的 name 不一致");
    assert!(
        got_spp.get("description").is_some_and(Value::is_string),
        "set_project_path 应有 description"
    );
    assert_eq!(
        got_spp.get("description"),
        want_spp.get("description"),
        "set_project_path 的 description 与 fixture 不一致"
    );
    assert_eq!(
        got_spp.get("inputSchema"),
        want_spp.get("inputSchema"),
        "set_project_path 的 inputSchema 与 fixture 不一致"
    );
}

// =====================================================================
// 6. 缺 action / 未知 action(含拼写建议)
// =====================================================================

#[test]
fn test_dispatch_missing_and_unknown_action_suggestions() {
    let fx = dispatch_fixture();
    let root = repo_root();
    let reg = registry();
    let expected_available = available_actions(&reg, "structure");

    // 案例 0:缺 action → 校验失败信封 + available_actions
    let r0 = assert_dispatch_case(&fx, "structure_missing_action", "structure", &root);
    assert_eq!(r0.get("success").and_then(Value::as_bool), Some(false));
    assert_eq!(r0.get("error_type").and_then(Value::as_str), Some("validation"));
    assert_eq!(r0.get("suggestion"), Some(&Value::Null), "无建议时 suggestion 应为 null");
    assert_eq!(
        str_array(r0.get("available_actions").expect("缺少 `available_actions`")),
        expected_available,
        "available_actions 应等于 structure 的 actions ∪ bespoke_actions(排序)"
    );

    // 案例 1:未知 action "outlin" → difflib 拼写建议命中 "outline"
    let r1 = assert_dispatch_case(&fx, "structure_unknown_action_with_suggestion", "structure", &root);
    assert_eq!(r1.get("success").and_then(Value::as_bool), Some(false));
    assert_eq!(r1.get("suggestion").and_then(Value::as_str), Some("outline"), "拼写建议应为 outline");
    let error1 = r1.get("error").and_then(Value::as_str).expect("缺少 `error`");
    assert!(error1.contains("unknown action 'outlin'"), "error 应回显未知 action: {error1}");
    assert!(error1.contains("did you mean"), "error 应包含拼写建议: {error1}");
    assert!(error1.contains("outline"), "error 应列出建议目标: {error1}");

    // 案例 2:未知 action "zzzzzz" → 无建议的失败信封
    let r2 = assert_dispatch_case(&fx, "structure_unknown_action_without_suggestion", "structure", &root);
    assert_eq!(r2.get("success").and_then(Value::as_bool), Some(false));
    assert_eq!(r2.get("suggestion"), Some(&Value::Null), "无可行建议时 suggestion 应为 null");
    let error2 = r2.get("error").and_then(Value::as_str).expect("缺少 `error`");
    assert!(error2.contains("unknown action 'zzzzzz'"), "error 应回显未知 action: {error2}");
}

// =====================================================================
// 7. action=help(无目标 / 指定 target_action)
// =====================================================================

#[test]
fn test_dispatch_action_help_and_target_action() {
    let fx = dispatch_fixture();
    let root = repo_root();
    let reg = registry();
    let expected_available = available_actions(&reg, "structure");

    // 案例 3:help 无 target → 列出全部 action,不带单 action schema
    let r3 = assert_dispatch_case(&fx, "structure_help_no_target", "structure", &root);
    assert_eq!(r3.get("success").and_then(Value::as_bool), Some(true));
    assert_eq!(r3.get("action").and_then(Value::as_str), Some("help"));
    assert_eq!(r3.get("target_action"), Some(&Value::Null), "未指定目标时 target_action 应为 null");
    assert_eq!(r3.get("schema_status").and_then(Value::as_str), Some("not_requested"));
    assert_eq!(
        str_array(r3.get("actions").expect("缺少 `actions`")),
        expected_available,
        "help 信封的 actions 应等于 structure 的 action 全集"
    );

    // 案例 4:help + target_action=outline → 附带该 action 的精确 input schema
    let r4 = assert_dispatch_case(&fx, "structure_help_target_outline", "structure", &root);
    assert_eq!(r4.get("success").and_then(Value::as_bool), Some(true));
    assert_eq!(r4.get("target_action").and_then(Value::as_str), Some("outline"));
    assert_eq!(r4.get("schema_status").and_then(Value::as_str), Some("available"));
    let schema = r4.get("action_schema").and_then(Value::as_object).expect("缺少 `action_schema`");
    for key in ["additionalProperties", "properties", "required", "type"] {
        assert!(schema.contains_key(key), "action_schema 缺少字段 `{key}`");
    }
}

// =====================================================================
// 8. 非法 output_format / 非法参数名(INVALID_ARGUMENT 信封)
// =====================================================================

#[test]
fn test_dispatch_invalid_output_format_and_invalid_argument() {
    let fx = dispatch_fixture();
    let root = repo_root();

    // 案例 5:outline 不支持 output_format=yaml
    let r5 = assert_dispatch_case(&fx, "structure_invalid_output_format", "structure", &root);
    assert_eq!(r5.get("success").and_then(Value::as_bool), Some(false));
    assert_eq!(r5.get("error_type").and_then(Value::as_str), Some("validation"));
    assert_eq!(r5.get("error_code").and_then(Value::as_str), Some("INVALID_ARGUMENT"));
    assert_eq!(
        str_array(r5.get("invalid_arguments").expect("缺少 `invalid_arguments`")),
        ["output_format"]
    );
    let allowed = r5.get("allowed_values").and_then(Value::as_object).expect("缺少 `allowed_values`");
    assert_eq!(
        str_array(allowed.get("output_format").expect("allowed_values 缺少 `output_format`")),
        ["json"],
        "structure.outline 的 output_format 只允许 json"
    );
    let error5 = r5.get("error").and_then(Value::as_str).expect("缺少 `error`");
    assert!(
        error5.contains("invalid value for 'output_format'") && error5.contains("'yaml'"),
        "error 应回显非法值: {error5}"
    );

    // 案例 6:未知名参数 bogus_param
    let r6 = assert_dispatch_case(&fx, "structure_invalid_argument", "structure", &root);
    assert_eq!(r6.get("success").and_then(Value::as_bool), Some(false));
    assert_eq!(r6.get("error_code").and_then(Value::as_str), Some("INVALID_ARGUMENT"));
    assert_eq!(
        str_array(r6.get("invalid_arguments").expect("缺少 `invalid_arguments`")),
        ["bogus_param"]
    );
    let error6 = r6.get("error").and_then(Value::as_str).expect("缺少 `error`");
    assert!(error6.contains("unsupported arguments: bogus_param"), "error 应回显未知名参数: {error6}");
    // 白名单回显:两个案例的 allowed_arguments 相同(即 outline 的参数投影)
    assert_eq!(
        r5.get("allowed_arguments"),
        r6.get("allowed_arguments"),
        "同一 action 的参数白名单应稳定"
    );
}

// =====================================================================
// 9. read 的分数行号边界(Python 侧抛 ValueError 的唯一案例)
// =====================================================================

#[test]
fn test_dispatch_read_fractional_bounds_error() {
    let fx = dispatch_fixture();
    let root = repo_root();
    let c = case(&fx, "structure_read_fractional_line_bound");
    // fixture 记录的是异常结局:ValueError + 消息
    assert_eq!(c.get("exception_type").and_then(Value::as_str), Some("ValueError"));
    assert!(c.get("result").is_none(), "该案例在 fixture 中没有 result,只有异常结局");
    let message = c
        .get("exception_message")
        .and_then(Value::as_str)
        .expect("缺少 `exception_message`");

    // Rust 契约:dispatch_facade 永不 panic,ValueError 以失败信封承载,且消息原样内嵌
    let input = c.get("input").expect("缺少 `input`");
    let actual = tsa_core::facade::dispatch_facade("structure", input, &root);
    assert!(
        actual.get("success").and_then(Value::as_bool) == Some(false),
        "Python 侧抛 ValueError 的案例,Rust 侧必须以失败信封承载,而不是 panic/成功"
    );
    let serialized =
        serde_json::to_string(&actual).unwrap_or_else(|err| panic!("信封序列化失败: {err}"));
    assert!(
        serialized.contains(message),
        "失败信封应原样内嵌异常消息 `{message}`,实际: {serialized}"
    );
}

// =====================================================================
// 10. structure 真实 action 黄金三联:analyze / outline / read
// =====================================================================

#[test]
fn test_dispatch_structure_analyze_outline_read_golden() {
    let fx = dispatch_fixture();
    let root = repo_root();

    for name in ["structure_analyze", "structure_outline", "structure_read_lines_1_to_15"] {
        let actual = assert_dispatch_case(&fx, name, "structure", &root);
        assert_eq!(
            actual.get("success").and_then(Value::as_bool),
            Some(true),
            "case `{name}` 应为成功信封"
        );
        // file_path 原样回显(fixture 中的仓库根相对路径)
        let input_path = case(&fx, name)
            .get("input")
            .and_then(|input| input.get("file_path"))
            .and_then(Value::as_str)
            .unwrap_or_else(|| panic!("case `{name}` 的 input 缺少 `file_path`"));
        assert_eq!(
            actual.get("file_path").and_then(Value::as_str),
            Some(input_path),
            "case `{name}` 应原样回显 file_path"
        );
    }

    // read 案例补充:行区间 1..=15 应被忠实执行
    let read = assert_dispatch_case(&fx, "structure_read_lines_1_to_15", "structure", &root);
    let range = read.get("range").and_then(Value::as_object).expect("缺少 `range`");
    assert_eq!(range.get("start").and_then(Value::as_i64), Some(1));
    assert_eq!(range.get("end").and_then(Value::as_i64), Some(15));
}

// =====================================================================
// 11. legacy 兼容分发 + scope=graph 注入 + 纯查表路由
// =====================================================================

#[test]
fn test_dispatch_legacy_shim_and_scope_graph_injection() {
    let fx = dispatch_fixture();
    let root = repo_root();
    // legacy 案例按生成器口径用 "." 作为 project_root 转发;
    // 先把进程 cwd 切到仓库根,使 "." 的解析与 cargo 起始 cwd 无关。
    // (同二进制内其它测试均用绝对路径,不受 cwd 切换影响。)
    std::env::set_current_dir(&root)
        .unwrap_or_else(|err| panic!("无法切换 cwd 到仓库根 {root}: {err}"));

    // 案例 11:get_code_outline → structure.outline,信封内嵌去弃用块
    let c11 = case(&fx, "legacy_get_code_outline");
    let out11 = tsa_core::facade::dispatch_legacy(
        "get_code_outline",
        c11.get("input").expect("缺少 `input`"),
        ".",
    )
    .unwrap_or_else(|err| panic!("legacy `get_code_outline` 应成功转发到 structure.outline: {err}"));
    assert_eq!(
        normalized(&out11),
        normalized(c11.get("result").expect("缺少 `result`")),
        "case `legacy_get_code_outline` 的转发结果与黄金 fixture 归一化后不一致"
    );
    assert_eq!(
        out11.get("deprecation"),
        c11.get("deprecation"),
        "去弃用信息应原样透传到结果信封"
    );

    // 案例 12:codegraph_call_graph → nav.callers,且 legacy 名必须注入 scope="graph"
    // (输入本身没有 scope 字段;fixture 的 forwarded_to_nav 记录了 Python 侧的实际转发参数)
    let c12 = case(&fx, "legacy_codegraph_call_graph");
    assert!(
        c12.get("input")
            .and_then(Value::as_object)
            .expect("input 不是对象")
            .get("scope")
            .is_none(),
        "fixture 前提:legacy 输入不含 scope,scope 是兼容层注入的"
    );
    let forwarded = c12
        .get("forwarded_to_nav")
        .and_then(Value::as_object)
        .expect("case `legacy_codegraph_call_graph` 缺少 `forwarded_to_nav`");
    assert_eq!(
        forwarded.get("scope").and_then(Value::as_str),
        Some("graph"),
        "兼容层应向 nav.callers 注入 scope=graph"
    );
    let out12 = tsa_core::facade::dispatch_legacy(
        "codegraph_call_graph",
        c12.get("input").expect("缺少 `input`"),
        ".",
    )
    .unwrap_or_else(|err| panic!("legacy `codegraph_call_graph` 应成功转发到 nav.callers: {err}"));
    // 黄金结果本身就是在 scope=graph 注入下产生的 —— 深对比等价于断言注入发生
    assert_eq!(
        normalized(&out12),
        normalized(c12.get("result").expect("缺少 `result`")),
        "case `legacy_codegraph_call_graph` 的转发结果与黄金 fixture 归一化后不一致"
    );
    assert_eq!(
        out12.get("deprecation"),
        c12.get("deprecation"),
        "去弃用信息应原样透传到结果信封"
    );

    // 案例 13/14:纯查表路由 legacy_name -> (facade, action)
    for (case_name, legacy_name) in [
        ("legacy_to_facade_query_code", "query_code"),
        ("legacy_to_facade_codegraph_symbol_search", "codegraph_symbol_search"),
    ] {
        let c = case(&fx, case_name);
        let want = str_array(c.get("result").expect("缺少 `result`"));
        assert_eq!(want.len(), 2, "case `{case_name}` 的 result 应为 [facade, action]");
        assert_eq!(
            tsa_core::facade::legacy_to_facade(legacy_name),
            Some((want[0], want[1])),
            "`{legacy_name}` 的查表路由与 fixture 不一致"
        );
    }

    // 查表失败路径:未知名与已移除名都返回 Err(调用方包装为错误信封)
    for bad in ["no_such_tool", "batch_search"] {
        let outcome = tsa_core::facade::dispatch_legacy(bad, &serde_json::json!({}), ".");
        assert!(outcome.is_err(), "legacy 分发对 `{bad}` 应返回 Err,实际: {outcome:?}");
    }
}
