//! envelope 模块的红灯契约测试(Stage 1,SPEC §5.2)。
//!
//! 黄金对照物为 `rust/fixtures/envelope/*.json` 与 `rust/fixtures/cli/cli_outputs.json`
//! (Python 侧 tree_sitter_analyzer 3.1.2 真实输出的规范化 JSON,由
//! `rust/fixtures/tools/gen_envelope_cli.py` 捕获,禁止手工编纂;顶层形状由
//! `fixtures_smoke.rs` 把守,本文件只做行为对照)。
//!
//! Stage 1 判据:每个测试都**先调用** `tsa_core::envelope::*`(当前函数体全部
//! `todo!()`)再断言,因此行为测试统一以 `not yet implemented` 失败,而不是
//! fixture 读取/解析错误。Stage 2-3 实装后,本文件全部断言必须转绿且不得改动 fixture。
//!
//! 键序是契约的一部分(`serde_json` 启用 `preserve_order`):除 `Value` 值相等外,
//! 还通过 `assert_json_matches` 逐字节比对紧凑序列化结果,强制键序与整数/浮点形态一致。

use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

use serde_json::{json, Map, Value};
use tsa_core::envelope::{
    build_agent_friendly_error, build_agent_summary, build_error, build_error_response,
    build_response, build_success_response, canonical_verdicts, classify_error,
    cli_structure_json, ensure_canonical_error_envelope, ensure_canonical_success_envelope,
    envelope_violations, normalize_path_k12, validate_tool_response, CanonicalVerdict,
};

// ---------- fixture 装载与断言助手 ----------

/// fixtures 根目录:相对 crate 清单定位(`rust/tsa-core` → `rust/fixtures`),与 cwd 无关。
fn fixtures_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../fixtures")
}

/// 仓库根目录(fixture 生成器与 CLI 黄金输出共同的工作目录)。
fn repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

/// 读取并解析一份 fixture;失败即 panic(契约测试不该静默跳过)。
fn load(rel_path: &str) -> Value {
    let path = fixtures_dir().join(rel_path);
    let raw = fs::read_to_string(&path)
        .unwrap_or_else(|err| panic!("无法读取 fixture {}: {err}", path.display()));
    serde_json::from_str(&raw)
        .unwrap_or_else(|err| panic!("fixture 不是合法 JSON {}: {err}", path.display()))
}

/// 取 `Value` 的字符串字段。
fn s<'a>(value: &'a Value, key: &str) -> &'a str {
    value
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or_else(|| panic!("字段 `{key}` 缺失或非字符串"))
}

/// 取 `Value` 的数组字段(切片)。
fn arr<'a>(value: &'a Value, key: &str) -> &'a [Value] {
    value
        .get(key)
        .and_then(Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or_else(|| panic!("字段 `{key}` 缺失或非数组"))
}

/// 取 `Value` 的对象字段。
fn obj<'a>(value: &'a Value, key: &str) -> &'a Map<String, Value> {
    value
        .get(key)
        .and_then(Value::as_object)
        .unwrap_or_else(|| panic!("字段 `{key}` 缺失或非对象"))
}

/// 取 JSON 对象内的对象字段。
fn mobj<'a>(map: &'a Map<String, Value>, key: &str) -> &'a Map<String, Value> {
    map.get(key)
        .and_then(Value::as_object)
        .unwrap_or_else(|| panic!("字段 `{key}` 缺失或非对象"))
}

/// 取 JSON 对象内的字符串字段。
fn mstr<'a>(map: &'a Map<String, Value>, key: &str) -> &'a str {
    map.get(key)
        .and_then(Value::as_str)
        .unwrap_or_else(|| panic!("字段 `{key}` 缺失或非字符串"))
}

/// 由键值对构造 `Map<String, Value>`(等价 Python 侧的 `**fields` 展开)。
fn jmap(pairs: &[(&str, Value)]) -> Map<String, Value> {
    pairs.iter().map(|(k, v)| (k.to_string(), v.clone())).collect()
}

/// 值相等 + 键序一致的双重对照(preserve_order 下键序属于逐字节契约)。
fn assert_json_matches(actual: &Value, golden: &Value, ctx: &str) {
    assert_eq!(actual, golden, "{ctx}: JSON 值不一致");
    let actual_text = serde_json::to_string(actual).expect("actual 序列化失败");
    let golden_text = serde_json::to_string(golden).expect("golden 序列化失败");
    assert_eq!(actual_text, golden_text, "{ctx}: 键序/序列化字节不一致");
}

/// 从黄金错误信封反推调用时的 `arguments`:身份镜像顺序
/// `file_path → symbol → query → roots[0] → mode`,fixture 覆盖 file_path / query / mode
/// 三种;均缺席时为 `None`(与生成器 `ERROR_CASES` 表逐用例对应)。
fn identity_arguments_from_golden(golden: &Map<String, Value>) -> Option<Value> {
    for key in ["file_path", "query", "mode"] {
        if let Some(text) = golden.get(key).and_then(Value::as_str) {
            let mut arguments = Map::new();
            arguments.insert(key.to_string(), Value::String(text.to_string()));
            return Some(Value::Object(arguments));
        }
    }
    None
}

// ---------- canonical verdicts ----------

#[test]
fn test_canonical_verdicts_match_fixture() {
    let got = canonical_verdicts().to_vec();
    let valid = load("envelope/response_builder_valid.json");
    let from_valid: Vec<&str> = arr(&valid, "canonical_verdicts")
        .iter()
        .map(|v| v.as_str().expect("canonical_verdicts 项非字符串"))
        .collect();
    assert_eq!(got, from_valid, "canonical_verdicts 须与 fixture 逐字一致");
    // 第二份 fixture 交叉对照
    let validation = load("envelope/envelope_validation.json");
    let from_validation: Vec<&str> = arr(&validation, "canonical_verdicts")
        .iter()
        .map(|v| v.as_str().expect("canonical_verdicts 项非字符串"))
        .collect();
    assert_eq!(got, from_validation, "两份 fixture 的 canonical 集合必须相同");
    // `CanonicalVerdict` 枚举全集与 `canonical_verdicts()` 一致(顺序即 Python 侧 sorted)
    let enum_strs: Vec<&str> = [
        CanonicalVerdict::Safe,
        CanonicalVerdict::Review,
        CanonicalVerdict::Caution,
        CanonicalVerdict::Unsafe,
        CanonicalVerdict::Info,
        CanonicalVerdict::Warn,
        CanonicalVerdict::Error,
        CanonicalVerdict::NotFound,
    ]
    .iter()
    .map(CanonicalVerdict::as_str)
    .collect();
    let mut sorted_enum = enum_strs.clone();
    sorted_enum.sort_unstable();
    assert_eq!(got, sorted_enum, "枚举 as_str 全集必须等于 canonical 集合");
    assert_eq!(got.len(), 8, "canonical verdict 恰为 8 个");
}

// ---------- build_response 族工厂 ----------

#[test]
fn test_build_response_all_canonical_verdicts() {
    let fixture = load("envelope/response_builder_valid.json");
    for case in arr(&fixture, "build_response_all_verdicts") {
        let verdict = s(case, "verdict");
        let result = build_response(
            verdict,
            true,
            None,
            jmap(&[("mode", json!("fixture")), ("total_count", json!(1))]),
        )
        .unwrap_or_else(|err| panic!("verdict={verdict} 为 canonical,不应报错: {err}"));
        assert_json_matches(
            &result,
            &Value::Object(obj(case, "result").clone()),
            &format!("build_response({verdict})"),
        );
    }
    assert_eq!(arr(&fixture, "build_response_all_verdicts").len(), 8);
}

#[test]
fn test_build_response_warnings_variants() {
    let fixture = load("envelope/response_builder_valid.json");
    for case in arr(&fixture, "build_response_warnings_variants") {
        let label = s(case, "label");
        // fixture 的 warnings_argument:null → None,[] → 空切片,非空 → 元素列表
        let warnings: Option<Vec<&str>> = case
            .get("warnings_argument")
            .and_then(Value::as_array)
            .map(|list| list.iter().map(|w| w.as_str().expect("warnings 项非字符串")).collect());
        let result = build_response("INFO", true, warnings.as_deref(), jmap(&[("mode", json!("warnings_probe"))]))
            .unwrap_or_else(|err| panic!("label={label} 不应报错: {err}"));
        assert_json_matches(
            &result,
            &Value::Object(obj(case, "result").clone()),
            &format!("warnings 变体 {label}"),
        );
        let present = result.get("warnings").is_some();
        let expected_present = case
            .get("warnings_key_present")
            .and_then(Value::as_bool)
            .expect("缺少 warnings_key_present");
        assert_eq!(present, expected_present, "label={label}: warnings 键在场性不一致");
    }
    assert_eq!(arr(&fixture, "build_response_warnings_variants").len(), 3);
}

#[test]
fn test_build_response_rejects_invalid_verdicts() {
    let fixture = load("envelope/response_builder_invalid.json");
    for case in arr(&fixture, "invalid_verdicts") {
        let input = s(case, "input");
        let message = s(case, "message");
        let err = build_response(input, true, None, Map::new())
            .expect_err(&format!("verdict={input:?} 必须被拒绝"));
        assert_eq!(err.verdict, input, "错误须回显非法 verdict 原值");
        assert_eq!(err.message, message, "input={input}: 错误消息必须逐字一致");
        assert_eq!(err.to_string(), message, "Display 必须渲染完整消息");
        // 其余工厂同样过 canonical 校验,InvalidVerdictError 形态一致
        assert_eq!(
            build_error("boom", input, Map::new()).expect_err("build_error 须拒绝非法 verdict").message,
            message,
            "input={input}: build_error 消息必须同形"
        );
        assert_eq!(
            build_error_response("t", "e", input, Map::new())
                .expect_err("build_error_response 须拒绝非法 verdict")
                .message,
            message,
            "input={input}: build_error_response 消息必须同形"
        );
        assert_eq!(
            build_success_response("t", Map::new(), input, None)
                .expect_err("build_success_response 须拒绝非法 verdict")
                .message,
            message,
            "input={input}: build_success_response 消息必须同形"
        );
        assert_eq!(
            build_agent_summary(input, "m", None)
                .expect_err("build_agent_summary 须拒绝非法 verdict")
                .message,
            message,
            "input={input}: build_agent_summary 消息必须同形"
        );
    }
    assert_eq!(arr(&fixture, "invalid_verdicts").len(), 9);
}

#[test]
fn test_build_error_and_error_response() {
    let fixture = load("envelope/response_builder_valid.json");
    let error_cases = arr(&fixture, "build_error");
    // build_error(error='boom') → 默认 verdict=ERROR
    let golden = obj(&error_cases[0], "result");
    let result = build_error("boom", "ERROR", Map::new()).expect("build_error('boom') 不应报错");
    assert_json_matches(&result, &Value::Object(golden.clone()), "build_error('boom')");
    // build_error(error=..., verdict='NOT_FOUND', mode='lookup')
    let golden = obj(&error_cases[1], "result");
    let result = build_error("no such symbol", "NOT_FOUND", jmap(&[("mode", json!("lookup"))]))
        .expect("build_error(NOT_FOUND) 不应报错");
    assert_json_matches(&result, &Value::Object(golden.clone()), "build_error(NOT_FOUND, mode=lookup)");
    assert_eq!(error_cases.len(), 2);

    let response_cases = arr(&fixture, "build_error_response");
    // build_error_response('query', 'bad symbol') → 默认 verdict=ERROR,附 tool 键
    let golden = obj(&response_cases[0], "result");
    let result = build_error_response("query", "bad symbol", "ERROR", Map::new())
        .expect("build_error_response('query') 不应报错");
    assert_json_matches(&result, &Value::Object(golden.clone()), "build_error_response('query')");
    // verdict='NOT_FOUND' + 附加字段 available_keys
    let golden = obj(&response_cases[1], "result");
    let result = build_error_response(
        "read_partial",
        "key missing",
        "NOT_FOUND",
        jmap(&[("available_keys", json!(["a", "b"]))]),
    )
    .expect("build_error_response(NOT_FOUND) 不应报错");
    assert_json_matches(&result, &Value::Object(golden.clone()), "build_error_response(NOT_FOUND)");
    assert_eq!(response_cases.len(), 2);
}

#[test]
fn test_build_success_and_agent_summary() {
    let fixture = load("envelope/response_builder_valid.json");
    let success_cases = arr(&fixture, "build_success_response");
    // duration_ms=None → 键缺席;Python 侧的 page=1(**fields)并入 data 展开等价复现
    let golden = obj(&success_cases[0], "result");
    let result = build_success_response(
        "query",
        jmap(&[("total", json!(3)), ("page", json!(1))]),
        "INFO",
        None,
    )
    .expect("duration_ms=None 不应报错");
    assert_json_matches(&result, &Value::Object(golden.clone()), "build_success_response(None)");
    assert!(result.get("duration_ms").is_none(), "duration_ms=None 时键必须缺席");
    // duration_ms=12.5 → 键在场且值一致
    let golden = obj(&success_cases[1], "result");
    let result = build_success_response(
        "query",
        jmap(&[("total", json!(3)), ("page", json!(1))]),
        "INFO",
        Some(12.5),
    )
    .expect("duration_ms=12.5 不应报错");
    assert_json_matches(&result, &Value::Object(golden.clone()), "build_success_response(12.5)");
    assert_eq!(result.get("duration_ms"), Some(&json!(12.5)));
    assert_eq!(success_cases.len(), 2);

    let summary_cases = arr(&fixture, "build_agent_summary");
    // 无 recommendations → 键缺席
    let golden = obj(&summary_cases[0], "result");
    let result =
        build_agent_summary("WARN", "index is stale", None).expect("build_agent_summary 不应报错");
    assert_json_matches(&result, &Value::Object(golden.clone()), "build_agent_summary(无 recommendations)");
    assert!(result.get("recommendations").is_none());
    // 带 recommendations → 键在场
    let golden = obj(&summary_cases[1], "result");
    let result = build_agent_summary("CAUTION", "coverage limited", Some(&["narrow the query"]))
        .expect("build_agent_summary 不应报错");
    assert_json_matches(&result, &Value::Object(golden.clone()), "build_agent_summary(带 recommendations)");
    assert_eq!(summary_cases.len(), 2);
}

// ---------- validate_tool_response / envelope_violations ----------

#[test]
fn test_validate_tool_response_valid_and_invalid() {
    let fixture = load("envelope/envelope_validation.json");
    let mut valid_count = 0;
    for case in arr(&fixture, "valid") {
        let name = s(case, "name");
        let envelope = case.get("envelope").expect("缺少 envelope");
        validate_tool_response(envelope, name)
            .unwrap_or_else(|err| panic!("valid 用例 {name} 应通过校验: {err}"));
        valid_count += 1;
    }
    assert_eq!(valid_count, 5);

    let mut invalid_count = 0;
    for case in arr(&fixture, "invalid") {
        let name = s(case, "name");
        let envelope = case.get("envelope").expect("缺少 envelope");
        let outcome_record = obj(case, "validate_tool_response");
        let raised = outcome_record.get("raised").and_then(Value::as_bool).expect("缺少 raised");
        let outcome = validate_tool_response(envelope, name);
        if raised {
            let expected = outcome_record
                .get("assertion_error")
                .and_then(Value::as_str)
                .expect("raised=true 时缺 assertion_error");
            let err = outcome.expect_err(&format!("用例 {name} 应触发 base 断言失败"));
            assert_eq!(err, expected, "用例 {name}: 断言消息须逐字一致");
        } else {
            outcome.unwrap_or_else(|err| panic!("用例 {name} 不应触发 base 断言: {err}"));
        }
        invalid_count += 1;
    }
    assert_eq!(invalid_count, 17);
}

#[test]
fn test_envelope_violations_all_11_rules() {
    let fixture = load("envelope/envelope_validation.json");
    // 合法信封:零违规
    for case in arr(&fixture, "valid") {
        let name = s(case, "name");
        let envelope = case.get("envelope").expect("缺少 envelope");
        assert!(
            envelope_violations(envelope, name).is_empty(),
            "valid 用例 {name} 不应报违规"
        );
    }
    // 非法信封:违规清单逐项(规则名 + 消息)一致
    let mut fired_union: BTreeSet<String> = BTreeSet::new();
    for case in arr(&fixture, "invalid") {
        let name = s(case, "name");
        let envelope = case.get("envelope").expect("缺少 envelope");
        let violations = envelope_violations(envelope, name);
        let expected: Vec<(String, String)> = arr(case, "envelope_violations")
            .iter()
            .map(|pair| {
                let pair = pair.as_array().expect("违规项应为 [rule, message] 二元组");
                (
                    pair[0].as_str().expect("rule 非字符串").to_string(),
                    pair[1].as_str().expect("message 非字符串").to_string(),
                )
            })
            .collect();
        assert_eq!(violations, expected, "用例 {name}: 违规清单须逐项一致");
        let mut rules: Vec<&str> = violations.iter().map(|(rule, _)| rule.as_str()).collect();
        rules.sort_unstable();
        rules.dedup();
        let expected_rules: Vec<&str> = arr(case, "rules_fired")
            .iter()
            .map(|r| r.as_str().expect("rules_fired 项非字符串"))
            .collect();
        assert_eq!(rules, expected_rules, "用例 {name}: 触发规则集须一致");
        fired_union.extend(violations.iter().map(|(rule, _)| rule.clone()));
    }
    // 11 条规则全部被真实触发(复刻 fixture 的 rules_actually_fired 自检)
    let rules_declared: BTreeSet<String> = arr(&fixture, "envelope_rules")
        .iter()
        .map(|r| r.as_str().expect("envelope_rules 项非字符串").to_string())
        .collect();
    let rules_fired_fixture: BTreeSet<String> = arr(&fixture, "rules_actually_fired")
        .iter()
        .map(|r| r.as_str().expect("rules_actually_fired 项非字符串").to_string())
        .collect();
    assert_eq!(fired_union, rules_fired_fixture, "Rust 侧触发的规则全集须与 fixture 一致");
    assert_eq!(fired_union, rules_declared, "11 条 envelope 规则必须全部被真实触发");
    assert_eq!(fired_union.len(), 11);
}

// ---------- 错误恢复(error_recovery)----------

#[test]
fn test_error_recovery_classify_12_cases() {
    let fixture = load("envelope/error_recovery.json");
    let cases = arr(&fixture, "error_cases");
    for case in cases {
        let name = s(case, "name");
        let message = s(case, "sanitized_message");
        let exc_class = s(case, "exception_class");
        let classified = classify_error(message, exc_class);
        let expected = obj(case, "classify");
        assert_eq!(classified.error_type, mstr(expected, "error_type"), "用例 {name}: error_type 不一致");
        assert_eq!(classified.recovery_hint, mstr(expected, "recovery_hint"), "用例 {name}: recovery_hint 不一致");
        assert_eq!(
            classified.suggested_tool, mstr(expected, "suggested_tool"),
            "用例 {name}: suggested_tool 不一致(空串 = 无建议)"
        );
    }
    assert_eq!(cases.len(), 12);
}

#[test]
fn test_error_recovery_build_agent_friendly_error() {
    let fixture = load("envelope/error_recovery.json");
    let cases = arr(&fixture, "error_cases");
    for case in cases {
        let name = s(case, "name");
        let message = s(case, "sanitized_message");
        let exc_class = s(case, "exception_class");
        let golden = obj(case, "build_agent_friendly_error");
        // arguments 从黄金输出的身份镜像字段反推(与生成器 ERROR_CASES 表一致)
        let arguments = identity_arguments_from_golden(golden);
        let envelope = build_agent_friendly_error("fixture_probe", message, exc_class, arguments.as_ref());
        assert_json_matches(
            &envelope,
            &Value::Object(golden.clone()),
            &format!("build_agent_friendly_error({name})"),
        );
    }
    assert_eq!(cases.len(), 12);
}

#[test]
fn test_error_recovery_preserves_preset_and_derives_identity() {
    let fixture = load("envelope/error_recovery.json");

    // (a) 预设字段不被覆盖:调用方给出的 error_type / next_step 原样保留
    //(输入即生成器字面量;预设字段在黄金输出中被保留,可直接从黄金侧回取)
    let golden_preset = obj(&fixture, "error_envelope_preserves_preset_fields");
    let preset_input = Value::Object(jmap(&[
        ("success", json!(false)),
        ("error", json!(mstr(golden_preset, "error"))),
        ("error_type", json!(mstr(golden_preset, "error_type"))),
        ("next_step", json!(mstr(golden_preset, "next_step"))),
    ]));
    let completed = ensure_canonical_error_envelope(&preset_input, "fixture_probe");
    assert_json_matches(&completed, &Value::Object(golden_preset.clone()), "preserves_preset_fields");

    // (b) 缺 error 的失败响应:从 errors 列表推导 error,并从消息前导码推导 error_code
    let golden_derived = obj(&fixture, "error_envelope_derives_identity");
    let derived_input = Value::Object(jmap(&[
        ("success", json!(false)),
        ("errors", json!(golden_derived.get("errors").cloned().expect("黄金输出缺 errors 列表"))),
    ]));
    let completed = ensure_canonical_error_envelope(&derived_input, "fixture_probe");
    assert_json_matches(&completed, &Value::Object(golden_derived.clone()), "derives_identity");

    // (c) 12 用例中 arguments=None 的最小信封(无身份镜像字段)同样可由 Rust 入口复现;
    //带身份镜像的用例需要 arguments,Rust 入口不接收,由 build_agent_friendly_error 测试覆盖
    let mut minimal_count = 0;
    for case in arr(&fixture, "error_cases") {
        let name = s(case, "name");
        let golden = obj(case, "ensure_canonical_error_envelope_from_minimal");
        if identity_arguments_from_golden(golden).is_some() {
            continue;
        }
        let minimal_input = Value::Object(jmap(&[
            ("success", json!(false)),
            ("error", json!(mstr(golden, "error"))),
        ]));
        let completed = ensure_canonical_error_envelope(&minimal_input, "fixture_probe");
        assert_json_matches(
            &completed,
            &Value::Object(golden.clone()),
            &format!("from_minimal({name})"),
        );
        minimal_count += 1;
    }
    assert_eq!(minimal_count, 6, "无身份镜像的 from_minimal 用例应为 6 个");
}

#[test]
fn test_k12_path_normalization_and_m14_language_echo() {
    let fixture = load("envelope/error_recovery.json");

    // K12 直测:'./a\b.py' → 'a/b.py'(\ 归一为 /,前导 ./ 剥除)
    let k12 = obj(&fixture, "k12_path_normalization");
    let direct = mobj(k12, "normalize_path_string_direct");
    let input_path = mstr(direct, "input");
    let normalized = normalize_path_k12(input_path);
    assert_eq!(normalized, mstr(direct, "output"), "K12 路径归一化直测不一致");
    // './X' 与 'X' 必须字节一致(前导 ./ 可循环剥除)
    assert_eq!(
        normalize_path_k12(&format!("./{normalized}")),
        normalized,
        "前导 ./ 必须可循环剥除"
    );

    // K12 信封级:file_path 回显归一化 + M10 verdict 顶层/agent_summary 镜像
    let input_envelope = k12.get("input_envelope").expect("缺少 input_envelope");
    let output = ensure_canonical_success_envelope(input_envelope, "k12_probe", None);
    assert_json_matches(&output, &Value::Object(mobj(k12, "output_envelope").clone()), "k12_path_normalization");

    // M14:单文件成功信封自动检测并回显 language(.py → python),verdict 兜底 'n/a'
    let m14 = obj(&fixture, "m14_language_echo");
    let input_envelope = m14.get("input_envelope").expect("缺少 input_envelope");
    let output = ensure_canonical_success_envelope(input_envelope, "m14_probe", None);
    assert_json_matches(&output, &Value::Object(mobj(m14, "output_envelope").clone()), "m14_language_echo");
}

// ---------- CLI structure JSON(v3.1.2 黄金)----------

/// CLI 输出归一化:镜像 fixture 生成器的确定性化处理 ——
/// (1) 绝对仓库根前缀折叠为相对路径;(2) 计时键(数值)置 null;(3) 墙钟 `timestamp` 双侧剔除。
fn normalize_cli_output(value: &Value, root: &Path) -> Value {
    let root_str = root.display().to_string();
    let prefix = format!("{root_str}/");
    match value {
        Value::String(text) => {
            let normalized = if text.contains(&prefix) {
                text.replace(&prefix, "")
            } else if text == &root_str {
                ".".to_string()
            } else if text.contains(&root_str) {
                text.replace(&root_str, ".")
            } else {
                text.clone()
            };
            Value::String(normalized)
        }
        Value::Array(items) => Value::Array(items.iter().map(|item| normalize_cli_output(item, root)).collect()),
        Value::Object(map) => {
            let mut out = Map::new();
            for (key, child) in map {
                if key == "timestamp" {
                    continue;
                }
                if matches!(key.as_str(), "analysis_time" | "duration_ms" | "elapsed_ms" | "elapsed_time")
                    && child.is_number()
                {
                    out.insert(key.clone(), Value::Null);
                } else {
                    out.insert(key.clone(), normalize_cli_output(child, root));
                }
            }
            Value::Object(out)
        }
        _ => value.clone(),
    }
}

#[test]
fn test_cli_structure_json_matches_v312_golden() {
    let root = repo_root()
        .canonicalize()
        .unwrap_or_else(|err| panic!("无法定位仓库根: {err}"));
    let corpus = root.join("tests/golden/corpus_python.py");
    let actual = cli_structure_json(corpus.to_str().expect("语料路径非 UTF-8"))
        .expect("structure JSON 生成失败");
    // 缺文件路径必须走 Err(对照 fixture 的 missing_file 用例:exit_code=1、stdout 不可解析)
    let missing = corpus.with_file_name("does_not_exist_xyz.py");
    assert!(
        cli_structure_json(missing.to_str().expect("路径非 UTF-8")).is_err(),
        "缺文件必须以 Err 收场"
    );

    // 黄金:fixture `structure` 用例的 stdout_json
    let cli = load("cli/cli_outputs.json");
    let case = arr(&cli, "cases")
        .iter()
        .find(|c| c.get("name").and_then(Value::as_str) == Some("structure"))
        .expect("cli_outputs.json 缺少 structure 用例");
    let golden = case.get("stdout_json").expect("structure 用例缺 stdout_json");

    // 双侧过同一归一化(键序保留),再逐字节对照
    let actual_n = normalize_cli_output(&actual, &root);
    let golden_n = normalize_cli_output(golden, &root);
    assert_json_matches(&actual_n, &golden_n, "cli structure 输出对照 v3.1.2 黄金");

    // 信封契约(_CLI_ENVELOPE_KEYS):顶层 4 键 + agent_summary 必备 2 键 + verdict 镜像
    for key in ["success", "summary_line", "verdict", "agent_summary"] {
        assert!(actual.get(key).is_some(), "顶层缺 `{key}`");
    }
    let summary = actual
        .get("agent_summary")
        .and_then(Value::as_object)
        .expect("agent_summary 非对象");
    for key in ["summary_line", "verdict"] {
        assert!(summary.contains_key(key), "agent_summary 缺 `{key}`");
    }
    assert_eq!(actual.get("success"), Some(&Value::Bool(true)));
    assert_eq!(actual.get("verdict"), Some(&Value::String("INFO".into())));
    assert_eq!(
        summary.get("verdict"),
        actual.get("verdict"),
        "顶层 verdict 必须镜像 agent_summary.verdict"
    );
}
