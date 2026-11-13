# 測試：能不能用 PowerShell 讀 Outlook 並建草稿（不寄）
$ErrorActionPreference = "Stop"
try {
  $ol = New-Object -ComObject Outlook.Application
} catch {
  Write-Host "失敗：無法連到 Outlook（可能是新版 Outlook，或 COM 被公司擋）。改用 Gmail 轉寄版。" -ForegroundColor Red
  exit 1
}
$ns = $ol.GetNamespace("MAPI")
$inbox = $ns.GetDefaultFolder(6)
Write-Host "收件匣最新 5 封：" -ForegroundColor Cyan
$inbox.Items | Sort-Object ReceivedTime -Descending | Select-Object -First 5 Subject, SenderName, ReceivedTime | Format-Table -AutoSize
$m = $ol.CreateItem(0)
$m.Subject = "[測試] Claude 草稿（不會寄出）"
$m.Body = "這是 PM 工作台的測試草稿，可以直接刪掉。"
$m.Save()
Write-Host "成功：草稿匣應該多了一封「[測試] Claude 草稿」。整條路通了。" -ForegroundColor Green
