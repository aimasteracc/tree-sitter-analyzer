//! JSON envelope 契约(SPEC §2.1(a))。
//!
//! 对照 Python 侧来源:
//! - `mcp/tools/tool_response.py`(`CANONICAL_VERDICTS`、`ENVELOPE_RULES`、`validate_tool_response`、`envelope_violations`)
//! - `mcp/tools/_response_builder.py`(工厂函数族、`InvalidVerdictError`)
//! - `mcp/server_utils/error_recovery.py`(错误信封规范化、K12 路径归一化、M14 language 回显)
//! - `tests/unit/cli/test_cli_envelope_contract.py` 的 `_CLI_ENVELOPE_KEYS`(CLI 4 键信封)
//!
//! 黄金对照物:`rust/fixtures/envelope/*.json` 与 `rust/fixtures/cli/cli_outputs.json`。
//! Stage 1:全部函数体为 `todo!()`,签名即 Stage 2-3 的实现契约。

#![allow(unused_variables, dead_code)]

use serde_json::{Map, Value};

/// canonical verdict 枚举(8 个,SPEC §2.1;与 Python 侧两处 `CANONICAL_VERDICTS` frozenset 一致)。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum CanonicalVerdict {
    /// SAFE
    Safe,
    /// REVIEW
    Review,
    /// CAUTION
    Caution,
    /// UNSAFE
    Unsafe,
    /// INFO
    Info,
    /// WARN
    Warn,
    /// ERROR
    Error,
    /// NOT_FOUND
    NotFound,
}

impl CanonicalVerdict {
    /// 序列化用的规范字符串(与 fixture `canonical_verdicts` 逐字一致)。
    pub fn as_str(&self) -> &'static str {
        match self {
            CanonicalVerdict::Safe => "SAFE",
            CanonicalVerdict::Review => "REVIEW",
            CanonicalVerdict::Caution => "CAUTION",
            CanonicalVerdict::Unsafe => "UNSAFE",
            CanonicalVerdict::Info => "INFO",
            CanonicalVerdict::Warn => "WARN",
            CanonicalVerdict::Error => "ERROR",
            CanonicalVerdict::NotFound => "NOT_FOUND",
        }
    }
}

/// `build_response` 收到非 canonical verdict 时返回的错误。
///
/// 对应 Python 侧 `InvalidVerdictError(ValueError)`:`message` 必须与 fixture
/// `response_builder_invalid.json` 逐字一致(含非法值与 `sorted(CANONICAL_VERDICTS)`)。
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
#[error("{message}")]
pub struct InvalidVerdictError {
    /// 非法的 verdict 原值
    pub verdict: String,
    /// 完整错误消息(格式见 fixture,例:`verdict='OK' not in canonical set [...]. Use build_error() ...`)
    pub message: String,
}

/// 一条 envelope 违规(与 fixture 中 `[rule, message]` 二元组对应)。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EnvelopeViolation {
    /// 违规规则名(必须来自 `ENVELOPE_RULES` 闭集,如 `failure-verdict`)
    pub rule: String,
    /// 人类可读的违规说明
    pub message: String,
}

impl EnvelopeViolation {
    /// 转为与 fixture 元组形态一致的 `(rule, message)`。
    pub fn as_tuple(&self) -> (String, String) {
        (self.rule.clone(), self.message.clone())
    }
}

/// `error_recovery._classify` 的分类结果。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ErrorClassification {
    /// 机器可读错误类型(如 `file_not_found`、`validation`、`internal`)
    pub error_type: String,
    /// 人类可读恢复提示(agent_summary.next_step 同源)
    pub recovery_hint: String,
    /// 建议的后续工具(空串 = 无建议;如 `set_project_path`、`index`)
    pub suggested_tool: String,
}

/// 8 个 canonical verdict 字符串(SPEC §2.1;顺序即 Python 侧 `sorted(CANONICAL_VERDICTS)`):
/// `["SAFE", "REVIEW", "CAUTION", "UNSAFE", "INFO", "WARN", "ERROR", "NOT_FOUND"]`。
pub fn canonical_verdicts() -> &'static [&'static str] {
    todo!("Stage 2-3: envelope not yet implemented in Rust")
}

/// `build_response(*, verdict, success=True, warnings=None, **fields)`。
///
/// 输出 `{"success", "verdict", **fields}`,warnings 非空时追加 `"warnings"`(拷贝为 list)。
/// verdict 不在 canonical 集合时立即返回 `Err(InvalidVerdictError)`。
pub fn build_response(
    verdict: &str,
    success: bool,
    warnings: Option<&[&str]>,
    fields: Map<String, Value>,
) -> Result<Value, InvalidVerdictError> {
    todo!("Stage 2-3: envelope not yet implemented in Rust")
}

/// `build_error(*, error, verdict="ERROR", **fields)`。
///
/// 输出 `{"success": False, "verdict", "error", **fields}`;verdict 同样过 canonical 校验。
pub fn build_error(
    error: &str,
    verdict: &str,
    fields: Map<String, Value>,
) -> Result<Value, InvalidVerdictError> {
    todo!("Stage 2-3: envelope not yet implemented in Rust")
}

/// `build_error_response(tool_name, error, verdict="ERROR", **fields)`。
///
/// 同 `build_error` 并追加 `"tool": tool_name`。
pub fn build_error_response(
    tool_name: &str,
    error: &str,
    verdict: &str,
    fields: Map<String, Value>,
) -> Result<Value, InvalidVerdictError> {
    todo!("Stage 2-3: envelope not yet implemented in Rust")
}

/// `build_success_response(tool_name, data, verdict="INFO", duration_ms=None, **fields)`。
///
/// 输出 `{"success": True, "verdict", "tool", **data, **fields}`,`duration_ms` 非 None 时追加。
pub fn build_success_response(
    tool_name: &str,
    data: Map<String, Value>,
    verdict: &str,
    duration_ms: Option<f64>,
) -> Result<Value, InvalidVerdictError> {
    todo!("Stage 2-3: envelope not yet implemented in Rust")
}

/// `build_agent_summary(verdict, message, recommendations=None, **fields)`。
///
/// 输出 `{"success": True, "verdict", "message", **fields}`,recommendations 非空时追加。
pub fn build_agent_summary(
    verdict: &str,
    message: &str,
    recommendations: Option<&[&str]>,
) -> Result<Value, InvalidVerdictError> {
    todo!("Stage 2-3: envelope not yet implemented in Rust")
}

/// `validate_tool_response(payload, tool_name)` 的 Rust 形态。
///
/// Python 侧违规 raise `AssertionError`;此处返回 `Err(断言消息)`。
/// 判据(payload 必须 dict;`success` 必存在且为 bool;失败时必须有 `error: str`;
/// `verdict` 存在时必须 canonical)对应规则 1 `base`。
/// 消息格式见 fixture `envelope_validation.json` 的 `assertion_error` 字段。
pub fn validate_tool_response(payload: &Value, tool_name: &str) -> Result<(), String> {
    todo!("Stage 2-3: envelope not yet implemented in Rust")
}

/// `envelope_violations(payload, tool_name)`:返回全部 `(rule, message)` 违规,不抛异常;空列表 = 合规。
///
/// 必须覆盖 11 条 envelope 规则(fixture `rules_actually_fired` 已逐一验证)。
pub fn envelope_violations(payload: &Value, tool_name: &str) -> Vec<(String, String)> {
    todo!("Stage 2-3: envelope not yet implemented in Rust")
}

/// `error_recovery._classify(sanitized_message, exception_class)`。
///
/// 消息文本优先于异常类(15 条子串规则按序首中即停),异常类回退表次之,最终兜底 `internal`。
/// 对照 fixture `error_recovery.json` 的 `error_cases` 字段(12 个用例)。
pub fn classify_error(error_message: &str, exc_class: &str) -> ErrorClassification {
    todo!("Stage 2-3: envelope not yet implemented in Rust")
}

/// `error_recovery.build_agent_friendly_error(tool_name, error, arguments=...)`。
///
/// 工具抛异常时的入口:产出 canonical 错误信封(含兼容别名 `error_category`/`recovery_hint`,
/// 从 arguments 镜像标识字段 `file_path → symbol → query → roots[0] → mode`)。
/// `error_message` 形如 `"FileNotFoundError: File not found: x.py"`(类名 + 冒号 + str(exc))。
/// 对照 fixture `error_recovery.json` 每个用例的 `build_agent_friendly_error` 字段。
pub fn build_agent_friendly_error(
    tool_name: &str,
    error_message: &str,
    exc_class: &str,
    arguments: Option<&Value>,
) -> Value {
    todo!("Stage 2-3: envelope not yet implemented in Rust")
}

/// `error_recovery.ensure_canonical_error_envelope(tool_name, payload, arguments=...)`。
///
/// 工具返回 `{success: False}` dict 时的补全入口:预设字段(`error_type`/`next_step`)不覆盖;
/// 缺 `error` 时从 `errors` 列表推导并从消息前导码推导 `error_code`。
/// 对照 fixture 的 `error_envelope_preserves_preset_fields`、`error_envelope_derives_identity`。
pub fn ensure_canonical_error_envelope(payload: &Value, tool_name: &str) -> Value {
    todo!("Stage 2-3: envelope not yet implemented in Rust")
}

/// `error_recovery.ensure_canonical_success_envelope(tool_name, payload)`。
///
/// 成功路径补全:K12(回显 `file_path`/`source_file` 归一化)、M14(单文件响应回显
/// `language`)、M10(verdict 顶层与 agent_summary 镜像,兜底 `agent_summary.verdict = "n/a"`)。
/// 对照 fixture 的 `k12_path_normalization` 与 `m14_language_echo`。
pub fn ensure_canonical_success_envelope(
    payload: &Value,
    tool_name: &str,
    file_path: Option<&str>,
) -> Value {
    todo!("Stage 2-3: envelope not yet implemented in Rust")
}

/// K12 路径回显归一化(`_normalize_path_string`):`\` → `/`,循环剥掉前导 `./`。
///
/// 使 `./X` 与 `X` 字节一致;对照 fixture `k12_path_normalization.normalize_path_string_direct`
/// (`"./a\b.py"` → `"a/b.py"`)。
pub fn normalize_path_k12(path: &str) -> String {
    todo!("Stage 2-3: envelope not yet implemented in Rust")
}

/// CLI 结构化输出(`--structure --output-format json` 路径)。
///
/// 信封契约:顶层含 `success`/`summary_line`/`verdict`/`agent_summary` 4 键
/// (`_CLI_ENVELOPE_KEYS`),`agent_summary` 含 `summary_line`/`verdict` 2 键,
/// 顶层 `verdict` 必须镜像 `agent_summary.verdict`。
/// 对照 fixture `cli/cli_outputs.json` 的 `structure` case(语料:`tests/golden/corpus_python.py`)。
pub fn cli_structure_json(file_path: &str) -> Result<Value, String> {
    todo!("Stage 2-3: envelope not yet implemented in Rust")
}
