@echo off
rem ============================================================
rem 每日新闻简报 - 一键生成（手动）
rem 双击运行：自动抓取 → AI 处理 → 生成 HTML → 发送到 QQ 邮箱
rem 不再自动打开报告；成功约 3 秒后自动关闭窗口，出错则停留显示
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
    rem 兜底：从 PATH 里找一个真正能执行的 python（跳过商店占位程序）
    for /f "delims=" %%p in ('where python 2^>nul') do (
        "%%p" --version >nul 2>nul && set "PY=%%p"
    )
)
if not defined PY (
    echo [错误] 未找到可用的 Python，请先安装 Python 3.12 并加入 PATH。
    pause
    exit /b 1
)

echo 正在生成今日新闻简报，约需 1-2 分钟，请稍候...
%PY% -m news_crawler.main
if errorlevel 1 (
    echo.
    echo [错误] 生成失败，请查看 logs 目录日志排查原因。
    pause
    exit /b 1
)

echo.
echo 生成完成！报告已保存到 output 目录并发送到邮箱（若已配置授权码）。
echo 可在 output\ 年月\ 目录下找到当天的 HTML 报告。
timeout /t 6 >nul
exit /b 0

