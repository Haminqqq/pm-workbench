# 截 Teams 視窗（找不到就截主螢幕）存成 PNG，讓 Claude Code 直接讀圖
# 用法：powershell -ExecutionPolicy Bypass -File teams\capture.ps1 [-Window Teams] [-Out teams\shots\x.png]
param([string]$Window = "Teams", [string]$Out = "")
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class U32 {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L,T,R,B; }
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
[void][U32]::SetProcessDPIAware()
if (-not $Out) { $d = Join-Path $PSScriptRoot "shots"; New-Item -ItemType Directory -Force $d | Out-Null; $Out = Join-Path $d ((Get-Date).ToString("yyyyMMdd-HHmmss") + ".png") }
$p = Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like "*$Window*" } | Select-Object -First 1
if ($p) {
  [void][U32]::ShowWindow($p.MainWindowHandle, 9); [void][U32]::SetForegroundWindow($p.MainWindowHandle); Start-Sleep -Milliseconds 500
  $r = New-Object U32+RECT; [void][U32]::GetWindowRect($p.MainWindowHandle, [ref]$r)
  $rect = New-Object System.Drawing.Rectangle $r.L, $r.T, ($r.R-$r.L), ($r.B-$r.T)
} else {
  Write-Host "找不到標題含「$Window」的視窗，改截主螢幕" -ForegroundColor Yellow
  $rect = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
}
$bmp = New-Object System.Drawing.Bitmap $rect.Width, $rect.Height
$g = [System.Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen($rect.Location, [System.Drawing.Point]::Empty, $rect.Size)
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png); $g.Dispose(); $bmp.Dispose()
Write-Host "已截圖 → $Out"
