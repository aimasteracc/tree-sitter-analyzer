#!/usr/bin/env pwsh
# Tree-Sitter Analyzer V2 - 安装验证脚本

Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host "Tree-Sitter Analyzer V2 - Cursor 集成验证" -ForegroundColor Cyan
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host ""

$projectRoot = "C:/git-private/tree-sitter-analyzer-workspace/tree-sitter-analyzer-v2"

# 检查 1: 项目目录
Write-Host "[1/5] 检查项目目录..." -ForegroundColor Yellow
if (Test-Path $projectRoot) {
    Write-Host "  [OK] 项目目录存在: $projectRoot" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] 项目目录不存在: $projectRoot" -ForegroundColor Red
    exit 1
}

# 检查 2: uv 命令
Write-Host ""
Write-Host "[2/5] 检查 uv 包管理器..." -ForegroundColor Yellow
try {
    $uvVersion = uv --version 2>&1
    Write-Host "  [OK] uv 已安装: $uvVersion" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] uv 未安装或不在 PATH 中" -ForegroundColor Red
    Write-Host "  请安装 uv: https://github.com/astral-sh/uv" -ForegroundColor Yellow
    exit 1
}

# 检查 3: Python 导入
Write-Host ""
Write-Host "[3/5] 检查 MCP 服务器导入..." -ForegroundColor Yellow
Set-Location $projectRoot
try {
    $importTest = uv run python -c "from tree_sitter_analyzer_v2.mcp.server import TreeSitterAnalyzerMCPServer; print('OK')" 2>&1
    if ($importTest -match "OK") {
        Write-Host "  [OK] MCP 服务器可以正常导入" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] MCP 服务器导入失败" -ForegroundColor Red
        Write-Host "  错误: $importTest" -ForegroundColor Red
        Write-Host "  请运行: uv pip install -e '.[mcp]'" -ForegroundColor Yellow
        exit 1
    }
} catch {
    Write-Host "  [FAIL] 导入测试失败: $_" -ForegroundColor Red
    exit 1
}

# 检查 4: MCP 依赖
Write-Host ""
Write-Host "[4/5] 检查 MCP 依赖..." -ForegroundColor Yellow
try {
    $mcpCheck = uv run python -c "import mcp; print('OK')" 2>&1
    if ($mcpCheck -match "OK") {
        Write-Host "  [OK] MCP SDK 已安装" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] MCP SDK 未安装" -ForegroundColor Red
        Write-Host "  请运行: uv pip install -e '.[mcp]'" -ForegroundColor Yellow
        exit 1
    }
} catch {
    Write-Host "  [FAIL] MCP SDK 检查失败" -ForegroundColor Red
    exit 1
}

# 检查 5: 运行完整测试
Write-Host ""
Write-Host "[5/5] 运行完整测试..." -ForegroundColor Yellow
Set-Location "C:/git-private/tree-sitter-analyzer-workspace"
$testFile = "C:/git-private/tree-sitter-analyzer-workspace/test_mcp_server.py"
if (Test-Path $testFile) {
    try {
        $testOutput = uv run --directory tree-sitter-analyzer-v2 python $testFile 2>&1
        if ($testOutput -match "\[SUCCESS\]") {
            Write-Host "  [OK] 所有测试通过!" -ForegroundColor Green
        } else {
            Write-Host "  [FAIL] 测试失败" -ForegroundColor Red
            Write-Host "  输出: $testOutput" -ForegroundColor Red
            exit 1
        }
    } catch {
        Write-Host "  [FAIL] 测试执行失败: $_" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "  [WARN] 测试文件不存在，跳过测试" -ForegroundColor Yellow
    Write-Host "  提示: 可以手动运行测试验证功能" -ForegroundColor Yellow
}

# 成功总结
Write-Host ""
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host "验证完成!" -ForegroundColor Green
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Tree-Sitter Analyzer V2 已准备好在 Cursor 中使用!" -ForegroundColor Green
Write-Host ""
Write-Host "下一步:" -ForegroundColor Yellow
Write-Host "  1. 查看配置文件: 快速配置.txt" -ForegroundColor White
Write-Host "  2. 复制配置到 Cursor MCP 设置" -ForegroundColor White
Write-Host "  3. 重启 Cursor" -ForegroundColor White
Write-Host "  4. 开始使用!" -ForegroundColor White
Write-Host ""
Write-Host "详细文档:" -ForegroundColor Yellow
Write-Host "  - CURSOR配置说明.md (详细配置)" -ForegroundColor White
Write-Host "  - 如何在Cursor中使用.md (快速开始)" -ForegroundColor White
Write-Host "  - CURSOR集成完成.md (完整总结)" -ForegroundColor White
Write-Host ""
Write-Host "============================================================================" -ForegroundColor Cyan

exit 0
