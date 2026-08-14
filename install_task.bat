@echo off
rem ============================================================
rem 注册 Windows 计划任务：每天 08:00 自动运行每日新闻简报
rem 任务名：DailyNewsReport
rem 如需改时间，把下面的 08:00 改成你想要的时刻（HH:MM）
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"

schtasks /Create /TN "DailyNewsReport" /TR "\"%~dp0run_daily.bat\"" /SC DAILY /ST 08:00 /F

echo.
echo 计划任务已注册（每天 08:00 运行）。
echo 查看任务：   schtasks /Query /TN DailyNewsReport
echo 立即运行：   schtasks /Run /TN DailyNewsReport
echo 删除任务：   schtasks /Delete /TN DailyNewsReport /F
pause
