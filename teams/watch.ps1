# 背景守望（可選）：每 N 分鐘看一次 Teams 通知，名單內的人有新訊息就叫 Claude 分析、跳通知、草稿放剪貼簿。
# 用法：powershell -ExecutionPolicy Bypass -File teams\watch.ps1 -Every 10
# 停止：關掉這個視窗。絕不會自動回 Teams。
param([int]$Every = 10)
$root = Split-Path $PSScriptRoot -Parent
$listFile = Join-Path $PSScriptRoot "watch_list.txt"
Write-Host "Teams 守望啟動：每 $Every 分鐘檢查；名單 $listFile" -ForegroundColor Cyan
while ($true) {
  $json = Join-Path $PSScriptRoot "notif.json"
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "read_notifications.ps1") -Since $Every -Out $json | Out-Null
  $rows = @(); if (Test-Path $json) { $rows = @(Get-Content $json -Raw -Encoding UTF8 | ConvertFrom-Json) }
  $names = @(); if (Test-Path $listFile) { $names = Get-Content $listFile -Encoding UTF8 | Where-Object { $_.Trim() } }
  $hit = $rows | Where-Object { $s=$_.sender; ($names.Count -eq 0) -or ($names | Where-Object { $s -like "*$_*" }) }
  if ($hit) {
    $stamp = (Get-Date).ToString("yyyyMMdd-HHmm"); $log = Join-Path $PSScriptRoot "log\$stamp.md"
    New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
    $prompt = "看 Teams：讀 teams/notif.json，只做分析與草稿（不建卡、不寫 Notion）。每則：對方要什麼、跟哪張待追卡有關、建議回法、草稿。草稿存 teams/draft.txt，第一則的草稿用 teams/clip.ps1 放剪貼簿。分析結果存 $log。"
    Push-Location $root; & claude -p $prompt --allowedTools "Bash,Read,Write,ArtifactData" | Out-Null; Pop-Location
    $who = ($hit | Select-Object -First 3 | ForEach-Object { "$($_.sender)：$($_.preview)" }) -join "；"
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "toast.ps1") -Title "Claude 看了 Teams（$($hit.Count) 則）" -Body $who
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "mark_seen.ps1") -File $json | Out-Null
  }
  Start-Sleep -Seconds ($Every * 60)
}
