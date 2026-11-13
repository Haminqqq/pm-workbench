# 沒有 git 的更新方式：先在瀏覽器到 GitHub 頁面 Code → Download ZIP（會存到「下載」），再雙擊 update.bat
# 這個腳本會找「下載」裡最新的 pm-workbench-main.zip，解壓覆蓋到這個資料夾，然後刪掉 zip。
# 只覆蓋工具檔；mail、downloads、CRD、teams\shots 等妳的資料不在 zip 裡，不會被動到。
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$dl = Join-Path $env:USERPROFILE "Downloads"
$zip = Get-ChildItem $dl -Filter "pm-workbench-main*.zip" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $zip) { Write-Host "「下載」裡找不到 pm-workbench-main.zip，先到 GitHub 頁面 Code → Download ZIP。" -ForegroundColor Red; exit 1 }
$tmp = Join-Path $env:TEMP ("pmwb_" + [guid]::NewGuid().ToString("N"))
Expand-Archive -Path $zip.FullName -DestinationPath $tmp -Force
$src = Get-ChildItem $tmp -Directory | Select-Object -First 1
Copy-Item -Path (Join-Path $src.FullName "*") -Destination $root -Recurse -Force
Remove-Item $tmp -Recurse -Force; Remove-Item $zip.FullName -Force
Write-Host "已更新到 $root（來源 $($zip.Name)，$($zip.LastWriteTime)）。重開 claude 讓新 skill 生效。" -ForegroundColor Green
