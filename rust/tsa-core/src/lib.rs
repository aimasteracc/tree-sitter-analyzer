//! tsa-core —— tree-sitter-analyzer Rust 改写 Stage 1 红灯契约 crate(SPEC §4.3 / §5.2)。
//!
//! 本 crate 只声明三块核心表面的类型与函数签名(envelope / facade 分发 / Python 插件),
//! 全部函数体为按模块定制的 `todo!("Stage 2-3: ... not yet implemented in Rust")`:
//! `tests/` 下的契约测试以 `rust/fixtures/`(PyPI v3.1.2 真实输出的规范化 JSON)为黄金对照,
//! Stage 1 验收判据为「编译零警告 + fixtures 冒烟全绿 + 行为测试全部因未实现而红」(SPEC §5.2)。
//!
//! 依赖 `serde_json` 的 `preserve_order` 特性:信封键序是逐字节对照的一部分。
//!
//! 注释语言规范:本 crate 内注释一律使用中文(AGENTS.md 2026-09-05 裁决)。

#![allow(unused_variables, dead_code)]

pub mod envelope;
pub mod facade;
pub mod python_plugin;
