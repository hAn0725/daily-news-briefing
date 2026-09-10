@echo off
rem ============================================================
rem 每日新闻简报 - 看门狗入口（DailyNewsWatchdog 计划任务调用）
rem 每天 20:30 检查当天日报是否已发送；未发送则发一封诊断告警邮件。
rem 本脚本不抓新闻、不跑 AI，只做检查与发信，几十秒内结束。
rem ============================================================
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if not exist "logs" mkdir logs

set "WD_LOG=%~dp0logs\watchdog.log"
>> "%WD_LOG%" echo [%date% %time%] ===== watchdog started =====

set "PY_EXE="
set "PY_ARGS="
if exist "%~dp0.runtime\Scripts\python.exe" (
    "%~dp0.runtime\Scripts\python.exe" --version >nul 2>nul
    if not errorlevel 1 set "PY_EXE=%~dp0.runtime\Scripts\python.exe"
)
if not defined PY_EXE if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" --version >nul 2>nul
    if not errorlevel 1 set "PY_EXE=%~dp0.venv\Scripts\python.exe"
)
rem 优先使用已知可用的完整路径
if not defined PY_EXE if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" --version >nul 2>nul
    if not errorlevel 1 set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not defined PY_EXE (
    where py >nul 2>nul
    if not errorlevel 1 set "PY_EXE=py" & set "PY_ARGS=-3"
)
if not defined PY_EXE (
    >> "%WD_LOG%" echo [%date% %time%] ERROR: Python 未找到，请先安装 Python 并加入 PATH
    exit /b 1
)

>> "%WD_LOG%" echo [%date% %time%] Python: "%PY_EXE%" %PY_ARGS%
"%PY_EXE%" %PY_ARGS% -m news_crawler.main --watchdog >> "%WD_LOG%" 2>&1
set "RC=%ERRORLEVEL%"
>> "%WD_LOG%" echo [%date% %time%] ===== watchdog finished rc=%RC% =====
exit /b %RC%
