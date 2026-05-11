# Tree-sitter-analyzer 自主开发计划

## Goal
将 ts-analyzer 建设为"代码上下文平台"——最高质量、最高 token 效率、和 AI 工具最深入集成

## Phase 状态

- [x] Phase 1: MCP 协议 + 基础分析器（17 语言）
- [x] Phase 2: 格式引擎 + TOON 输出
- [x] Phase 3: 安全边界 + 路径验证
- [x] Phase 4: 缓存系统 + 查询优化
- [x] Phase 5: CI/CD + test mastery scan
- [x] Phase 6: wiki 驱动性能优化（增量解析）
- [x] Phase 7: 项目级可视化（依赖图、健康评分）

## Decisions Made
| 决策 | 理由 | 日期 |
|------|------|------|
| unittest.TestCase → pytest | 统一测试框架 | 2026-05-11 |
| LegacyTableFormatter → FullFormatter | 减少依赖 | 2026-05-11 |
| 移除 pytest-xdist -n auto | 消除 pytest-cov 并发冲突 | 2026-05-11 |
| 增量解析加入 parser | wiki/tree-sitter-performance 推荐 | 2026-05-11 |
| test_mastery_scan.py 创建 | wiki 质量门槛基线 | 2026-05-11 |

## Sprint 追踪

### Sprint N+1: 项目级可视化
- 依赖图生成
- 文件级健康评分
- impact/blast radius 分析

### Sprint N+2: 代码瘦身
- 45 个 oversized 测试文件拆分
- 7 个低于断言密度的测试文件增强
- 3+ 个文件迁移到 hypothesis property test
