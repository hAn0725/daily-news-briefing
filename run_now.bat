@echo off
rem ============================================================
rem 每日新闻简报 - 一键生成（手动）
rem 双击运行：自动抓取 → AI 处理 → 生成 PDF → 发送到 QQ 邮箱
rem 不再自动打开报告；成功约 3 秒后自动关闭窗口，出错则停留显示
rem ============================================================
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if not exist "logs" mkdir logs

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
    rem 兜底：从 PATH 里找一个真正能执行的 python（跳过商店占位程序）
    for /f "delims=" %%p in ('where python 2^>nul') do (
        if not defined PY_EXE "%%p" --version >nul 2>nul && set "PY_EXE=%%p"
    )
)
if not defined PY_EXE (
    echo [错误] 未找到可用的 Python，请先安装 Python 3.12 并加入 PATH。
    pause
    exit /b 1
)

echo 正在生成今日新闻简报，约需 1-2 分钟，请稍候...
"%PY_EXE%" %PY_ARGS% -m news_crawler.main
if errorlevel 1 (
    echo.
    echo [错误] 生成失败，请查看 logs 目录日志排查原因。
    pause
    exit /b 1
)

echo.
echo 生成完成！报告已保存到 output 目录并发送到邮箱（若已配置授权码）。
echo 可在 output\ 年月\ 目录下找到当天的 PDF 报告。
timeout /t 6 >nul
exit /b 0

