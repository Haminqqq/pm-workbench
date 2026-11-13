# 把處理過的信加上類別「Claude 已處理」。不改已讀、不移動、不刪。
# 用法：powershell -ExecutionPolicy Bypass -File outlook\mark_done.ps1 -Ids mail\processed.txt   （每行一個 EntryID）
param([Parameter(Mandatory=$true)][string]$Ids)
$ErrorActionPreference = "Stop"
$DONE = "Claude 已處理"
$ol = New-Object -ComObject Outlook.Application
$ns = $ol.GetNamespace("MAPI")
$n = 0
foreach ($id in (Get-Content $Ids | Where-Object { $_.Trim() -ne "" })) {
  $m = $ns.GetItemFromID($id.Trim())
  $cats = @($m.Categories -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" })
  if ($cats -notcontains $DONE) {
    $m.Categories = (($cats + $DONE) -join ", ")
    $m.Save(); $n++
  }
}
Write-Host ("已標記 {0} 封為「{1}」" -f $n, $DONE)
