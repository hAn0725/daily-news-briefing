@echo off
rem ============================================================
rem 每日新闻简报 - 计划任务入口（07:00 由 DailyNewsReport 调用）
rem 流程：检测 VPN/外网（不通每 5 分钟重试，23:00 截止，仅空闲时段
rem       生成）→ 抓取 → AI 处理 → 生成 HTML → 发送到 QQ 邮箱
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

echo [%date% %time%] 开始生成每日新闻简报（含联网检测，可能长时间等待）...
%PY% -m news_crawler.main --wait-net >> "logs\run.log" 2>&1
echo [%date% %time%] 结束。日志：logs\run.log 与 logs\report_今天.log
