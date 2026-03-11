# Windows タスクスケジューラ設定スクリプト
# 管理者権限で実行してください: Right-click → "管理者として実行"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = (Get-Command python).Source
$mainScript = Join-Path $scriptDir "main.py"

Write-Host "=== 自律型AIカンパニー スケジューラ設定 ===" -ForegroundColor Cyan
Write-Host "Python: $pythonPath"
Write-Host "Script: $mainScript"

# 実行ラッパーバッチファイルを作成
$batchContent = @"
@echo off
cd /d "$scriptDir"
set PYTHONIOENCODING=utf-8
python main.py >> logs\run.log 2>&1
"@
$batchPath = Join-Path $scriptDir "run.bat"
$batchContent | Out-File -FilePath $batchPath -Encoding ASCII
New-Item -ItemType Directory -Force -Path (Join-Path $scriptDir "logs") | Out-Null

Write-Host "バッチファイル作成: $batchPath" -ForegroundColor Green

# タスクを登録（1日4回: 7:00, 12:00, 18:00, 22:00）
$times = @("07:00", "12:00", "18:00", "22:00")
$taskBaseName = "AICompany"

foreach ($time in $times) {
    $taskName = "$taskBaseName-$($time -replace ':', '')"

    # 既存タスクを削除
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

    $action = New-ScheduledTaskAction -Execute $batchPath
    $trigger = New-ScheduledTaskTrigger -Daily -At $time
    $settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable

    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description "AI Company 自動実行 $time" `
        -RunLevel Highest | Out-Null

    Write-Host "タスク登録: $taskName ($time)" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== 設定完了 ===" -ForegroundColor Cyan
Write-Host "毎日 7:00 / 12:00 / 18:00 / 22:00 に自動実行されます"
Write-Host "ログ: $scriptDir\logs\run.log"
Write-Host ""
Write-Host "削除するには: schtasks /delete /tn AICompany-* /f"
