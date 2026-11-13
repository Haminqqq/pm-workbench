@echo off
cd /d "%~dp0"
if not exist node_modules (
  echo 第一次啟動，安裝套件中...
  call npm install --omit=dev
)
start "" http://127.0.0.1:3737
node server.mjs
pause
