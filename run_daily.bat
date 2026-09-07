@echo off
rem ============================================================
rem 每日新闻简报 - 计划任务入口（07:00 由 DailyNewsReport 调用）
rem 流程：严格检测 VPN/外网（不通每 5 分钟重试，23:00 截止）
rem       → 校验海外新闻覆盖 → AI 处理 → 生成 PDF → 发送到 QQ 邮箱
rem ============================================================
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if not exist "logs" mkdir logs

set "RUN_LOG=%~dp0logs\run.log"
>> "%RUN_LOG%" echo [%date% %time%] ===== scheduled launcher started =====

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
    for /f "delims=" %%p in ('where python 2^>nul') do (
        if not defined PY_EXE "%%p" --version >nul 2>nul && set "PY_EXE=%%p"
    )
)
if not defined PY_EXE (
    >> "%RUN_LOG%" echo [%date% %time%] ERROR: Python 未找到，请先安装 Python 3.12 并加入 PATH
    exit /b 1
)

>> "%RUN_LOG%" echo [%date% %time%] Python: "%PY_EXE%" %PY_ARGS%
>> "%RUN_LOG%" echo [%date% %time%] 开始生成每日新闻简报（含联网检测，可能长时间等待）...
:run_report
"%PY_EXE%" %PY_ARGS% -m news_crawler.main --wait-net >> "%RUN_LOG%" 2>&1
set "RC=%ERRORLEVEL%"
if "%RC%"=="3" (
    >> "%RUN_LOG%" echo [%date% %time%] 海外新闻覆盖不足，5 分钟后重新抓取...
    "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -Command "Start-Sleep -Seconds 300"
    goto run_report
)
if "%RC%"=="4" (
    >> "%RUN_LOG%" echo [%date% %time%] GLM 免费接口暂时限流，5 分钟后重试...
    "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -Command "Start-Sleep -Seconds 300"
    goto run_report
)
>> "%RUN_LOG%" echo [%date% %time%] ===== scheduled launcher finished rc=%RC% =====
exit /b %RC%
