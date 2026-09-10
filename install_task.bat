@echo off
rem ============================================================
rem 注册 Windows 计划任务：每天 07:00 自动生成并发送新闻简报
rem 任务名：DailyNewsReport（经 run_scheduled.vbs 隐藏窗口运行）
rem 如需改时间，把下面的 07:00 改成你想要的时刻（HH:MM）
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"

schtasks /Create /TN "DailyNewsReport" /TR "wscript.exe \"%~dp0run_scheduled.vbs\"" /SC DAILY /ST 07:00 /F
if errorlevel 1 (
    echo.
    echo [错误] 计划任务注册失败，请右键本文件"以管理员身份运行"后重试。
    pause
    exit /b 1
)

rem 错过 07:00 则在下次可用时补跑；允许电池供电/唤醒；最晚运行到当日 23:30
powershell -NoProfile -Command "try{$t=Get-ScheduledTask -TaskName 'DailyNewsReport';$s=$t.Settings;$s.StartWhenAvailable=$true;$s.WakeToRun=$true;$s.DisallowStartIfOnBatteries=$false;$s.StopIfGoingOnBatteries=$false;$s.ExecutionTimeLimit='PT16H30M';Set-ScheduledTask -TaskName 'DailyNewsReport' -Settings $s|Out-Null}catch{Write-Error $_;exit 1}"
if errorlevel 1 (
    echo [错误] 计划任务已创建，但可靠性设置更新失败。请以管理员身份重新运行。
    pause
    exit /b 1
)

rem ---------- 看门狗任务：每天 20:30 检查当天日报是否已发送 ----------
rem 未发送则发一封诊断告警邮件（电脑睡眠错过时开机后补跑检查）
schtasks /Create /TN "DailyNewsWatchdog" /TR "wscript.exe \"%~dp0run_scheduled.vbs\" run_watchdog.bat" /SC DAILY /ST 20:30 /F
if errorlevel 1 (
    echo.
    echo [错误] 看门狗任务注册失败，请右键本文件"以管理员身份运行"后重试。
    pause
    exit /b 1
)
powershell -NoProfile -Command "try{$t=Get-ScheduledTask -TaskName 'DailyNewsWatchdog';$s=$t.Settings;$s.StartWhenAvailable=$true;$s.WakeToRun=$true;$s.DisallowStartIfOnBatteries=$false;$s.StopIfGoingOnBatteries=$false;$s.ExecutionTimeLimit='PT1H';Set-ScheduledTask -TaskName 'DailyNewsWatchdog' -Settings $s|Out-Null}catch{Write-Error $_;exit 1}"
if errorlevel 1 (
    echo [错误] 看门狗任务已创建，但可靠性设置更新失败。请以管理员身份重新运行。
    pause
    exit /b 1
)

echo.
echo 计划任务已注册：
echo   DailyNewsReport   每天 07:00 隐藏运行（不弹黑框）：抓取 + AI + 发邮件
echo   DailyNewsWatchdog 每天 20:30 检查当天是否已发送，未发送则发告警邮件
echo 若 7 点电脑处于睡眠/关机，唤醒或开机后会自动补跑。
echo 查看任务：   schtasks /Query /TN DailyNewsReport /V
echo 立即运行：   schtasks /Run /TN DailyNewsReport
echo 删除任务：   schtasks /Delete /TN DailyNewsReport /F  和  /TN DailyNewsWatchdog /F
echo 启动器日志： logs\scheduler.log（含真实退出码）
echo 看门狗日志： logs\watchdog.log
echo.
echo [重要] 首次使用请先运行：python tools\store_smtp.py
echo        录入 QQ 邮箱 SMTP 授权码，否则定时任务只生成不发送。
pause
