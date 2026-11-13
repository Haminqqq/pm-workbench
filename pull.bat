@echo off
rem 更新工具：用完整路徑叫 git，不需要 PATH 裡有 git（避免 Claude Code 抓到 bash.exe）
cd /d "%~dp0"
if exist "%USERPROFILE%\PortableGit\cmd\git.exe" (
  "%USERPROFILE%\PortableGit\cmd\git.exe" pull
) else (
  echo 沒有 PortableGit，改用 update.bat（Download ZIP）
)
pause
