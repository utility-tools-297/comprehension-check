@echo off
chcp 65001 >nul
rem comprehension-check のローカルサーバを起動する（Windows）。
cd /d "%~dp0\.."
rem 既に 8020 を使っているプロセス（前回のサーバの消し忘れ等）を停止してから起動する。
rem これで「ポート使用中（WinError 10048）」で起動できない事態を防ぐ。
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8020 " ^| findstr LISTENING') do (
    echo 既存のサーバ ^(PID %%p^) を停止します...
    taskkill /F /PID %%p >nul 2>&1
)
uv run python -m comprehension_check
pause
