@echo off
rem ============================================================
rem 每日新闻简报 - 运行入口（供 Windows 计划任务调用）
rem ============================================================
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if not exist "logs" mkdir logs

set "PY="
rem 优先使用已知可用的完整路径
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    for /f "delims=" %%p in ('where python 2^>nul') do (
        "%%p" --version >nul 2>nul && set "PY=%%p"
    )
)
if not defined PY (
    echo [%date% %time%] Python 未找到，请先安装 Python 3.12 并加入 PATH
    exit /b 1
)

echo [%date% %time%] 开始生成每日新闻简报...
%PY% -m news_crawler.main >> "logs\run.log" 2>&1
echo [%date% %time%] 完成。日志：logs\run.log
