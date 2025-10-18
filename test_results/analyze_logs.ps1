[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Write-Host "=== System temp directory log analysis ==="
Write-Host ""

$logFile = Join-Path $env:TEMP "tree_sitter_analyzer.log"
if (Test-Path $logFile) {
    $content = Get-Content $logFile
    $debugCount = ($content | Where-Object { $_ -match " - DEBUG - " }).Count
    $infoCount = ($content | Where-Object { $_ -match " - INFO - " }).Count
    $warningCount = ($content | Where-Object { $_ -match " - WARNING - " }).Count
    $errorCount = ($content | Where-Object { $_ -match " - ERROR - " }).Count
    
    Write-Host "  DEBUG: $debugCount"
    Write-Host "  INFO: $infoCount"
    Write-Host "  WARNING: $warningCount"
    Write-Host "  ERROR: $errorCount"
    Write-Host "  Total: $($content.Count)"
} else {
    Write-Host "  File not found"
}

Write-Host ""
Write-Host "=== Test directory log analysis ==="
Write-Host ""

foreach ($dir in @("test_logs_debug", "test_logs_info", "test_logs_warning", "test_logs_error", "test_logs_int", "test_logs_content", "test_logs_separation")) {
    Write-Host "Directory: $dir"
    $logFile = Join-Path $dir "tree_sitter_analyzer.log"
    if (Test-Path $logFile) {
        $content = Get-Content $logFile
        $debugCount = ($content | Where-Object { $_ -match " - DEBUG - " }).Count
        $infoCount = ($content | Where-Object { $_ -match " - INFO - " }).Count
        $warningCount = ($content | Where-Object { $_ -match " - WARNING - " }).Count
        $errorCount = ($content | Where-Object { $_ -match " - ERROR - " }).Count
        
        Write-Host "  DEBUG: $debugCount"
        Write-Host "  INFO: $infoCount"
        Write-Host "  WARNING: $warningCount"
        Write-Host "  ERROR: $errorCount"
        Write-Host "  Total: $($content.Count)"
    } else {
        Write-Host "  File not found"
    }
    Write-Host ""
}