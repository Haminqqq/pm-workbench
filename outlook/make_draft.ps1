# 在 Outlook 建一封草稿（回覆或新信），可加附件。只 Save，絕不 Send。
# 回覆：powershell -ExecutionPolicy Bypass -File outlook\make_draft.ps1 -ReplyTo <EntryID> -BodyFile mail\draft-1.txt [-ReplyAll] [-Attach "D:\CRD\xxx.xlsx"]
# 新信：powershell -ExecutionPolicy Bypass -File outlook\make_draft.ps1 -To "a@x.com;b@x.com" -Subject "..." -BodyFile mail\draft-2.txt [-Cc "..."] [-Attach "..."]
param(
  [string]$ReplyTo = "",
  [switch]$ReplyAll,
  [string]$To = "",
  [string]$Cc = "",
  [string]$Subject = "",
  [Parameter(Mandatory=$true)][string]$BodyFile,
  [string[]]$Attach = @()
)
$ErrorActionPreference = "Stop"
$ol = New-Object -ComObject Outlook.Application
$ns = $ol.GetNamespace("MAPI")
$body = Get-Content -Raw -Encoding utf8 $BodyFile
if ($ReplyTo -ne "") {
  $orig = $ns.GetItemFromID($ReplyTo)
  $m = if ($ReplyAll) { $orig.ReplyAll() } else { $orig.Reply() }
  # 把草稿放在引用內容上方
  $m.Body = $body + "`n`n" + $m.Body
  if ($Cc -ne "") { $m.CC = $Cc }
} else {
  if ($To -eq "" -or $Subject -eq "") { throw "新信需要 -To 與 -Subject" }
  $m = $ol.CreateItem(0)
  $m.To = $To; if ($Cc -ne "") { $m.CC = $Cc }
  $m.Subject = $Subject
  $m.Body = $body
}
foreach ($p in $Attach) {
  if (-not (Test-Path $p)) { throw "附件不存在：$p" }
  $m.Attachments.Add((Resolve-Path $p).Path) | Out-Null
}
$m.Save()
Write-Host ("草稿已存：{0}（附件 {1} 個）。請到草稿匣檢查後自己送出。" -f $m.Subject, $Attach.Count)
