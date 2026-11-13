# 讀 Outlook 信件 → JSON。只讀，不改任何信件狀態。
# 用法：powershell -ExecutionPolicy Bypass -File outlook\read_mail.ps1 -Days 2 -Out mail\inbox.json [-Folder Sent] [-SaveAttachments downloads\2026-11-13] [-IncludeDone]
param(
  [int]$Days = 2,
  [string]$Out = "mail\inbox.json",
  [ValidateSet("Inbox","Sent")][string]$Folder = "Inbox",
  [string]$SaveAttachments = "",
  [switch]$IncludeDone
)
$ErrorActionPreference = "Stop"
$DONE = "Claude 已處理"
$ol = New-Object -ComObject Outlook.Application
$ns = $ol.GetNamespace("MAPI")
$f = if ($Folder -eq "Sent") { $ns.GetDefaultFolder(5) } else { $ns.GetDefaultFolder(6) }
$since = (Get-Date).AddDays(-$Days)
$items = $f.Items
$items.Sort("[ReceivedTime]", $true)
$filter = "[ReceivedTime] >= '" + $since.ToString("g") + "'"
$list = @()
$attachExts = @(".xlsx",".xlsm",".xls",".csv",".pdf",".docx",".pptx",".zip",".msg")
foreach ($m in $items.Restrict($filter)) {
  if ($m.Class -ne 43) { continue }   # 43 = MailItem
  if (-not $IncludeDone -and ($m.Categories -split ",") -contains $DONE) { continue }
  $atts = @()
  foreach ($a in $m.Attachments) {
    $ext = [System.IO.Path]::GetExtension($a.FileName).ToLower()
    $rec = @{ name = $a.FileName; size = $a.Size; saved = "" }
    if ($SaveAttachments -ne "" -and $attachExts -contains $ext) {
      New-Item -ItemType Directory -Force -Path $SaveAttachments | Out-Null
      $p = Join-Path (Resolve-Path $SaveAttachments) $a.FileName
      $a.SaveAsFile($p); $rec.saved = $p
    }
    $atts += $rec
  }
  $body = $m.Body
  if ($body.Length -gt 20000) { $body = $body.Substring(0, 20000) + "`n…(截斷)" }
  $list += [ordered]@{
    entryId        = $m.EntryID
    conversationId = $m.ConversationID
    subject        = $m.Subject
    from           = $m.SenderName
    fromEmail      = $m.SenderEmailAddress
    to             = $m.To
    cc             = $m.CC
    received       = $m.ReceivedTime.ToString("yyyy-MM-dd HH:mm")
    unread         = $m.UnRead
    categories     = $m.Categories
    body           = $body
    attachments    = $atts
  }
}
New-Item -ItemType Directory -Force -Path (Split-Path $Out) | Out-Null
$list | ConvertTo-Json -Depth 5 | Out-File -Encoding utf8 $Out
Write-Host ("寫出 {0} 封到 {1}" -f $list.Count, $Out)
