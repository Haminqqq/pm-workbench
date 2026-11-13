# 讀 Windows 通知資料庫裡的 Teams 通知（誰、哪個聊天室、說了什麼、何時）
# 用法：powershell -ExecutionPolicy Bypass -File teams\read_notifications.ps1 -Since 480 -Out teams\notif.json
# 只讀：複製 wpndatabase.db 到暫存再查，用 Windows 內建的 winsqlite3.dll，不裝任何東西。
param(
  [int]$Since = 480,            # 只列最近 N 分鐘
  [string]$Out = "",            # 輸出 JSON 路徑；空＝印在畫面
  [string]$Filter = "Teams",    # 通知來源 App 名稱含這個字
  [switch]$All                  # 含已看過的（預設排除 .seen 裡的 id）
)
$ErrorActionPreference = "Stop"
$src = Join-Path $env:LOCALAPPDATA "Microsoft\Windows\Notifications\wpndatabase.db"
if (-not (Test-Path $src)) { Write-Host "找不到通知資料庫：$src" -ForegroundColor Red; exit 1 }
$tmp = Join-Path $env:TEMP ("wpn_" + [guid]::NewGuid().ToString("N") + ".db")
Copy-Item $src $tmp -Force
foreach ($ext in @("-wal","-shm")) { if (Test-Path ($src+$ext)) { Copy-Item ($src+$ext) ($tmp+$ext) -Force } }

Add-Type -TypeDefinition @"
using System; using System.Runtime.InteropServices;
public static class WS3 {
  [DllImport("winsqlite3.dll", CharSet=CharSet.Unicode)] public static extern int sqlite3_open16(string f, out IntPtr db);
  [DllImport("winsqlite3.dll", CharSet=CharSet.Unicode)] public static extern int sqlite3_prepare16_v2(IntPtr db, string sql, int n, out IntPtr st, IntPtr tail);
  [DllImport("winsqlite3.dll")] public static extern int sqlite3_step(IntPtr st);
  [DllImport("winsqlite3.dll")] public static extern IntPtr sqlite3_column_text16(IntPtr st, int i);
  [DllImport("winsqlite3.dll")] public static extern long sqlite3_column_int64(IntPtr st, int i);
  [DllImport("winsqlite3.dll")] public static extern int sqlite3_finalize(IntPtr st);
  [DllImport("winsqlite3.dll")] public static extern int sqlite3_close(IntPtr db);
}
"@
$db=[IntPtr]::Zero; $st=[IntPtr]::Zero
if ([WS3]::sqlite3_open16($tmp,[ref]$db) -ne 0) { Write-Host "開不了資料庫" -ForegroundColor Red; exit 1 }
$sql = "SELECT n.Id, h.PrimaryId, n.ArrivedTime, CAST(n.Payload AS TEXT) FROM Notification n JOIN NotificationHandler h ON n.HandlerId=h.RecordId WHERE n.Type='toast' ORDER BY n.ArrivedTime DESC"
if ([WS3]::sqlite3_prepare16_v2($db,$sql,-1,[ref]$st,[IntPtr]::Zero) -ne 0) { Write-Host "查詢失敗（資料庫結構可能不同）" -ForegroundColor Red; exit 1 }
$seenPath = Join-Path $PSScriptRoot ".seen"
$seen = @{}; if ((-not $All) -and (Test-Path $seenPath)) { Get-Content $seenPath | ForEach-Object { $seen[$_]=1 } }
$cut = (Get-Date).AddMinutes(-$Since)
$rows = @()
while ([WS3]::sqlite3_step($st) -eq 100) {
  $id  = [WS3]::sqlite3_column_int64($st,0)
  $app = [Runtime.InteropServices.Marshal]::PtrToStringUni([WS3]::sqlite3_column_text16($st,1))
  $ft  = [WS3]::sqlite3_column_int64($st,2)
  $xml = [Runtime.InteropServices.Marshal]::PtrToStringUni([WS3]::sqlite3_column_text16($st,3))
  if ($app -notlike "*$Filter*") { continue }
  $at = [DateTime]::FromFileTime($ft)
  if ($at -lt $cut) { break }
  if ($seen.ContainsKey([string]$id)) { continue }
  $texts = @()
  try { $x=[xml]$xml; $texts = @($x.SelectNodes("//text") | ForEach-Object { $_.InnerText.Trim() } | Where-Object { $_ }) } catch { $texts=@($xml) }
  # 常見格式：[0] 發言人（或「發言人 in 聊天室」）、[1] 內文、[2] 聊天室／attribution
  $sender=$texts[0]; $chat=""; if ($sender -match '^(.*?)\s+(in|於|在)\s+(.+)$') { $sender=$Matches[1]; $chat=$Matches[3] }
  if ($texts.Count -ge 3 -and -not $chat) { $chat=$texts[2] }
  $rows += [pscustomobject]@{ id=[string]$id; at=$at.ToString("yyyy-MM-dd HH:mm"); app=$app; sender=$sender; chat=$chat; preview=$(if($texts.Count -ge 2){$texts[1]}else{""}); texts=$texts }
}
[void][WS3]::sqlite3_finalize($st); [void][WS3]::sqlite3_close($db)
Remove-Item $tmp* -Force -ErrorAction SilentlyContinue
if ($Out) { $rows | ConvertTo-Json -Depth 4 | Set-Content -Path $Out -Encoding UTF8; Write-Host "Teams 通知 $($rows.Count) 則 → $Out" }
else { $rows | Select-Object at,sender,chat,preview | Format-Table -AutoSize -Wrap }
if ($rows.Count -eq 0) { Write-Host "最近 $Since 分鐘沒有 Teams 通知（或 Windows 通知／Teams 通知被關閉）。" -ForegroundColor Yellow }
