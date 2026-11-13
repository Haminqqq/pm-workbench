# 把草稿檔放進剪貼簿（不會貼進任何視窗、不會送出）
param([string]$File = "teams\draft.txt")
Set-Clipboard -Value (Get-Content $File -Raw -Encoding UTF8)
Write-Host "草稿已在剪貼簿：到 Teams 聊天室 Ctrl+V，看一眼再按 Enter。" -ForegroundColor Green
