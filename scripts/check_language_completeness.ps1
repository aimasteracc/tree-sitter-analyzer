# Language Completeness Checker (PowerShell)
#
# Usage: .\scripts\check_language_completeness.ps1 -Language csharp -Extension cs

param(
    [Parameter(Mandatory=$true)]
    [string]$Language,

    [Parameter(Mandatory=$true)]
    [string]$Extension
)

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Language Completeness Check: $Language" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

$Total = 0
$Passed = 0

function Check-Item {
    param(
        [string]$Description,
        [scriptblock]$Condition
    )

    $script:Total++

    if (& $Condition) {
        Write-Host "✓ $Description" -ForegroundColor Green
        $script:Passed++
        return $true
    } else {
        Write-Host "✗ $Description" -ForegroundColor Red
        return $false
    }
}

Write-Host "=== Core Components ===" -ForegroundColor Yellow
Check-Item "Plugin file exists" { Test-Path "tree_sitter_analyzer/languages/${Language}_plugin.py" }
Check-Item "Query file exists" { Test-Path "tree_sitter_analyzer/queries/${Language}.py" }
Check-Item "Formatter file exists" { Test-Path "tree_sitter_analyzer/formatters/${Language}_formatter.py" }
Write-Host ""

Write-Host "=== Configuration ===" -ForegroundColor Yellow
Check-Item "Entry point registered in pyproject.toml" {
    (Get-Content "pyproject.toml" -Raw) -match "${Language} = "
}
Check-Item "Formatter config in formatter_config.py" {
    (Get-Content "tree_sitter_analyzer/formatters/formatter_config.py" -Raw) -match "`"${Language}`":"
}
Check-Item "Formatter registered in factory" {
    (Get-Content "tree_sitter_analyzer/formatters/language_formatter_factory.py" -Raw) -match $Language
}
Check-Item "Language detector configured" {
    (Get-Content "tree_sitter_analyzer/language_detector.py" -Raw) -match "`"\.${Extension}`""
}
Write-Host ""

Write-Host "=== Plugin Methods ===" -ForegroundColor Yellow
if (Test-Path "tree_sitter_analyzer/languages/${Language}_plugin.py") {
    $pluginContent = Get-Content "tree_sitter_analyzer/languages/${Language}_plugin.py" -Raw
    Check-Item "get_queries() method exists" { $pluginContent -match "def get_queries" }
    Check-Item "execute_query_strategy() method exists" { $pluginContent -match "def execute_query_strategy" }
    Check-Item "get_element_categories() method exists" { $pluginContent -match "def get_element_categories" }
} else {
    Write-Host "⊘ Plugin methods check skipped (plugin file missing)" -ForegroundColor Gray
    $Total += 3
}
Write-Host ""

Write-Host "=== Formatter Methods ===" -ForegroundColor Yellow
if (Test-Path "tree_sitter_analyzer/formatters/${Language}_formatter.py") {
    $formatterContent = Get-Content "tree_sitter_analyzer/formatters/${Language}_formatter.py" -Raw
    Check-Item "_format_full_table() method exists" { $formatterContent -match "def _format_full_table" }
    Check-Item "_format_compact_table() method exists" { $formatterContent -match "def _format_compact_table" }
    Check-Item "_format_csv() method exists" { $formatterContent -match "def _format_csv" }
} else {
    Write-Host "⊘ Formatter methods check skipped (formatter file missing)" -ForegroundColor Gray
    $Total += 3
}
Write-Host ""

Write-Host "=== Samples and Tests ===" -ForegroundColor Yellow
Check-Item "Sample file exists (examples/Sample.${Extension})" { Test-Path "examples/Sample.${Extension}" }
Check-Item "Test file exists (tests/test_languages/test_${Language}_plugin.py)" {
    Test-Path "tests/test_languages/test_${Language}_plugin.py"
}
Write-Host ""

Write-Host "=== Documentation ===" -ForegroundColor Yellow
Check-Item "README.md mentions language" {
    (Get-Content "README.md" -Raw) -match $Language
}
Check-Item "CHANGELOG.md mentions language" {
    (Get-Content "CHANGELOG.md" -Raw) -match $Language
}
Write-Host ""

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Results: $Passed/$Total checks passed" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan

if ($Passed -eq $Total) {
    Write-Host "✓ Language implementation is COMPLETE!" -ForegroundColor Green
    exit 0
} else {
    $Failed = $Total - $Passed
    Write-Host "✗ Language implementation is INCOMPLETE ($Failed checks failed)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please review the failed checks above and complete the missing components." -ForegroundColor Yellow
    exit 1
}
