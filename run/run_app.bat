@echo off
chcp 65001 >nul
rem Launch the comprehension-check local server (Windows).
cd /d "%~dp0\.."

rem Require uv (https://docs.astral.sh/uv/). If it is missing, guide and exit
rem so the user is not left with an unhelpful "uv is not recognized" error.
where uv >nul 2>&1
if errorlevel 1 (
    echo [ERROR] "uv" was not found on this PC.
    echo Install uv first, then open a NEW terminal and run this again:
    echo     winget install --id astral-sh.uv -e
    echo   or: powershell -c "irm https://astral.sh/uv/install.ps1 ^| iex"
    echo Docs: https://docs.astral.sh/uv/getting-started/installation/
    pause
    exit /b 1
)

rem Stop any process already listening on 8020 (e.g. a leftover server)
rem to avoid "port in use" (WinError 10048) on startup.
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8020 " ^| findstr LISTENING') do (
    echo Stopping existing server ^(PID %%p^)...
    taskkill /F /PID %%p >nul 2>&1
)

uv run python -m comprehension_check
pause
