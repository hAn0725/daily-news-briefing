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

rem 错过 07:00（如电脑睡眠/关机）则在下次可用时补跑；允许电池供电运行、允许唤醒
powershell -NoProfile -Command "try{$t=Get-ScheduledTask -TaskName 'DailyNewsReport';$s=$t.Settings;$s.StartWhenAvailable=$true;$s.WakeToRun=$true;$s.DisallowStartIfOnBatteries=$false;$s.StopIfGoingOnBatteries=$false;Set-ScheduledTask -TaskName 'DailyNewsReport' -Settings $s|Out-Null}catch{}"

echo.
echo 计划任务已注册：每天 07:00 隐藏运行（不弹黑框）。
echo 若 7 点电脑处于睡眠/关机，唤醒或开机后会自动补跑。
echo 查看任务：   schtasks /Query /TN DailyNewsReport /V
echo 立即运行：   schtasks /Run /TN DailyNewsReport
echo 删除任务：   schtasks /Delete /TN DailyNewsReport /F
echo.
echo [重要] 首次使用请先运行：python tools\store_smtp.py
echo        录入 QQ 邮箱 SMTP 授权码，否则定时任务只生成不发送。
pause
