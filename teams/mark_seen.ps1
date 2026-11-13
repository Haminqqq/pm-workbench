# 把 notif.json 裡的通知 id 記到 .seen，下次 read_notifications 不再列出
param([string]$File = "teams\notif.json")
$ids = (Get-Content $File -Raw -Encoding UTF8 | ConvertFrom-Json) | ForEach-Object { $_.id }
$ids | Add-Content -Path (Join-Path $PSScriptRoot ".seen") -Encoding UTF8
Write-Host "已記錄 $($ids.Count) 則"
